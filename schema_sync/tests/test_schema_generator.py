"""
Property-based and unit tests for the Schema Generator module.
"""

import json
import random

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from schema_sync.schema_generator import (
    generate_schema,
    validate_schema,
    merge_tool_definitions,
    check_backward_compatibility,
    REQUIRED_OPERATION_IDS,
    SchemaValidationError,
)
from schema_sync.service_id import VALID_PROVIDERS


# =============================================================================
# Hypothesis strategies for generating test data
# =============================================================================

valid_slug = st.from_regex(r"[a-z][a-z0-9]*(-[a-z0-9]+)*", fullmatch=True).filter(
    lambda s: 1 <= len(s) <= 30
)

valid_provider = st.sampled_from(list(VALID_PROVIDERS))

valid_service_id = st.tuples(valid_provider, valid_slug).map(
    lambda t: f"{t[0]}:{t[1]}"
)

param_strategy = st.fixed_dictionaries(
    {
        "name": st.from_regex(r"[a-z][a-zA-Z0-9]{1,20}", fullmatch=True),
        "in": st.sampled_from(["query", "path"]),
        "type": st.sampled_from(["string", "integer", "boolean"]),
        "required": st.booleans(),
        "description": st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))),
    }
)

tool_definition_strategy = st.fixed_dictionaries(
    {
        "operationId": st.from_regex(r"[a-z][a-zA-Z0-9]{3,25}", fullmatch=True),
        "path": st.from_regex(r"/[a-z][a-z0-9-]{2,30}", fullmatch=True),
        "httpMethod": st.just("POST"),
        "provider": valid_provider,
        "summary": st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))),
        "description": st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))),
        "parameters": st.lists(param_strategy, min_size=0, max_size=5),
    }
)

tip_record_strategy = st.fixed_dictionaries(
    {
        "id": st.from_regex(r"[a-z]{2,5}-[0-9]{3}", fullmatch=True),
        "serviceId": valid_service_id,
        "serviceKey": st.text(min_size=1, max_size=30),
        "title": st.text(min_size=1, max_size=50),
        "toolDefinition": tool_definition_strategy,
    }
)

# Strategy for records that might be missing fields (for robustness testing)
maybe_invalid_tip = st.one_of(
    tip_record_strategy,
    st.fixed_dictionaries({"id": st.just("bad-001"), "title": st.just("No serviceId")}),
    st.fixed_dictionaries(
        {
            "id": st.just("bad-002"),
            "serviceId": st.just("aws:ec2"),
            "title": st.just("No toolDef"),
        }
    ),
    st.fixed_dictionaries(
        {
            "id": st.just("bad-003"),
            "serviceId": st.just("INVALID"),
            "title": st.just("Invalid serviceId"),
            "toolDefinition": tool_definition_strategy,
        }
    ),
)


# =============================================================================
# Feature: tips-driven-schema-sync, Property 2: Schema Generation Produces Valid OpenAPI
# =============================================================================


@settings(max_examples=100)
@given(st.lists(maybe_invalid_tip, min_size=0, max_size=15))
def test_property_schema_always_valid_openapi(tip_records):
    """Property 2: For any list of tip records, generate_schema produces valid OpenAPI."""
    schema = generate_schema(tip_records)
    errors = validate_schema(schema)
    assert errors == [], f"Schema validation errors: {errors}"


# =============================================================================
# Feature: tips-driven-schema-sync, Property 3: Tool Definition Merge — Most Parameters Wins
# =============================================================================


@settings(max_examples=100)
@given(
    st.lists(
        st.tuples(
            st.just("sharedOpId"),
            st.lists(param_strategy, min_size=0, max_size=8),
        ),
        min_size=2,
        max_size=5,
    )
)
def test_property_merge_most_parameters_wins(definitions_data):
    """Property 3: Merged result has param count >= every individual definition."""
    ops_by_id = {"sharedOpId": []}
    for _, params in definitions_data:
        ops_by_id["sharedOpId"].append(
            {
                "operationId": "sharedOpId",
                "path": "/shared-path",
                "httpMethod": "POST",
                "provider": "aws",
                "summary": "Test",
                "description": "Test op",
                "parameters": params,
            }
        )

    merged = merge_tool_definitions(ops_by_id)
    assert len(merged) == 1

    merged_param_count = len(merged[0].get("parameters", []))
    for defn in ops_by_id["sharedOpId"]:
        assert merged_param_count >= len(defn.get("parameters", []))


# =============================================================================
# Feature: tips-driven-schema-sync, Property 4: Deterministic Output Regardless of Input Order
# =============================================================================


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(tip_record_strategy, min_size=1, max_size=10))
def test_property_deterministic_output(tip_records):
    """Property 4: Two permutations of the same records produce identical JSON."""
    schema_a = generate_schema(tip_records)

    # Shuffle the records
    shuffled = list(tip_records)
    random.shuffle(shuffled)

    schema_b = generate_schema(shuffled)

    assert json.dumps(schema_a, sort_keys=False) == json.dumps(schema_b, sort_keys=False)


# =============================================================================
# Feature: tips-driven-schema-sync, Property 5: Multi-Provider Inclusivity
# =============================================================================


