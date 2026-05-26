"""Terraform identifier conversion for AWS resource IDs.

Converts AWS resource identifiers (e.g., i-0abc123def, vol-xxx, eipalloc-xxx)
to valid Terraform identifiers matching the pattern [a-z][a-z0-9_-]*.

Terraform identifiers must:
- Start with a lowercase letter
- Contain only lowercase letters, digits, underscores, and hyphens
- Be deterministic (same input always produces same output)
"""

import re


# Pattern for valid Terraform identifiers
_TERRAFORM_ID_PATTERN = re.compile(r'^[a-z][a-z0-9_-]*$')

# Characters allowed in Terraform identifiers (after the first character)
_ALLOWED_CHARS = set('abcdefghijklmnopqrstuvwxyz0123456789_-')

# Characters allowed as the first character
_ALLOWED_FIRST_CHARS = set('abcdefghijklmnopqrstuvwxyz')


def to_terraform_identifier(aws_id: str) -> str:
    """Convert an AWS resource ID to a valid Terraform identifier.

    Transforms AWS resource identifiers like 'i-0abc123def', 'vol-xxx',
    'eipalloc-xxx' into valid Terraform identifiers that match the pattern
    [a-z][a-z0-9_-]*.

    The conversion is deterministic: the same input always produces the same
    output.

    Args:
        aws_id: An AWS resource identifier string.

    Returns:
        A valid Terraform identifier string.

    Raises:
        ValueError: If aws_id is empty or None.

    Examples:
        >>> to_terraform_identifier('i-0abc123def')
        'i-0abc123def'
        >>> to_terraform_identifier('vol-0abc123')
        'vol-0abc123'
        >>> to_terraform_identifier('eipalloc-0abc123')
        'eipalloc-0abc123'
        >>> to_terraform_identifier('arn:aws:ec2:us-east-1:123456789012:instance/i-0abc')
        'arn_aws_ec2_us-east-1_123456789012_instance_i-0abc'
    """
    if not aws_id:
        raise ValueError("AWS resource ID cannot be empty or None")

    # Lowercase the entire input for consistency
    result = aws_id.lower()

    # Replace characters that aren't allowed with underscores
    converted = []
    for char in result:
        if char in _ALLOWED_CHARS:
            converted.append(char)
        else:
            # Replace disallowed characters (colons, slashes, dots, etc.)
            # with underscores
            converted.append('_')

    result = ''.join(converted)

    # Collapse consecutive underscores into a single underscore
    result = re.sub(r'_+', '_', result)

    # Strip leading/trailing underscores and hyphens
    result = result.strip('_-')

    # Ensure the identifier starts with a lowercase letter
    if not result:
        # If everything was stripped, use a fallback prefix
        result = 'res'
    elif result[0] not in _ALLOWED_FIRST_CHARS:
        # Prepend 'r' prefix if the first character is not a letter
        result = 'r' + result

    # Final validation - should always pass given the logic above
    assert _TERRAFORM_ID_PATTERN.match(result), (
        f"Generated identifier '{result}' does not match Terraform pattern"
    )

    return result


def is_valid_terraform_identifier(identifier: str) -> bool:
    """Check if a string is a valid Terraform identifier.

    Args:
        identifier: The string to validate.

    Returns:
        True if the string matches [a-z][a-z0-9_-]*, False otherwise.
    """
    if not identifier:
        return False
    return bool(_TERRAFORM_ID_PATTERN.match(identifier))
