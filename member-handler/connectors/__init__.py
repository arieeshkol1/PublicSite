"""Cloud provider connectors package."""
from .base_connector import ProviderConnector

# Connector registry — maps provider name to connector class
_CONNECTORS = {}


def register_connector(provider_name, connector_class):
    """Register a connector class for a provider."""
    _CONNECTORS[provider_name] = connector_class


def get_connector(provider_name):
    """Get connector instance for a provider. Returns None if not registered."""
    cls = _CONNECTORS.get(provider_name)
    return cls() if cls else None


def list_providers():
    """List all registered provider names."""
    return list(_CONNECTORS.keys())
