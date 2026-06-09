"""
Enrich Tips Table with actionable drill-down instructions.

For each AWS service tip, adds a 'drilldownApis' field that tells the AI agent
which AWS APIs to call to investigate savings for that specific service.
Also adds 'drilldownInstructions' with step-by-step analysis guidance.

Run via CI/CD: python scripts/enrich_tips_drilldown.py
"""

import boto3
import json
import logging
from decimal import Decimal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
TIPS_TABLE = 'ViewMyBill-CostOptimizationTips'

# ============================================================
# AWS API mapping per service for cost investigation
# ============================================================
# Each entry maps a service to the APIs the agent should call
# to gather actionable savings data for that service.

SERVICE_DRILLDOWN_MAP = {
    "EC2": {
        "apis": [
            "ce:GetRightsizingRecommendation(Service='AmazonEC2')",
            "compute-optimizer:GetEC2InstanceRecommendations",
            "ec2:DescribeInstances(Filters=[{Name:'instance-state-name',Values:['running']}])",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/EC2',MetricName='CPUUtilization',Period=86400,Statistics=['Average'],StartTime=-14d)",
            "ce:GetSavingsPlansPurchaseRecommendation(SavingsPlansType='COMPUTE_SP')",
            "pricing:GetProducts(ServiceCode='AmazonEC2',Filters=[{Type:'TERM_MATCH',Field:'instanceType',Value:'<current_type>'}])"
        ],
        "drilldownInstructions": "1. Call GetRightsizingRecommendation to find oversized instances with specific instance IDs and estimated savings. 2. Call Compute Optimizer for CPU/memory utilization data over 14 days. 3. For each instance with <10% avg CPU, calculate savings from downsizing (current_price - recommended_price) * 730hrs. 4. Check Savings Plans coverage with GetSavingsPlansCoverage to see on-demand vs covered ratio. 5. Show specific instance-level recommendations: 'Instance i-xxx at 5% CPU — downsize from m5.xlarge ($140/mo) to t3.medium ($30/mo), saving $110/mo.'"
    },
    "EC2 - Other": {
        "apis": [
            "ce:GetCostAndUsage(Filter={Dimensions:{Key:'SERVICE',Values:['EC2 - Other']}},GroupBy=[{Type:'DIMENSION',Key:'USAGE_TYPE'}])",
            "ec2:DescribeVolumes(Filters=[{Name:'status',Values:['available']}])",
            "ec2:DescribeAddresses(Filters=[{Name:'association-id',Values:[]}])",
            "ec2:DescribeNatGateways",
            "ec2:DescribeSnapshots(OwnerIds=['self'])"
        ],
        "drilldownInstructions": "1. Break down 'EC2 - Other' by usage type using GetCostAndUsage with USAGE_TYPE grouping. 2. Identify top usage types: NatGateway-Hours, EBS:VolumeUsage, ElasticIP:IdleAddress, DataTransfer-Out-Bytes. 3. For NatGateway: check if VPC endpoints can replace it ($0.045/hr → $0.01/hr per endpoint). 4. For EBS: find unattached volumes (status='available') with DescribeVolumes. 5. For EIPs: find unassociated addresses with DescribeAddresses. 6. Show: 'EC2-Other breakdown: NAT Gateway $X/mo, EBS Volumes $Y/mo, EIPs $Z/mo. Actions: Release 2 idle EIPs (-$7.30/mo), delete 3 unattached volumes (-$24/mo).'"
    },
    "RDS": {
        "apis": [
            "ce:GetRightsizingRecommendation(Service='AmazonRDS')",
            "rds:DescribeDBInstances",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/RDS',MetricName='CPUUtilization',Period=86400,Statistics=['Average'],StartTime=-14d)",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/RDS',MetricName='DatabaseConnections',Period=86400,Statistics=['Maximum'],StartTime=-14d)",
            "ce:GetReservationPurchaseRecommendation(Service='AmazonRDS')",
            "pricing:GetProducts(ServiceCode='AmazonRDS',Filters=[{Type:'TERM_MATCH',Field:'databaseEngine',Value:'<engine>'}])"
        ],
        "drilldownInstructions": "1. List all RDS instances with DescribeDBInstances — note instance class, engine, Multi-AZ, storage. 2. Get 14-day CPU average from CloudWatch. 3. Get max connections — if max <5 over 14 days, instance may be idle. 4. For instances <10% CPU: recommend downsizing (e.g., db.r5.large → db.t3.medium saves ~$200/mo). 5. Check if Aurora Serverless v2 is viable (for <30% average utilization). 6. Get RI recommendations from GetReservationPurchaseRecommendation for steady-state DBs."
    },
    "S3": {
        "apis": [
            "s3:ListBuckets",
            "s3:GetBucketLifecycleConfiguration(Bucket='<each_bucket>')",
            "s3:ListBucketIntelligentTieringConfigurations(Bucket='<each_bucket>')",
            "s3:GetBucketMetricsConfiguration(Bucket='<each_bucket>')",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/S3',MetricName='BucketSizeBytes',StorageType='StandardStorage')",
            "ce:GetCostAndUsage(Filter={Dimensions:{Key:'SERVICE',Values:['Amazon Simple Storage Service']}},GroupBy=[{Type:'DIMENSION',Key:'USAGE_TYPE'}])"
        ],
        "drilldownInstructions": "1. List all buckets and check lifecycle policies — buckets without lifecycle are wasting money on old objects. 2. Break down S3 cost by usage type: StandardStorage, Requests-Tier1 (PUT), Requests-Tier2 (GET), DataTransfer-Out. 3. For buckets >100GB without lifecycle: recommend Intelligent Tiering (auto-saves 40-68% on infrequent objects). 4. Check for multipart upload fragments (incomplete uploads). 5. Show: '14 buckets without lifecycle policies. Adding 30-day IA transition + 90-day Glacier saves estimated $X/mo based on Y GB stored.'"
    },
    "Lambda": {
        "apis": [
            "lambda:ListFunctions",
            "lambda:GetFunction(FunctionName='<each>')",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/Lambda',MetricName='Invocations',Period=2592000,Statistics=['Sum'],StartTime=-30d)",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/Lambda',MetricName='Duration',Period=2592000,Statistics=['Average'],StartTime=-30d)",
            "compute-optimizer:GetLambdaFunctionRecommendations",
            "pricing:GetProducts(ServiceCode='AWSLambda')"
        ],
        "drilldownInstructions": "1. List all Lambda functions with their memory settings. 2. Get invocation count and average duration from CloudWatch for last 30 days. 3. Functions with 0 invocations are waste — recommend deletion. 4. Call Compute Optimizer for memory right-sizing (over-provisioned memory = paying for unused). 5. For high-invocation functions: check if Provisioned Concurrency is needed or if memory reduction would save (less memory = lower cost/ms). 6. Calculate: cost = invocations × (duration_ms/1000) × (memory_mb/1024) × $0.0000166667."
    },
    "EBS": {
        "apis": [
            "ec2:DescribeVolumes",
            "ec2:DescribeSnapshots(OwnerIds=['self'])",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/EBS',MetricName='VolumeReadOps',Period=604800,Statistics=['Sum'],StartTime=-14d)",
            "compute-optimizer:GetEBSVolumeRecommendations",
            "ce:GetCostAndUsage(Filter={Dimensions:{Key:'USAGE_TYPE',Values:['EBS:VolumeUsage.gp2']}},GroupBy=[{Type:'DIMENSION',Key:'USAGE_TYPE'}])"
        ],
        "drilldownInstructions": "1. List all volumes — identify unattached (status='available') for immediate deletion savings. 2. Identify gp2 volumes — migrate to gp3 for 20% savings (same performance, lower cost). 3. Check volume IOPS utilization — if provisioned IOPS but <10% used, downgrade. 4. List snapshots older than 180 days — archive to save 75% (standard → archive tier). 5. Calculate: 'X unattached volumes = $Y/mo waste. Z gp2 volumes → gp3 migration saves $W/mo.'"
    },
    "CloudWatch Logs": {
        "apis": [
            "logs:DescribeLogGroups",
            "logs:DescribeLogStreams(logGroupName='<each>',orderBy='LastEventTime',limit=1)",
            "ce:GetCostAndUsage(Filter={Dimensions:{Key:'SERVICE',Values:['AmazonCloudWatch']}},GroupBy=[{Type:'DIMENSION',Key:'USAGE_TYPE'}])"
        ],
        "drilldownInstructions": "1. List all log groups with their retention settings and stored bytes. 2. Identify groups with 'Never expire' retention — set to 30 or 90 days to stop unbounded growth. 3. Find empty log groups (0 bytes stored) for cleanup. 4. Break down CloudWatch Logs cost by usage type: DataIngestion (most expensive at $0.50/GB), Storage, DataScanned. 5. For high-ingestion groups: recommend log level reduction or exclusion filters."
    },
    "DynamoDB": {
        "apis": [
            "dynamodb:ListTables",
            "dynamodb:DescribeTable(TableName='<each>')",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/DynamoDB',MetricName='ConsumedReadCapacityUnits',Period=86400,Statistics=['Average','Maximum'],StartTime=-14d)",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/DynamoDB',MetricName='ConsumedWriteCapacityUnits',Period=86400,Statistics=['Average','Maximum'],StartTime=-14d)",
            "ce:GetReservationPurchaseRecommendation(Service='AmazonDynamoDB')"
        ],
        "drilldownInstructions": "1. List tables and check billing mode (PROVISIONED vs PAY_PER_REQUEST). 2. For provisioned tables: compare provisioned capacity vs consumed (CloudWatch). If consumed <30% of provisioned, switch to on-demand or reduce provisioned. 3. For on-demand tables with steady traffic: consider reserved capacity (up to 77% savings). 4. Check for unused tables (0 read/write over 14 days). 5. Show: 'Table X provisioned 100 WCU but uses avg 12 WCU — switch to on-demand saves ~$Y/mo or reduce to 15 WCU.'"
    },
    "ElastiCache": {
        "apis": [
            "elasticache:DescribeCacheClusters(ShowCacheNodeInfo=True)",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/ElastiCache',MetricName='CPUUtilization',Period=86400,Statistics=['Average'],StartTime=-14d)",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/ElastiCache',MetricName='CurrConnections',Period=86400,Statistics=['Maximum'],StartTime=-14d)",
            "ce:GetReservationPurchaseRecommendation(Service='AmazonElastiCache')"
        ],
        "drilldownInstructions": "1. List all cache clusters with node types and engine (Redis/Memcached). 2. Check CPU utilization — if <10% over 14 days, consider downsizing. 3. Check connections — if near 0, cluster may be unused. 4. For steady-state clusters: check RI recommendations (up to 55% savings on 1-yr). 5. Consider Serverless ElastiCache for variable workloads."
    },
    "NAT Gateway": {
        "apis": [
            "ec2:DescribeNatGateways",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/NATGateway',MetricName='BytesOutToDestination',Period=86400,Statistics=['Sum'],StartTime=-7d)",
            "ec2:DescribeVpcEndpoints",
            "ce:GetCostAndUsage(Filter={Dimensions:{Key:'USAGE_TYPE',Values:['NatGateway-Hours','NatGateway-Bytes']}},GroupBy=[{Type:'DIMENSION',Key:'USAGE_TYPE'}])"
        ],
        "drilldownInstructions": "1. List all NAT Gateways — each costs $0.045/hr ($32.40/mo) plus $0.045/GB processed. 2. Check bytes processed to identify traffic patterns. 3. For S3/DynamoDB traffic: use VPC Gateway Endpoints (free!) instead of routing through NAT. 4. For other AWS services: use Interface VPC Endpoints ($0.01/hr, much cheaper than NAT for service traffic). 5. Show: 'NAT Gateway processing X GB/mo = $Y in data charges. Replace with VPC endpoints for S3/DynamoDB traffic to save $Z/mo.'"
    },
    "CloudFront": {
        "apis": [
            "cloudfront:ListDistributions",
            "cloudfront:GetDistribution(Id='<each>')",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/CloudFront',MetricName='Requests',Period=2592000,Statistics=['Sum'],StartTime=-30d)",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/CloudFront',MetricName='BytesDownloaded',Period=2592000,Statistics=['Sum'],StartTime=-30d)"
        ],
        "drilldownInstructions": "1. List all distributions — check if any are serving zero traffic (waste). 2. Compare origin requests vs edge requests — low cache hit ratio means inefficient caching (tune TTLs). 3. Check Price Class — if using PriceClass_All but traffic is only from US/EU, switch to PriceClass_100 for lower edge costs. 4. For high-bandwidth distributions: check if compression is enabled (saves 60-70% on text content). 5. Calculate: requests × $0.0085/10K + bytes × $0.085/GB."
    },
    "Rekognition": {
        "apis": [
            "ce:GetCostAndUsage(Filter={Dimensions:{Key:'SERVICE',Values:['Amazon Rekognition']}},GroupBy=[{Type:'DIMENSION',Key:'USAGE_TYPE'}])",
            "rekognition:ListCollections",
            "pricing:GetProducts(ServiceCode='AmazonRekognition')"
        ],
        "drilldownInstructions": "1. Break down Rekognition cost by usage type: FaceSearchImageCount, DetectLabels, DetectFaces, etc. 2. Each API has tiered pricing ($1.00/1000 images for first 1M, then $0.80/1000). 3. Calculate: total_cost / price_per_1000 × 1000 = number of API calls made. 4. Check if face collections exist that are unused (ListCollections). 5. If high volume: check if you can reduce call frequency, batch images, or use cheaper alternatives (e.g., custom ML model on SageMaker for specific use cases)."
    },
    "EKS": {
        "apis": [
            "eks:ListClusters",
            "eks:DescribeCluster(name='<each>')",
            "eks:ListNodegroups(clusterName='<each>')",
            "eks:DescribeNodegroup(clusterName='<cluster>',nodegroupName='<each>')",
            "autoscaling:DescribeAutoScalingGroups",
            "compute-optimizer:GetEC2InstanceRecommendations"
        ],
        "drilldownInstructions": "1. List clusters and node groups — check instance types and scaling config. 2. For each node group: check min/max/desired capacity — if min=max, no auto-scaling (likely over-provisioned). 3. Use Compute Optimizer to check node CPU/memory utilization. 4. Consider Spot instances for worker nodes (60-90% savings). 5. Check if Karpenter or Cluster Autoscaler is configured. 6. Show: 'Node group X has 5 m5.xlarge always-on. Average CPU 15% — consolidate to 3 nodes or use Spot mix.'"
    },
    "Data Transfer": {
        "apis": [
            "ce:GetCostAndUsage(Filter={Dimensions:{Key:'SERVICE',Values:['AWS Data Transfer']}},GroupBy=[{Type:'DIMENSION',Key:'USAGE_TYPE'}])",
            "ec2:DescribeNatGateways",
            "ec2:DescribeVpcEndpoints",
            "cloudfront:ListDistributions"
        ],
        "drilldownInstructions": "1. Break down data transfer by usage type: DataTransfer-Out-Bytes (internet egress), DataTransfer-Regional-Bytes (cross-AZ), AWS-Out-Bytes (cross-region). 2. Internet egress is most expensive ($0.09/GB). 3. For internet-bound traffic: use CloudFront ($0.085/GB, plus caching reduces origin fetches). 4. For cross-AZ traffic: keep services in same AZ where possible. 5. For S3 transfers: use S3 Transfer Acceleration only when needed, use same-region access. 6. Show breakdown with dollar amounts and recommend specific routing changes."
    },
    "Glue": {
        "apis": [
            "glue:GetJobs",
            "glue:GetJobRuns(JobName='<each>',MaxResults=10)",
            "glue:GetCrawlers",
            "ce:GetCostAndUsage(Filter={Dimensions:{Key:'SERVICE',Values:['AWS Glue']}},GroupBy=[{Type:'DIMENSION',Key:'USAGE_TYPE'}])"
        ],
        "drilldownInstructions": "1. List all Glue jobs — check DPU allocation and execution time. 2. Check job run history: if runs are short (<5 min), reduce DPU count (charged per DPU-hour, minimum 10 min). 3. For crawlers: check frequency — daily crawlers on static schemas waste money. 4. Consider Glue Auto Scaling (adjusts DPUs dynamically). 5. Compare with serverless Spark on EMR Serverless for batch workloads."
    },
    "KMS": {
        "apis": [
            "kms:ListKeys",
            "kms:DescribeKey(KeyId='<each>')",
            "kms:ListAliases",
            "ce:GetCostAndUsage(Filter={Dimensions:{Key:'SERVICE',Values:['AWS Key Management Service']}},GroupBy=[{Type:'DIMENSION',Key:'USAGE_TYPE'}])"
        ],
        "drilldownInstructions": "1. List all KMS keys — each customer-managed key costs $1.00/month. 2. Check key state: keys in 'PendingDeletion' or disabled still cost until fully deleted. 3. Break down by usage type: KMS-Keys ($1/key/mo) vs KMS-Requests ($0.03/10K requests). 4. For keys used only for S3 default encryption: switch to AWS-managed key (free) or S3-SSE (free). 5. Delete unused customer-managed keys. Show: 'X customer-managed keys = $X/mo. Y keys have 0 usage — schedule deletion.'"
    },
    "SageMaker": {
        "apis": [
            "sagemaker:ListEndpoints",
            "sagemaker:DescribeEndpoint(EndpointName='<each>')",
            "sagemaker:ListNotebookInstances",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/SageMaker',MetricName='Invocations',Period=86400,Statistics=['Sum'],StartTime=-7d)"
        ],
        "drilldownInstructions": "1. List all endpoints — real-time endpoints cost per instance-hour even with 0 invocations. 2. Check invocation count: endpoints with 0 invocations are pure waste. 3. For low-traffic endpoints: switch to Serverless Inference (scales to zero). 4. Check notebook instances: stopped notebooks still incur storage charges; unused ones should be deleted. 5. For training jobs: use Spot training (up to 90% savings) for fault-tolerant workloads."
    },
    "Bedrock": {
        "apis": [
            "ce:GetCostAndUsage(Filter={Dimensions:{Key:'SERVICE',Values:['Amazon Bedrock']}},GroupBy=[{Type:'DIMENSION',Key:'USAGE_TYPE'}])",
            "bedrock:ListFoundationModels",
            "pricing:GetProducts(ServiceCode='AmazonBedrock')"
        ],
        "drilldownInstructions": "1. Break down Bedrock cost by usage type to identify which models are most expensive. 2. Check input vs output token ratios — high output token costs suggest verbose responses that could be trimmed. 3. Compare model pricing: Claude Haiku ($0.25/1M input) vs Claude Sonnet ($3/1M input) — use Haiku for simple tasks. 4. Implement prompt caching for repeated context. 5. For batch workloads: use Batch Inference (50% cheaper than real-time)."
    },
    "ELB": {
        "apis": [
            "elbv2:DescribeLoadBalancers",
            "elbv2:DescribeTargetGroups",
            "elbv2:DescribeTargetHealth(TargetGroupArn='<each>')",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/ApplicationELB',MetricName='RequestCount',Period=86400,Statistics=['Sum'],StartTime=-7d)"
        ],
        "drilldownInstructions": "1. List all load balancers — each ALB costs ~$16/mo + LCU charges. 2. Check target health: LBs with 0 healthy targets are pure waste. 3. Check request count: LBs with near-zero traffic should be deleted or consolidated. 4. For multiple LBs serving similar traffic: consolidate using path-based routing on a single ALB. 5. Show: 'Found X load balancers. Y have 0 healthy targets (waste: $Z/mo). W have <100 requests/day — consider consolidation.'"
    },
    "Elastic IP": {
        "apis": [
            "ec2:DescribeAddresses",
            "ce:GetCostAndUsage(Filter={Dimensions:{Key:'USAGE_TYPE',Values:['ElasticIP:IdleAddress']}})"
        ],
        "drilldownInstructions": "1. List all Elastic IPs with DescribeAddresses. 2. Filter for unassociated EIPs (no InstanceId or NetworkInterfaceId). 3. Each idle EIP costs $0.005/hr = $3.65/mo. 4. Release all unassociated EIPs immediately. 5. Show: 'Found X Elastic IPs, Y are unassociated. Releasing Y EIPs saves $Z/mo.'"
    },
    "Auto Scaling": {
        "apis": [
            "autoscaling:DescribeAutoScalingGroups",
            "autoscaling:DescribeScalingActivities(AutoScalingGroupName='<each>')",
            "cloudwatch:GetMetricStatistics(Namespace='AWS/EC2',MetricName='CPUUtilization',Period=86400,Statistics=['Average'],StartTime=-7d)"
        ],
        "drilldownInstructions": "1. List all ASGs — check min/max/desired capacity settings. 2. If min=desired=max: no auto-scaling happening (fixed cost, likely over-provisioned). 3. Check if scaling policies exist — ASGs without policies never scale. 4. For dev/test ASGs: schedule scale-to-zero during off-hours (use Act > Scheduler). 5. Check instance diversity — single instance type risks capacity issues; add Spot mix for savings."
    }
}


