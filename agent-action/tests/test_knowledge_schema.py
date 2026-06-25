"""
Unit tests for the Knowledge action group schema (schemas/knowledge.json).

Feature: vendor-agnostic-ai-usage

Asserts the vendor-agnostic getAIUsage tool definition facts:
- operation path /get-ai-usage with operationId getAIUsage
- required accountId, memberEmail, dimension parameters
- dimension enum values cost, units, actor
- optional service and period parameters

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
"""

import json
import os

import pytest

_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "schemas",
    "knowledge.json",
)


@pytest.fixture(scope="module")
def schema():
    with open(_SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def get_ai_usage_op(schema):
    paths = schema["paths"]
    assert "/get-ai-usage" in paths, "Missing /get-ai-usage operation path"
    return paths["/get-ai-usage"]["post"]


def _params_by_name(operation):
    return {p["name"]: p for p in operation.get("parameters", [])}


def test_knowledge_json_is_valid_json():
    # Loading without error confirms the schema is valid JSON (Req 3.1).
    with open(_SCHEMA_PATH, encoding="utf-8") as fh:
        json.load(fh)


def test_get_ai_usage_path_and_operation_id(get_ai_usage_op):
    """Req 3.1: /get-ai-usage path exists with operationId getAIUsage."""
    assert get_ai_usage_op["operationId"] == "getAIUsage"


def test_required_account_id_and_member_email(get_ai_usage_op):
    """Req 3.2: accountId and memberEmail are required parameters."""
    params = _params_by_name(get_ai_usage_op)
    for name in ("accountId", "memberEmail"):
        assert name in params, f"Missing required parameter {name}"
        assert params[name]["required"] is True
        assert params[name]["in"] == "query"


def test_dimension_required_with_enum(get_ai_usage_op):
    """Req 3.3: dimension is required and accepts cost, units, actor."""
    params = _params_by_name(get_ai_usage_op)
    assert "dimension" in params
    dimension = params["dimension"]
    assert dimension["required"] is True
    assert set(dimension["schema"]["enum"]) == {"cost", "units", "actor"}


def test_service_optional(get_ai_usage_op):
    """Req 3.4: service is an optional parameter."""
    params = _params_by_name(get_ai_usage_op)
    assert "service" in params
    assert params["service"]["required"] is False


def test_period_optional(get_ai_usage_op):
    """Req 3.5: period is an optional parameter."""
    params = _params_by_name(get_ai_usage_op)
    assert "period" in params
    assert params["period"]["required"] is False
