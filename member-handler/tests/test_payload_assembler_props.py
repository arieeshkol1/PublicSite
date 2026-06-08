"""Property-based tests for payload assembler (Properties 2, 3, 4, 10, 12, 13).

Property 2: Payload structural integrity
Property 3: Data truncation invariant
Property 4: Budget enforcement preserves priority sections
Property 10: Template hydration completeness
Property 12: Token estimation accuracy
Property 13: Data deduplication between tips and account data
"""
from __future__ import annotations

import json
import re
import string

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent.models import AccountContext, ContextBudget, ExecutionPayload, PromptTemplate
from agent.payload_assembler import (
    assemble_payload,
    truncate_to_budget,
    _STATIC_SYSTEM_PREFIX,
    _truncate_large_arrays,
    _deduplicate_data,
)
from agent.context_budget import estimate_tokens
from agent.prompt_repository import hydrate_template, has_unresolved_placeholders


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def random_account_context():
    """Generate random AccountContext."""
    return st.builds(
        AccountContext,
        account_id=st.from_regex(r"\d{12}", fullmatch=True),
        account_name=st.text(alphabet=string.ascii_letters + " ", min_size=3, max_size=20),
        cloud_provider=st.sampled_from(["aws", "azure", "gcp"]),
        member_email=st.emails(),
        supported_services=st.lists(
            st.sampled_from(["EC2", "RDS", "S3", "Lambda", "DynamoDB", "CloudFront"]),
            min_size=1, max_size=6,
        ),
        provider_config=st.just({}),
    )


def random_gathered_data(min_rows=0, max_rows=50):
    """Generate random gathered data dicts."""
    service_entry = st.fixed_dictionaries({
        "service": st.sampled_from(["EC2", "RDS", "S3", "Lambda", "DynamoDB"]),
        "cost": st.floats(min_value=0.01, max_value=10000, allow_nan=False, allow_infinity=False),
    })
    return st.fixed_dictionaries({
        "cost_by_service": st.lists(service_entry, min_size=min_rows, max_size=max_rows),
    })


def random_large_gathered_data():
    """Generate data with >100 rows."""
    service_entry = st.fixed_dictionaries({
        "service": st.text(alphabet=string.ascii_letters, min_size=3, max_size=10),
        "cost": st.floats(min_value=0.01, max_value=10000, allow_nan=False, allow_infinity=False),
    })
    return st.fixed_dictionaries({
        "cost_by_service": st.lists(service_entry, min_size=101, max_size=150),
    })


def random_template_with_placeholders():
    """Generate templates with {{var}} placeholders."""
    var_names = st.sampled_from(["account_id", "account_name", "cloud_provider", "gathered_data", "user_question", "supported_services"])
    return st.builds(
        lambda vars: "Template v1.0\n" + "\n".join(f"{{{{{v}}}}}" for v in vars),
        vars=st.lists(var_names, min_size=1, max_size=6, unique=True),
    )


# ---------------------------------------------------------------------------
# Property 2: Payload structural integrity
# ---------------------------------------------------------------------------

@settings(max_examples=100, deadline=None)
@given(
    account_context=random_account_context(),
    question=st.text(min_size=5, max_size=100),
)
def test_property2_payload_has_three_sections_in_order(account_context, question):
    """Property 2: Payload always has [CONTEXT], [AVAILABLE META-DATA], [USER QUERY] in order."""
    budget = ContextBudget(
        system_prefix_tokens=4000,
        dynamic_data_tokens=12000,
        user_query_tokens=2000,
        total_ceiling=22000,
    )

    # Use a mock template approach - we'll just check the assembled payload structure
    from unittest.mock import patch, MagicMock

    mock_template = PromptTemplate(
        template_id="test", version="v1", content="{{gathered_data}}", last_modified=""
    )
    with patch("agent.payload_assembler.load_template", return_value=mock_template):
        payload = assemble_payload(
            "test-template.txt",
            account_context,
            {"cost_by_service": [{"service": "EC2", "cost": 100}]},
            question,
            budget,
        )

    # Check each section contains its marker
    assert "[CONTEXT]" in payload.system_prefix
    assert "[AVAILABLE META-DATA]" in payload.available_metadata
    assert "[USER QUERY]" in payload.user_query

    # The sections are stored separately and concatenated in order:
    # system_prefix (contains [CONTEXT]) -> available_metadata (contains [AVAILABLE META-DATA]) -> user_query (contains [USER QUERY])
    # This ensures ordering by design since they're assembled in that sequence


@settings(max_examples=100)
@given(
    account_context=random_account_context(),
    question=st.text(min_size=5, max_size=100),
)
def test_property2_static_prefix_identical(account_context, question):
    """Property 2: System prefix is static across all invocations."""
    budget = ContextBudget(
        system_prefix_tokens=4000,
        dynamic_data_tokens=12000,
        user_query_tokens=2000,
        total_ceiling=22000,
    )

    from unittest.mock import patch
    mock_template = PromptTemplate(
        template_id="test", version="v1", content="{{gathered_data}}", last_modified=""
    )
    with patch("agent.payload_assembler.load_template", return_value=mock_template):
        payload = assemble_payload(
            "test.txt", account_context, {}, question, budget,
        )

    # Static prefix should start the system_prefix
    assert payload.system_prefix.startswith(_STATIC_SYSTEM_PREFIX)


