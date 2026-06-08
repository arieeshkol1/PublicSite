"""Structured output validator - JSON schema validation for internal state passing."""
from __future__ import annotations

import json
import logging
from typing import Any

from .constants import CLASSIFICATION_SCHEMA

logger = logging.getLogger(__name__)


def validate_json_output(data: Any, schema: dict | None = None) -> tuple[bool, str]:
    """Validate data against a JSON schema.

    Returns (is_valid, error_message).
    """
    if schema is None:
        schema = CLASSIFICATION_SCHEMA

    if data is None:
        return False, "Output is None"

    # Check type
    expected_type = schema.get("type", "object")
    if expected_type == "object" and not isinstance(data, dict):
        return False, f"Expected object, got {type(data).__name__}"

    # Check required fields
    required_fields = schema.get("required", [])
    if isinstance(data, dict):
        missing = [f for f in required_fields if f not in data]
        if missing:
            return False, f"Missing required fields: {missing}"

    # Check property constraints
    properties = schema.get("properties", {})
    if isinstance(data, dict):
        for field, constraints in properties.items():
            if field not in data:
                continue

            value = data[field]

            # Enum check
            if "enum" in constraints and value not in constraints["enum"]:
                return False, f"Field '{field}' value '{value}' not in enum {constraints['enum']}"

            # Type check
            field_type = constraints.get("type")
            if field_type == "string" and not isinstance(value, str):
                return False, f"Field '{field}' expected string, got {type(value).__name__}"
            elif field_type == "number" and not isinstance(value, (int, float)):
                return False, f"Field '{field}' expected number, got {type(value).__name__}"

            # Range checks
            if "minimum" in constraints and isinstance(value, (int, float)):
                if value < constraints["minimum"]:
                    return False, f"Field '{field}' value {value} below minimum {constraints['minimum']}"
            if "maximum" in constraints and isinstance(value, (int, float)):
                if value > constraints["maximum"]:
                    return False, f"Field '{field}' value {value} above maximum {constraints['maximum']}"

    return True, ""


def validate_classification_output(data: dict) -> tuple[bool, str]:
    """Validate classification output against the classification schema."""
    return validate_json_output(data, CLASSIFICATION_SCHEMA)


def validate_with_retry(
    producer_fn,
    schema: dict | None = None,
    max_retries: int = 1,
    fallback: Any = None,
) -> Any:
    """Call producer_fn, validate output, retry on failure, fallback on final failure.

    Args:
        producer_fn: Callable that produces the data to validate
        schema: JSON schema to validate against
        max_retries: Number of retries on validation failure
        fallback: Value to return if all attempts fail
    """
    for attempt in range(max_retries + 1):
        try:
            result = producer_fn()

            # If result is a string, try to parse as JSON
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    if attempt < max_retries:
                        logger.warning(f"Output not valid JSON (attempt {attempt + 1}), retrying...")
                        continue
                    logger.warning("Output not valid JSON, using fallback")
                    return fallback

            is_valid, error = validate_json_output(result, schema)
            if is_valid:
                return result

            if attempt < max_retries:
                logger.warning(f"Validation failed (attempt {attempt + 1}): {error}, retrying...")
            else:
                logger.warning(f"Validation failed after all attempts: {error}, using fallback")
                return fallback

        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"Producer failed (attempt {attempt + 1}): {e}, retrying...")
            else:
                logger.warning(f"Producer failed after all attempts: {e}, using fallback")
                return fallback

    return fallback