# ============================================================
# AZURE API mapping per service for cost investigation
# ============================================================
AZURE_DRILLDOWN_MAP = {
    "Virtual Machines": {
        "apis": [
            "az advisor recommendation list --category Cost",
            "az vm list --query '[].{name:name,size:hardwareProfile.vmSize,state:powerState}'",
            "az monitor metrics list --resource <vm_id> --metric 'Percentage CPU' --interval P14D --aggregation Average",
            "az reservations reservation-order list",
            "az consumption usage list --start-date <30d_ago> --end-date <today> --query '[?meterCategory==\"Virtual Machines\"]'"
        ],
        "drilldownInstructions": "1. Run Azure Advisor cost recommendations to get VM rightsizing suggestions with specific savings amounts. 2. List all VMs with their sizes and power states — deallocated VMs still incur disk costs. 3. Check 14-day CPU average via Monitor metrics — if <10%, recommend B-series (burstable) or smaller size. 4. Check reservation coverage — unreserved steady-state VMs should use Azure Savings Plans (up to 65% savings). 5. For dev/test: recommend Azure Dev/Test pricing (up to 55% off Windows VMs) or auto-shutdown schedules."
    },
    "App Service": {
        "apis": [
            "az webapp list --query '[].{name:name,sku:sku.name,state:state,resourceGroup:resourceGroup}'",
            "az monitor metrics list --resource <app_id> --metric 'CpuPercentage' --interval P7D --aggregation Average",
            "az monitor metrics list --resource <app_id> --metric 'Requests' --interval P7D --aggregation Total",
            "az appservice plan list --query '[].{name:name,sku:sku.name,workers:numberOfWorkers}'"
        ],
        "drilldownInstructions": "1. List all App Service Plans with their SKU tiers and worker counts. 2. Check CPU utilization — plans at <20% can be downsized. 3. Check request volume — apps with near-zero requests may be unused. 4. For low-traffic apps: consider moving from Premium to Basic/Free tier, or consolidate multiple apps into one plan. 5. Use deployment slots only when needed (each slot = separate instance). 6. Show: 'Plan X runs 3 workers at Premium P1v3 ($295/mo each). CPU avg 8% — downsize to B1 ($54/mo) or consolidate saves $720/mo.'"
    },
    "Azure SQL": {
        "apis": [
            "az sql db list --server <server> --query '[].{name:name,sku:currentSku.name,maxSizeBytes:maxSizeBytes,status:status}'",
            "az monitor metrics list --resource <db_id> --metric 'dtu_consumption_percent' --interval P14D --aggregation Average",
            "az monitor metrics list --resource <db_id> --metric 'cpu_percent' --interval P14D --aggregation Average",
            "az sql db list-usages --server <server> --database-name <db>",
            "az advisor recommendation list --category Cost --resource-type 'Microsoft.Sql/servers/databases'"
        ],
        "drilldownInstructions": "1. List all SQL databases with their pricing tier (DTU or vCore model). 2. Check DTU/CPU utilization over 14 days — if <20% average, recommend downsizing. 3. For intermittent workloads (<5% off-hours): switch to Serverless tier (auto-pause after idle period, pay only for compute used). 4. For steady-state: check Azure Hybrid Benefit (BYOL saves up to 55%) and Reserved Capacity (up to 33% off). 5. Check if databases can be consolidated into Elastic Pools for shared resources."
    },
    "Storage": {
        "apis": [
            "az storage account list --query '[].{name:name,sku:sku.name,kind:kind,accessTier:accessTier}'",
            "az storage blob service-properties show --account-name <each>",
            "az monitor metrics list --resource <account_id> --metric 'UsedCapacity' --interval P30D",
            "az storage account management-policy show --account-name <each>",
            "az advisor recommendation list --category Cost --resource-type 'Microsoft.Storage/storageAccounts'"
        ],
        "drilldownInstructions": "1. List all storage accounts — check access tier (Hot/Cool/Archive). 2. Get used capacity per account from Monitor metrics. 3. Check if lifecycle management policies exist — accounts without policies keep all data in Hot tier (most expensive). 4. For infrequently accessed data: move to Cool tier (50% cheaper) or Archive (90% cheaper). 5. Check for accounts with Premium/GRS redundancy that could use Standard/LRS. 6. Show: 'Account X has Y TB in Hot tier with no lifecycle policy. Moving to Cool saves $Z/mo.'"
    },
    "Cosmos DB": {
        "apis": [
            "az cosmosdb list --query '[].{name:name,kind:kind,locations:locations[0].locationName}'",
            "az cosmosdb sql database list --account-name <each>",
            "az cosmosdb sql container throughput show --account-name <acct> --database-name <db> --name <container>",
            "az monitor metrics list --resource <account_id> --metric 'NormalizedRUConsumption' --interval P7D --aggregation Average"
        ],
        "drilldownInstructions": "1. List all Cosmos DB accounts and databases. 2. Check provisioned RU/s vs consumed RU/s (NormalizedRUConsumption metric). 3. If consumption <20%: reduce provisioned throughput or switch to Autoscale (pay for actual usage, max out at provisioned). 4. For low-traffic workloads: switch to Serverless mode (pay per request, no minimum). 5. Check for Reserved Capacity (up to 65% savings on 3-year commitment for steady-state). 6. Review multi-region writes — disable if not needed (doubles RU costs)."
    },
    "Azure Database for PostgreSQL": {
        "apis": [
            "az postgres flexible-server list --query '[].{name:name,sku:sku.name,tier:sku.tier,state:state}'",
            "az monitor metrics list --resource <server_id> --metric 'cpu_percent' --interval P14D --aggregation Average",
            "az monitor metrics list --resource <server_id> --metric 'active_connections' --interval P14D --aggregation Maximum",
            "az postgres flexible-server show --name <server> --query '{storage:storage.storageSizeGb,backup:backup.backupRetentionDays}'"
        ],
        "drilldownInstructions": "1. List all Flexible Servers with SKU tier (Burstable/General Purpose/Memory Optimized). 2. Check 14-day CPU average — servers <20% CPU on General Purpose should move to Burstable tier (B-series). 3. Check active connections — 0 connections over 14 days means server is unused. 4. Use stop/start capability for dev/test servers during off-hours. 5. Check backup retention — reduce from 35 to 7 days if not needed. 6. Reserved capacity (1yr/3yr) for steady-state production servers."
    },
    "Azure Kubernetes Service": {
        "apis": [
            "az aks list --query '[].{name:name,nodeResourceGroup:nodeResourceGroup,kubernetesVersion:kubernetesVersion}'",
            "az aks nodepool list --cluster-name <cluster> --resource-group <rg>",
            "az aks nodepool show --cluster-name <cluster> --resource-group <rg> --name <pool> --query '{vmSize:vmSize,count:count,minCount:minCount,maxCount:maxCount,enableAutoScaling:enableAutoScaling}'",
            "az monitor metrics list --resource <cluster_id> --metric 'node_cpu_usage_percentage' --interval P7D --aggregation Average"
        ],
        "drilldownInstructions": "1. List all AKS clusters and their node pools. 2. Check if autoscaling is enabled — fixed-size pools waste capacity during off-hours. 3. Check node CPU usage — if <30% average, the cluster is over-provisioned. 4. For non-production: use Spot node pools (up to 90% savings). 5. Check if cluster autoscaler is configured with appropriate min/max. 6. Consider scale-to-zero for dev/test during off-hours. 7. Use Azure Advisor for specific node pool sizing recommendations."
    },
    "Azure Cache for Redis": {
        "apis": [
            "az redis list --query '[].{name:name,sku:sku.name,family:sku.family,capacity:sku.capacity}'",
            "az monitor metrics list --resource <redis_id> --metric 'usedmemorypercentage' --interval P14D --aggregation Average",
            "az monitor metrics list --resource <redis_id> --metric 'connectedclients' --interval P14D --aggregation Maximum",
            "az advisor recommendation list --category Cost --resource-type 'Microsoft.Cache/redis'"
        ],
        "drilldownInstructions": "1. List all Redis caches with tier (Basic/Standard/Premium) and capacity. 2. Check memory utilization — if <30%, downsize capacity. 3. Check connected clients — 0 clients means unused cache. 4. For dev/test: switch from Standard (replicated) to Basic (no SLA, much cheaper). 5. For steady-state: check Reserved Capacity (up to 55% savings). 6. Consider Azure Cache for Redis Enterprise for better price-performance ratio at scale."
    },
    "Azure Firewall": {
        "apis": [
            "az network firewall list --query '[].{name:name,sku:sku.name,threat:threatIntelMode}'",
            "az monitor metrics list --resource <firewall_id> --metric 'Throughput' --interval P7D --aggregation Average",
            "az monitor metrics list --resource <firewall_id> --metric 'DataProcessed' --interval P30D --aggregation Total"
        ],
        "drilldownInstructions": "1. List all Azure Firewalls — each Premium instance costs ~$1,752/mo + data processing. 2. Check if Standard tier is sufficient (Premium adds IDPS, TLS inspection — not always needed). 3. Check data processed volume — low throughput may indicate the firewall can be shared across VNets. 4. For dev/test environments: consider NSGs instead of Firewall (free vs $1,752/mo). 5. Consolidate multiple firewalls using Azure Firewall Manager hub architecture."
    },
    "Application Gateway": {
        "apis": [
            "az network application-gateway list --query '[].{name:name,sku:sku.name,tier:sku.tier,capacity:sku.capacity}'",
            "az monitor metrics list --resource <gw_id> --metric 'TotalRequests' --interval P7D --aggregation Total",
            "az monitor metrics list --resource <gw_id> --metric 'CurrentConnections' --interval P7D --aggregation Average"
        ],
        "drilldownInstructions": "1. List all Application Gateways — check SKU tier (Standard_v2, WAF_v2) and capacity units. 2. Check request volume and connections — gateways with near-zero traffic are waste. 3. If fixed capacity: switch to autoscale (pay for actual CU usage, not reserved). 4. Consolidate multiple gateways behind a single gateway with path-based routing. 5. WAF_v2 costs 2x Standard_v2 — evaluate if WAF is needed on all gateways."
    },
    "Azure AD": {
        "apis": [
            "az ad user list --query '[].{displayName:displayName,accountEnabled:accountEnabled,userType:userType}'",
            "az rest --method get --url 'https://graph.microsoft.com/v1.0/subscribedSkus'",
            "az ad group list --query '[].{displayName:displayName,memberCount:length(members)}'",
            "az rest --method get --url 'https://graph.microsoft.com/v1.0/reports/getOffice365ActiveUserDetail(period=\"D30\")'"
        ],
        "drilldownInstructions": "1. List all licensed users — identify accounts that haven't signed in for 90+ days. 2. Check subscribed SKUs to see P1/P2 license assignments. 3. Remove P2 licenses from users who don't need Privileged Identity Management or Identity Protection. 4. Downgrade inactive users from P2 to P1, or P1 to Free. 5. Use group-based licensing to auto-manage assignments. 6. Show: 'X users have P2 license ($9/user/mo) but only Y use PIM features. Downgrade X-Y users to P1 saves $Z/mo.'"
    },
    "Azure Backup": {
        "apis": [
            "az backup vault list --query '[].{name:name,resourceGroup:resourceGroup}'",
            "az backup item list --vault-name <vault> --resource-group <rg> --query '[].{name:name,protectionState:properties.protectionState,policyName:properties.policyId}'",
            "az backup policy list --vault-name <vault> --resource-group <rg>"
        ],
        "drilldownInstructions": "1. List all Recovery Services vaults and protected items. 2. Check for items in 'ProtectionStopped' state — they still incur storage costs. 3. Review backup retention policies — reducing from 30 to 7 daily backups saves significant storage. 4. Check for redundant backups (same VM backed up in multiple vaults). 5. Switch from GRS (geo-redundant) to LRS (locally redundant) storage for non-critical workloads (50% cheaper)."
    },
}

