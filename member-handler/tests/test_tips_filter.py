"""
Unit tests for the tips_filter module — provider-specific mappings, filtering, and deduplication.
"""

import time
import sys
import os
from unittest.mock import MagicMock, patch
from decimal import Decimal

import pytest

# Ensure member-handler is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import tips_filter
from tips_filter import (
    AWS_SERVICE_MAPPING,
    AZURE_SERVICE_MAPPING,
    GCP_SERVICE_MAPPING,
    PROVIDER_MAPPINGS,
    _get_service_mapping,
    _search_tips,
    _deduplicate_tips,
    _filter_cached_tips,
    merge_tips_multi_provider,
    _get_cached_tips,
    _set_cached_tips,
    _tips_cache,
    TIPS_CACHE_TTL,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the tips cache before each test."""
    tips_filter._tips_cache.clear()
    yield
    tips_filter._tips_cache.clear()


def _make_tip(tip_id, service='EC2', confidence='high-confidence', source='curated', positive_count=0):
    """Helper to create a tip item."""
    return {
        'tipId': tip_id,
        'service': service,
        'title': f'Tip {tip_id}',
        'description': f'Description for {tip_id}',
        'confidenceTag': confidence,
        'source': source,
        'positiveCount': positive_count,
    }


def _make_mock_table(tips_by_service):
    """Create a mock DynamoDB table that returns tips based on service key."""
    mock_table = MagicMock()

    def mock_query(**kwargs):
        key_expr = kwargs.get('KeyConditionExpression')
        # Extract service name from the Key condition expression
        service = None
        try:
            expr = key_expr.get_expression()
            # values is (Key object, service_name_string)
            service = expr['values'][1]
        except (AttributeError, KeyError, IndexError):
            pass
        items = tips_by_service.get(service, [])
        return {'Items': items}

    def mock_scan(**kwargs):
        all_items = []
        for items in tips_by_service.values():
            all_items.extend(items)
        limit = kwargs.get('Limit', 20)
        return {'Items': all_items[:limit]}

    mock_table.query = MagicMock(side_effect=mock_query)
    mock_table.scan = MagicMock(side_effect=mock_scan)
    return mock_table


# ============================================================
# Test: Provider mapping dictionaries
# ============================================================

class TestProviderMappings:
    """Test the provider-specific service mapping dictionaries."""

    def test_aws_mapping_has_core_services(self):
        assert AWS_SERVICE_MAPPING['ec2'] == 'EC2'
        assert AWS_SERVICE_MAPPING['s3'] == 'S3'
        assert AWS_SERVICE_MAPPING['rds'] == 'RDS'
        assert AWS_SERVICE_MAPPING['lambda'] == 'Lambda'

    def test_azure_mapping_has_core_services(self):
        assert AZURE_SERVICE_MAPPING['vm'] == 'Virtual Machines'
        assert AZURE_SERVICE_MAPPING['app service'] == 'App Service'
        assert AZURE_SERVICE_MAPPING['azure sql'] == 'Azure SQL'
        assert AZURE_SERVICE_MAPPING['storage'] == 'Storage'
        assert AZURE_SERVICE_MAPPING['functions'] == 'Azure Functions'
        assert AZURE_SERVICE_MAPPING['cosmos'] == 'Cosmos DB'
        assert AZURE_SERVICE_MAPPING['aks'] == 'AKS'
        assert AZURE_SERVICE_MAPPING['kubernetes'] == 'AKS'

    def test_gcp_mapping_has_core_services(self):
        assert GCP_SERVICE_MAPPING['compute'] == 'Compute Engine'
        assert GCP_SERVICE_MAPPING['vm'] == 'Compute Engine'
        assert GCP_SERVICE_MAPPING['gcs'] == 'Cloud Storage'
        assert GCP_SERVICE_MAPPING['cloud sql'] == 'Cloud SQL'
        assert GCP_SERVICE_MAPPING['bigquery'] == 'BigQuery'
        assert GCP_SERVICE_MAPPING['gke'] == 'GKE'
        assert GCP_SERVICE_MAPPING['kubernetes'] == 'GKE'

    def test_all_mappings_include_general_keywords(self):
        for provider, mapping in PROVIDER_MAPPINGS.items():
            assert mapping.get('general') == 'General', f"{provider} missing 'general' -> 'General'"
            assert mapping.get('cost') == 'General', f"{provider} missing 'cost' -> 'General'"
            assert mapping.get('billing') == 'General', f"{provider} missing 'billing' -> 'General'"

    def test_get_service_mapping_returns_correct_mapping(self):
        assert _get_service_mapping('aws') is AWS_SERVICE_MAPPING
        assert _get_service_mapping('azure') is AZURE_SERVICE_MAPPING
        assert _get_service_mapping('gcp') is GCP_SERVICE_MAPPING

    def test_get_service_mapping_defaults_to_aws_for_unknown(self):
        assert _get_service_mapping('unknown') is AWS_SERVICE_MAPPING
        assert _get_service_mapping('') is AWS_SERVICE_MAPPING


# ============================================================
# Test: _search_tips with provider parameter
# ============================================================

class TestSearchTipsWithProvider:
    """Test _search_tips uses provider-specific mappings."""

    def test_aws_provider_uses_aws_mapping(self):
        ec2_tips = [_make_tip('ec2-001', 'EC2'), _make_tip('ec2-002', 'EC2')]
        general_tips = [_make_tip('gen-001', 'General')]
        mock_table = _make_mock_table({
            'EC2': ec2_tips,
            'General': general_tips,
            'AI-GENERATED': [],
        })

        result = _search_tips('How can I reduce EC2 costs?', provider='aws', tips_table=mock_table)
        tip_ids = [t['tipId'] for t in result]
        assert 'ec2-001' in tip_ids
        assert 'gen-001' in tip_ids

    def test_azure_provider_uses_azure_mapping(self):
        vm_tips = [_make_tip('azure-vm-001', 'Virtual Machines')]
        general_tips = [_make_tip('gen-001', 'General')]
        mock_table = _make_mock_table({
            'Virtual Machines': vm_tips,
            'General': general_tips,
            'AI-GENERATED': [],
        })

        result = _search_tips('How to optimize my VM costs?', provider='azure', tips_table=mock_table)
        tip_ids = [t['tipId'] for t in result]
        assert 'azure-vm-001' in tip_ids
        assert 'gen-001' in tip_ids

    def test_gcp_provider_uses_gcp_mapping(self):
        compute_tips = [_make_tip('gcp-compute-001', 'Compute Engine')]
        general_tips = [_make_tip('gen-001', 'General')]
        mock_table = _make_mock_table({
            'Compute Engine': compute_tips,
            'General': general_tips,
            'AI-GENERATED': [],
        })

        result = _search_tips('How to reduce compute costs?', provider='gcp', tips_table=mock_table)
        tip_ids = [t['tipId'] for t in result]
        assert 'gcp-compute-001' in tip_ids
        assert 'gen-001' in tip_ids

    def test_general_tips_always_included(self):
        """General tips are returned regardless of provider, even with no keyword match."""
        general_tips = [_make_tip('gen-001', 'General')]
        mock_table = _make_mock_table({
            'General': general_tips,
            'AI-GENERATED': [],
        })

        # Question with "cost" keyword maps to General in all providers
        result = _search_tips('What is my total cost?', provider='azure', tips_table=mock_table)
        tip_ids = [t['tipId'] for t in result]
        assert 'gen-001' in tip_ids

    def test_defaults_to_aws_when_no_provider(self):
        ec2_tips = [_make_tip('ec2-001', 'EC2')]
        general_tips = [_make_tip('gen-001', 'General')]
        mock_table = _make_mock_table({
            'EC2': ec2_tips,
            'General': general_tips,
            'AI-GENERATED': [],
        })

        # Default provider is 'aws'
        result = _search_tips('EC2 optimization', tips_table=mock_table)
        tip_ids = [t['tipId'] for t in result]
        assert 'ec2-001' in tip_ids


# ============================================================
# Test: Deduplication
# ============================================================

class TestDeduplication:
    """Test tipId deduplication logic."""

    def test_removes_duplicate_tip_ids(self):
        tips = [
            _make_tip('tip-001', 'EC2'),
            _make_tip('tip-001', 'EC2'),  # duplicate
            _make_tip('tip-002', 'S3'),
        ]
        result = _deduplicate_tips(tips)
        assert len(result) == 2
        assert result[0]['tipId'] == 'tip-001'
        assert result[1]['tipId'] == 'tip-002'

    def test_keeps_first_occurrence_on_duplicate(self):
        tips = [
            _make_tip('tip-001', 'EC2', confidence='high-confidence'),
            _make_tip('tip-001', 'General', confidence='low'),
        ]
        result = _deduplicate_tips(tips)
        assert len(result) == 1
        assert result[0]['service'] == 'EC2'

    def test_tips_without_tip_id_always_included(self):
        tips = [
            {'service': 'EC2', 'title': 'No ID tip 1'},
            {'service': 'EC2', 'title': 'No ID tip 2'},
            _make_tip('tip-001', 'EC2'),
        ]
        result = _deduplicate_tips(tips)
        assert len(result) == 3

    def test_empty_list(self):
        assert _deduplicate_tips([]) == []


# ============================================================
# Test: merge_tips_multi_provider
# ============================================================

class TestMergeTipsMultiProvider:
    """Test multi-provider tip merging with deduplication."""

    def test_merges_tips_from_multiple_providers(self):
        aws_tips = [_make_tip('tip-001', 'EC2'), _make_tip('tip-002', 'S3')]
        azure_tips = [_make_tip('tip-003', 'Virtual Machines')]

        result = merge_tips_multi_provider({'aws': aws_tips, 'azure': azure_tips})
        tip_ids = [t['tipId'] for t in result]
        assert 'tip-001' in tip_ids
        assert 'tip-002' in tip_ids
        assert 'tip-003' in tip_ids

    def test_deduplicates_across_providers(self):
        """Same tipId from different providers is deduplicated."""
        aws_tips = [_make_tip('gen-001', 'General')]
        azure_tips = [_make_tip('gen-001', 'General')]  # same tip
        gcp_tips = [_make_tip('gen-001', 'General')]  # same tip again

        result = merge_tips_multi_provider({
            'aws': aws_tips,
            'azure': azure_tips,
            'gcp': gcp_tips,
        })
        assert len(result) == 1
        assert result[0]['tipId'] == 'gen-001'

    def test_respects_max_10_limit(self):
        many_tips = [_make_tip(f'tip-{i:03d}', 'EC2') for i in range(15)]
        result = merge_tips_multi_provider({'aws': many_tips})
        assert len(result) <= 10

    def test_empty_providers(self):
        result = merge_tips_multi_provider({'aws': [], 'azure': []})
        assert result == []


# ============================================================
# Test: Cache interaction with provider filtering
# ============================================================

class TestCacheWithProviderFiltering:
    """Test that cached tips are filtered by provider mappings."""

    def test_cached_tips_are_filtered_by_question(self):
        cached = [
            _make_tip('vm-001', 'Virtual Machines'),
            _make_tip('sql-001', 'Azure SQL'),
            _make_tip('gen-001', 'General'),
        ]
        # Search for VM-related question
        result = _filter_cached_tips(cached, 'How to optimize my VM?', 'azure')
        tip_ids = [t['tipId'] for t in result]
        assert 'vm-001' in tip_ids
        assert 'gen-001' in tip_ids  # General always included

    def test_cached_general_always_included(self):
        cached = [
            _make_tip('vm-001', 'Virtual Machines'),
            _make_tip('gen-001', 'General'),
        ]
        # A question with "cost" keyword maps to General
        result = _filter_cached_tips(cached, 'What is my cost breakdown?', 'azure')
        tip_ids = [t['tipId'] for t in result]
        assert 'gen-001' in tip_ids

    def test_search_tips_uses_cache_on_second_call(self):
        """Second call to _search_tips should use cached results."""
        vm_tips = [_make_tip('vm-001', 'Virtual Machines')]
        general_tips = [_make_tip('gen-001', 'General')]
        mock_table = _make_mock_table({
            'Virtual Machines': vm_tips,
            'General': general_tips,
            'AI-GENERATED': [],
        })

        # First call — populates cache
        result1 = _search_tips('How to optimize my VM?', provider='azure', tips_table=mock_table)

        # Second call — should use cache (mock_table.query count doesn't increase)
        mock_table.query.reset_mock()
        result2 = _search_tips('How to optimize my VM?', provider='azure', tips_table=mock_table)

        # Cache should have been used, so no new queries
        mock_table.query.assert_not_called()
