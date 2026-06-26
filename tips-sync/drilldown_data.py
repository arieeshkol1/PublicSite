"""
Drilldown data lookup for tips enrichment.

Provides a get_drilldown_data(service, cloud) function that returns
the drilldown APIs and instructions for a given service on a specific cloud.
Used by sync_engine.py when inserting new tips.
"""

# Compact drilldown map — service name → {apis, drilldownInstructions}
# Organized by cloud provider

_AWS_MAP = {
    "EC2": {"apis": ["ce:GetRightsizingRecommendation(Service='AmazonEC2')", "compute-optimizer:GetEC2InstanceRecommendations", "cloudwatch:GetMetricStatistics(CPUUtilization,Period=14d)", "ce:GetSavingsPlansPurchaseRecommendation(COMPUTE_SP)"], "drilldownInstructions": "Call GetRightsizingRecommendation for oversized instances. Check Compute Optimizer for CPU/memory utilization. For <10% CPU instances, calculate savings from downsizing. Check Savings Plans coverage ratio."},
    "EC2 - Other": {"apis": ["ce:GetCostAndUsage(GroupBy=USAGE_TYPE)", "ec2:DescribeVolumes(status=available)", "ec2:DescribeAddresses(unassociated)", "ec2:DescribeNatGateways"], "drilldownInstructions": "Break down by usage type: NatGateway-Hours, EBS:VolumeUsage, ElasticIP:IdleAddress. Find unattached volumes and unassociated EIPs for immediate savings."},
    "RDS": {"apis": ["ce:GetRightsizingRecommendation(Service='AmazonRDS')", "rds:DescribeDBInstances", "cloudwatch:GetMetricStatistics(CPUUtilization,DatabaseConnections)", "ce:GetReservationPurchaseRecommendation(AmazonRDS)"], "drilldownInstructions": "List RDS instances, check 14-day CPU and connection count. <10% CPU or <5 max connections = idle. Consider Aurora Serverless v2 for variable workloads."},
    "S3": {"apis": ["s3:ListBuckets", "s3:GetBucketLifecycleConfiguration", "s3:ListBucketIntelligentTieringConfigurations", "ce:GetCostAndUsage(GroupBy=USAGE_TYPE)"], "drilldownInstructions": "Check lifecycle policies on all buckets. Buckets >100GB without lifecycle should use Intelligent Tiering. Break down cost by storage class and request type."},
    "Lambda": {"apis": ["lambda:ListFunctions", "cloudwatch:GetMetricStatistics(Invocations,Duration)", "compute-optimizer:GetLambdaFunctionRecommendations"], "drilldownInstructions": "List functions with memory settings. Check invocations (0 = waste) and average duration. Use Compute Optimizer for memory right-sizing."},
    "EBS": {"apis": ["ec2:DescribeVolumes", "ec2:DescribeSnapshots(OwnerIds=self)", "compute-optimizer:GetEBSVolumeRecommendations"], "drilldownInstructions": "Find unattached volumes (immediate savings). Identify gp2 volumes for gp3 migration (20% savings). List snapshots >180 days for archive tier."},
    "CloudWatch Logs": {"apis": ["logs:DescribeLogGroups", "ce:GetCostAndUsage(GroupBy=USAGE_TYPE)"], "drilldownInstructions": "List log groups with retention settings. Groups with 'Never expire' should be set to 30-90 days. Break down cost by DataIngestion vs Storage."},
    "DynamoDB": {"apis": ["dynamodb:ListTables", "dynamodb:DescribeTable", "cloudwatch:GetMetricStatistics(ConsumedRead/WriteCapacityUnits)"], "drilldownInstructions": "Compare provisioned vs consumed capacity. If consumed <30% of provisioned, switch to on-demand or reduce. Check for unused tables."},
    "ElastiCache": {"apis": ["elasticache:DescribeCacheClusters", "cloudwatch:GetMetricStatistics(CPUUtilization,CurrConnections)", "ce:GetReservationPurchaseRecommendation(AmazonElastiCache)"], "drilldownInstructions": "Check CPU and connections. Near-zero connections = unused. For steady-state: RI recommendations (55% savings)."},
    "NAT Gateway": {"apis": ["ec2:DescribeNatGateways", "ec2:DescribeVpcEndpoints", "cloudwatch:GetMetricStatistics(BytesOutToDestination)"], "drilldownInstructions": "Each NAT costs $32.40/mo + $0.045/GB. Replace with VPC Gateway Endpoints for S3/DynamoDB (free) or Interface Endpoints for other services."},
    "CloudFront": {"apis": ["cloudfront:ListDistributions", "cloudwatch:GetMetricStatistics(Requests,BytesDownloaded)"], "drilldownInstructions": "Check for zero-traffic distributions. Compare cache hit ratio. Switch to PriceClass_100 if traffic is US/EU only."},
    "Rekognition": {"apis": ["ce:GetCostAndUsage(GroupBy=USAGE_TYPE)", "rekognition:ListCollections", "pricing:GetProducts(AmazonRekognition)"], "drilldownInstructions": "Break down by usage type (FaceSearch, DetectLabels). Calculate API call count from cost. Check for unused face collections."},
    "EKS": {"apis": ["eks:ListClusters", "eks:ListNodegroups", "eks:DescribeNodegroup", "compute-optimizer:GetEC2InstanceRecommendations"], "drilldownInstructions": "Check node pool scaling config. Fixed pools waste capacity. Use Spot instances for workers (60-90% savings)."},
    "Data Transfer": {"apis": ["ce:GetCostAndUsage(GroupBy=USAGE_TYPE)", "ec2:DescribeNatGateways", "cloudfront:ListDistributions"], "drilldownInstructions": "Break down: internet egress ($0.09/GB) vs cross-AZ vs cross-region. Use CloudFront for internet egress. Use VPC endpoints for service traffic."},
    "KMS": {"apis": ["kms:ListKeys", "kms:DescribeKey", "ce:GetCostAndUsage(GroupBy=USAGE_TYPE)"], "drilldownInstructions": "Each customer-managed key = $1/mo. Find keys with 0 usage. Switch to AWS-managed keys where possible (free)."},
    "ELB": {"apis": ["elbv2:DescribeLoadBalancers", "elbv2:DescribeTargetHealth", "cloudwatch:GetMetricStatistics(RequestCount)"], "drilldownInstructions": "Find LBs with 0 healthy targets or zero traffic. Consolidate multiple LBs with path-based routing."},
    "Elastic IP": {"apis": ["ec2:DescribeAddresses"], "drilldownInstructions": "Each idle EIP = $3.65/mo. Release all unassociated EIPs immediately."},
    "Auto Scaling": {"apis": ["autoscaling:DescribeAutoScalingGroups", "cloudwatch:GetMetricStatistics(CPUUtilization)"], "drilldownInstructions": "Check if min=desired=max (no scaling). Schedule scale-to-zero for dev/test off-hours."},
    "Glue": {"apis": ["glue:GetJobs", "glue:GetJobRuns", "glue:GetCrawlers"], "drilldownInstructions": "Check DPU allocation vs job duration. Reduce DPUs for short jobs. Reduce crawler frequency for static schemas."},
    "SageMaker": {"apis": ["sagemaker:ListEndpoints", "sagemaker:ListNotebookInstances", "cloudwatch:GetMetricStatistics(Invocations)"], "drilldownInstructions": "Find endpoints with 0 invocations (pure waste). Switch low-traffic endpoints to Serverless Inference. Delete unused notebooks."},
    "Bedrock": {"apis": ["ce:GetCostAndUsage(GroupBy=USAGE_TYPE)", "pricing:GetProducts(AmazonBedrock)"], "drilldownInstructions": "Break down by model. Compare model pricing (Haiku vs Sonnet). Use Batch Inference for non-real-time tasks (50% cheaper)."},
    "General": {"apis": ["ce:GetCostAndUsage(GroupBy=SERVICE)", "ce:GetSavingsPlansCoverage", "ce:GetReservationCoverage"], "drilldownInstructions": "Get overall cost breakdown by service. Check Savings Plans and RI coverage. Identify top spending services for deeper investigation."},
}

