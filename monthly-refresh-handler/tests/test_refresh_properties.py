"""Property-based tests for the Monthly Refresh Job.

Covers design Properties 18 (resilience + count invariant) and 19
(idempotence). DynamoDB, Cost Explorer, and per-account refresh are mocked.
"""

import os
import sys
from unittest.mock import patch, MagicMock

from hypothesis import given, settings, strategies as st

_HERE = os.path.dirname(__file__)
# member-handler holds invoice_drilldown / invoice_forecast imported by the handler
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, '..', '..', 'member-handler')))
# the monthly handler dir must precede member-handler so its lambda_function wins
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, '..')))

import lambda_function as mr  # noqa: E402

RUNS = 100


def _accounts(n):
    return [{'memberEmail': f'user{i}@e.com', 'accountId': f'{i:012d}',
             'cloudProvider': 'aws'} for i in range(n)]


# ─── Property 18: resilience + count invariant ────────────────────────────────

@given(
    n=st.integers(min_value=0, max_value=20),
    fail_idxs=st.sets(st.integers(min_value=0, max_value=19), max_size=20),
)
@settings(max_examples=RUNS, deadline=None)
def test_property18_count_invariant(n, fail_idxs):
    accounts = _accounts(n)
    fail = {i for i in fail_idxs if i < n}

    def fake_refresh(member_email, account_id, provider_key, now):
        idx = int(account_id)
        if idx in fail:
            raise RuntimeError('boom')
        return {'accountId': account_id, 'status': 'succeeded'}

    mock_table = MagicMock()
    mock_table.scan.return_value = {'Items': accounts}

    with patch.object(mr.dynamodb, 'Table', return_value=mock_table), \
         patch.object(mr, '_refresh_account_monthly', side_effect=fake_refresh), \
         patch.object(mr.time, 'sleep'):
        result = mr.lambda_handler({}, None)

    summary = result['body']
    assert summary['processed'] == n
    assert summary['succeeded'] + summary['failed'] == summary['processed']
    assert summary['failed'] == len(fail)
    assert len(summary['failures']) == len(fail)


# ─── Property 19: idempotence (deterministic summary across repeated runs) ─────

@given(n=st.integers(min_value=0, max_value=15))
@settings(max_examples=RUNS, deadline=None)
def test_property19_summary_idempotent(n):
    accounts = _accounts(n)

    def fake_refresh(member_email, account_id, provider_key, now):
        return {'accountId': account_id, 'status': 'succeeded'}

    mock_table = MagicMock()
    mock_table.scan.return_value = {'Items': accounts}

    with patch.object(mr.dynamodb, 'Table', return_value=mock_table), \
         patch.object(mr, '_refresh_account_monthly', side_effect=fake_refresh), \
         patch.object(mr.time, 'sleep'):
        first = mr.lambda_handler({}, None)['body']
        second = mr.lambda_handler({}, None)['body']

    assert first == second


# ─── _build_run_summary unit coverage ─────────────────────────────────────────

def test_build_run_summary_shape():
    results = [
        {'accountId': '1', 'status': 'succeeded'},
        {'accountId': '2', 'status': 'failed', 'error': 'x'},
        {'accountId': '3', 'status': 'succeeded'},
    ]
    s = mr._build_run_summary(results)
    assert s == {
        'processed': 3,
        'succeeded': 2,
        'failed': 1,
        'failures': [{'accountId': '2', 'error': 'x'}],
    }
