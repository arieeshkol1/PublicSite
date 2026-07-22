"""
Connector Configuration Validator.
Validates Connector_Config bodies for the Admin Connector Configuration feature.
"""

import re


# Validation patterns
PROVIDER_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]{1,30}$')
CONNECTOR_CLASS_PATTERN = re.compile(r'^[a-z_]+\.[A-Za-z]+$')
CACHE_PK_PREFIX_PATTERN = re.compile(r'^[A-Z][A-Z0-9_]*$')
VALID_AUTH_TYPES = {'iam_role', 'service_principal', 'service_account', 'api_key', 'oauth2'}

# Required top-level fields
REQUIRED_FIELDS = [
    'providerKey', 'displayName', 'iconUrl', 'authType', 'syncFields',
    'tipsRepository', 'invoiceFields', 'cacheSchema', 'supportedOperations',
    'stalenessThresholdHours', 'costEstimationRates', 'cloud', 'connectorClass'
]


def validate_connector_config(body: dict, is_update: bool = False) -> list:
    """Validate a connector config body.

    Collects ALL validation errors and returns them as a list.
    An empty list means the body is valid.

    Args:
        body: The connector configuration dictionary to validate.
        is_update: If True, skips providerKey requirement (key comes from path).

    Returns:
        List of error message strings. Empty list means valid.
    """
    errors = []

    if not isinstance(body, dict):
        return ['Request body must be a JSON object']

    # Check required fields
    fields_to_check = REQUIRED_FIELDS if not is_update else [f for f in REQUIRED_FIELDS if f != 'providerKey']
    for field in fields_to_check:
        if field not in body or body[field] is None:
            errors.append(f'{field}: is required')

    # Validate providerKey format
    provider_key = body.get('providerKey')
    if provider_key is not None:
        if not isinstance(provider_key, str) or not PROVIDER_KEY_PATTERN.match(provider_key):
            errors.append('providerKey: must match pattern ^[a-z][a-z0-9_]{1,30}$')

    # Validate authType enum
    auth_type = body.get('authType')
    if auth_type is not None:
        if auth_type not in VALID_AUTH_TYPES:
            errors.append(f'authType: must be one of {sorted(VALID_AUTH_TYPES)}')

    # Validate stalenessThresholdHours
    staleness = body.get('stalenessThresholdHours')
    if staleness is not None:
        if not isinstance(staleness, int) or staleness < 1 or staleness > 720:
            errors.append('stalenessThresholdHours: must be a positive integer between 1 and 720')

    # Validate supportedOperations
    supported_ops = body.get('supportedOperations')
    if supported_ops is not None:
        if not isinstance(supported_ops, list) or len(supported_ops) == 0:
            errors.append('supportedOperations: must be a non-empty list of strings')
        elif not all(isinstance(op, str) for op in supported_ops):
            errors.append('supportedOperations: must be a non-empty list of strings')

    # Validate cacheSchema.pkPrefix
    cache_schema = body.get('cacheSchema')
    if cache_schema is not None:
        if isinstance(cache_schema, dict):
            pk_prefix = cache_schema.get('pkPrefix')
            if pk_prefix is not None:
                if not isinstance(pk_prefix, str) or not CACHE_PK_PREFIX_PATTERN.match(pk_prefix):
                    errors.append('cacheSchema.pkPrefix: must be a non-empty uppercase string matching ^[A-Z][A-Z0-9_]*$')
            else:
                errors.append('cacheSchema.pkPrefix: is required')
        else:
            errors.append('cacheSchema: must be an object with pkPrefix, skFormat, and fieldNames')

    # Validate connectorClass format
    connector_class = body.get('connectorClass')
    if connector_class is not None:
        if not isinstance(connector_class, str) or not CONNECTOR_CLASS_PATTERN.match(connector_class):
            errors.append('connectorClass: must match pattern ^[a-z_]+\\.[A-Za-z]+$')

    return errors
