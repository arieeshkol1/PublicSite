"""Unit tests for bedrock_client.py — mocked AWS services."""
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from bedrock_client import (
    analyze_bill,
    _get_optimization_tips,
    _build_prompt,
    _invoke_bedrock,
    _parse_analysis_response,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PARSED_BILL = {
    "invoice_number": "EUINIL26-139120",
    "account_id": "845760127781",
    "period_start": "2026-02-01",
    "period_end": "2026-02-28",
    "currency": "USD",
    "total_cost": Decimal("123.45"),
    "line_items": [
        {"service": "Amazon EC2", "cost": Decimal("80.00"), "description": "Running instances"},
        {"service": "Amazon S3", "cost": Decimal("43.45"), "description": "Storage"},
    ],
    "service_totals": {
        "Amazon EC2": Decimal("80.00"),
        "Amazon S3": Decimal("43.45"),
    },
}

VALID_ANALYSIS_JSON = json.dumps({
    "summary": "Your total bill is $123.45. EC2 is the top spender.",
    "explanations": [
        {"service": "Amazon EC2", "cost": "$80.00", "explanation": "Running instances in us-east-1."},
        {"service": "Amazon S3", "cost": "$43.45", "explanation": "Object storage costs."},
    ],
    "recommendations": [
        {
            "title": "Right-size EC2",
            "description": "Use Compute Optimizer to find savings.",
            "estimated_savings": "20-40%",
            "difficulty": "easy",
        },
    ],
})

SAMPLE_TIPS = [
    {
        "service": "EC2",
        "tipId": "ec2-001",
        "category": "right-sizing",
        "title": "Right-size EC2 instances",
        "description": "Use Compute Optimizer.",
        "estimatedSavings": "20-40%",
        "difficulty": "easy",
    },
    {
        "service": "General",
        "tipId": "general-001",
        "category": "monitoring",
        "title": "Enable Cost Explorer",
        "description": "Track spending trends.",
        "estimatedSavings": "5-15%",
        "difficulty": "easy",
    },
]


# ---------------------------------------------------------------------------
# _parse_analysis_response tests
# ---------------------------------------------------------------------------

class TestParseAnalysisResponse:
    """Test JSON parsing and validation of Bedrock responses."""

    def test_valid_json_parsed(self):
        result = _parse_analysis_response(VALID_ANALYSIS_JSON)
        assert result["summary"] == "Your total bill is $123.45. EC2 is the top spender."
        assert len(result["explanations"]) == 2
        assert len(result["recommendations"]) == 1

    def test_json_wrapped_in_code_fence(self):
        wrapped = f"```json\n{VALID_ANALYSIS_JSON}\n```"
        result = _parse_analysis_response(wrapped)
        assert "summary" in result

    def test_json_wrapped_in_plain_code_fence(self):
        wrapped = f"```\n{VALID_ANALYSIS_JSON}\n```"
        result = _parse_analysis_response(wrapped)
        assert "summary" in result

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            _parse_analysis_response("this is not json at all")

    def test_missing_summary_raises_value_error(self):
        bad = json.dumps({"explanations": [], "recommendations": []})
        with pytest.raises(ValueError, match="summary"):
            _parse_analysis_response(bad)

    def test_missing_explanations_raises_value_error(self):
        bad = json.dumps({"summary": "ok", "recommendations": []})
        with pytest.raises(ValueError, match="explanations"):
            _parse_analysis_response(bad)

    def test_missing_recommendations_raises_value_error(self):
        bad = json.dumps({"summary": "ok", "explanations": []})
        with pytest.raises(ValueError, match="recommendations"):
            _parse_analysis_response(bad)

    def test_explanation_missing_field_raises_value_error(self):
        bad = json.dumps({
            "summary": "ok",
            "explanations": [{"service": "EC2", "cost": "$10"}],  # missing 'explanation'
            "recommendations": [],
        })
        with pytest.raises(ValueError, match="explanation"):
            _parse_analysis_response(bad)

    def test_recommendation_missing_field_raises_value_error(self):
        bad = json.dumps({
            "summary": "ok",
            "explanations": [],
            "recommendations": [{"title": "Save", "description": "Do stuff"}],  # missing estimated_savings
        })
        with pytest.raises(ValueError, match="estimated_savings"):
            _parse_analysis_response(bad)

    def test_non_dict_json_raises_value_error(self):
        with pytest.raises(ValueError, match="not a JSON object"):
            _parse_analysis_response("[1, 2, 3]")


# ---------------------------------------------------------------------------
# _build_prompt tests
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    """Test prompt construction."""

    def test_includes_bill_data(self):
        prompt = _build_prompt(SAMPLE_PARSED_BILL, [])
        assert "EUINIL26-139120" in prompt
        assert "845760127781" in prompt
        assert "Amazon EC2" in prompt
        assert "Amazon S3" in prompt

    def test_includes_tips_when_provided(self):
        prompt = _build_prompt(SAMPLE_PARSED_BILL, SAMPLE_TIPS)
        assert "Right-size EC2 instances" in prompt
        assert "Enable Cost Explorer" in prompt
        assert "20-40%" in prompt

    def test_no_tips_message_when_empty(self):
        prompt = _build_prompt(SAMPLE_PARSED_BILL, [])
        assert "No specific tips available" in prompt

    def test_includes_line_items(self):
        prompt = _build_prompt(SAMPLE_PARSED_BILL, [])
        assert "Running instances" in prompt
        assert "Storage" in prompt

    def test_includes_billing_period(self):
        prompt = _build_prompt(SAMPLE_PARSED_BILL, [])
        assert "2026-02-01" in prompt
        assert "2026-02-28" in prompt


# ---------------------------------------------------------------------------
# _invoke_bedrock tests (mocked)
# ---------------------------------------------------------------------------

class TestInvokeBedrock:
    """Test Bedrock invocation with mocked boto3 client."""

    @patch("bedrock_client.boto3.client")
    def test_successful_invocation(self, mock_boto_client):
        mock_bedrock = MagicMock()
        mock_boto_client.return_value = mock_bedrock

        response_body = json.dumps({
            "output": {"message": {"content": [{"text": VALID_ANALYSIS_JSON}]}}
        }).encode()
        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        mock_bedrock.invoke_model.return_value = {"body": mock_response}

        result = _invoke_bedrock("test prompt")
        assert result == VALID_ANALYSIS_JSON

        # Verify the request format
        call_kwargs = mock_bedrock.invoke_model.call_args[1]
        body = json.loads(call_kwargs["body"])
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][0]["content"][0]["text"] == "test prompt"
        assert body["inferenceConfig"]["temperature"] == 0.7

    @patch("bedrock_client.boto3.client")
    def test_throttling_raises_runtime_error(self, mock_boto_client):
        from botocore.exceptions import ClientError

        mock_bedrock = MagicMock()
        mock_boto_client.return_value = mock_bedrock
        mock_bedrock.invoke_model.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "InvokeModel",
        )

        with pytest.raises(RuntimeError, match="Service is busy"):
            _invoke_bedrock("test prompt")

    @patch("bedrock_client.boto3.client")
    def test_service_unavailable_raises_runtime_error(self, mock_boto_client):
        from botocore.exceptions import ClientError

        mock_bedrock = MagicMock()
        mock_boto_client.return_value = mock_bedrock
        mock_bedrock.invoke_model.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailableException", "Message": "Service down"}},
            "InvokeModel",
        )

        with pytest.raises(RuntimeError, match="AI service temporarily unavailable"):
            _invoke_bedrock("test prompt")

    @patch("bedrock_client.boto3.client")
    def test_other_client_error_propagates(self, mock_boto_client):
        from botocore.exceptions import ClientError

        mock_bedrock = MagicMock()
        mock_boto_client.return_value = mock_bedrock
        mock_bedrock.invoke_model.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "No access"}},
            "InvokeModel",
        )

        with pytest.raises(ClientError):
            _invoke_bedrock("test prompt")


