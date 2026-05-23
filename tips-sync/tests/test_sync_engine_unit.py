"""Unit tests for sync_engine module."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from sync_engine import merge_sources, compute_deltas, create_batches, apply_deltas
from models import compute_content_hash


class TestMergeSources:
    """Tests for merge_sources function."""

    def test_empty_sources(self):
        """Merging empty sources returns empty list."""
        result = merge_sources([], [], [])
        assert result == []

    def test_baseline_priority_over_coh(self):
        """Baseline tips take priority over COH tips with same ID."""
        baseline = [{"id": "ec2-001", "title": "Baseline Title", "service": "EC2"}]
        coh = [{"id": "ec2-001", "title": "COH Title", "service": "EC2"}]
        ta = []

        result = merge_sources(baseline, coh, ta)
        assert len(result) == 1
        assert result[0]["title"] == "Baseline Title"

    def test_baseline_priority_over_ta(self):
        """Baseline tips take priority over TA tips with same ID."""
        baseline = [{"id": "s3-001", "title": "Baseline", "service": "S3"}]
        coh = []
        ta = [{"id": "s3-001", "title": "TA Title", "service": "S3"}]

        result = merge_sources(baseline, coh, ta)
        assert len(result) == 1
        assert result[0]["title"] == "Baseline"

    def test_coh_priority_over_ta(self):
        """COH tips take priority over TA tips with same ID."""
        baseline = []
        coh = [{"id": "rds-001", "title": "COH Title", "service": "RDS"}]
        ta = [{"id": "rds-001", "title": "TA Title", "service": "RDS"}]

        result = merge_sources(baseline, coh, ta)
        assert len(result) == 1
        assert result[0]["title"] == "COH Title"

    def test_unique_tips_from_all_sources(self):
        """Tips with unique IDs from all sources are all included."""
        baseline = [{"id": "ec2-001", "title": "B1", "service": "EC2"}]
        coh = [{"id": "s3-001", "title": "C1", "service": "S3"}]
        ta = [{"id": "rds-001", "title": "T1", "service": "RDS"}]

        result = merge_sources(baseline, coh, ta)
        assert len(result) == 3
        ids = {t["id"] for t in result}
        assert ids == {"ec2-001", "s3-001", "rds-001"}

    def test_tips_without_id_are_skipped(self):
        """Tips without an 'id' field are excluded from merge."""
        baseline = [{"id": "ec2-001", "title": "B1", "service": "EC2"}]
        coh = [{"title": "No ID", "service": "S3"}]
        ta = [{"id": "", "title": "Empty ID", "service": "RDS"}]

        result = merge_sources(baseline, coh, ta)
        assert len(result) == 1
        assert result[0]["id"] == "ec2-001"


class TestComputeDeltas:
    """Tests for compute_deltas function."""

    def test_new_tip_classified_as_insert(self):
        """A tip with an ID not in existing_tips is classified as insert."""
        merged = [
            {
                "id": "ec2-001",
                "title": "T",
                "description": "D",
                "estimatedSavings": "10%",
                "automatedCheck": "AC",
                "service": "EC2",
            }
        ]
        existing = {}

        inserts, updates, unchanged = compute_deltas(merged, existing)
        assert len(inserts) == 1
        assert len(updates) == 0
        assert unchanged == 0
        assert inserts[0]["id"] == "ec2-001"

    def test_unchanged_tip_is_skipped(self):
        """A tip with matching content hash is classified as unchanged."""
        content_hash = compute_content_hash("T", "D", "10%", "AC")
        merged = [
            {
                "id": "ec2-001",
                "title": "T",
                "description": "D",
                "estimatedSavings": "10%",
                "automatedCheck": "AC",
                "service": "EC2",
            }
        ]
        existing = {
            "ec2-001": {
                "id": "ec2-001",
                "title": "T",
                "description": "D",
                "estimatedSavings": "10%",
                "automatedCheck": "AC",
                "contentHash": content_hash,
                "service": "EC2",
                "actionType": "advisory",
                "version": 1,
            }
        }

        inserts, updates, unchanged = compute_deltas(merged, existing)
        assert len(inserts) == 0
        assert len(updates) == 0
        assert unchanged == 1

    def test_changed_tip_classified_as_update(self):
        """A tip with different content hash is classified as update."""
        old_hash = compute_content_hash("Old Title", "D", "10%", "AC")
        merged = [
            {
                "id": "ec2-001",
                "title": "New Title",
                "description": "D",
                "estimatedSavings": "10%",
                "automatedCheck": "AC",
                "service": "EC2",
                "syncSource": "cost-optimization-hub",
                "lastSyncedAt": "2024-01-01T00:00:00Z",
            }
        ]
        existing = {
            "ec2-001": {
                "id": "ec2-001",
                "title": "Old Title",
                "description": "D",
                "estimatedSavings": "10%",
                "automatedCheck": "AC",
                "contentHash": old_hash,
                "service": "EC2",
                "actionType": "deep-link",
                "actionLabel": "Fix Now",
                "level": 2,
                "checkImplemented": True,
                "version": 3,
            }
        }

        inserts, updates, unchanged = compute_deltas(merged, existing)
        assert len(inserts) == 0
        assert len(updates) == 1
        assert unchanged == 0

        # Verify operational fields are preserved
        updated = updates[0]
        assert updated["title"] == "New Title"
        assert updated["actionType"] == "deep-link"
        assert updated["actionLabel"] == "Fix Now"
        assert updated["level"] == 2
        assert updated["checkImplemented"] is True
        assert updated["version"] == 3

    def test_no_deletes(self):
        """Existing tips not in merged list are not affected (no-delete invariant)."""
        merged = [
            {
                "id": "ec2-001",
                "title": "T",
                "description": "D",
                "estimatedSavings": "10%",
                "automatedCheck": "AC",
                "service": "EC2",
            }
        ]
        existing = {
            "ec2-001": {
                "id": "ec2-001",
                "contentHash": compute_content_hash("T", "D", "10%", "AC"),
            },
            "s3-001": {"id": "s3-001", "contentHash": "abc123"},
        }

        inserts, updates, unchanged = compute_deltas(merged, existing)
        # s3-001 is not in merged, but it's not deleted either
        assert len(inserts) == 0
        assert len(updates) == 0
        assert unchanged == 1


class TestCreateBatches:
    """Tests for create_batches helper."""

    def test_empty_list(self):
        """Empty list returns empty batches."""
        assert create_batches([]) == []

    def test_less_than_batch_size(self):
        """List smaller than batch size returns single batch."""
        items = list(range(10))
        batches = create_batches(items, batch_size=25)
        assert len(batches) == 1
        assert batches[0] == items

    def test_exact_batch_size(self):
        """List exactly batch size returns single batch."""
        items = list(range(25))
        batches = create_batches(items, batch_size=25)
        assert len(batches) == 1
        assert len(batches[0]) == 25

    def test_multiple_batches(self):
        """List larger than batch size is split correctly."""
        items = list(range(60))
        batches = create_batches(items, batch_size=25)
        assert len(batches) == 3
        assert len(batches[0]) == 25
        assert len(batches[1]) == 25
        assert len(batches[2]) == 10

    def test_max_batch_size_constraint(self):
        """No batch exceeds the specified batch_size."""
        items = list(range(100))
        batches = create_batches(items, batch_size=25)
        for batch in batches:
            assert len(batch) <= 25


class TestApplyDeltas:
    """Tests for apply_deltas function."""

    def test_successful_inserts(self):
        """Inserts are written with conditional put."""
        table = MagicMock()
        table.put_item = MagicMock(return_value={})

        inserts = [
            {"id": "ec2-001", "service": "EC2", "title": "T1"},
            {"id": "s3-001", "service": "S3", "title": "T2"},
        ]

        inserted, updated, conflicts = apply_deltas(table, inserts, [])
        assert inserted == 2
        assert updated == 0
        assert conflicts == []
        assert table.put_item.call_count == 2

    def test_successful_updates(self):
        """Updates are written with version condition."""
        table = MagicMock()
        table.put_item = MagicMock(return_value={})

        updates = [
            {"id": "ec2-001", "service": "EC2", "title": "Updated", "version": 2},
        ]

        inserted, updated, conflicts = apply_deltas(table, [], updates)
        assert inserted == 0
        assert updated == 1
        assert conflicts == []

    def test_insert_conflict_handled(self):
        """ConditionalCheckFailedException on insert is handled gracefully."""
        table = MagicMock()
        error_response = {"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}}
        table.put_item = MagicMock(
            side_effect=ClientError(error_response, "PutItem")
        )

        inserts = [{"id": "ec2-001", "service": "EC2", "title": "T1"}]

        inserted, updated, conflicts = apply_deltas(table, inserts, [])
        assert inserted == 0
        assert updated == 0
        assert conflicts == ["ec2-001"]

    def test_update_version_conflict_handled(self):
        """ConditionalCheckFailedException on update is handled gracefully."""
        table = MagicMock()
        error_response = {"Error": {"Code": "ConditionalCheckFailedException", "Message": "version"}}
        table.put_item = MagicMock(
            side_effect=ClientError(error_response, "PutItem")
        )

        updates = [{"id": "ec2-001", "service": "EC2", "title": "T1", "version": 1}]

        inserted, updated, conflicts = apply_deltas(table, [], updates)
        assert inserted == 0
        assert updated == 0
        assert conflicts == ["ec2-001"]

    @patch("sync_engine.time.sleep")
    def test_throttling_retries_with_backoff(self, mock_sleep):
        """Throttling errors trigger exponential backoff retry."""
        table = MagicMock()
        error_response = {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "throttled"}}
        # Fail twice, then succeed
        table.put_item = MagicMock(
            side_effect=[
                ClientError(error_response, "PutItem"),
                ClientError(error_response, "PutItem"),
                {},
            ]
        )

        inserts = [{"id": "ec2-001", "service": "EC2", "title": "T1"}]

        inserted, updated, conflicts = apply_deltas(table, inserts, [])
        assert inserted == 1
        assert mock_sleep.call_count == 2
        # First retry: 100ms, second retry: 200ms
        mock_sleep.assert_any_call(0.1)
        mock_sleep.assert_any_call(0.2)

    @patch("sync_engine.time.sleep")
    def test_throttling_exhausts_retries(self, mock_sleep):
        """After max retries, throttled item is skipped (not a conflict)."""
        table = MagicMock()
        error_response = {"Error": {"Code": "ThrottlingException", "Message": "throttled"}}
        table.put_item = MagicMock(
            side_effect=ClientError(error_response, "PutItem")
        )

        inserts = [{"id": "ec2-001", "service": "EC2", "title": "T1"}]

        inserted, updated, conflicts = apply_deltas(table, inserts, [])
        assert inserted == 0
        assert conflicts == []  # Throttle exhaustion is not a conflict
        assert table.put_item.call_count == 3  # 3 attempts

    def test_batching_applied(self):
        """Items are processed in batches of max 25."""
        table = MagicMock()
        table.put_item = MagicMock(return_value={})

        # Create 30 inserts
        inserts = [{"id": f"ec2-{i:03d}", "service": "EC2", "title": f"T{i}"} for i in range(30)]

        inserted, updated, conflicts = apply_deltas(table, inserts, [])
        assert inserted == 30
        assert table.put_item.call_count == 30
