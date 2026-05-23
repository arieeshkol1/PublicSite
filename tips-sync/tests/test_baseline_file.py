"""Unit tests for tips-sync/sources/baseline_file.py."""

import json
import os
import tempfile

import pytest

from sources.baseline_file import load_baseline_tips


class TestLoadBaselineTips:
    """Tests for load_baseline_tips function."""

    def test_loads_tips_from_valid_file(self, tmp_path):
        """Valid JSON file with tips returns the list of tip dicts."""
        tips_data = {
            "version": "1.0",
            "tips": [
                {
                    "id": "ec2-001",
                    "service": "EC2",
                    "category": "right-sizing",
                    "title": "Right-size EC2 instances",
                    "description": "Use Compute Optimizer",
                    "estimatedSavings": "20-40%",
                    "difficulty": "easy",
                    "automatedCheck": "compute-optimizer check",
                },
                {
                    "id": "s3-001",
                    "service": "S3",
                    "category": "storage-class",
                    "title": "Use S3 Intelligent-Tiering",
                    "description": "Automatically moves data",
                    "estimatedSavings": "10-30%",
                    "difficulty": "easy",
                    "automatedCheck": "s3 lifecycle check",
                },
            ],
        }
        file_path = tmp_path / "tips.json"
        file_path.write_text(json.dumps(tips_data), encoding="utf-8")

        result = load_baseline_tips(str(file_path))

        assert len(result) == 2
        assert result[0]["id"] == "ec2-001"
        assert result[1]["id"] == "s3-001"

    def test_marks_tips_with_baseline_sync_source(self, tmp_path):
        """Each tip is marked with syncSource='baseline'."""
        tips_data = {
            "tips": [
                {
                    "id": "ec2-001",
                    "service": "EC2",
                    "category": "right-sizing",
                    "title": "Test tip",
                    "description": "Desc",
                    "estimatedSavings": "10%",
                    "difficulty": "easy",
                    "automatedCheck": "check",
                }
            ]
        }
        file_path = tmp_path / "tips.json"
        file_path.write_text(json.dumps(tips_data), encoding="utf-8")

        result = load_baseline_tips(str(file_path))

        assert result[0]["syncSource"] == "baseline"

    def test_returns_empty_list_on_file_not_found(self):
        """FileNotFoundError returns empty list."""
        result = load_baseline_tips("/nonexistent/path/tips.json")

        assert result == []

    def test_returns_empty_list_on_invalid_json(self, tmp_path):
        """Malformed JSON returns empty list."""
        file_path = tmp_path / "bad.json"
        file_path.write_text("{ not valid json !!!", encoding="utf-8")

        result = load_baseline_tips(str(file_path))

        assert result == []

    def test_returns_empty_list_when_tips_key_missing(self, tmp_path):
        """JSON without 'tips' key returns empty list."""
        file_path = tmp_path / "no_tips.json"
        file_path.write_text(json.dumps({"version": "1.0"}), encoding="utf-8")

        result = load_baseline_tips(str(file_path))

        assert result == []

    def test_preserves_existing_tip_fields(self, tmp_path):
        """All existing fields in tip dicts are preserved."""
        tips_data = {
            "tips": [
                {
                    "id": "ec2-001",
                    "service": "EC2",
                    "category": "right-sizing",
                    "title": "Right-size",
                    "description": "Desc",
                    "estimatedSavings": "20%",
                    "difficulty": "easy",
                    "automatedCheck": "check",
                    "checkImplemented": True,
                    "actionType": "deep-link",
                    "actionLabel": "View",
                    "level": 2,
                    "serviceKey": "Amazon EC2",
                }
            ]
        }
        file_path = tmp_path / "tips.json"
        file_path.write_text(json.dumps(tips_data), encoding="utf-8")

        result = load_baseline_tips(str(file_path))

        assert result[0]["checkImplemented"] is True
        assert result[0]["actionType"] == "deep-link"
        assert result[0]["level"] == 2
        assert result[0]["serviceKey"] == "Amazon EC2"