_AZURE_MAP = {
    "Virtual Machines": {"apis": ["az advisor recommendation list --category Cost", "az vm list", "az monitor metrics list (CPU)", "az reservations list"], "drilldownInstructions": "Run Azure Advisor cost recommendations. Check 14-day CPU — <10% means downsize to B-series. For steady-state: Azure Savings Plans (up to 65%). For dev/test: Dev/Test pricing (55% off Windows)."},
    "App Service": {"apis": ["az appservice plan list", "az monitor metrics list (CpuPercentage, Requests)"], "drilldownInstructions": "List plans with SKU tiers. Check CPU — <20% means downsize. Consolidate multiple apps into one plan. Move low-traffic apps to Free/Basic tier."},
    "Azure SQL": {"apis": ["az sql db list", "az monitor metrics list (dtu_consumption_percent, cpu_percent)", "az advisor recommendation list"], "drilldownInstructions": "Check DTU/CPU utilization. <20% = downsize. For intermittent workloads: Serverless tier (auto-pause). For steady-state: Reserved Capacity + Hybrid Benefit."},
    "Storage": {"apis": ["az storage account list", "az monitor metrics list (UsedCapacity)", "az storage account management-policy show"], "drilldownInstructions": "Check access tiers (Hot/Cool/Archive). Accounts without lifecycle policies waste money. Move infrequent data to Cool (50% cheaper) or Archive (90% cheaper)."},
    "Cosmos DB": {"apis": ["az cosmosdb list", "az monitor metrics list (NormalizedRUConsumption)", "az cosmosdb sql container throughput show"], "drilldownInstructions": "Compare provisioned vs consumed RUs. <20% = reduce or switch to Autoscale. For low-traffic: Serverless mode. For steady-state: Reserved Capacity (65% off 3yr)."},
    "Azure Database for PostgreSQL": {"apis": ["az postgres flexible-server list", "az monitor metrics list (cpu_percent, active_connections)"], "drilldownInstructions": "Check CPU and connections. <20% CPU on General Purpose = move to Burstable. 0 connections = unused. Use stop/start for dev/test."},
    "Azure Kubernetes Service": {"apis": ["az aks list", "az aks nodepool list", "az monitor metrics list (node_cpu_usage)"], "drilldownInstructions": "Check if autoscaling enabled. Fixed pools waste capacity. Use Spot node pools for non-critical workloads (90% savings). Scale-to-zero for dev/test."},
    "Azure Cache for Redis": {"apis": ["az redis list", "az monitor metrics list (usedmemorypercentage, connectedclients)"], "drilldownInstructions": "Check memory usage and clients. <30% memory = downsize. 0 clients = unused. For dev/test: Basic tier (no SLA, much cheaper)."},
    "Azure Firewall": {"apis": ["az network firewall list", "az monitor metrics list (Throughput, DataProcessed)"], "drilldownInstructions": "Each Premium = ~$1,752/mo. Check if Standard is sufficient. For dev/test: use NSGs instead (free). Consolidate via Firewall Manager."},
    "Application Gateway": {"apis": ["az network application-gateway list", "az monitor metrics list (TotalRequests, CurrentConnections)"], "drilldownInstructions": "Check request volume. Near-zero = waste. Switch fixed capacity to autoscale. Consolidate with path-based routing."},
    "Azure AD": {"apis": ["az ad user list", "Graph API: subscribedSkus", "Graph API: getOffice365ActiveUserDetail"], "drilldownInstructions": "Find inactive users with P1/P2 licenses. Downgrade unused P2 to P1 or Free. Use group-based licensing for auto-management."},
    "Azure Backup": {"apis": ["az backup vault list", "az backup item list", "az backup policy list"], "drilldownInstructions": "Find items in ProtectionStopped state (still costs storage). Reduce retention from 30 to 7 days for non-critical. Switch GRS to LRS (50% cheaper)."},
    "Azure Files": {"apis": ["az storage share-rm list", "az monitor metrics list (FileCapacity)"], "drilldownInstructions": "Check tier (Premium/Transaction-optimized/Hot/Cool). For infrequent access: switch to Cool tier. Check provisioned vs used capacity on Premium shares."},
    "Azure Databricks": {"apis": ["az databricks workspace list", "az monitor metrics list (cluster usage)"], "drilldownInstructions": "Check cluster auto-termination settings. Idle clusters waste money. Use Spot instances for worker nodes. Consider serverless compute for SQL workloads."},
    "Azure DevOps": {"apis": ["az devops project list", "az pipelines list"], "drilldownInstructions": "Audit parallel jobs allocation. Free tier includes 1 parallel job. Check if self-hosted agents can replace Microsoft-hosted (cheaper for high volume). Remove unused projects."},
}