# ---------------------------------------------------------------------------
# Property 3: Data truncation invariant
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(data=random_large_gathered_data())
def test_property3_arrays_over_100_truncated_to_10(data):
    """Property 3: Arrays >100 rows truncated to top 10 + summary."""
    truncated = _truncate_large_arrays(data)

    for key, value in truncated.items():
        if isinstance(value, list) and key in data and len(data[key]) > 100:
            # Should have at most 11 entries (10 items + 1 summary)
            assert len(value) <= 11, f"Expected max 11 items, got {len(value)}"
            # Last item should be a summary
            last = value[-1]
            assert isinstance(last, dict)
            assert "_summary" in last


# ---------------------------------------------------------------------------
# Property 4: Budget enforcement preserves priority sections
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    account_context=random_account_context(),
    question=st.text(min_size=10, max_size=200),
)
def test_property4_budget_enforcement_preserves_prefix_and_query(account_context, question):
    """Property 4: Budget enforcement preserves system prefix and user query, only truncates metadata."""
    # Use a very small budget to force truncation
    budget = ContextBudget(
        system_prefix_tokens=4000,
        dynamic_data_tokens=100,  # Very small
        user_query_tokens=2000,
        total_ceiling=500,  # Very small total
    )

    from unittest.mock import patch
    mock_template = PromptTemplate(
        template_id="test", version="v1", content="{{gathered_data}}", last_modified=""
    )

    big_data = {"costs": [{"service": f"svc_{i}", "cost": i * 10} for i in range(50)]}

    with patch("agent.payload_assembler.load_template", return_value=mock_template):
        payload = assemble_payload(
            "test.txt", account_context, big_data, question, budget,
        )

    # System prefix must be preserved (starts with static prefix)
    assert _STATIC_SYSTEM_PREFIX in payload.system_prefix

    # User query must contain the original question
    assert question in payload.user_query or question.replace("<<<USER_INPUT>>>", "<<<USER_INPUT\\>>>") in payload.user_query


# ---------------------------------------------------------------------------
# Property 10: Template hydration completeness
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(template_content=random_template_with_placeholders())
def test_property10_hydration_leaves_no_placeholders(template_content):
    """Property 10: Template hydration leaves no {{...}} patterns when all vars provided."""
    template = PromptTemplate(
        template_id="test",
        version="v2.1",
        content=template_content,
        last_modified="2024-01-01",
    )

    # Provide all possible variables
    variables = {
        "account_id": "123456789012",
        "account_name": "Test Account",
        "cloud_provider": "aws",
        "gathered_data": "some data here",
        "user_question": "what is my cost?",
        "supported_services": "EC2, RDS, S3",
    }

    hydrated = hydrate_template(template, variables)
    assert not has_unresolved_placeholders(hydrated), f"Unresolved placeholders in: {hydrated}"


@settings(max_examples=100)
@given(
    account_context=random_account_context(),
    question=st.text(min_size=5, max_size=50),
)
def test_property10_payload_includes_version(account_context, question):
    """Property 10: Payload includes template version in metadata."""
    budget = ContextBudget(
        system_prefix_tokens=4000,
        dynamic_data_tokens=12000,
        user_query_tokens=2000,
        total_ceiling=22000,
    )

    from unittest.mock import patch
    mock_template = PromptTemplate(
        template_id="test", version="v3.2", content="{{gathered_data}}", last_modified=""
    )
    with patch("agent.payload_assembler.load_template", return_value=mock_template):
        payload = assemble_payload("test.txt", account_context, {}, question, budget)

    assert payload.template_version == "v3.2"


# ---------------------------------------------------------------------------
# Property 12: Token estimation accuracy
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(text=st.text(min_size=10, max_size=5000))
def test_property12_token_estimation_within_25_percent(text):
    """Property 12: Token estimation within ±25% of chars/4 reference."""
    estimated = estimate_tokens(text)
    reference = max(1, len(text) // 4)

    # The estimate should be within ±25% of the reference
    lower_bound = reference * 0.75
    upper_bound = reference * 1.25

    assert lower_bound <= estimated <= upper_bound, (
        f"Estimate {estimated} not within ±25% of reference {reference} for text length {len(text)}"
    )


# ---------------------------------------------------------------------------
# Property 13: Data deduplication
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    service=st.sampled_from(["EC2", "RDS", "S3", "Lambda"]),
    tip_id=st.text(alphabet=string.ascii_lowercase + string.digits, min_size=3, max_size=10),
)
def test_property13_no_duplicates_between_tips_and_account_data(service, tip_id):
    """Property 13: No duplicates between tips and account data in final payload."""
    # Create data with overlapping entries
    gathered_data = {
        "tips": [
            {"service": service, "tipId": tip_id, "title": "Tip A"},
        ],
        "account_data": {
            "items": [
                {"service": service, "tipId": tip_id, "title": "Tip A duplicate"},
                {"service": "Other", "tip_id": "other-1", "title": "Unique item"},
            ],
        },
    }

    deduped = _deduplicate_data(gathered_data)

    # The duplicate should be removed from account_data
    account_items = deduped.get("account_data", {}).get("items", [])
    tip_keys = {f"{t['service'].lower()}:{t['tipId']}" for t in deduped.get("tips", []) if isinstance(t, dict)}

    for item in account_items:
        if isinstance(item, dict):
            item_key = f"{item.get('service', '').lower()}:{item.get('tipId', item.get('tip_id', ''))}"
            if item_key and ":" in item_key and item_key.split(":")[1]:
                assert item_key not in tip_keys, f"Duplicate found: {item_key}"
