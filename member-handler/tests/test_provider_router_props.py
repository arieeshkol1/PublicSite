"""Property-based tests for provider routing (Property 14).

Property 14: Provider routing correctness
For any resolved account context with cloud_provider 'aws', 'azure', or 'gcp',
the Provider Abstraction Layer SHALL select the correct connector.
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent.provider_connectors import get_connector, AWSConnector, AzureConnector, GCPConnector
from agent.ai_model_router import get_model_config, _DEFAULT_MODEL_CONFIG
from agent.models import ModelConfig


# ---------------------------------------------------------------------------
# Property 14: Provider routing correctness
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(provider=st.sampled_from(["aws", "azure", "gcp"]))
def test_property14_correct_connector_selected(provider):
    """Property 14: aws/azure/gcp routes to correct connector."""
    connector = get_connector(provider)

    expected_types = {
        "aws": AWSConnector,
        "azure": AzureConnector,
        "gcp": GCPConnector,
    }

    assert isinstance(connector, expected_types[provider]), (
        f"Expected {expected_types[provider].__name__} for '{provider}', "
        f"got {type(connector).__name__}"
    )


@settings(max_examples=100)
@given(provider=st.text(min_size=1, max_size=20).filter(
    lambda x: x.lower() not in ("aws", "azure", "gcp")
))
def test_property14_invalid_provider_raises(provider):
    """Property 14: Invalid provider raises ValueError."""
    with pytest.raises(ValueError) as exc_info:
        get_connector(provider)
    assert "Unsupported" in str(exc_info.value) or "provider" in str(exc_info.value).lower()


@settings(max_examples=100)
@given(
    has_tenant_config=st.booleans(),
    tenant_provider=st.sampled_from(["bedrock", "openai", "azure-openai"]),
    tenant_model=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-.", min_size=3, max_size=30),
)
def test_property14_tenant_config_overrides_global(has_tenant_config, tenant_provider, tenant_model):
    """Property 14: Tenant config overrides global default."""
    with patch("agent.ai_model_router.boto3") as mock_boto3:
        mock_resource = MagicMock()
        mock_table = MagicMock()
        mock_boto3.resource.return_value = mock_resource
        mock_resource.Table.return_value = mock_table

        if has_tenant_config:
            mock_table.get_item.return_value = {
                "Item": {
                    "aiModelConfig": {
                        "provider": tenant_provider,
                        "modelId": tenant_model,
                        "region": "us-west-2",
                        "maxTokens": 8192,
                        "temperature": 0.2,
                    }
                }
            }
        else:
            mock_table.get_item.return_value = {"Item": {}}

        config = get_model_config("test@example.com")

    if has_tenant_config:
        assert config.provider == tenant_provider
        assert config.model_id == tenant_model
        assert config.region == "us-west-2"
    else:
        # Should use global default
        assert config.provider == _DEFAULT_MODEL_CONFIG.provider
        assert config.model_id == _DEFAULT_MODEL_CONFIG.model_id


@settings(max_examples=100)
@given(provider=st.sampled_from(["aws", "azure", "gcp"]))
def test_property14_connector_has_required_methods(provider):
    """Property 14: Each connector has the required interface methods."""
    connector = get_connector(provider)

    assert hasattr(connector, "get_cost_data")
    assert hasattr(connector, "get_resource_recommendations")
    assert hasattr(connector, "get_historical_costs")
    assert callable(connector.get_cost_data)
    assert callable(connector.get_resource_recommendations)
    assert callable(connector.get_historical_costs)
