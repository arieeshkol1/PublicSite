"""
Tips filtering module with provider-specific service mappings.

Provides cloud-provider-aware keyword-to-service mappings for querying
the ViewMyBill-CostOptimizationTips DynamoDB table, plus deduplication
logic for multi-provider tip merging.
"""

import time
import logging

import boto3
import boto3.dynamodb.conditions
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# ============================================================
# Provider-specific service mappings
# ============================================================

AWS_SERVICE_MAPPING = {
    # EC2 variants
    'ec2': 'EC2', 'ec 2': 'EC2', 'elastic compute': 'EC2', 'compute cloud': 'EC2', 'instances': 'EC2',
    # S3 variants
    's3': 'S3', 's 3': 'S3', 'simple storage': 'S3', 'bucket': 'S3', 'buckets': 'S3',
    # RDS variants
    'rds': 'RDS', 'relational database': 'RDS', 'database service': 'RDS', 'aurora': 'RDS',
    # Lambda variants
    'lambda': 'Lambda', 'lamda': 'Lambda', 'lamba': 'Lambda',
    # CloudFront
    'cloudfront': 'CloudFront', 'cloud front': 'CloudFront', 'cdn': 'CloudFront',
    # DynamoDB variants
    'dynamodb': 'DynamoDB', 'dynamo': 'DynamoDB', 'dynammo': 'DynamoDB', 'dynamo db': 'DynamoDB',
    # EBS
    'ebs': 'EBS', 'elastic block': 'EBS', 'volumes': 'EBS',
    # ELB
    'elb': 'ELB', 'load balancer': 'ELB', 'alb': 'ELB', 'nlb': 'ELB',
    # Container services
    'ecs': 'ECS', 'fargate': 'ECS', 'eks': 'EKS', 'kubernetes': 'EKS',
    # Redshift
    'redshift': 'Redshift', 'red shift': 'Redshift',
    # ElastiCache
    'elasticache': 'ElastiCache', 'elasti cache': 'ElastiCache', 'redis': 'ElastiCache', 'memcached': 'ElastiCache',
    # Route53
    'route53': 'Route53', 'route 53': 'Route53',
    # CloudWatch
    'cloudwatch': 'CloudWatch', 'cloud watch': 'CloudWatch', 'cloudwatch logs': 'CloudWatch Logs', 'logs': 'CloudWatch Logs',
    # IAM / VPC / NAT
    'iam': 'IAM', 'vpc': 'VPC', 'nat': 'NAT Gateway', 'nat gateway': 'NAT Gateway',
    # KMS
    'kms': 'KMS', 'key management': 'KMS', 'encryption': 'KMS',
    # Rekognition variants (common misspellings)
    'rekognition': 'Rekognition', 'recognition': 'Rekognition', 'recoknition': 'Rekognition',
    'rekogn': 'Rekognition', 'rekog': 'Rekognition', 'recog': 'Rekognition',
    'face detection': 'Rekognition', 'image analysis': 'Rekognition',
    # SageMaker / Bedrock / AI
    'sagemaker': 'SageMaker', 'sage maker': 'SageMaker', 'bedrock': 'Bedrock',
    # Glue / Athena
    'glue': 'Glue', 'athena': 'Athena',
    # General / billing keywords
    'general': 'General', 'cost': 'General', 'billing': 'General',
    'save': 'General', 'efficient': 'General', 'optimize': 'General',
    'support': 'General', 'tax': 'General',
    'forecast': 'General', 'budget': 'General',
    # Other services
    'data transfer': 'Data Transfer', 'transfer': 'Data Transfer',
    'efs': 'EFS', 'elastic file': 'EFS',
    'amplify': 'Amplify', 'cognito': 'Cognito',
    'guardduty': 'GuardDuty', 'guard duty': 'GuardDuty',
    'waf': 'WAF', 'firewall': 'WAF',
    'sns': 'SNS', 'ses': 'SES', 'email': 'SES',
    'step functions': 'Step Functions', 'step function': 'Step Functions',
    'auto scaling': 'Auto Scaling', 'autoscaling': 'Auto Scaling',
    'cost explorer': 'General',
}

AZURE_SERVICE_MAPPING = {
    'vm': 'Virtual Machines', 'virtual machine': 'Virtual Machines',
    'app service': 'App Service', 'web app': 'App Service',
    'azure sql': 'Azure SQL', 'sql database': 'Azure SQL',
    'storage': 'Storage', 'blob': 'Storage',
    'functions': 'Azure Functions', 'cosmos': 'Cosmos DB',
    'aks': 'AKS', 'kubernetes': 'AKS',
    'cdn': 'Azure CDN', 'dns': 'Azure DNS',
    'monitor': 'Azure Monitor', 'vnet': 'VNet',
    'key vault': 'Azure Key Vault',
    'general': 'General', 'cost': 'General', 'billing': 'General',
    'save': 'General', 'efficient': 'General', 'optimize': 'General',
}

