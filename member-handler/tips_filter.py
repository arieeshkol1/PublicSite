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
    'ec2': 'EC2', 's3': 'S3', 'rds': 'RDS', 'lambda': 'Lambda',
    'cloudfront': 'CloudFront', 'dynamodb': 'DynamoDB', 'ebs': 'EBS',
    'elb': 'ELB', 'ecs': 'ECS', 'eks': 'EKS', 'redshift': 'Redshift',
    'elasticache': 'ElastiCache', 'route53': 'Route53', 'route 53': 'Route53',
    'cloudwatch': 'CloudWatch', 'iam': 'IAM', 'vpc': 'VPC', 'nat': 'NAT Gateway',
    'kms': 'KMS', 'general': 'General', 'cost': 'General', 'billing': 'General',
    'save': 'General', 'efficient': 'General', 'optimize': 'General',
    'data transfer': 'Data Transfer', 'efs': 'EFS',
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

# Maps provider name to corresponding service mapping dictionary
PROVIDER_MAPPINGS = {
    'aws': AWS_SERVICE_MAPPING,
    'azure': AZURE_SERVICE_MAPPING,
    'gcp': GCP_SERVICE_MAPPING,
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

    Uses provider-specific keyword-to-service mappings to query only relevant
    service partitions. Always includes tips tagged with service "General".

    Args:
        question: The user's question text.
        provider: Cloud provider ("aws", "azure", "gcp"). Defaults to "aws".
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
        # Filter cached tips based on question keywords
        return _filter_cached_tips(cached, question, provider)

    question_lower = question.lower()
    service_mapping = _get_service_mapping(provider)

    # Find matching services from the question keywords
    matched_services = set()
    for keyword, service_name in service_mapping.items():
        if keyword in question_lower:
            matched_services.add(service_name)

    # Always include "General" tips regardless of provider
    matched_services.add('General')

    tips = []
    try:
        if matched_services:
            for svc in list(matched_services)[:5]:
                result = tips_table.query(
                    KeyConditionExpression=boto3.dynamodb.conditions.Key('service').eq(svc)
                )
                tips.extend(result.get('Items', []))
            # Also check AI-GENERATED tips (from auto-save)
            try:
                ai_tips = tips_table.query(
                    KeyConditionExpression=boto3.dynamodb.conditions.Key('service').eq('AI-GENERATED')
                )
                tips.extend(ai_tips.get('Items', []))
            except Exception:
                pass
        else:
            result = tips_table.scan(Limit=20)
            tips = result.get('Items', [])
    except ClientError as e:
        logger.warning(f"Tips table query error: {e}")

    # Deduplicate by tipId
    tips = _deduplicate_tips(tips)

    # Sort: high-confidence first, then by feedbackScore, then curated
    tips.sort(key=_tip_sort_key)

    # Cache the results for this provider
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
