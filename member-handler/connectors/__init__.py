"""Cloud provider connectors package."""
from .base_connector import ProviderConnector

# Connector registry — maps provider name to connector class
_CONNECTORS = {}


def register_connector(provider_name, connector_class):
    """Register a connector class for a provider."""
    _CONNECTORS[provider_name] = connector_class


def get_connector(provider_name):
    """Get connector instance for a provider. Returns None if not registered."""
    # Lazy-load connectors on first access to ensure registration
    if not _CONNECTORS:
        _load_connectors()
    cls = _CONNECTORS.get(provider_name)
    return cls() if cls else None


def _load_connectors():
    """Import all connector modules to trigger auto-registration."""
    try:
        from . import aws_connector  # noqa: F401
    except ImportError:
        pass
    try:
        from . import azure_connector  # noqa: F401
    except ImportError:
        pass
    try:
        from . import gcp_connector  # noqa: F401
    except ImportError:
        pass


def list_providers():
    """List all registered provider names."""
    if not _CONNECTORS:
        _load_connectors()
    return list(_CONNECTORS.keys())
