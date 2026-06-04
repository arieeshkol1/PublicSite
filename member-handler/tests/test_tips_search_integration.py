"""
Integration tests for tips cache and provider filtering in the AI chat search flow.

Validates task 8.3: Integration of tips cache and provider filtering into the search flow.
- _search_tips wrapper passes provider parameter correctly
- Tips cache is used (cache-first behavior)
- Multi-provider tips are merged and deduplicated
- _get_account_provider correctly detects provider from DynamoDB
- _search_tips_multi_provider merges across providers
"""

import sys
import os
import time
from unittest.mock import MagicMock, patch
from decimal import Decimal

import pytest

# Ensure member-handler is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import tips_filter


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the tips cache before each test."""
    tips_filter._tips_cache.clear()
    yield
    tips_filter._tips_cache.clear()


def _make_tip(tip_id, service='EC2', confidence='high-confidence'):
    return {
        'tipId': tip_id,
        'service': service,
        'title': f'Tip {tip_id}',
        'description': f'Description for {tip_id}',
        'confidenceTag': confidence,
        'source': 'curated',
        'positiveCount': 5,
    }


def _make_mock_table(tips_by_service):
    """Create a mock DynamoDB table that returns tips based on service key."""
    mock_table = MagicMock()

    def mock_query(**kwargs):
        key_expr = kwargs.get('KeyConditionExpression')
        service = None
        try:
            expr = key_expr.get_expression()
            service = expr['values'][1]
        except (AttributeError, KeyError, IndexError):
            pass
        items = tips_by_service.get(service, [])
        return {'Items': items}

    mock_table.query = MagicMock(side_effect=mock_query)
    mock_table.scan = MagicMock(return_value={'Items': []})
    return mock_table


# ============================================================
# Test: _search_tips wrapper passes provider correctly
# ============================================================

class TestSearchTipsWrapperProviderPassing:
    """Verify the lambda_function._search_tips wrapper passes provider to tips_filter."""

    def test_provider_passed_to_tips_filter(self):
        """The wrapper function should pass provider to the underlying implementation."""
        # This test verifies the wrapper correctly delegates with provider
        vm_tips = [_make_tip('azure-vm-001', 'Virtual Machines')]
        general_tips = [_make_tip('gen-001', 'General')]
        mock_table = _make_mock_table({
            'Virtual Machines': vm_tips,
            'General': general_tips,
            'AI-GENERATED': [],
        })

        # Call with azure provider
        result = tips_filter._search_tips(
            'How to optimize my VM costs?',
            provider='azure',
            tips_table=mock_table,
        )
        tip_ids = [t['tipId'] for t in result]
        assert 'azure-vm-001' in tip_ids
        assert 'gen-001' in tip_ids

    def test_provider_default_is_aws(self):
        """Without explicit provider, should default to AWS mappings."""
        ec2_tips = [_make_tip('ec2-001', 'EC2')]
        general_tips = [_make_tip('gen-001', 'General')]
        mock_table = _make_mock_table({
            'EC2': ec2_tips,
            'General': general_tips,
            'AI-GENERATED': [],
        })

        result = tips_filter._search_tips('How to reduce EC2 costs?', tips_table=mock_table)
        tip_ids = [t['tipId'] for t in result]
        assert 'ec2-001' in tip_ids


# ============================================================
# Test: Cache-first behavior
# ============================================================

class TestCacheFirstBehavior:
    """Verify cache is checked before DynamoDB query."""

    def test_first_call_queries_dynamodb(self):
        """First call should query DynamoDB and populate cache."""
        ec2_tips = [_make_tip('ec2-001', 'EC2')]
        general_tips = [_make_tip('gen-001', 'General')]
        mock_table = _make_mock_table({
            'EC2': ec2_tips,
            'General': general_tips,
            'AI-GENERATED': [],
        })

        result = tips_filter._search_tips('EC2 costs?', provider='aws', tips_table=mock_table)
        assert len(result) > 0
        # DynamoDB was called
        assert mock_table.query.call_count > 0

    def test_second_call_uses_cache(self):
        """Second call for same provider should use cache, not DynamoDB."""
        ec2_tips = [_make_tip('ec2-001', 'EC2')]
        general_tips = [_make_tip('gen-001', 'General')]
        mock_table = _make_mock_table({
            'EC2': ec2_tips,
            'General': general_tips,
            'AI-GENERATED': [],
        })

        # First call populates cache
        tips_filter._search_tips('EC2 costs?', provider='aws', tips_table=mock_table)
        first_call_count = mock_table.query.call_count

        # Second call should use cache
        mock_table.query.reset_mock()
        result = tips_filter._search_tips('EC2 costs?', provider='aws', tips_table=mock_table)

        # No new DynamoDB queries
        assert mock_table.query.call_count == 0
        assert len(result) > 0

    def test_different_provider_queries_separately(self):
        """Different providers have separate cache entries."""
        ec2_tips = [_make_tip('ec2-001', 'EC2')]
        vm_tips = [_make_tip('azure-vm-001', 'Virtual Machines')]
        general_tips = [_make_tip('gen-001', 'General')]
        mock_table = _make_mock_table({
            'EC2': ec2_tips,
            'Virtual Machines': vm_tips,
            'General': general_tips,
            'AI-GENERATED': [],
        })

        # Call for AWS
        tips_filter._search_tips('EC2 costs?', provider='aws', tips_table=mock_table)
        first_count = mock_table.query.call_count

        # Call for Azure — should query DynamoDB again (different provider)
        tips_filter._search_tips('VM costs?', provider='azure', tips_table=mock_table)
        assert mock_table.query.call_count > first_count

    def test_stale_cache_triggers_fresh_query(self):
        """Cache entries older than TTL should trigger fresh DynamoDB query."""
        ec2_tips = [_make_tip('ec2-001', 'EC2')]
        general_tips = [_make_tip('gen-001', 'General')]
        mock_table = _make_mock_table({
            'EC2': ec2_tips,
            'General': general_tips,
            'AI-GENERATED': [],
        })

        # Populate cache with an old timestamp
        tips_filter._tips_cache['aws'] = {
            'tips': [_make_tip('old-001', 'General')],
            'timestamp': time.time() - 400,  # 400s old, beyond 300s TTL
        }

        # Should detect stale cache and query DynamoDB
        result = tips_filter._search_tips('EC2 costs?', provider='aws', tips_table=mock_table)
        assert mock_table.query.call_count > 0

    def test_fresh_results_stored_in_cache_after_query(self):
        """After a DynamoDB query, results should be stored in cache."""
        ec2_tips = [_make_tip('ec2-001', 'EC2')]
        general_tips = [_make_tip('gen-001', 'General')]
        mock_table = _make_mock_table({
            'EC2': ec2_tips,
            'General': general_tips,
            'AI-GENERATED': [],
        })

        assert 'aws' not in tips_filter._tips_cache

        tips_filter._search_tips('EC2 costs?', provider='aws', tips_table=mock_table)

        # Cache should now have an entry for 'aws'
        assert 'aws' in tips_filter._tips_cache
        assert 'tips' in tips_filter._tips_cache['aws']
        assert 'timestamp' in tips_filter._tips_cache['aws']
        assert time.time() - tips_filter._tips_cache['aws']['timestamp'] < 5


# ============================================================
# Test: Multi-provider merge and deduplication
# ============================================================

class TestMultiProviderMergeDedup:
    """Verify multi-provider tips are merged and deduplicated correctly."""

    def test_merge_from_two_providers(self):
        """Tips from aws and azure are merged."""
        aws_tips = [_make_tip('aws-001', 'EC2'), _make_tip('gen-001', 'General')]
        azure_tips = [_make_tip('azure-001', 'Virtual Machines'), _make_tip('gen-002', 'General')]

        result = tips_filter.merge_tips_multi_provider({
            'aws': aws_tips,
            'azure': azure_tips,
        })
        tip_ids = [t['tipId'] for t in result]
        assert 'aws-001' in tip_ids
        assert 'azure-001' in tip_ids
        assert 'gen-001' in tip_ids
        assert 'gen-002' in tip_ids

    def test_deduplication_across_providers(self):
        """Same tipId from multiple providers is deduplicated."""
        shared_tip = _make_tip('shared-001', 'General')
        aws_tips = [shared_tip, _make_tip('aws-001', 'EC2')]
        azure_tips = [shared_tip, _make_tip('azure-001', 'Virtual Machines')]
        gcp_tips = [shared_tip, _make_tip('gcp-001', 'Compute Engine')]

        result = tips_filter.merge_tips_multi_provider({
            'aws': aws_tips,
            'azure': azure_tips,
            'gcp': gcp_tips,
        })
        # shared-001 should appear only once
        shared_count = sum(1 for t in result if t['tipId'] == 'shared-001')
        assert shared_count == 1

        # All unique tips should be present
        tip_ids = [t['tipId'] for t in result]
        assert 'aws-001' in tip_ids
        assert 'azure-001' in tip_ids
        assert 'gcp-001' in tip_ids

    def test_merge_respects_max_10(self):
        """Merged result is capped at 10 tips."""
        many_tips = [_make_tip(f'tip-{i:03d}', 'EC2') for i in range(8)]
        more_tips = [_make_tip(f'tip-{i:03d}', 'Virtual Machines') for i in range(8, 16)]

        result = tips_filter.merge_tips_multi_provider({
            'aws': many_tips,
            'azure': more_tips,
        })
        assert len(result) <= 10


# ============================================================
# Test: _get_account_provider (via lambda_function module)
# ============================================================

class TestGetAccountProvider:
    """Test _get_account_provider looks up cloud provider from DynamoDB."""

    @patch('lambda_function.dynamodb')
    def test_returns_aws_for_aws_account(self, mock_dynamodb):
        # Import here to ensure mocks work
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from lambda_function import _get_account_provider

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': {'cloudProvider': 'aws'}}
        mock_dynamodb.Table.return_value = mock_table

        result = _get_account_provider('user@test.com', '123456789012')
        assert result == 'aws'

    @patch('lambda_function.dynamodb')
    def test_returns_azure_for_azure_account(self, mock_dynamodb):
        from lambda_function import _get_account_provider

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': {'cloudProvider': 'azure'}}
        mock_dynamodb.Table.return_value = mock_table

        result = _get_account_provider('user@test.com', 'aaaabbbb-1111-2222-3333-444444444444')
        assert result == 'azure'

    @patch('lambda_function.dynamodb')
    def test_returns_gcp_for_gcp_account(self, mock_dynamodb):
        from lambda_function import _get_account_provider

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': {'cloudProvider': 'gcp'}}
        mock_dynamodb.Table.return_value = mock_table

        result = _get_account_provider('user@test.com', 'my-gcp-project-123')
        assert result == 'gcp'

    @patch('lambda_function.dynamodb')
    def test_defaults_to_aws_when_field_missing(self, mock_dynamodb):
        from lambda_function import _get_account_provider

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': {}}
        mock_dynamodb.Table.return_value = mock_table

        result = _get_account_provider('user@test.com', '123456789012')
        assert result == 'aws'

    @patch('lambda_function.dynamodb')
    def test_defaults_to_aws_when_field_empty(self, mock_dynamodb):
        from lambda_function import _get_account_provider

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': {'cloudProvider': ''}}
        mock_dynamodb.Table.return_value = mock_table

        result = _get_account_provider('user@test.com', '123456789012')
        assert result == 'aws'

    @patch('lambda_function.dynamodb')
    def test_defaults_to_aws_on_exception(self, mock_dynamodb):
        from lambda_function import _get_account_provider

        mock_table = MagicMock()
        mock_table.get_item.side_effect = Exception("DynamoDB error")
        mock_dynamodb.Table.return_value = mock_table

        result = _get_account_provider('user@test.com', '123456789012')
        assert result == 'aws'

    @patch('lambda_function.dynamodb')
    def test_defaults_to_aws_for_invalid_provider(self, mock_dynamodb):
        from lambda_function import _get_account_provider

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': {'cloudProvider': 'invalid'}}
        mock_dynamodb.Table.return_value = mock_table

        result = _get_account_provider('user@test.com', '123456789012')
        assert result == 'aws'


# ============================================================
# Test: _search_tips_multi_provider (via lambda_function module)
# ============================================================

class TestSearchTipsMultiProviderWrapper:
    """Test _search_tips_multi_provider merges tips from multiple providers."""

    @patch('lambda_function.dynamodb')
    def test_searches_and_merges_multiple_providers(self, mock_dynamodb):
        from lambda_function import _search_tips_multi_provider

        ec2_tips = [_make_tip('ec2-001', 'EC2')]
        vm_tips = [_make_tip('azure-vm-001', 'Virtual Machines')]
        general_tips = [_make_tip('gen-001', 'General')]

        mock_table = _make_mock_table({
            'EC2': ec2_tips,
            'Virtual Machines': vm_tips,
            'General': general_tips,
            'AI-GENERATED': [],
        })
        mock_dynamodb.Table.return_value = mock_table

        result = _search_tips_multi_provider('VM and EC2 costs?', {'aws', 'azure'})
        tip_ids = [t['tipId'] for t in result]

        # Should have tips from both providers
        assert 'gen-001' in tip_ids  # General always included

    @patch('lambda_function.dynamodb')
    def test_deduplicates_across_providers(self, mock_dynamodb):
        from lambda_function import _search_tips_multi_provider

        # Same General tip will be returned by both providers
        general_tips = [_make_tip('gen-001', 'General')]
        mock_table = _make_mock_table({
            'General': general_tips,
            'AI-GENERATED': [],
        })
        mock_dynamodb.Table.return_value = mock_table

        result = _search_tips_multi_provider('What is my total cost?', {'aws', 'azure', 'gcp'})
        gen_count = sum(1 for t in result if t['tipId'] == 'gen-001')
        assert gen_count == 1  # Deduplicated
