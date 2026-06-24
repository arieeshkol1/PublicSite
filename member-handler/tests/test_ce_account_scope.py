"""Unit tests for ce_account_scope — Cost Explorer per-account scoping.

Verifies that CE queries are restricted to the connected account's
LINKED_ACCOUNT, so a payer/management-account connection never returns the
whole consolidated organization's costs.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ce_account_scope import (
    is_aws_account_id,
    linked_account_filter,
    merge_filters,
    apply_account_scope,
)

ACCT = '258894854541'


class TestIsAwsAccountId:
    def test_valid_12_digit(self):
        assert is_aws_account_id('123456789012') is True

    def test_rejects_non_aws(self):
        assert is_aws_account_id('my-gcp-project') is False
        assert is_aws_account_id('a1b2c3d4-1234-5678-9abc-def012345678') is False
        assert is_aws_account_id('') is False
        assert is_aws_account_id(None) is False

    def test_rejects_wrong_length(self):
        assert is_aws_account_id('1234') is False
        assert is_aws_account_id('1234567890123') is False


class TestApplyAccountScope:
    def test_adds_linked_account_filter(self):
        params = {'TimePeriod': {'Start': '2026-01-01', 'End': '2026-02-01'},
                  'Granularity': 'MONTHLY', 'Metrics': ['UnblendedCost']}
        out = apply_account_scope(params, ACCT)
        assert out['Filter'] == {'Dimensions': {'Key': 'LINKED_ACCOUNT', 'Values': [ACCT]}}
        # original is not mutated
        assert 'Filter' not in params

    def test_and_combines_with_existing_filter(self):
        existing = {'Dimensions': {'Key': 'SERVICE', 'Values': ['Amazon EC2']}}
        params = {'Granularity': 'MONTHLY', 'Filter': existing}
        out = apply_account_scope(params, ACCT)
        assert 'And' in out['Filter']
        keys = {f['Dimensions']['Key'] for f in out['Filter']['And']}
        assert keys == {'SERVICE', 'LINKED_ACCOUNT'}

    def test_appends_to_existing_and_list(self):
        existing = {'And': [{'Dimensions': {'Key': 'SERVICE', 'Values': ['X']}}]}
        out = apply_account_scope({'Filter': existing}, ACCT)
        assert len(out['Filter']['And']) == 2

    def test_noop_for_non_aws_account(self):
        params = {'Granularity': 'MONTHLY'}
        out = apply_account_scope(params, 'gcp-project-123')
        assert 'Filter' not in out

    def test_merge_filters_none(self):
        add = linked_account_filter(ACCT)
        assert merge_filters(None, add) == add
