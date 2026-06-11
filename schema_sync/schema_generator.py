"""
Schema Generator — Pure function that produces OpenAPI 3.0.0 from tip records.

No side effects. Takes a list of tip records (already deserialized from DynamoDB)
and returns a valid OpenAPI 3.0.0 JSON-serializable dict.
"""

import json
import logging
from collections import defaultdict

from .service_id import validate_service_id, get_provider

logger = logging.getLogger(__name__)

# The 11 existing operations that must always be present during migration
REQUIRED_OPERATION_IDS = [
    "getCostData",
    "getMonthlyComparison",
    "getEC2Instances",
    "getRDSInstances",
    "getLambdaFunctions",
    "getS3Buckets",
    "getEBSVolumes",
    "getNetworkResources",
    "getBudgets",
    "getFinOpsSettings",
    "getAWSPricing",
]


class SchemaValidationError(Exception):
    """Raised when a generated schema fails structural validation."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Schema validation failed: {errors}")


def generate_schema(tip_records: list[dict]) -> dict:
    """
    Generate an OpenAPI 3.0.0 schema from tip records.

    Args:
        tip_records: List of DynamoDB tip items (already deserialized).

    Returns:
        A valid OpenAPI 3.0.0 JSON-serializable dict.

    Raises:
        SchemaValidationError: If the generated schema fails structural validation.
    """
    # Collect tool definitions grouped by operationId
    ops_by_id: dict[str, list[dict]] = defaultdict(list)

    for record in tip_records:
        # Skip records without serviceId
        service_id = record.get("serviceId")
        if not service_id or not validate_service_id(service_id):
            if service_id:
                logger.warning(
                    "Tip record '%s' has invalid serviceId '%s', skipping",
                    record.get("id", "unknown"),
                    service_id,
                )
            else:
                logger.warning(
                    "Tip record '%s' missing serviceId, skipping",
                    record.get("id", "unknown"),
                )
            continue

        # Skip records without toolDefinition
        tool_def = record.get("toolDefinition")
        if not tool_def:
            continue

        # Validate toolDefinition has required fields
        if not _is_valid_tool_definition(tool_def):
            logger.warning(
                "Tip record '%s' has invalid toolDefinition, skipping",
                record.get("id", "unknown"),
            )
            continue

        operation_id = tool_def["operationId"]
        ops_by_id[operation_id].append(tool_def)

    # Merge and build paths
    merged_ops = merge_tool_definitions(ops_by_id)
    paths = _build_paths(merged_ops)

    schema = {
        "openapi": "3.0.0",
        "info": {
            "title": "SlashMyBill FinOps Actions",
            "version": "3.0.0",
            "description": "Auto-generated action group schema from Tips Table",
        },
        "paths": paths,
    }

    # Validate before returning
    errors = validate_schema(schema)
    if errors:
        raise SchemaValidationError(errors)

    return schema


def merge_tool_definitions(ops_by_id: dict[str, list[dict]]) -> list[dict]:
    """
    Merge multiple tool definitions sharing the same operationId.

    Uses the definition with the most parameters. Logs a warning on conflicts.

    Args:
        ops_by_id: Dict mapping operationId -> list of tool definitions.

    Returns:
        A list of merged (unique) tool definition dicts.
    """
    merged = []

    for operation_id in sorted(ops_by_id.keys()):
        definitions = ops_by_id[operation_id]
        if len(definitions) == 1:
            merged.append(definitions[0])
        else:
            # Pick the one with the most parameters.
            # Tiebreaker: sort by JSON representation for determinism.
            best = max(
                definitions,
                key=lambda d: (
                    len(d.get("parameters", [])),
                    json.dumps(d, sort_keys=True),
                ),
            )
            logger.warning(
                "operationId '%s' has %d conflicting definitions, "
                "using definition with %d parameters",
                operation_id,
                len(definitions),
                len(best.get("parameters", [])),
            )
            merged.append(best)

    return merged


def validate_schema(schema: dict) -> list[str]:
    """
    Validate schema against OpenAPI 3.0.0 structure rules.

    Returns:
        List of validation errors (empty list = valid).
    """
    errors = []

    # Check top-level fields
    if schema.get("openapi") != "3.0.0":
        errors.append("Missing or invalid 'openapi' field (must be '3.0.0')")

    info = schema.get("info")
    if not isinstance(info, dict):
        errors.append("Missing 'info' object")
    else:
        for field in ("title", "version", "description"):
            if not info.get(field):
                errors.append(f"Missing 'info.{field}'")

    paths = schema.get("paths")
    if not isinstance(paths, dict):
        errors.append("Missing 'paths' object")
    else:
        valid_methods = {"get", "post", "put", "delete", "patch", "options", "head"}
        for path_key, path_item in paths.items():
            if not isinstance(path_item, dict):
                errors.append(f"Path '{path_key}' is not a dict")
                continue
            for method, operation in path_item.items():
                if method not in valid_methods:
                    errors.append(f"Path '{path_key}' has invalid method '{method}'")
                    continue
                if not isinstance(operation, dict):
                    errors.append(
                        f"Path '{path_key}' method '{method}' is not a dict"
                    )
                    continue
                if not operation.get("operationId"):
                    errors.append(
                        f"Path '{path_key}' method '{method}' missing operationId"
                    )
                if not isinstance(operation.get("parameters", []), list):
                    errors.append(
                        f"Path '{path_key}' method '{method}' parameters is not a list"
                    )
                if not isinstance(operation.get("responses", {}), dict):
                    errors.append(
                        f"Path '{path_key}' method '{method}' responses is not a dict"
                    )
                elif not operation.get("responses"):
                    errors.append(
                        f"Path '{path_key}' method '{method}' has empty responses"
                    )

    return errors


def check_backward_compatibility(
    schema: dict, required_ops: list[str] | None = None
) -> list[str]:
    """
    Check that all required operationIds are present in the schema.

    Args:
        schema: The generated OpenAPI schema dict.
        required_ops: List of required operationIds. Defaults to REQUIRED_OPERATION_IDS.

    Returns:
        List of missing operationIds (empty = all present).
    """
    if required_ops is None:
        required_ops = REQUIRED_OPERATION_IDS

    # Collect all operationIds from the schema
    present_ops = set()
    paths = schema.get("paths", {})
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if isinstance(operation, dict) and "operationId" in operation:
                present_ops.add(operation["operationId"])

    return sorted(set(required_ops) - present_ops)


def _is_valid_tool_definition(tool_def: dict) -> bool:
    """Check that a tool definition has the minimum required fields."""
    required_fields = ("operationId", "path", "httpMethod")
    for field in required_fields:
        if not tool_def.get(field):
            return False
    return True


def _build_paths(merged_ops: list[dict]) -> dict:
    """
    Build the OpenAPI paths object from merged tool definitions.

    Produces deterministic output by sorting paths alphabetically.
    """
    paths: dict[str, dict] = {}

    for tool_def in merged_ops:
        path = tool_def["path"]
        method = tool_def["httpMethod"].lower()
        operation_id = tool_def["operationId"]

        # Build parameters list (sorted by name for determinism)
        params = []
        raw_params = tool_def.get("parameters", [])
        for p in sorted(raw_params, key=lambda x: x.get("name", "")):
            param = {
                "name": p.get("name", ""),
                "in": p.get("in", "query"),
                "required": bool(p.get("required", False)),
                "schema": {
                    "type": p.get("type", "string"),
                    "description": p.get("description", ""),
                },
            }
            params.append(param)

        operation = {
            "operationId": operation_id,
            "summary": tool_def.get("summary", ""),
            "description": tool_def.get("description", ""),
            "parameters": params,
            "responses": {"200": {"description": f"{operation_id} response"}},
        }

        paths[path] = {method: operation}

    # Sort paths for deterministic output
    return dict(sorted(paths.items()))