GCP_SERVICE_MAPPING = {
    'compute': 'Compute Engine', 'vm': 'Compute Engine',
    'gcs': 'Cloud Storage', 'storage': 'Cloud Storage',
    'cloud sql': 'Cloud SQL', 'sql': 'Cloud SQL',
    'functions': 'Cloud Functions',
    'bigquery': 'BigQuery', 'bq': 'BigQuery',
    'gke': 'GKE', 'kubernetes': 'GKE',
    'cdn': 'Cloud CDN', 'dns': 'Cloud DNS',
    'monitoring': 'Cloud Monitoring',
    'vpc': 'VPC', 'kms': 'Cloud KMS',
    'general': 'General', 'cost': 'General', 'billing': 'General',
    'save': 'General', 'efficient': 'General', 'optimize': 'General',
}

OPENAI_SERVICE_MAPPING = {
    'gpt-4': 'GPT-4', 'gpt4': 'GPT-4', 'gpt-4o': 'GPT-4o',
    'gpt-3.5': 'GPT-3.5-Turbo', 'gpt-3': 'GPT-3.5-Turbo',
    'chatgpt': 'General', 'openai': 'General',
    'token': 'Token Optimization', 'tokens': 'Token Optimization',
    'prompt': 'Prompt Optimization', 'embedding': 'Embeddings',
    'fine-tune': 'Fine-Tuning', 'finetune': 'Fine-Tuning',
    'batch': 'Batch API', 'cache': 'Caching',
    'dall-e': 'DALL-E', 'whisper': 'Whisper', 'tts': 'TTS',
    'general': 'General', 'cost': 'General', 'billing': 'General',
    'save': 'General', 'efficient': 'General', 'optimize': 'General',
}

# Maps provider name to corresponding service mapping dictionary
PROVIDER_MAPPINGS = {
    'aws': AWS_SERVICE_MAPPING,
    'azure': AZURE_SERVICE_MAPPING,
    'gcp': GCP_SERVICE_MAPPING,
    'openai': OPENAI_SERVICE_MAPPING,
}


# ============================================================
# Tips cache (Lambda execution context, 5-minute TTL)
# ============================================================

_tips_cache: dict = {}  # {provider: {'tips': [...], 'timestamp': float}}
TIPS_CACHE_TTL = 300  # 5 minutes


def _get_cached_tips(provider: str):
    """Returns cached tips if fresh (< 300 seconds old), None if stale/missing."""
    entry = _tips_cache.get(provider)
    if entry is None:
        return None
    if time.time() - entry['timestamp'] >= TIPS_CACHE_TTL:
        # Stale — discard
        del _tips_cache[provider]
        return None
    return entry['tips']


def _set_cached_tips(provider: str, tips: list) -> None:
    """Stores tips in cache with current timestamp."""
    _tips_cache[provider] = {
        'tips': tips,
        'timestamp': time.time(),
    }


# ============================================================
# Tips search with provider filtering
# ============================================================

def _get_service_mapping(provider: str) -> dict:
    """Return the service mapping for the given provider, defaulting to AWS."""
    return PROVIDER_MAPPINGS.get(provider, AWS_SERVICE_MAPPING)


