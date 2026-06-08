"""Unit tests for legacy_mapper.py — validates backward compatibility mapping."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from legacy_mapper import LEGACY_TO_NEUTRAL, resolve_path


class TestLegacyToNeutralMapping:
    """Verify the LEGACY_TO_NEUTRAL dict contains all required mappings."""

    def test_mapping_has_at_least_11_entries(self):
        # 11 core mappings from Requirement 7.3 + 2 additional legacy paths
        # (/get-optimization-tips, /get-spot-placement-score) for full backward compat
        assert len(LEGACY_TO_NEUTRAL) >= 11

    def test_get_cost_data_maps_to_getCostBreakdown(self):
        assert LEGACY_TO_NEUTRAL['/get-cost-data'] == 'getCostBreakdown'

    def test_get_monthly_comparison_maps_to_getMonthlyTrend(self):
        assert LEGACY_TO_NEUTRAL['/get-monthly-comparison'] == 'getMonthlyTrend'

    def test_get_ec2_instances_maps_to_getComputeInstances(self):
        assert LEGACY_TO_NEUTRAL['/get-ec2-instances'] == 'getComputeInstances'

    def test_get_rds_instances_maps_to_getDatabaseInstances(self):
        assert LEGACY_TO_NEUTRAL['/get-rds-instances'] == 'getDatabaseInstances'

    def test_get_lambda_functions_maps_to_getServerlessFunctions(self):
        assert LEGACY_TO_NEUTRAL['/get-lambda-functions'] == 'getServerlessFunctions'

    def test_get_s3_buckets_maps_to_getObjectStorage(self):
        assert LEGACY_TO_NEUTRAL['/get-s3-buckets'] == 'getObjectStorage'

    def test_get_ebs_volumes_maps_to_getStorageVolumes(self):
        assert LEGACY_TO_NEUTRAL['/get-ebs-volumes'] == 'getStorageVolumes'

    def test_get_network_resources_maps_to_getNetworkResources(self):
        assert LEGACY_TO_NEUTRAL['/get-network-resources'] == 'getNetworkResources'

    def test_get_budgets_maps_to_getBudgets(self):
        assert LEGACY_TO_NEUTRAL['/get-budgets'] == 'getBudgets'

    def test_get_finops_settings_maps_to_getFinOpsSettings(self):
        assert LEGACY_TO_NEUTRAL['/get-finops-settings'] == 'getFinOpsSettings'

    def test_get_aws_pricing_maps_to_getPricingData(self):
        assert LEGACY_TO_NEUTRAL['/get-aws-pricing'] == 'getPricingData'


class TestResolvePath:
    """Verify resolve_path returns correct neutral name or passthrough."""

    def test_legacy_path_resolves_to_neutral(self):
        assert resolve_path('/get-ec2-instances') == 'getComputeInstances'

    def test_all_legacy_paths_resolve_correctly(self):
        for legacy, neutral in LEGACY_TO_NEUTRAL.items():
            assert resolve_path(legacy) == neutral

    def test_new_vendor_neutral_path_passes_through(self):
        assert resolve_path('getComputeInstances') == 'getComputeInstances'

    def test_unknown_path_passes_through(self):
        assert resolve_path('/some-unknown-path') == '/some-unknown-path'

    def test_empty_string_passes_through(self):
        assert resolve_path('') == ''

    def test_neutral_tool_name_passes_through(self):
        assert resolve_path('getCostBreakdown') == 'getCostBreakdown'
