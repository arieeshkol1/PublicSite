"""
Property-based and unit tests for the migration script.
"""

import copy

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from schema_sync.migrate_service_ids import (
    migrate_tips_table,
    LEGACY_SERVICE_KEY_MAP,
)
from schema_sync.service_id import validate_service_id


# =============================================================================
# Hypothesis strategies
# =============================================================================

known_service_key = st.sampled_from(list(LEGACY_SERVICE_KEY_MAP.keys()))
unknown_service_key = st.text(min_size=3, max_size=30).filter(
    lambda s: s not in LEGACY_SERVICE_KEY_MAP
)

record_with_known_key = st.fixed_dictionaries(
    {
        "id": st.from_regex(r"[a-z]{2,5}-[0-9]{3}", fullmatch=True),
        "service": st.just("EC2"),
        "serviceKey": known_service_key,
        "title": st.text(min_size=1, max_size=30),
    }
)

record_with_unknown_key = st.fixed_dictionaries(
    {
        "id": st.from_regex(r"[a-z]{2,5}-[0-9]{3}", fullmatch=True),
        "service": st.just("Unknown"),
        "serviceKey": unknown_service_key,
        "title": st.text(min_size=1, max_size=30),
    }
)

record_already_migrated = st.fixed_dictionaries(
    {
        "id": st.from_regex(r"[a-z]{2,5}-[0-9]{3}", fullmatch=True),
        "service": st.just("EC2"),
        "serviceKey": known_service_key,
        "serviceId": st.just("aws:ec2"),
        "title": st.text(min_size=1, max_size=30),
    }
)

any_record = st.one_of(
    record_with_known_key, record_with_unknown_key, record_already_migrated
)


# =============================================================================
# Feature: tips-driven-schema-sync, Property 7: Migration Idempotence
# =============================================================================


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(any_record, min_size=0, max_size=10))
def test_property_migration_idempotence(records):
    """Property 7: migrate(migrate(records)) == migrate(records)."""
    # First migration
    records_copy1 = copy.deepcopy(records)
    migrate_tips_table(records_copy1)

    # Second migration on already-migrated records
    records_copy2 = copy.deepcopy(records_copy1)
    migrate_tips_table(records_copy2)

    # Results should be identical
    assert records_copy1 == records_copy2


# =============================================================================
# Feature: tips-driven-schema-sync, Property 8: Migration Preserves Legacy Fields
# =============================================================================


@settings(max_examples=100)
@given(st.lists(any_record, min_size=1, max_size=15))
def test_property_migration_preserves_legacy_and_maps(records):
    """Property 8: Migration preserves serviceKey and maps to correct serviceId."""
    original = copy.deepcopy(records)
    migrate_tips_table(records)

    for orig, migrated in zip(original, records):
        service_key = orig.get("serviceKey")

        # serviceKey must ALWAYS be preserved
        assert migrated.get("serviceKey") == service_key

        if service_key in LEGACY_SERVICE_KEY_MAP and not orig.get("serviceId"):
            # Should have been mapped
            expected_id = LEGACY_SERVICE_KEY_MAP[service_key]
            assert migrated["serviceId"] == expected_id
            assert validate_service_id(migrated["serviceId"])
        elif service_key not in LEGACY_SERVICE_KEY_MAP and not orig.get("serviceId"):
            # Should remain unchanged (no serviceId added)
            assert "serviceId" not in migrated


# =============================================================================
# Unit Tests
# =============================================================================


class TestMigrateTipsTable:
    """Unit tests for migrate_tips_table."""

    def test_known_service_key_gets_mapped(self):
        records = [
            {"id": "ec2-001", "service": "EC2", "serviceKey": "Amazon EC2", "title": "Tip"}
        ]
        result = migrate_tips_table(records)
        assert result["migrated"] == 1
        assert records[0]["serviceId"] == "aws:ec2"
        assert records[0]["serviceKey"] == "Amazon EC2"

    def test_unknown_service_key_is_skipped(self):
        records = [
            {"id": "unk-001", "service": "X", "serviceKey": "Unknown Cloud", "title": "Tip"}
        ]
        result = migrate_tips_table(records)
        assert result["skipped"] == 1
        assert "serviceId" not in records[0]

    def test_already_migrated_is_skipped(self):
        records = [
            {
                "id": "ec2-001",
                "service": "EC2",
                "serviceKey": "Amazon EC2",
                "serviceId": "aws:ec2",
                "title": "Tip",
            }
        ]
        result = migrate_tips_table(records)
        assert result["skipped"] == 1

    def test_summary_counts(self):
        records = [
            {"id": "ec2-001", "service": "EC2", "serviceKey": "Amazon EC2", "title": "1"},
            {"id": "s3-001", "service": "S3", "serviceKey": "Amazon S3", "title": "2"},
            {"id": "unk-001", "service": "X", "serviceKey": "Unknown", "title": "3"},
            {
                "id": "rds-001",
                "service": "RDS",
                "serviceKey": "Amazon RDS",
                "serviceId": "aws:rds",
                "title": "4",
            },
        ]
        result = migrate_tips_table(records)
        assert result["total"] == 4
        assert result["migrated"] == 2
        assert result["skipped"] == 2

    def test_empty_records(self):
        result = migrate_tips_table([])
        assert result == {"migrated": 0, "skipped": 0, "total": 0}

    def test_record_without_service_key(self):
        records = [{"id": "x-001", "service": "X", "title": "No key"}]
        result = migrate_tips_table(records)
        assert result["skipped"] == 1
