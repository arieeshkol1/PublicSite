"""
provider_router.py — Cloud Provider Router for AI Chat.

Routes AI chat queries to the correct cloud connector based on the
account's `cloudProvider` field in MemberPortal-Accounts DynamoDB table.
"""

import os
import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

ACCOUNTS_TABLE_NAME = os.environ.get('ACCOUNTS_TABLE_NAME', 'MemberPortal-Accounts')

# Supported providers — default to "aws" for backward compatibility
SUPPORTED_PROVIDERS = {'aws', 'azure', 'gcp', 'openai'}
DEFAULT_PROVIDER = 'aws'


def _route_to_connector(account_id: str, member_email: str) -> tuple:
    """
    Reads cloudProvider from MemberPortal-Accounts table.
    Returns (provider_name, credentials_dict).
    Defaults to "aws" if field is missing/empty.

    Args:
        account_id: The cloud account identifier (AWS 12-digit, Azure UUID, or GCP project ID)
        member_email: The authenticated member's email (partition key)

    Returns:
        Tuple of (provider_name: str, credentials_dict: dict)
        - provider_name is one of "aws", "azure", "gcp"
        - credentials_dict contains provider-specific credential fields

    Raises:
        ValueError: If account is not found in the table
        RuntimeError: If DynamoDB read fails
    """
    dynamodb = boto3.resource('dynamodb')
    accounts_table = dynamodb.Table(ACCOUNTS_TABLE_NAME)

    try:
        response = accounts_table.get_item(
            Key={'memberEmail': member_email, 'accountId': account_id}
        )
    except ClientError as e:
        logger.error(f"DynamoDB read error in provider router: {e}")
        raise RuntimeError(f"Failed to read account record: {e}")

    account = response.get('Item')
    if not account:
        raise ValueError(f"Account {account_id} not found for member {member_email}")

    # Read cloudProvider, default to "aws" if missing or empty
    cloud_provider = (account.get('cloudProvider') or '').strip().lower()
    if not cloud_provider or cloud_provider not in SUPPORTED_PROVIDERS:
        cloud_provider = DEFAULT_PROVIDER

    # Extract provider-specific credentials
    credentials = _extract_credentials(cloud_provider, account, member_email)

    return (cloud_provider, credentials)


def _extract_credentials(provider: str, account: dict, member_email: str) -> dict:
    """
    Extract provider-specific credentials from the account item.

    Args:
        provider: The resolved provider name ("aws", "azure", "gcp")
        account: The full DynamoDB account item
        member_email: The member's email (used for AWS external ID derivation)

    Returns:
        Dict with provider-specific credential fields ready for connector use
    """
    if provider == 'aws':
        # AWS uses STS AssumeRole — credentials are derived from account_id + member_email
        return {
            'account_id': account['accountId'],
            'member_email': member_email,
            'session_name': 'SlashMyBillAIChat',
        }

    elif provider == 'azure':
        # Azure stores Service Principal credentials in the 'credentials' map
        stored = account.get('credentials', {})
        return {
            'tenant_id': stored.get('tenantId', ''),
            'client_id': stored.get('clientId', ''),
            'encrypted_client_secret': stored.get('encryptedClientSecret', ''),
        }

    elif provider == 'gcp':
        # GCP stores service account key fields in the 'credentials' map
        stored = account.get('credentials', {})
        return {
            'client_email': stored.get('clientEmail', ''),
            'project_id': stored.get('projectId', ''),
            'private_key_id': stored.get('privateKeyId', ''),
            'encrypted_private_key': stored.get('encryptedPrivateKey', ''),
        }

    elif provider == 'openai':
        # OpenAI stores the KMS-encrypted API key in the 'credentials' map
        stored = account.get('credentials', {})
        return {
            'encrypted_api_key': stored.get('encryptedApiKey', ''),
        }

    # Fallback — shouldn't reach here given SUPPORTED_PROVIDERS check above
    return {}