# ---------------------------------------------------------------------------
# _get_optimization_tips tests (mocked DynamoDB)
# ---------------------------------------------------------------------------

class TestGetOptimizationTips:
    """Test DynamoDB tip retrieval with mocked table."""

    @patch("bedrock_client.boto3.resource")
    def test_queries_services_and_general(self, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {"Items": [{"service": "EC2", "tipId": "ec2-001"}]}

        tips = _get_optimization_tips(["EC2", "S3"])

        # Should query EC2, S3, and General (3 queries)
        assert mock_table.query.call_count == 3

    @patch("bedrock_client.boto3.resource")
    def test_returns_combined_tips(self, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        def side_effect(**kwargs):
            expr = str(kwargs.get("KeyConditionExpression", ""))
            if "EC2" in expr:
                return {"Items": [{"service": "EC2", "tipId": "ec2-001"}]}
            return {"Items": [{"service": "General", "tipId": "gen-001"}]}

        mock_table.query.side_effect = side_effect

        tips = _get_optimization_tips(["EC2"])
        assert len(tips) == 2

    @patch("bedrock_client.boto3.resource")
    def test_dynamo_error_returns_partial_results(self, mock_resource):
        """DynamoDB errors are non-fatal — should log and continue."""
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        call_count = [0]

        def side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("DynamoDB timeout")
            return {"Items": [{"service": "General", "tipId": "gen-001"}]}

        mock_table.query.side_effect = side_effect

        tips = _get_optimization_tips(["EC2"])
        # Should still return tips from successful queries
        assert len(tips) >= 1

    @patch("bedrock_client.boto3.resource")
    def test_always_includes_general(self, mock_resource):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.query.return_value = {"Items": []}

        _get_optimization_tips([])

        # Should still query "General" even with empty services list
        assert mock_table.query.call_count == 1


# ---------------------------------------------------------------------------
# analyze_bill integration test (all mocked)
# ---------------------------------------------------------------------------

class TestAnalyzeBill:
    """Test the full pipeline with mocked AWS services."""

    @patch("bedrock_client._invoke_bedrock")
    @patch("bedrock_client._get_optimization_tips")
    def test_full_pipeline(self, mock_tips, mock_bedrock):
        mock_tips.return_value = SAMPLE_TIPS
        mock_bedrock.return_value = VALID_ANALYSIS_JSON

        result = analyze_bill(SAMPLE_PARSED_BILL)

        assert "summary" in result
        assert "explanations" in result
        assert "recommendations" in result
        mock_tips.assert_called_once_with(["Amazon EC2", "Amazon S3"])
        mock_bedrock.assert_called_once()

    @patch("bedrock_client._invoke_bedrock")
    @patch("bedrock_client._get_optimization_tips")
    def test_empty_service_totals(self, mock_tips, mock_bedrock):
        mock_tips.return_value = []
        mock_bedrock.return_value = VALID_ANALYSIS_JSON

        bill = {**SAMPLE_PARSED_BILL, "service_totals": {}}
        result = analyze_bill(bill)

        assert "summary" in result
        mock_tips.assert_called_once_with([])
