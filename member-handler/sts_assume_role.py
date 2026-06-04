"""
sts_assume_role.py — AWS STS AssumeRole auth plugin.

Uses registry auth config to compute role ARN and external ID.
Extensible pattern: future providers add oauth2.py, jwt_auth.py, etc.
"""

import hashlib
import boto3
from provider_registry import get_config

# Hardcoded fallback values for backward compatibility during migration.
# Used only when the registry is unavailable (empty config).
_FALLBACK_ROLE_ARN_PATTERN = 'arn:aws:iam::{accountId}:role/SlashMyBill-{accountId}'
_FALLBACK_EXTERNAL_ID_DERIVATION = 'sha256_member_email'
_FALLBACK_SESSION_DURATION = 3600


def assume_role(account_id: str, member_email: str, session_name: str = 'SlashMyBill') -> dict:
    """Assume cross-account role using registry-driven config.

    Falls back to hardcoded defaults if registry is unavailable (empty config),
    ensuring backward compatibility during migration.
    """
    auth_config = get_config('aws', 'auth')

    # Fallback: if registry returns empty config, use hardcoded defaults
    if not auth_config:
        role_arn_pattern = _FALLBACK_ROLE_ARN_PATTERN
        derivation_method = _FALLBACK_EXTERNAL_ID_DERIVATION
        session_duration = _FALLBACK_SESSION_DURATION
    else:
        role_arn_pattern = auth_config['role_arn_pattern']
        derivation_method = auth_config['external_id_derivation']
        session_duration = auth_config.get('session_duration_seconds', 3600)

    # Compute role ARN from pattern
    role_arn = role_arn_pattern.format(accountId=account_id)

    # Compute external ID using configured derivation method
    if derivation_method == 'sha256_member_email':
        external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()
    else:
        raise ValueError(f"Unknown derivation method: {derivation_method}")

    # Call STS AssumeRole
    sts = boto3.client('sts')
    response = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName=session_name,
        ExternalId=external_id,
        DurationSeconds=int(session_duration)
    )
    return response['Credentials']
