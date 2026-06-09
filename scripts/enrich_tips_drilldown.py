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
        
        # Skip non-AWS tips and SYNC_LOG entries
        if cloud != 'AWS' or tip_id.startswith('SYNC_'):
            continue
        
        # Find matching drilldown data
        drilldown = SERVICE_DRILLDOWN_MAP.get(service)
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
