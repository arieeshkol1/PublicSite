"""Base interface for cloud provider connectors."""
from abc import ABC, abstractmethod


class ProviderConnector(ABC):
    """Abstract base class for cloud provider connectors.

    Each cloud provider (AWS, Azure, GCP) implements this interface.
    """

    @abstractmethod
    def authenticate(self, credentials: dict) -> dict:
        """Authenticate with the provider.

        Args:
            credentials: Provider-specific credentials dict

        Returns:
            Auth context dict (token, session, etc.) for use in subsequent calls

        Raises:
            AuthenticationError: If credentials are invalid or expired
        """
        raise NotImplementedError

    @abstractmethod
    def test_connection(self, auth_context: dict, account_id: str) -> dict:
        """Test connectivity by attempting to read cost data.

        Args:
            auth_context: Result from authenticate()
            account_id: Provider-specific account identifier

        Returns:
            Dict with keys: success (bool), message (str), details (dict)
        """
        raise NotImplementedError

    @abstractmethod
    def get_cost_data(self, auth_context: dict, account_id: str, start_date: str, end_date: str) -> list:
        """Retrieve cost data for the given period.

        Args:
            auth_context: Result from authenticate()
            account_id: Provider-specific account identifier
            start_date: ISO date string (YYYY-MM-DD)
            end_date: ISO date string (YYYY-MM-DD)

        Returns:
            List of raw cost records (provider-specific format)
        """
        raise NotImplementedError


class ConnectorError(Exception):
    """Base exception for connector errors."""

    def __init__(self, message, status_code=500, error_code='ConnectorError'):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class AuthenticationError(ConnectorError):
    """Raised when authentication fails."""

    def __init__(self, message, provider='unknown'):
        super().__init__(message, status_code=400, error_code='AuthenticationFailed')
        self.provider = provider


class CostRetrievalError(ConnectorError):
    """Raised when cost data retrieval fails."""

    def __init__(self, message, provider='unknown'):
        super().__init__(message, status_code=500, error_code='CostRetrievalFailed')
        self.provider = provider