def _search_tips(question: str, provider: str = 'aws', tips_table=None, dynamodb_resource=None) -> list:
    """
    Search ViewMyBill-CostOptimizationTips for relevant tips matching the question.

    Uses the provider-cloud-index GSI to query efficiently by provider,
    avoiding full-table scans (C5: optimised key access).
    Always includes 'all' and 'General' tips regardless of provider.

    Args:
        question: The user's question text.
        provider: Cloud provider ("aws", "azure", "gcp", "openai", ...). Defaults to "aws".
        tips_table: Optional pre-resolved DynamoDB table resource (for testing).
        dynamodb_resource: Optional boto3 DynamoDB resource (for testing).

    Returns:
        List of tip items (deduplicated, sorted by confidence/score), max 10.
    """
    import os
    from decimal import Decimal

    if tips_table is None:
        if dynamodb_resource is None:
            dynamodb_resource = boto3.resource('dynamodb')
        table_name = os.environ.get('TIPS_TABLE_NAME', 'ViewMyBill-CostOptimizationTips')
        tips_table = dynamodb_resource.Table(table_name)

    # Check cache first
    cached = _get_cached_tips(provider)
    if cached is not None:
        return _filter_cached_tips(cached, question, provider)

    question_lower = question.lower()
    service_mapping = _get_service_mapping(provider)

    # Find matching services from the question keywords
    matched_services = set()
    for keyword, service_name in service_mapping.items():
        if keyword in question_lower:
            matched_services.add(service_name)
    matched_services.add('General')

    tips = []
    try:
        # Query by provider via GSI (avoids full table scan — C5)
        # We query the provider value AND the special 'all' sentinel that marks universal tips.
        providers_to_query = {provider, 'all'}
        for prov in providers_to_query:
            try:
                resp = tips_table.query(
                    IndexName='provider-cloud-index',
                    KeyConditionExpression=boto3.dynamodb.conditions.Key('provider').eq(prov),
                )
                tips.extend(resp.get('Items', []))
            except Exception as gsi_err:
                # GSI may not exist on older table — fall back to service-keyed queries
                logger.debug(f"GSI query failed for provider={prov}: {gsi_err} — using service query")
                if matched_services:
                    for svc in list(matched_services)[:5]:
                        result = tips_table.query(
                            KeyConditionExpression=boto3.dynamodb.conditions.Key('service').eq(svc)
                        )
                        tips.extend(result.get('Items', []))
                else:
                    result = tips_table.scan(Limit=20)
                    tips.extend(result.get('Items', []))
                break

        # Also include AI-GENERATED tips
        try:
            ai_tips = tips_table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('service').eq('AI-GENERATED')
            )
            tips.extend(ai_tips.get('Items', []))
        except Exception:
            pass

    except ClientError as e:
        logger.warning(f"Tips table query error: {e}")

    # Deduplicate by tipId
    tips = _deduplicate_tips(tips)
    tips.sort(key=_tip_sort_key)
    _set_cached_tips(provider, tips)
    return _decimal_to_native(tips[:10])


def _filter_cached_tips(cached_tips: list, question: str, provider: str) -> list:
    """Filter cached tips based on question keywords and provider mapping."""
    question_lower = question.lower()
    service_mapping = _get_service_mapping(provider)

    matched_services = set()
    for keyword, service_name in service_mapping.items():
        if keyword in question_lower:
            matched_services.add(service_name)

    # Always include General
    matched_services.add('General')

    if not matched_services:
        return _decimal_to_native(cached_tips[:10])

    # Filter tips that match the services (or AI-GENERATED)
    filtered = [
        t for t in cached_tips
        if t.get('service') in matched_services or t.get('service') == 'AI-GENERATED'
    ]

    filtered.sort(key=_tip_sort_key)
    return _decimal_to_native(filtered[:10])


def merge_tips_multi_provider(tips_by_provider: dict) -> list:
    """
    Merge tips from multiple provider queries, deduplicating by tipId.

    Args:
        tips_by_provider: Dict mapping provider names to lists of tip items.
            e.g., {"aws": [...], "azure": [...]}

    Returns:
        Deduplicated list of tips sorted by confidence/score, max 10.
    """
    all_tips = []
    for provider_tips in tips_by_provider.values():
        all_tips.extend(provider_tips)

    deduplicated = _deduplicate_tips(all_tips)
    deduplicated.sort(key=_tip_sort_key)
    return _decimal_to_native(deduplicated[:10])


# ============================================================
# Utility functions
# ============================================================

def _deduplicate_tips(tips: list) -> list:
    """Remove duplicate tips by tipId, keeping the first occurrence."""
    seen = set()
    unique_tips = []
    for t in tips:
        tid = t.get('tipId', '')
        if tid and tid not in seen:
            seen.add(tid)
            unique_tips.append(t)
        elif not tid:
            # Tips without a tipId are always included
            unique_tips.append(t)
    return unique_tips


def _tip_sort_key(t):
    """Sort key: high-confidence first, then by positive count, then curated."""
    if t.get('confidenceTag') == 'high-confidence':
        return (0, -(t.get('positiveCount', 0)))
    if t.get('source') == 'user-feedback':
        return (1, -(t.get('positiveCount', 0)))
    if t.get('source') == 'ai-agent':
        return (2, 0)
    return (3, 0)


def _decimal_to_native(obj):
    """Recursively convert Decimal values to int/float for JSON serialization."""
    from decimal import Decimal
    if isinstance(obj, list):
        return [_decimal_to_native(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _decimal_to_native(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    return obj
