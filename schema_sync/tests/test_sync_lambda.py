"""
Unit tests for the Sync Lambda orchestrator.
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from schema_sync.sync_lambda import (
    lambda_handler,
    _is_tool_relevant_event,
    _handle_sync,
)


class TestIsToolRelevantEvent:
    """Tests for _is_tool_relevant_event."""

    def test_insert_with_tool_definition(self):
        record = {
            "eventName": "INSERT",
            "dynamodb": {
                "NewImage": {"toolDefinition": {"M": {}}},
            },
        }
        assert _is_tool_relevant_event(record) is True

    def test_insert_without_tool_definition(self):
        record = {
            "eventName": "INSERT",
            "dynamodb": {"NewImage": {"title": {"S": "Just a tip"}}},
        }
        assert _is_tool_relevant_event(record) is False

    def test_modify_with_tool_definition(self):
        record = {
            "eventName": "MODIFY",
            "dynamodb": {
                "NewImage": {"toolDefinition": {"M": {}}},
                "OldImage": {},
            },
        }
        assert _is_tool_relevant_event(record) is True

    def test_remove_with_tool_definition(self):
        record = {
            "eventName": "REMOVE",
            "dynamodb": {"OldImage": {"toolDefinition": {"M": {}}}},
        }
        assert _is_tool_relevant_event(record) is True

    def test_remove_without_tool_definition(self):
        record = {
            "eventName": "REMOVE",
            "dynamodb": {"OldImage": {"title": {"S": "Just a tip"}}},
        }
        assert _is_tool_relevant_event(record) is False


class TestLambdaHandlerDryRun:
    """Tests for dryRun mode."""

    @patch("schema_sync.sync_lambda.check_backward_compatibility", return_value=[])
    @patch("schema_sync.sync_lambda.boto3")
    def test_dry_run_returns_schema_without_push(self, mock_boto3, mock_compat):
        """dryRun mode generates schema and returns it without Bedrock push."""
        # Mock DynamoDB scan
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [
                {
                    "service": "EC2",
                    "id": "ec2-001",
                    "serviceId": "aws:ec2",
                    "toolDefinition": {
                        "operationId": "getEC2Instances",
                        "path": "/get-ec2-instances",
                        "httpMethod": "POST",
                        "provider": "aws",
                        "summary": "List EC2",
                        "description": "Lists EC2",
                        "parameters": [
                            {
                                "name": "accountId",
                                "in": "query",
                                "type": "string",
                                "required": True,
                                "description": "AWS account ID",
                            }
                        ],
                    },
                }
            ]
        }
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        # Mock S3 for diff computation
        mock_s3 = MagicMock()
        mock_s3.get_object.side_effect = Exception("No existing schema")
        mock_boto3.client.return_value = mock_s3

        # Mock get_item for metadata
        mock_table.get_item.return_value = {"Item": {"currentVersion": 1}}

        result = _handle_sync(dry_run=True)

        assert result["dryRun"] is True
        assert "schema" in result
        assert result["operationCount"] >= 1

    @patch("schema_sync.sync_lambda.boto3")
    def test_validation_failure_aborts_push(self, mock_boto3):
        """If schema validation fails, no push happens."""
        # Mock DynamoDB scan returning invalid data that passes generation
        # but would fail backward compat
        mock_table = MagicMock()
        mock_table.scan.return_value = {"Items": []}
        mock_table.get_item.return_value = {"Item": {"currentVersion": 0}}
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_boto3.resource.return_value = mock_dynamodb

        result = _handle_sync(dry_run=False)

        # Should fail backward compatibility (no operations present)
        assert result["statusCode"] == 400
        assert "Missing" in result.get("body", "") or "Backward" in result.get("body", "")


class TestLambdaHandlerStreamEvents:
    """Tests for DynamoDB Stream event handling."""

    @patch("schema_sync.sync_lambda._handle_sync")
    def test_irrelevant_stream_event_skipped(self, mock_sync):
        """Stream events without toolDefinition changes are skipped."""
        event = {
            "Records": [
                {
                    "eventName": "MODIFY",
                    "dynamodb": {
                        "NewImage": {"title": {"S": "Updated title"}},
                        "OldImage": {"title": {"S": "Old title"}},
                    },
                }
            ]
        }
        result = lambda_handler(event, None)
        assert result["statusCode"] == 200
        assert "No relevant changes" in result["body"]
        mock_sync.assert_not_called()

    @patch("schema_sync.sync_lambda._handle_sync")
    def test_relevant_stream_event_triggers_sync(self, mock_sync):
        """Stream events with toolDefinition trigger sync."""
        mock_sync.return_value = {"statusCode": 200}
        event = {
            "Records": [
                {
                    "eventName": "INSERT",
                    "dynamodb": {
                        "NewImage": {"toolDefinition": {"M": {}}},
                    },
                }
            ]
        }
        result = lambda_handler(event, None)
        mock_sync.assert_called_once_with(dry_run=False)
