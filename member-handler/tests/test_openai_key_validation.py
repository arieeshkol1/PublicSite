"""Unit tests for OpenAI API key format validation."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from connectors.openai_connector import validate_openai_key_format, OpenAIConnector


class TestValidateOpenaiKeyFormat:
    """Tests for the standalone validate_openai_key_format function."""

    def test_valid_sk_org_key_minimum_length(self):
        """WHEN key starts with sk-org- and is exactly 40 chars, THEN valid."""
        key = 'sk-org-' + 'a' * 33  # 7 + 33 = 40
        result = validate_openai_key_format(key)
        assert result == {'valid': True}

    def test_valid_sk_proj_key_minimum_length(self):
        """WHEN key starts with sk-proj- and is exactly 40 chars, THEN valid."""
        key = 'sk-proj-' + 'a' * 32  # 8 + 32 = 40
        result = validate_openai_key_format(key)
        assert result == {'valid': True}

    def test_valid_sk_org_key_maximum_length(self):
        """WHEN key starts with sk-org- and is exactly 200 chars, THEN valid."""
        key = 'sk-org-' + 'a' * 193  # 7 + 193 = 200
        result = validate_openai_key_format(key)
        assert result == {'valid': True}

    def test_valid_sk_proj_key_maximum_length(self):
        """WHEN key starts with sk-proj- and is exactly 200 chars, THEN valid."""
        key = 'sk-proj-' + 'a' * 192  # 8 + 192 = 200
        result = validate_openai_key_format(key)
        assert result == {'valid': True}

    def test_valid_sk_org_key_typical_length(self):
        """WHEN key starts with sk-org- and is 51 chars, THEN valid."""
        key = 'sk-org-' + 'x' * 44  # 7 + 44 = 51
        result = validate_openai_key_format(key)
        assert result == {'valid': True}

    def test_valid_sk_proj_key_typical_length(self):
        """WHEN key starts with sk-proj- and is 56 chars, THEN valid."""
        key = 'sk-proj-' + 'x' * 48  # 8 + 48 = 56
        result = validate_openai_key_format(key)
        assert result == {'valid': True}

    def test_reject_generic_sk_prefix(self):
        """WHEN key starts with sk- but not sk-org- or sk-proj-, THEN invalid."""
        key = 'sk-' + 'a' * 47  # 50 chars, valid length but wrong prefix
        result = validate_openai_key_format(key)
        assert result['valid'] is False
        assert 'sk-org-' in result['error']
        assert 'sk-proj-' in result['error']

    def test_reject_empty_string(self):
        """WHEN key is empty, THEN invalid."""
        result = validate_openai_key_format('')
        assert result['valid'] is False
        assert 'empty' in result['error'].lower()

    def test_reject_none(self):
        """WHEN key is None (not a string), THEN invalid."""
        result = validate_openai_key_format(None)
        assert result['valid'] is False
        assert 'string' in result['error'].lower()

    def test_reject_integer(self):
        """WHEN key is an integer (not a string), THEN invalid."""
        result = validate_openai_key_format(12345)
        assert result['valid'] is False
        assert 'string' in result['error'].lower()

    def test_reject_too_short_sk_org(self):
        """WHEN key starts with sk-org- but is 39 chars, THEN invalid."""
        key = 'sk-org-' + 'a' * 32  # 7 + 32 = 39
        result = validate_openai_key_format(key)
        assert result['valid'] is False
        assert 'length' in result['error'].lower()

    def test_reject_too_short_sk_proj(self):
        """WHEN key starts with sk-proj- but is 39 chars, THEN invalid."""
        key = 'sk-proj-' + 'a' * 31  # 8 + 31 = 39
        result = validate_openai_key_format(key)
        assert result['valid'] is False
        assert 'length' in result['error'].lower()

    def test_reject_too_long_sk_org(self):
        """WHEN key starts with sk-org- but is 201 chars, THEN invalid."""
        key = 'sk-org-' + 'a' * 194  # 7 + 194 = 201
        result = validate_openai_key_format(key)
        assert result['valid'] is False
        assert 'length' in result['error'].lower()

    def test_reject_too_long_sk_proj(self):
        """WHEN key starts with sk-proj- but is 201 chars, THEN invalid."""
        key = 'sk-proj-' + 'a' * 193  # 8 + 193 = 201
        result = validate_openai_key_format(key)
        assert result['valid'] is False
        assert 'length' in result['error'].lower()

    def test_reject_no_prefix(self):
        """WHEN key has no recognized prefix, THEN invalid."""
        key = 'abcdefghij' * 5  # 50 chars, no sk- prefix
        result = validate_openai_key_format(key)
        assert result['valid'] is False
        assert 'sk-org-' in result['error']

    def test_reject_wrong_case_prefix(self):
        """WHEN key has SK-ORG- (uppercase), THEN invalid."""
        key = 'SK-ORG-' + 'a' * 43  # 50 chars
        result = validate_openai_key_format(key)
        assert result['valid'] is False

    def test_reject_sk_organization_prefix(self):
        """WHEN key starts with sk-organization- (not sk-org-), THEN invalid."""
        key = 'sk-organization-' + 'a' * 30  # 46 chars
        result = validate_openai_key_format(key)
        assert result['valid'] is False


class TestConnectorValidateKeyFormat:
    """Tests for the OpenAIConnector._validate_key_format static method."""

    def test_valid_key_returns_true(self):
        """WHEN key is valid, THEN _validate_key_format returns True."""
        key = 'sk-org-' + 'a' * 43  # 50 chars
        assert OpenAIConnector._validate_key_format(key) is True

    def test_invalid_key_returns_false(self):
        """WHEN key has wrong prefix, THEN _validate_key_format returns False."""
        key = 'sk-' + 'a' * 47  # 50 chars, wrong prefix
        assert OpenAIConnector._validate_key_format(key) is False

    def test_too_short_returns_false(self):
        """WHEN key is too short, THEN _validate_key_format returns False."""
        key = 'sk-org-' + 'a' * 10  # 17 chars
        assert OpenAIConnector._validate_key_format(key) is False
