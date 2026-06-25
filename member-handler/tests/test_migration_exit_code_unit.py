"""Unit test for the migration job's failure exit code.

Feature: vendor-agnostic-ai-usage, Task 10.3

A forced write failure must cause the migration to report the count of items
that failed to write and exit with a non-zero status (Req 9.5).
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'infrastructure'))

import migrate_openai_daily as mig  # noqa: E402


def _legacy_item():
    return {
        'pk': 'user@example.com#acct-123',
        'sk': f'{mig.LEGACY_SK_PREFIX}2025-06-01',
        'cost_amount': '10',
        'currency': 'USD',
        'service_breakdown': {'gpt-4o': 10.0},
        'token_breakdown': {'gpt-4o': {'input_tokens': 100, 'output_tokens': 50}},
        'fetched_at': '2025-06-02T03:00:00+00:00',
    }


class _AlwaysFailTable:
    """A table whose scan returns one legacy item but whose put_item raises."""

    def __init__(self, item):
        self._item = item

    def scan(self, FilterExpression=None, ExclusiveStartKey=None):  # noqa: N803
        return {'Items': [dict(self._item)]}

    def put_item(self, Item):  # noqa: N803
        raise RuntimeError('simulated DynamoDB write failure')


def test_migrate_counts_write_failures():
    """migrate() returns the number of failed writes (non-zero)."""
    table = _AlwaysFailTable(_legacy_item())
    failures = mig.migrate(table)
    # One legacy item -> one COST# rollup + one USAGE# detail, both fail.
    assert failures == 2


def test_migrate_failure_logs_failed_count(caplog):
    """put_overwrite logs each failed write so the count is observable."""
    table = _AlwaysFailTable(_legacy_item())
    with caplog.at_level(logging.ERROR, logger='migrate_openai_daily'):
        failures = mig.migrate(table)
    assert failures > 0
    assert any('Failed to write neutral item' in r.message for r in caplog.records)


def test_main_exits_non_zero_on_write_failure(monkeypatch):
    """main() returns a non-zero exit code and logs the failed count (Req 9.5)."""
    captured = {}

    class _FakeResource:
        def Table(self, name):  # noqa: N802 (boto3 method name)
            return _AlwaysFailTable(_legacy_item())

    import boto3
    monkeypatch.setattr(boto3, 'resource', lambda *a, **k: _FakeResource())

    errors = []
    monkeypatch.setattr(mig.logger, 'error',
                        lambda msg, *args, **kw: errors.append(msg % args if args else msg))

    exit_code = mig.main()
    assert exit_code != 0
    assert any('Migration failed for' in e for e in errors)


def test_main_exits_zero_on_success(monkeypatch):
    """main() returns 0 when every item writes successfully."""
    class _OkTable:
        def __init__(self):
            self.writes = 0

        def scan(self, FilterExpression=None, ExclusiveStartKey=None):  # noqa: N803
            return {'Items': [_legacy_item()]}

        def put_item(self, Item):  # noqa: N803
            self.writes += 1

    class _FakeResource:
        def Table(self, name):  # noqa: N802
            return _OkTable()

    import boto3
    monkeypatch.setattr(boto3, 'resource', lambda *a, **k: _FakeResource())

    assert mig.main() == 0