_GCP_MAP = {
    "Compute Engine": {"apis": ["gcloud recommender recommendations list (MachineTypeRecommender)", "gcloud recommender recommendations list (IdleResourceRecommender)", "gcloud compute instances list", "gcloud monitoring (cpu/utilization)"], "drilldownInstructions": "Use GCP Recommender for rightsizing and idle VMs. For steady-state: CUDs (1yr=37%, 3yr=57% off). For fault-tolerant: Spot VMs (60-91% savings)."},
    "Cloud Storage": {"apis": ["gcloud storage buckets list", "gcloud recommender recommendations list (bucket.Recommender)", "gsutil lifecycle get"], "drilldownInstructions": "Check lifecycle policies. Use Autoclass for automatic tier transitions. Move infrequent data to Nearline (50% cheaper) or Coldline (75% cheaper)."},
    "BigQuery": {"apis": ["gcloud recommender recommendations list (PartitionClusterRecommender)", "INFORMATION_SCHEMA.JOBS_BY_PROJECT (bytes_billed)"], "drilldownInstructions": "Check billing model (on-demand vs editions). Add partitioning/clustering (reduces scanned bytes). For >$500/mo: switch to BigQuery Editions with autoscaling slots."},
    "Cloud SQL": {"apis": ["gcloud sql instances list", "gcloud recommender recommendations list (IdleRecommender, OverprovisionedRecommender)", "gcloud monitoring (cpu/utilization)"], "drilldownInstructions": "Run Idle and Overprovisioned Recommenders. For dev/test: use stop/start scheduling. For steady-state: apply CUDs."},
    "Cloud Run": {"apis": ["gcloud run services list", "gcloud monitoring (request_count)", "gcloud run services describe (resources)"], "drilldownInstructions": "Set min-instances=0 for non-latency-critical services. Use cpu-throttled for background jobs (50% cheaper). Higher concurrency = fewer instances."},
    "Cloud Spanner": {"apis": ["gcloud spanner instances list", "gcloud monitoring (cpu/utilization)"], "drilldownInstructions": "Check CPU utilization (<20% = reduce PUs). Regional is 3x cheaper than multi-region. Apply CUDs for steady-state (up to 50% off 3yr). Use Autoscaler."},
    "GKE": {"apis": ["gcloud container clusters list", "gcloud container node-pools list", "gcloud recommender recommendations list (DiagnosisRecommender)"], "drilldownInstructions": "Enable autoscaling. Use Spot VMs in node pools. Consider GKE Autopilot (pay per pod). Scale-to-zero for dev."},
    "Cloud Logging": {"apis": ["gcloud logging sinks list", "gcloud logging metrics list"], "drilldownInstructions": "Charges $0.50/GiB after free 50 GiB/mo. Route verbose logs to Cloud Storage ($0.02/GiB). Create exclusion filters for noisy entries. Reduce retention."},
    "Cloud Functions": {"apis": ["gcloud functions list", "gcloud monitoring (execution_count)"], "drilldownInstructions": "Find functions with 0 invocations (waste). Check memory allocation for over-provisioning. Migrate Gen1 to Gen2 for better pricing."},
    "Networking": {"apis": ["gcloud compute forwarding-rules list", "gcloud compute addresses list (RESERVED)", "gcloud compute routers list"], "drilldownInstructions": "Unused reserved IPs = $7.30/mo each. Use Private Google Access for GCP service traffic (free vs NAT). Use Cloud CDN for internet content."},
    "App Engine": {"apis": ["gcloud app services list", "gcloud app instances list", "gcloud monitoring (request_count)"], "drilldownInstructions": "Check instance scaling settings. For low-traffic: reduce min_idle_instances to 0. Consider migrating to Cloud Run (scales to zero, better pricing)."},
    "Cloud Pub/Sub": {"apis": ["gcloud pubsub topics list", "gcloud pubsub subscriptions list", "gcloud monitoring (num_undelivered_messages)"], "drilldownInstructions": "Find subscriptions with large backlogs (paying for storage). Delete unused topics/subscriptions. Check message size — smaller messages = lower cost."},
    "Artifact Registry": {"apis": ["gcloud artifacts repositories list", "gcloud artifacts packages list"], "drilldownInstructions": "Set cleanup policies to auto-delete old images. Use regional repos (cheaper than multi-region). Check stored image sizes and versions count."},
}