# ============================================================
# GCP API mapping per service for cost investigation
# ============================================================
GCP_DRILLDOWN_MAP = {
    "Compute Engine": {
        "apis": [
            "gcloud recommender recommendations list --recommender=google.compute.instance.MachineTypeRecommender --location=<zone>",
            "gcloud recommender recommendations list --recommender=google.compute.instance.IdleResourceRecommender --location=<zone>",
            "gcloud compute instances list --format='table(name,machineType,status,zone)'",
            "gcloud monitoring metrics list --filter='metric.type=\"compute.googleapis.com/instance/cpu/utilization\"' --interval=P14D",
            "gcloud billing budgets list"
        ],
        "drilldownInstructions": "1. Run GCP Recommender for Machine Type recommendations (specific instance + suggested size + savings). 2. Run Idle Resource Recommender to find unused VMs. 3. List all instances with machine types and status. 4. Check CPU utilization over 14 days from Cloud Monitoring. 5. For steady-state: apply Committed Use Discounts (CUDs) — 1yr=37% off, 3yr=57% off. 6. For fault-tolerant: use Preemptible/Spot VMs (60-91% savings). 7. Show: 'VM X is n2-standard-8 at 5% CPU. Recommender suggests e2-medium saving $Y/mo.'"
    },
    "Cloud Storage": {
        "apis": [
            "gsutil ls -L gs://<bucket>/ | grep 'Storage class\\|Location\\|Size'",
            "gcloud storage buckets list --format='table(name,location,storageClass,lifecycle)'",
            "gcloud recommender recommendations list --recommender=google.storage.bucket.Recommender",
            "gsutil lifecycle get gs://<bucket>"
        ],
        "drilldownInstructions": "1. List all buckets with storage class and lifecycle configuration. 2. Run Storage Recommender for specific bucket-level suggestions. 3. Buckets without lifecycle rules keep all objects in the same class forever — add Object Lifecycle Management to auto-transition to Nearline (30+ days, 50% cheaper) or Coldline (90+ days, 75% cheaper). 4. Check for Autoclass feature (auto-moves objects between classes based on access patterns). 5. Show: 'Bucket X has Y TB in Standard with no lifecycle. Enabling Autoclass estimated to save $Z/mo.'"
    },
    "BigQuery": {
        "apis": [
            "bq show --format=prettyjson --project_id=<project> --dataset_id=<dataset>",
            "gcloud recommender recommendations list --recommender=google.bigquery.table.PartitionClusterRecommender",
            "SELECT total_bytes_billed, total_slot_ms FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT WHERE creation_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)",
            "bq ls --format=prettyjson --max_results=100 <dataset>"
        ],
        "drilldownInstructions": "1. Check billing model: on-demand ($6.25/TB scanned) vs flat-rate/editions (committed slots). 2. Run Partition/Cluster Recommender to find tables that would benefit from partitioning (reduces scanned bytes). 3. Query INFORMATION_SCHEMA for total bytes billed over 30 days to understand spend patterns. 4. For predictable workloads >$500/mo: switch to BigQuery Editions with autoscaling slots. 5. Check for tables without expiration — set partition expiration to auto-delete old data. 6. Use materialized views for repeated queries (cached results, no re-scan cost)."
    },
    "Cloud SQL": {
        "apis": [
            "gcloud sql instances list --format='table(name,databaseVersion,tier,region,state)'",
            "gcloud recommender recommendations list --recommender=google.cloudsql.instance.IdleRecommender",
            "gcloud recommender recommendations list --recommender=google.cloudsql.instance.OverprovisionedRecommender",
            "gcloud monitoring metrics list --filter='metric.type=\"cloudsql.googleapis.com/database/cpu/utilization\"' --interval=P14D"
        ],
        "drilldownInstructions": "1. List all Cloud SQL instances with tier and state. 2. Run Idle Recommender to find instances with no connections. 3. Run Overprovisioned Recommender for specific downsizing suggestions. 4. Check CPU utilization — instances <20% should downsize machine type. 5. For dev/test: use start/stop scheduling (stopped instances only incur storage costs). 6. Enable automatic storage increase to avoid over-provisioning disk. 7. For steady-state: apply Committed Use Discounts (1yr or 3yr)."
    },
    "Cloud Run": {
        "apis": [
            "gcloud run services list --format='table(name,region,lastModifier,status.conditions[0].status)'",
            "gcloud monitoring metrics list --filter='metric.type=\"run.googleapis.com/request_count\"' --interval=P30D",
            "gcloud run services describe <service> --format='yaml(spec.template.spec.containers[0].resources)'"
        ],
        "drilldownInstructions": "1. List all Cloud Run services. 2. Check request counts over 30 days — services with 0 requests are waste. 3. Check resource allocation: reduce CPU/memory limits if over-provisioned. 4. Set min-instances to 0 for non-latency-critical services (scales to zero = no cost when idle). 5. Use CPU throttling (cpu-throttled) for background jobs — 50% cheaper. 6. Set concurrency appropriately — higher concurrency = fewer instances needed."
    },
    "Cloud Spanner": {
        "apis": [
            "gcloud spanner instances list --format='table(name,config,nodeCount,processingUnits)'",
            "gcloud monitoring metrics list --filter='metric.type=\"spanner.googleapis.com/instance/cpu/utilization\"' --interval=P7D",
            "gcloud spanner databases list --instance=<instance>"
        ],
        "drilldownInstructions": "1. List all Spanner instances with processing units. 2. Check CPU utilization — Spanner recommends staying <65% for single-region, <45% for multi-region. 3. If CPU is <20%: reduce processing units (minimum 100 PU = ~$65/mo). 4. Check if multi-region is needed — regional instances are 3x cheaper than multi-region. 5. For predictable workloads: apply Committed Use Discounts (up to 50% savings on 3yr). 6. Use Autoscaler to dynamically adjust capacity based on load."
    },
    "GKE": {
        "apis": [
            "gcloud container clusters list --format='table(name,location,currentNodeCount,status)'",
            "gcloud container node-pools list --cluster=<cluster> --format='table(name,config.machineType,autoscaling.enabled,autoscaling.minNodeCount,autoscaling.maxNodeCount)'",
            "gcloud recommender recommendations list --recommender=google.container.DiagnosisRecommender --location=<zone>"
        ],
        "drilldownInstructions": "1. List all GKE clusters and node pools with machine types. 2. Check if node autoscaling is enabled — fixed pools waste capacity. 3. Use GKE Recommender for cluster optimization suggestions. 4. For non-critical workloads: use Spot VMs in node pools (60-91% savings). 5. Enable cluster autoscaler with appropriate min (0 for dev) and max. 6. Consider GKE Autopilot (pay per pod, no node management, auto-optimized). 7. Check for idle namespaces consuming reserved resources."
    },
    "Cloud Logging": {
        "apis": [
            "gcloud logging sinks list",
            "gcloud logging metrics list",
            "gcloud logging read 'timestamp>=\"<30d_ago>\"' --format='summary' --limit=0 --freshness=30d"
        ],
        "drilldownInstructions": "1. Check log ingestion volume — Cloud Logging charges $0.50/GiB after free 50 GiB/mo. 2. List log sinks — route verbose logs to Cloud Storage ($0.02/GiB) instead of Logging. 3. Create exclusion filters for noisy log entries (debug, trace) that don't need real-time analysis. 4. Set log retention to minimum needed (default 30 days for _Default bucket). 5. Use log-based metrics instead of storing raw logs for monitoring use cases."
    },
    "Cloud Functions": {
        "apis": [
            "gcloud functions list --format='table(name,runtime,status,entryPoint)'",
            "gcloud monitoring metrics list --filter='metric.type=\"cloudfunctions.googleapis.com/function/execution_count\"' --interval=P30D",
            "gcloud functions describe <function> --format='yaml(availableMemoryMb,timeout)'"
        ],
        "drilldownInstructions": "1. List all Cloud Functions with their runtime and memory settings. 2. Check execution count over 30 days — functions with 0 invocations are waste. 3. Check memory allocation — over-provisioned memory increases cost per invocation. 4. For Gen1 functions: migrate to Gen2 (Cloud Run based, better pricing for sustained traffic). 5. Set min-instances to 0 unless cold start is unacceptable. 6. Reduce timeout from default 540s to actual needed duration — prevents runaway executions."
    },
    "Networking": {
        "apis": [
            "gcloud compute forwarding-rules list",
            "gcloud compute addresses list --filter='status=RESERVED'",
            "gcloud compute routers list",
            "gcloud compute vpn-tunnels list"
        ],
        "drilldownInstructions": "1. List all static external IPs — unused reserved IPs cost $0.01/hr ($7.30/mo). 2. Check NAT gateways — each processes data at $0.045/GiB. Use Private Google Access for GCP service traffic (free). 3. List load balancers — unused forwarding rules still incur hourly charges. 4. For cross-region traffic: keep resources co-located to avoid egress ($0.01-0.08/GiB inter-region). 5. Use Cloud CDN for internet-facing content (cheaper egress + caching)."
    },
}