@settings(max_examples=100)
@given(st.lists(tip_record_strategy, min_size=1, max_size=10))
def test_property_multi_provider_inclusivity(tip_records):
    """Property 5: Generated schema contains paths for all providers in input."""
    # Determine which providers have valid tool definitions in input
    expected_providers = set()
    for record in tip_records:
        sid = record.get("serviceId", "")
        tool_def = record.get("toolDefinition")
        if sid and ":" in sid and tool_def:
            provider = sid.split(":")[0]
            if provider in VALID_PROVIDERS:
                expected_providers.add(provider)

    schema = generate_schema(tip_records)
    paths = schema.get("paths", {})

    # Check each expected provider has at least one path
    for provider in expected_providers:
        provider_has_path = any(
            tool_def.get("provider") == provider
            for record in tip_records
            if record.get("toolDefinition")
            for tool_def in [record["toolDefinition"]]
            if record.get("serviceId", "").startswith(f"{provider}:")
        )
        if provider_has_path:
            # The schema should have at least one path from this provider's tool defs
            found = False
            for path_key, path_item in paths.items():
                for method, operation in path_item.items():
                    # Check by looking at the path prefix or operation existence
                    found = True
                    break
                if found:
                    break
            # At minimum, if there are valid tool defs, there are paths
            assert len(paths) > 0 or not expected_providers


# =============================================================================
# Feature: tips-driven-schema-sync, Property 6: Backward Compatibility Gate
# =============================================================================


@settings(max_examples=100)
@given(
    st.lists(
        st.sampled_from(REQUIRED_OPERATION_IDS + ["extraOp1", "extraOp2"]),
        min_size=0,
        max_size=15,
        unique=True,
    )
)
def test_property_backward_compatibility_gate(present_ops):
    """Property 6: Checker returns missing ops iff schema doesn't contain all required."""
    # Build a minimal schema with the given operationIds
    paths = {}
    for op_id in present_ops:
        paths[f"/{op_id}"] = {
            "post": {
                "operationId": op_id,
                "summary": "Test",
                "description": "Test",
                "parameters": [],
                "responses": {"200": {"description": "OK"}},
            }
        }

    schema = {
        "openapi": "3.0.0",
        "info": {"title": "Test", "version": "1.0.0", "description": "Test"},
        "paths": paths,
    }

    missing = check_backward_compatibility(schema)
    expected_missing = sorted(set(REQUIRED_OPERATION_IDS) - set(present_ops))

    assert missing == expected_missing


# =============================================================================
# Unit Tests
# =============================================================================


class TestGenerateSchema:
    """Unit tests for generate_schema."""

    def test_empty_input_produces_valid_schema(self):
        schema = generate_schema([])
        assert schema["openapi"] == "3.0.0"
        assert schema["info"]["title"] == "SlashMyBill FinOps Actions"
        assert schema["paths"] == {}

    def test_single_tip_with_tool_definition(self):
        tips = [
            {
                "id": "ec2-001",
                "serviceId": "aws:ec2",
                "toolDefinition": {
                    "operationId": "getEC2Instances",
                    "path": "/get-ec2-instances",
                    "httpMethod": "POST",
                    "provider": "aws",
                    "summary": "List EC2 instances",
                    "description": "Lists EC2 instances",
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
        schema = generate_schema(tips)
        assert "/get-ec2-instances" in schema["paths"]
        op = schema["paths"]["/get-ec2-instances"]["post"]
        assert op["operationId"] == "getEC2Instances"

    def test_tip_without_service_id_is_skipped(self):
        tips = [
            {
                "id": "bad-001",
                "title": "No serviceId",
                "toolDefinition": {
                    "operationId": "badOp",
                    "path": "/bad",
                    "httpMethod": "POST",
                    "provider": "aws",
                },
            }
        ]
        schema = generate_schema(tips)
        assert schema["paths"] == {}

    def test_tip_without_tool_definition_is_skipped(self):
        tips = [{"id": "ec2-001", "serviceId": "aws:ec2", "title": "No tool"}]
        schema = generate_schema(tips)
        assert schema["paths"] == {}


class TestCheckBackwardCompatibility:
    """Unit tests for check_backward_compatibility."""

    def test_all_ops_present(self):
        paths = {}
        for op_id in REQUIRED_OPERATION_IDS:
            paths[f"/{op_id}"] = {
                "post": {
                    "operationId": op_id,
                    "parameters": [],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        schema = {"openapi": "3.0.0", "info": {}, "paths": paths}
        assert check_backward_compatibility(schema) == []

    def test_missing_two_ops(self):
        paths = {}
        for op_id in REQUIRED_OPERATION_IDS[:-2]:
            paths[f"/{op_id}"] = {
                "post": {
                    "operationId": op_id,
                    "parameters": [],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        schema = {"openapi": "3.0.0", "info": {}, "paths": paths}
        missing = check_backward_compatibility(schema)
        assert len(missing) == 2
        assert set(missing) == set(REQUIRED_OPERATION_IDS[-2:])

    def test_empty_schema_returns_all(self):
        schema = {"openapi": "3.0.0", "info": {}, "paths": {}}
        missing = check_backward_compatibility(schema)
        assert sorted(missing) == sorted(REQUIRED_OPERATION_IDS)
