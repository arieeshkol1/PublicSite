"""
Property-based tests for the vendor-agnostic getAIUsage path.

Feature: vendor-agnostic-ai-usage

Covers:
- Property 4: Vendor fields map onto neutral fields, with nulls for missing
  sources (Validates: Requirements 2.5, 2.6)
- Property 5: Default resolution window is the most recent 30 days
  (Validates: Requirements 3.6)
- Property 2: Unsupported connectors return a structured notSupported response
  (Validates: Requirements 1.5)

All HTTP and credential access is mocked; no production calls are made.
"""

import os
import sys
from datetime import date, datetime, timezone
from unittest.mock import patch

from hypothesis import given, settings, strategies as st

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from connectors.ai_vendor_connector import AIVendorConnector
import provider_router


# ─── Generators ───────────────────────────────────────────────────────────

# Identifier text including empty strings and non-ASCII actors/services.
# Kept cheap to generate while still exercising non-ASCII code paths.
_id_text = st.one_of(
    st.text(alphabet="abcdefABCDEF0123456789-_", min_size=0, max_size=10),
    st.sampled_from(["café", "naïve", "日本語", "Ω", "用户ABC", "مرحبا", "Ñoño", ""]),
)

_currency_text = st.sampled_from(["usd", "USD", "eur", "EUR", "gbp", "Usd"])

_token_count = st.integers(min_value=0, max_value=10**9)

_cost_value = st.floats(
    min_value=0, max_value=1_000_000, allow_nan=False, allow_infinity=False
)


@st.composite
def raw_result(draw):
    """A single raw OpenAI usage result with arbitrary subsets of fields."""
    r = {}
    if draw(st.booleans()):
        r["user_id"] = draw(_id_text)
    if draw(st.booleans()):
        r["project_id"] = draw(_id_text)
    if draw(st.booleans()):
        r["api_key_id"] = draw(_id_text)
    if draw(st.booleans()):
        r["model"] = draw(_id_text)
    if draw(st.booleans()):
        r["line_item"] = draw(_id_text)
    if draw(st.booleans()):
        r["input_tokens"] = draw(_token_count)
    if draw(st.booleans()):
        r["output_tokens"] = draw(_token_count)
    if draw(st.booleans()):
        r["amount"] = {
            "value": draw(_cost_value),
            "currency": draw(_currency_text),
        }
    return r


@st.composite
def raw_bucket(draw):
    """A usage bucket with a fixed start_time and a list of raw results."""
    return {
        "start_time": 1_704_067_200,  # 2024-01-01 UTC
        "results": draw(st.lists(raw_result(), min_size=0, max_size=6)),
    }


# Expected-mapping helpers (mirror the connector's documented direction).

def _expected_actor(r):
    return r.get("user_id") or r.get("project_id") or r.get("api_key_id") or None


def _expected_service(r):
    return r.get("model") or r.get("line_item") or None


def _expected_quantity_unit(r):
    it = r.get("input_tokens")
    ot = r.get("output_tokens")
    if it is None and ot is None:
        return None, None
    return int(it or 0) + int(ot or 0), "tokens"


def _expected_cost(r):
    amount = r.get("amount") or {}
    value = amount.get("value")
    return round(float(value), 4) if value is not None else None


_NEUTRAL_KEYS = {
    "date", "actor", "service", "usage_quantity", "unit", "cost_amount", "currency",
}


def _make_request_side_effect(usage_buckets):
    """Route usage vs. cost endpoints to the appropriate canned response."""

    def _side_effect(endpoint, api_key, organization_id=""):
        if "usage/completions" in endpoint:
            return {"data": usage_buckets, "has_more": False}
        # org costs endpoint -> no rollups needed for the mapping assertions
        return {"data": [], "has_more": False}

    return _side_effect


# ─── Property 4: vendor -> neutral field mapping with nulls ────────────────

@settings(max_examples=150, deadline=None)
@given(buckets=st.lists(raw_bucket(), min_size=0, max_size=4))
def test_property_4_vendor_fields_map_to_neutral_with_nulls(buckets):
    """**Validates: Requirements 2.5, 2.6**

    Each raw vendor result maps onto neutral fields in the documented
    direction (tokens->units, user_id->actor, model->service), and neutral
    fields with no source are set to null rather than omitted.
    """
    connector = AIVendorConnector()
    creds = {"api_key": "sk-test", "organization_id": "org-test", "vendor": "openai"}

    with patch.object(connector, "_get_credentials", return_value=creds), patch.object(
        connector, "_make_openai_request", side_effect=_make_request_side_effect(buckets)
    ):
        # dimension="cost" returns the full per-detail usage list (ungrouped).
        result = connector.get_ai_usage("org-test", "user@test.com", {"dimension": "cost"})

    assert "error" not in result
    usage = result["usage"]

    # Flatten expected results in bucket/result order (mapping preserves order).
    expected_results = [r for b in buckets for r in b["results"]]
    assert len(usage) == len(expected_results)

    for raw, neutral in zip(expected_results, usage):
        # null-not-omitted: every neutral key is present.
        assert _NEUTRAL_KEYS.issubset(neutral.keys())

        assert neutral["actor"] == _expected_actor(raw)
        assert neutral["service"] == _expected_service(raw)

        exp_qty, exp_unit = _expected_quantity_unit(raw)
        assert neutral["usage_quantity"] == exp_qty
        assert neutral["unit"] == exp_unit

        assert neutral["cost_amount"] == _expected_cost(raw)

        amount = raw.get("amount") or {}
        exp_currency = (amount.get("currency") or "USD").upper()
        assert neutral["currency"] == exp_currency


# ─── Property 5: default window is the most recent 30 days ─────────────────

@settings(max_examples=100, deadline=None)
@given(
    dimension=st.sampled_from(["cost", "units", "actor", None]),
    extra=st.dictionaries(st.sampled_from(["foo", "bar"]), st.text(max_size=4), max_size=2),
)
def test_property_5_default_window_is_last_30_days(dimension, extra):
    """**Validates: Requirements 3.6**

    When getAIUsage is invoked without a period, the resolved window is the
    most recent 30 days (end == today, span == 30 days).
    """
    connector = AIVendorConnector()
    creds = {"api_key": "sk-test", "organization_id": "org-test", "vendor": "openai"}

    params = dict(extra)
    if dimension is not None:
        params["dimension"] = dimension

    with patch.object(connector, "_get_credentials", return_value=creds), patch.object(
        connector, "_make_openai_request", side_effect=_make_request_side_effect([])
    ):
        result = connector.get_ai_usage("org-test", "user@test.com", params)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    period = result["period"]
    assert period["end"] == today

    start = date.fromisoformat(period["start"])
    end = date.fromisoformat(period["end"])
    assert (end - start).days == 30


# ─── Property 2: unsupported connectors return notSupported, never raise ───

@settings(max_examples=100, deadline=None)
@given(
    provider=st.sampled_from(["aws", "azure", "gcp"]),
    account_id=st.text(min_size=1, max_size=16),
)
def test_property_2_unsupported_connectors_return_not_supported(provider, account_id):
    """**Validates: Requirements 1.5**

    Routing getAIUsage to AWS/Azure/GCP connectors yields notSupported=True
    and never raises (those connectors do not implement AI usage retrieval).
    """
    with patch.object(provider_router, "resolve_provider", return_value=provider):
        # Real connector instances are used so SUPPORTED_OPERATIONS is authoritative.
        result = provider_router.route_tool(
            "getAIUsage", account_id, "user@test.com", {"dimension": "cost"}
        )

    assert result.get("notSupported") is True
    assert "error" not in result