# ============================================================
# OpenAI API mapping for cost investigation
# ============================================================
OPENAI_DRILLDOWN_MAP = {
    "Token Optimization": {
        "apis": [
            "GET https://api.openai.com/v1/organization/usage?date=<YYYY-MM-DD>",
            "GET https://api.openai.com/v1/organization/costs?start_time=<unix>&end_time=<unix>&group_by=line_item",
            "GET https://api.openai.com/v1/organization/usage?date=<YYYY-MM-DD>&group_by=model"
        ],
        "drilldownInstructions": "1. Query OpenAI Usage API grouped by model to identify which models consume most tokens. 2. Check input vs output token ratio — high output suggests verbose completions (set max_tokens). 3. Compare model costs: GPT-4o ($2.50/1M input) vs GPT-4o-mini ($0.15/1M input) — use mini for simple tasks. 4. Implement prompt caching (repeated system prompts cached at 50% off). 5. Batch API for non-real-time tasks (50% cheaper). 6. Show: 'Last 30 days: X tokens on GPT-4o ($Y), Z tokens on GPT-4o-mini ($W). Moving 60% of GPT-4o calls to mini saves $V/mo.'"
    },
    "Model Selection": {
        "apis": [
            "GET https://api.openai.com/v1/organization/costs?start_time=<unix>&end_time=<unix>&group_by=model",
            "GET https://api.openai.com/v1/organization/usage?date=<YYYY-MM-DD>&group_by=model",
            "GET https://api.openai.com/v1/models"
        ],
        "drilldownInstructions": "1. Query costs grouped by model to see which models drive spend. 2. Identify tasks currently using GPT-4o that could use GPT-4o-mini (classification, extraction, summarization). 3. For embedding workloads: compare text-embedding-3-small ($0.02/1M tokens) vs text-embedding-3-large ($0.13/1M). 4. For image generation: DALL-E 3 vs DALL-E 2 (3x price difference). 5. Evaluate fine-tuned models: training cost amortized over volume may be cheaper than base model for repetitive tasks."
    },
    "API Usage": {
        "apis": [
            "GET https://api.openai.com/v1/organization/usage?date=<YYYY-MM-DD>",
            "GET https://api.openai.com/v1/organization/costs?start_time=<unix>&end_time=<unix>&bucket_width=1d",
            "GET https://api.openai.com/v1/organization/limits"
        ],
        "drilldownInstructions": "1. Query daily usage to identify traffic patterns and peak hours. 2. Check if rate limits are being hit (429 errors → wasted retries). 3. Implement request batching for bulk operations. 4. Use streaming for long completions (no cost difference but better UX). 5. Set up usage alerts at 80% of monthly budget. 6. Review if any API keys are making unexpected calls (compromised key audit)."
    },
    "Assistants": {
        "apis": [
            "GET https://api.openai.com/v1/organization/costs?start_time=<unix>&end_time=<unix>&group_by=line_item",
            "GET https://api.openai.com/v1/assistants",
            "GET https://api.openai.com/v1/vector_stores"
        ],
        "drilldownInstructions": "1. Check Assistants API costs — file_search and code_interpreter incur additional charges beyond base model. 2. Vector store storage costs: $0.10/GB/day — delete unused vector stores. 3. Code interpreter sessions: $0.03/session — ensure sessions are cleaned up. 4. For retrieval-heavy use cases: compare Assistants API file_search cost vs self-hosted RAG (one-time embedding cost). 5. Audit thread lifecycle — long-lived threads with large context consume more tokens per turn."
    },
    "Fine-tuning": {
        "apis": [
            "GET https://api.openai.com/v1/fine_tuning/jobs",
            "GET https://api.openai.com/v1/organization/costs?start_time=<unix>&end_time=<unix>&group_by=line_item"
        ],
        "drilldownInstructions": "1. List all fine-tuning jobs and their training token counts. 2. Calculate amortized training cost: training_cost / expected_inference_calls. 3. Compare fine-tuned model inference cost vs base model with long prompts (fine-tuning eliminates repeated instructions). 4. Delete unused fine-tuned model checkpoints (storage costs). 5. For tasks with <1000 calls/month: few-shot prompting may be cheaper than maintaining a fine-tuned model."
    },
}


