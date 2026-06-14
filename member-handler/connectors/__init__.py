"""Cloud provider connectors package."""
from .base_connector import ProviderConnector

# Connector registry — maps provider name to {'class': ConnectorClass, 'vendor_type': str}
_CONNECTORS = {}


def register_connector(provider_name, connector_class, vendor_type='cloud_provider'):
    """Register a connector class for a provider.

    Args:
        provider_name: String identifier for the provider (e.g. 'aws', 'openai')
        connector_class: Class implementing ProviderConnector interface
        vendor_type: Category string — 'cloud_provider' or 'ai_vendor' (default: 'cloud_provider')
    """
    _CONNECTORS[provider_name] = {
        'class': connector_class,
        'vendor_type': vendor_type,
    }


def get_connector(provider_name):
    """Get connector instance for a provider. Returns None if not registered."""
    # Lazy-load connectors on first access to ensure registration
    if not _CONNECTORS:
        _load_connectors()
    entry = _CONNECTORS.get(provider_name)
    return entry['class']() if entry else None


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
    try:
        from . import openai_connector  # noqa: F401
    except ImportError:
        pass
    try:
        from . import groundcover_connector  # noqa: F401
    except ImportError:
        pass


def list_providers(vendor_type=None):
    """List registered provider names, optionally filtered by vendor_type.

    Args:
        vendor_type: If specified, return only providers matching this vendor_type.
                     If None, return all registered providers.

    Returns:
        List of provider name strings.
    """
    if not _CONNECTORS:
        _load_connectors()
    if vendor_type:
        return [name for name, entry in _CONNECTORS.items()
                if entry['vendor_type'] == vendor_type]
    return list(_CONNECTORS.keys())
