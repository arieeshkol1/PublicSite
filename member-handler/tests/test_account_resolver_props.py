"""Property-based tests for account resolver (Property 1).

Property 1: Account ID format validation
For any string input, validate_account_format SHALL return the correct provider type
('aws', 'azure', or 'gcp') for strings matching the respective format and SHALL raise
ValueError for all other strings.
"""
from __future__ import annotations

import re
import string
import uuid

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent.account_resolver import validate_account_format


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def valid_aws_account_ids():
    """Generate valid AWS account IDs (exactly 12 digits)."""
    return st.text(
        alphabet=string.digits,
        min_size=12,
        max_size=12,
    )


def valid_azure_account_ids():
    """Generate valid Azure account IDs (UUID format)."""
    return st.builds(lambda: str(uuid.uuid4()))


def valid_gcp_project_ids():
    """Generate valid GCP project IDs (6-30 char, starts with lowercase, lowercase+digits+hyphens, ends with alphanumeric)."""
    return st.from_regex(
        r"[a-z][a-z0-9\-]{4,28}[a-z0-9]",
        fullmatch=True,
    )


def invalid_account_ids():
    """Generate strings that don't match any valid format."""
    return st.one_of(
        # Too short for any
        st.text(min_size=1, max_size=4),
        # Digits but wrong length (not 12)
        st.text(alphabet=string.digits, min_size=1, max_size=11),
        st.text(alphabet=string.digits, min_size=13, max_size=20),
        # Uppercase starts (invalid GCP)
        st.from_regex(r"[A-Z][a-z0-9]{5,10}", fullmatch=True),
        # Contains special chars
        st.from_regex(r"[a-z]{3}[!@#$%]{2}[a-z]{3}", fullmatch=True),
        # Empty string
        st.just(""),
    )


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(account_id=valid_aws_account_ids())
def test_property1_valid_aws_ids_return_aws(account_id):
    """Property 1: Valid AWS IDs (12 digits) return 'aws'."""
    result = validate_account_format(account_id)
    assert result == "aws", f"Expected 'aws' for {account_id}, got {result}"


@settings(max_examples=100)
@given(data=st.data())
def test_property1_valid_azure_ids_return_azure(data):
    """Property 1: Valid Azure IDs (UUID) return 'azure'."""
    account_id = str(uuid.uuid4())
    result = validate_account_format(account_id)
    assert result == "azure", f"Expected 'azure' for {account_id}, got {result}"


@settings(max_examples=100)
@given(account_id=valid_gcp_project_ids())
def test_property1_valid_gcp_ids_return_gcp(account_id):
    """Property 1: Valid GCP project IDs return 'gcp'."""
    # Ensure it's not accidentally a 12-digit number (which would be AWS)
    assume(not re.match(r"^\d{12}$", account_id))
    # Ensure it's not accidentally a UUID (which would be Azure)
    assume(not re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        account_id, re.IGNORECASE
    ))
    result = validate_account_format(account_id)
    assert result == "gcp", f"Expected 'gcp' for {account_id}, got {result}"


@settings(max_examples=100)
@given(account_id=invalid_account_ids())
def test_property1_invalid_ids_raise_valueerror(account_id):
    """Property 1: Invalid IDs raise ValueError without internal details."""
    # Filter out strings that accidentally match valid patterns
    assume(not re.match(r"^\d{12}$", account_id))
    assume(not re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        account_id, re.IGNORECASE
    ))
    assume(not re.match(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$", account_id))

    with pytest.raises(ValueError) as exc_info:
        validate_account_format(account_id)

    # Error message should not expose internal details
    error_msg = str(exc_info.value)
    assert "dynamodb" not in error_msg.lower()
    assert "table" not in error_msg.lower()
    assert "lambda" not in error_msg.lower()
    assert "arn:" not in error_msg.lower()
