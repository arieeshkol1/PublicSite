"""
Legacy Path Mapper Module

Maps legacy AWS-specific API paths to vendor-neutral handler names.
Supports backward compatibility during migration to vendor-neutral tooling.

Requirements: 7.1, 7.2, 7.3
"""

# Mapping of all 11 legacy API paths to their vendor-neutral handler names
LEGACY_TO_NEUTRAL = {
    # Original legacy AWS-specific paths
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
    '/get-optimization-tips': 'getOptimizationTips',
    '/get-spot-placement-score': 'getSpotCandidates',
    # Vendor-neutral schema paths (from OpenAPI action group schemas)
    '/get-cost-breakdown': 'getCostBreakdown',
    '/get-monthly-trend': 'getMonthlyTrend',
    '/get-cost-forecast': 'getCostForecast',
    '/get-cost-anomalies': 'getCostAnomalies',
    '/get-compute-instances': 'getComputeInstances',
    '/get-rightsizing-recommendations': 'getRightsizingRecommendations',
    '/get-spot-candidates': 'getSpotCandidates',
    '/get-licensing-analysis': 'getLicensingAnalysis',
    '/get-database-instances': 'getDatabaseInstances',
    '/get-storage-volumes': 'getStorageVolumes',
    '/get-object-storage': 'getObjectStorage',
    '/get-serverless-functions': 'getServerlessFunctions',
    '/get-container-clusters': 'getContainerClusters',
    '/get-commitment-coverage': 'getCommitmentCoverage',
    '/get-tag-compliance': 'getTagCompliance',
    '/get-business-metrics': 'getBusinessMetrics',
    '/get-pricing-data': 'getPricingData',
    '/get-ai-vendor-usage': 'getAIVendorUsage',
    '/update-drilldown-plan': 'updateDrilldownPlan',
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
