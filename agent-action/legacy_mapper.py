"""
Legacy Path Mapper Module

Maps legacy AWS-specific API paths to vendor-neutral handler names.
Supports backward compatibility during migration to vendor-neutral tooling.

Requirements: 7.1, 7.2, 7.3
"""

# Mapping of all 11 legacy API paths to their vendor-neutral handler names
LEGACY_TO_NEUTRAL = {
    '/get-cost-data': 'getCostBreakdown',
    '/get-monthly-comparison': 'getMonthlyTrend',
    '/get-ec2-instances': 'getComputeInstances',
    '/get-rds-instances': 'getDatabaseInstances',
    '/get-lambda-functions': 'getServerlessFunctions',
    '/get-s3-buckets': 'getObjectStorage',
    '/get-ebs-volumes': 'getStorageVolumes',
    '/get-network-resources': 'getNetworkResources',
    '/get-budgets': 'getBudgets',
    '/get-finops-settings': 'getFinOpsSettings',
    '/get-aws-pricing': 'getPricingData',
    # Additional legacy paths not in the original 11 but present in the handler
    '/get-optimization-tips': 'getOptimizationTips',
    '/get-spot-placement-score': 'getSpotCandidates',
}


def resolve_path(api_path: str) -> str:
    """
    Resolve an API path to its vendor-neutral tool name.

    If the path is a legacy path, it is mapped to the corresponding
    vendor-neutral handler name. Otherwise, the path is returned as-is
    (passthrough for new vendor-neutral paths).

    Args:
        api_path: The API path from the Bedrock Agent invocation
                  (e.g., '/get-ec2-instances' or 'getComputeInstances')

    Returns:
        The vendor-neutral tool name (e.g., 'getComputeInstances')
    """
    return LEGACY_TO_NEUTRAL.get(api_path, api_path)
