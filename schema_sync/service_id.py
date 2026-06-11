"""
Service ID Module — Universal Service ID system for cross-layer referencing.

Provides canonical <provider>:<service-slug> identifiers used across
Tips, Tools, and Cost Cache layers.
"""

import re

# Supported providers
VALID_PROVIDERS = ("aws", "gcp", "azure", "openai")

# Regex for a valid service slug: lowercase kebab-case starting with a letter
_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

# Full Service ID pattern
_SERVICE_ID_PATTERN = re.compile(
    r"^(aws|gcp|azure|openai):[a-z][a-z0-9]*(-[a-z0-9]+)*$"
)

# Authoritative Service Registry
SERVICE_REGISTRY: dict[str, dict] = {
    "aws:ec2": {
        "displayName": "Amazon EC2",
        "provider": "aws",
        "aliases": ["Amazon EC2", "EC2", "Elastic Compute Cloud"],
    },
    "aws:s3": {
        "displayName": "Amazon S3",
        "provider": "aws",
        "aliases": ["Amazon Simple Storage Service", "Amazon S3", "S3"],
    },
    "aws:rds": {
        "displayName": "Amazon RDS",
        "provider": "aws",
        "aliases": ["Amazon Relational Database Service", "Amazon RDS", "RDS"],
    },
    "aws:lambda": {
        "displayName": "AWS Lambda",
        "provider": "aws",
        "aliases": ["AWS Lambda", "Lambda"],
    },
    "aws:ebs": {
        "displayName": "Amazon EBS",
        "provider": "aws",
        "aliases": ["EC2 - Other", "EBS", "Elastic Block Store"],
    },
    "aws:vpc": {
        "displayName": "Amazon VPC",
        "provider": "aws",
        "aliases": ["Amazon Virtual Private Cloud", "VPC"],
    },
    "aws:cloudfront": {
        "displayName": "Amazon CloudFront",
        "provider": "aws",
        "aliases": ["Amazon CloudFront", "CloudFront"],
    },
    "gcp:compute-engine": {
        "displayName": "Google Compute Engine",
        "provider": "gcp",
        "aliases": ["Compute Engine", "GCE"],
    },
    "azure:virtual-machines": {
        "displayName": "Azure Virtual Machines",
        "provider": "azure",
        "aliases": ["Azure VMs", "Virtual Machines"],
    },
    "openai:api": {
        "displayName": "OpenAI API",
        "provider": "openai",
        "aliases": ["OpenAI", "GPT API"],
    },
}


def validate_service_id(service_id: str) -> bool:
    """
    Validate that a string is a valid Service ID.

    Format: <provider>:<service-slug>
    - provider: one of aws, gcp, azure, openai
    - service-slug: lowercase kebab-case starting with a letter

    Args:
        service_id: The string to validate.

    Returns:
        True if valid, False otherwise.
    """
    if not isinstance(service_id, str):
        return False
    return bool(_SERVICE_ID_PATTERN.match(service_id))


def resolve_alias(alias: str) -> str | None:
    """
    Resolve a display name or alias to its canonical Service_ID.

    Args:
        alias: A display name or known alias (e.g., "Amazon EC2", "S3").

    Returns:
        The canonical Service_ID string, or None if no match found.
    """
    if not isinstance(alias, str):
        return None
    # Check display names and aliases
    for service_id, entry in SERVICE_REGISTRY.items():
        if alias == entry["displayName"]:
            return service_id
        if alias in entry["aliases"]:
            return service_id
    return None


def get_provider(service_id: str) -> str:
    """
    Extract the provider from a Service_ID.

    Args:
        service_id: A valid Service_ID string (e.g., 'aws:ec2').

    Returns:
        The provider portion (e.g., 'aws').

    Raises:
        ValueError: If the service_id format is invalid.
    """
    if not validate_service_id(service_id):
        raise ValueError(f"Invalid Service_ID format: {service_id}")
    return service_id.split(":")[0]