_OPENAI_MAP = {
    "Token Optimization": {"apis": ["GET /v1/organization/usage?group_by=model", "GET /v1/organization/costs?group_by=line_item"], "drilldownInstructions": "Check input vs output token ratio. Use GPT-4o-mini ($0.15/1M) for simple tasks instead of GPT-4o ($2.50/1M). Implement prompt caching. Use Batch API for non-real-time (50% off)."},
    "Model Selection": {"apis": ["GET /v1/organization/costs?group_by=model", "GET /v1/models"], "drilldownInstructions": "Identify tasks on expensive models that could use cheaper ones. GPT-4o-mini handles classification/extraction well. text-embedding-3-small is 6.5x cheaper than large."},
    "API Usage": {"apis": ["GET /v1/organization/usage", "GET /v1/organization/costs?bucket_width=1d", "GET /v1/organization/limits"], "drilldownInstructions": "Check daily patterns. Implement request batching. Set usage alerts at 80% budget. Audit API keys for unexpected calls."},
    "Assistants": {"apis": ["GET /v1/organization/costs?group_by=line_item", "GET /v1/assistants", "GET /v1/vector_stores"], "drilldownInstructions": "Vector store = $0.10/GB/day — delete unused stores. Code interpreter = $0.03/session. Compare file_search cost vs self-hosted RAG."},
    "Fine-tuning": {"apis": ["GET /v1/fine_tuning/jobs", "GET /v1/organization/costs?group_by=line_item"], "drilldownInstructions": "Calculate amortized training cost per inference call. Delete unused checkpoints. For <1000 calls/mo: few-shot prompting may be cheaper."},
}


