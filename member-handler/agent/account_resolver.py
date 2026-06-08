"""Account resolver - validates and resolves cloud account context."""
from __future__ import annotations

import logging
import re

import boto3

from .models import AccountContext
from .constants import ACCOUNTS_TABLE, TIPS_TABLE

logger = logging.getLogger(__name__)

# Account ID format patterns
_AWS_PATTERN = re.compile(r"^\d{12}$")
_AZURE_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_GCP_PATTERN = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")


def validate_account_format(account_id: str) -> str:
    """Validate account ID format and return the provider type.

    Returns:
        'aws', 'azure', or 'gcp'

    Raises:
        ValueError: If the account ID doesn't match any valid format.
    """
    if not account_id or not isinstance(account_id, str):
        raise ValueError(
            "Account ID is required. Expected: AWS (12 digits), Azure (UUID), or GCP (project ID)."
        )

    account_id = account_id.strip()

    if _AWS_PATTERN.match(account_id):
        return "aws"
    if _AZURE_PATTERN.match(account_id):
        return "azure"
    if _GCP_PATTERN.match(account_id):
        return "gcp"

    raise ValueError(
        "Invalid account ID format. Expected: AWS (12 digits), Azure (UUID), or GCP (6-30 char lowercase project ID)."
    )


def resolve_account(account_id: str, member_email: str) -> AccountContext:
    """Resolve full account context from DynamoDB.

    Validates format, queries Accounts table, loads supported services from Tips_Table.
    """
    cloud_provider = validate_account_format(account_id)

    dynamodb = boto3.resource("dynamodb")

    # Query Accounts table for account metadata
    accounts_table = dynamodb.Table(ACCOUNTS_TABLE)
    try:
        response = accounts_table.get_item(Key={"accountId": account_id})
        item = response.get("Item")
    except Exception as e:
        logger.error(f"Failed to query accounts table: {e}")
        raise ValueError("Unable to resolve account. Please try again.") from None

    if not item:
        raise ValueError("Account not connected. Please add the account first.")

    account_name = item.get("accountName", account_id)
    provider_config = item.get("providerConfig", {})

    # Load supported services from Tips_Table
    supported_services = _load_supported_services(dynamodb)

    return AccountContext(
        account_id=account_id,
        account_name=account_name,
        cloud_provider=cloud_provider,
        member_email=member_email,
        supported_services=supported_services,
        provider_config=provider_config,
    )


def _load_supported_services(dynamodb) -> list[str]:
    """Load supported service categories from Tips_Table."""
    try:
        tips_table = dynamodb.Table(TIPS_TABLE)
        response = tips_table.scan(
            ProjectionExpression="service",
            Select="SPECIFIC_ATTRIBUTES",
        )
        items = response.get("Items", [])
        services = sorted(set(item.get("service", "") for item in items if item.get("service")))
        return services
    except Exception as e:
        logger.warning(f"Failed to load supported services: {e}")
        return []