def enrich_tips():
    """Update existing tips in DynamoDB with drilldown API instructions."""
    table = dynamodb.Table(TIPS_TABLE)
    
    # Scan all tips
    items = []
    response = table.scan()
    items.extend(response.get('Items', []))
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))
    
    logger.info(f"Found {len(items)} tips in table")
    
    updated = 0
    for item in items:
        service = item.get('service', '')
        tip_id = item.get('tipId', '')
        cloud = item.get('cloud', '')
        
        # Skip SYNC_LOG entries
        if tip_id.startswith('SYNC_'):
            continue
        
        # Select the right map based on cloud provider
        if cloud == 'AWS':
            drilldown_map = SERVICE_DRILLDOWN_MAP
        elif cloud == 'AZURE':
            drilldown_map = AZURE_DRILLDOWN_MAP
        elif cloud == 'GCP':
            drilldown_map = GCP_DRILLDOWN_MAP
        elif cloud == 'OpenAI':
            drilldown_map = OPENAI_DRILLDOWN_MAP
        else:
            continue
        
        # Find matching drilldown data
        drilldown = drilldown_map.get(service)
        if not drilldown:
            continue
        
        # Only update if not already enriched
        if item.get('drilldownApis'):
            continue
        
        try:
            table.update_item(
                Key={'service': service, 'tipId': tip_id},
                UpdateExpression='SET drilldownApis = :apis, drilldownInstructions = :instr',
                ExpressionAttributeValues={
                    ':apis': drilldown['apis'],
                    ':instr': drilldown['drilldownInstructions'],
                }
            )
            updated += 1
        except Exception as e:
            logger.warning(f"Failed to update {service}/{tip_id}: {e}")
    
    logger.info(f"Enriched {updated} tips with drilldown instructions")
    return updated


if __name__ == '__main__':
    count = enrich_tips()
    print(f"Done. Updated {count} tips with drilldown API instructions.")