_FALLBACK_MAP = {
    # Generic cost-API drilldown per provider. Used when a specific service
    # mapping does not exist, so EVERY tip still has an executable drilldown
    # that runs through the CUSTOMER's connection (cost lands on the customer).
    "AWS": {"apis": ["ce:GetCostAndUsage(GroupBy=SERVICE)", "ce:GetCostAndUsage(Filter={SERVICE:['<service>']},GroupBy=USAGE_TYPE)"], "drilldownInstructions": "Break down spend for this service via Cost Explorer (GroupBy=USAGE_TYPE) on the customer's connected account. Identify the largest usage types and idle/over-provisioned resources to target."},
    "AZURE": {"apis": ["az consumption usage list --query \"[?contains(instanceName,'<service>')]\"", "az costmanagement query --type Usage --dataset-grouping name=ServiceName type=Dimension"], "drilldownInstructions": "Query Azure Cost Management for this service on the customer's subscription. Group by meter/resource to find the biggest line items and right-sizing opportunities."},
    "GCP": {"apis": ["gcloud billing accounts list", "bq query (SELECT service.description, SUM(cost) FROM billing_export GROUP BY 1)"], "drilldownInstructions": "Query the customer's BigQuery billing export (or billing console) for this service. Group by SKU to find the largest cost drivers and idle resources."},
    "OPENAI": {"apis": ["GET /v1/organization/costs?group_by=line_item", "GET /v1/organization/usage?group_by=model"], "drilldownInstructions": "Pull the customer's OpenAI organization costs/usage grouped by model and line item. Identify expensive models and high-token operations to optimize."},
    # GroundCover proxies Anthropic (and other) model usage via a Prometheus
    # metrics API. The drilldown pulls per-model token/cost from the customer's
    # GroundCover connection (the neutral getAIUsage:units / :actor operations).
    "GROUNDCOVER": {"apis": ["getAIUsage:units", "getAIUsage:actor"], "drilldownInstructions": "Pull the customer's GroundCover gen-AI token/cost metrics grouped by model and by user. Identify the most expensive models and heaviest users to target."},
    # Generic AI-vendor fallback for any token-billed AI provider not listed
    # above — uses the neutral, vendor-agnostic usage operations.
    "AI": {"apis": ["getAIUsage:units", "getAIUsage:actor"], "drilldownInstructions": "Pull the customer's AI usage/cost grouped by model/service and by user from their connection. Rank by cost to find the biggest drivers."},
}


