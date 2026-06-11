"""
Unit tests and property tests for the Service ID module.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from schema_sync.service_id import (
    validate_service_id,
    resolve_alias,
    get_provider,
    SERVICE_REGISTRY,
    VALID_PROVIDERS,
)


# =============================================================================
# Feature: tips-driven-schema-sync, Property 1: Service ID Format Validation
# =============================================================================


# Strategy for generating valid service slugs
valid_slug = st.from_regex(r"[a-z][a-z0-9]*(-[a-z0-9]+)*", fullmatch=True).filter(
    lambda s: len(s) <= 50
)

# Strategy for generating valid service IDs
valid_service_id = st.tuples(
    st.sampled_from(list(VALID_PROVIDERS)), valid_slug
).map(lambda t: f"{t[0]}:{t[1]}")


@settings(max_examples=100)
@given(valid_service_id)
def test_property_valid_service_ids_accepted(service_id):
    """Property 1: Valid Service IDs are always accepted."""
    assert validate_service_id(service_id) is True


@settings(max_examples=100)
@given(st.text(min_size=0, max_size=100))
def test_property_service_id_validation_rejects_invalid(text):
    """Property 1: Invalid Service IDs are rejected."""
    import re

    pattern = re.compile(r"^(aws|gcp|azure|openai):[a-z][a-z0-9]*(-[a-z0-9]+)*$")
    expected = bool(pattern.match(text))
    assert validate_service_id(text) == expected


# =============================================================================
# Unit Tests for Service ID module
# =============================================================================


class TestValidateServiceId:
    """Unit tests for validate_service_id."""

    def test_valid_aws_ec2(self):
        assert validate_service_id("aws:ec2") is True

    def test_valid_gcp_compute_engine(self):
        assert validate_service_id("gcp:compute-engine") is True

    def test_valid_azure_virtual_machines(self):
        assert validate_service_id("azure:virtual-machines") is True

    def test_valid_openai_api(self):
        assert validate_service_id("openai:api") is True

    def test_invalid_missing_colon(self):
        assert validate_service_id("awsec2") is False

    def test_invalid_unknown_provider(self):
        assert validate_service_id("ibm:watson") is False

    def test_invalid_uppercase_slug(self):
        assert validate_service_id("aws:EC2") is False

    def test_invalid_empty_slug(self):
        assert validate_service_id("aws:") is False

    def test_invalid_empty_string(self):
        assert validate_service_id("") is False

    def test_invalid_slug_starts_with_number(self):
        assert validate_service_id("aws:2ec") is False

    def test_invalid_slug_with_underscore(self):
        assert validate_service_id("aws:my_service") is False

    def test_invalid_none(self):
        assert validate_service_id(None) is False  # type: ignore

    def test_valid_multi_segment_slug(self):
        assert validate_service_id("aws:my-cool-service-v2") is True


class TestResolveAlias:
    """Unit tests for resolve_alias."""

    def test_resolve_amazon_ec2(self):
        assert resolve_alias("Amazon EC2") == "aws:ec2"

    def test_resolve_ec2_short(self):
        assert resolve_alias("EC2") == "aws:ec2"

    def test_resolve_s3_short(self):
        assert resolve_alias("S3") == "aws:s3"

    def test_resolve_amazon_s3(self):
        assert resolve_alias("Amazon S3") == "aws:s3"

    def test_resolve_compute_engine(self):
        assert resolve_alias("Compute Engine") == "gcp:compute-engine"

    def test_resolve_unknown(self):
        assert resolve_alias("Unknown Service") is None

    def test_resolve_none(self):
        assert resolve_alias(None) is None  # type: ignore

    def test_resolve_empty_string(self):
        assert resolve_alias("") is None


class TestGetProvider:
    """Unit tests for get_provider."""

    def test_aws_provider(self):
        assert get_provider("aws:ec2") == "aws"

    def test_gcp_provider(self):
        assert get_provider("gcp:compute-engine") == "gcp"

    def test_azure_provider(self):
        assert get_provider("azure:virtual-machines") == "azure"

    def test_openai_provider(self):
        assert get_provider("openai:api") == "openai"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            get_provider("invalid")
