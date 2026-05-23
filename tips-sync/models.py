"""
Data models for Tips Sync.

Contains TipRecord dataclass, content hash computation,
and tip ID generation utilities.
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional, Set


@dataclass
class TipRecord:
    """Represents a single cost optimization tip in the Tips_Table.

    Contains all required content fields, operational fields with defaults
    for new AWS-sourced tips, and sync metadata fields.
    """

    # Required content fields
    id: str
    service: str
    category: str
    title: str
    description: str
    estimatedSavings: str
    difficulty: str
    automatedCheck: str

    # Sync metadata fields
    contentHash: str = ""
    syncSource: str = ""
    lastSyncedAt: str = ""
    version: int = 1

    # Operational fields with defaults for new AWS-sourced tips
    checkImplemented: bool = False
    actionType: str = "advisory"
    actionLabel: str = "View Details"
    level: int = 3

    # Optional operational fields (preserved during updates)
    actionTarget: Optional[str] = None
    serviceKey: Optional[str] = None
    implementedInAct: Optional[bool] = None
    implementedInScheduler: Optional[bool] = None


def compute_content_hash(
    title: str, description: str, estimated_savings: str, automated_check: str
) -> str:
    """Compute SHA-256 hash of content fields for delta detection.

    The hash is used to determine whether a tip's content has changed
    since the last sync, avoiding unnecessary DynamoDB writes.

    Args:
        title: Tip title.
        description: Tip description.
        estimated_savings: Estimated savings string (e.g., "20-40%").
        automated_check: Automated check implementation details.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    content = f"{title}|{description}|{estimated_savings}|{automated_check}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def generate_tip_id(service: str, existing_ids: Set[str]) -> str:
    """Generate a unique sequential tip ID for a given service.

    Produces IDs in the format {service_lowercase}-{sequential_number},
    finding the next available number that doesn't collide with existing IDs.

    Args:
        service: AWS service name (e.g., "EC2", "S3").
        existing_ids: Set of existing tip IDs to check for uniqueness.

    Returns:
        A unique tip ID string (e.g., "ec2-042").
    """
    service_lower = service.lower()
    prefix = f"{service_lower}-"

    # Find the highest existing number for this service
    max_number = 0
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")

    for existing_id in existing_ids:
        match = pattern.match(existing_id)
        if match:
            num = int(match.group(1))
            if num > max_number:
                max_number = num

    # Generate the next sequential ID
    next_number = max_number + 1
    new_id = f"{prefix}{next_number:03d}"

    # Ensure uniqueness (handles edge cases with non-standard numbering)
    while new_id in existing_ids:
        next_number += 1
        new_id = f"{prefix}{next_number:03d}"

    return new_id