# AI-vendor model: maps each AI provider key to its specific drilldown map (or
# None to use the generic AI fallback). Keeps AI vendors vendor-agnostic — the
# generic fallback covers any provider added later with no code change.
_AI_VENDOR_MAPS = {
    "OPENAI": _OPENAI_MAP,
    "GROUNDCOVER": None,   # no service-level map yet -> generic AI fallback
}


def get_drilldown_data(service: str, cloud: str) -> dict:
    """Return drilldown data for a service on a given cloud provider.

    Falls back to a generic per-provider cost-API drilldown when no specific
    service mapping exists, so every tip has an executable check that runs
    through the customer's connection. The ``cloud`` key is matched
    case-insensitively. Returns {} only for genuinely unknown providers.
    """
    cloud_key = (cloud or "").strip().upper()

    # Cloud-provider service maps (case-insensitive lookup).
    provider_map = {
        "AWS": _AWS_MAP,
        "AZURE": _AZURE_MAP,
        "GCP": _GCP_MAP,
        "OPENAI": _OPENAI_MAP,
    }.get(cloud_key)

    # AI-vendor providers (openai/groundcover/...) — use their specific service
    # map if present, otherwise the generic AI fallback below.
    if provider_map is None and cloud_key in _AI_VENDOR_MAPS:
        provider_map = _AI_VENDOR_MAPS[cloud_key] or {}

    if provider_map is None:
        return {}

    data = provider_map.get(service)
    if data:
        return data

    # Fallback: generic cost-API drilldown for this provider. AI vendors with no
    # explicit fallback row use the generic "AI" fallback.
    fb = _FALLBACK_MAP.get(cloud_key)
    if not fb and cloud_key in _AI_VENDOR_MAPS:
        fb = _FALLBACK_MAP.get("AI")
    if not fb:
        return {}
    apis = [a.replace("<service>", service) for a in fb["apis"]]
    return {"apis": apis, "drilldownInstructions": fb["drilldownInstructions"]}
