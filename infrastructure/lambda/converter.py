# lambda/convert.py
import os
import json
import time
import uuid
import base64
from typing import Any, Dict, List

import boto3
from botocore.exceptions import BotoCoreError, ClientError

ecs = boto3.client("ecs")

# --- Required env from stack.py ---
CLUSTER_ARN       = os.environ["ECS_CLUSTER_ARN"]
TASK_DEF_ARN      = os.environ["TASK_DEF_ARN"]
SUBNET_IDS        = [s for s in os.environ.get("SUBNET_IDS", "").split(",") if s]
SECURITY_GROUP_ID = os.environ["SECURITY_GROUP_ID"]
ASSIGN_PUBLIC_IP  = os.environ.get("ASSIGN_PUBLIC_IP", "DISABLED")  # "ENABLED" or "DISABLED"

INPUT_BUCKET      = os.environ["INPUT_BUCKET"]
OUTPUT_BUCKET     = os.environ["OUTPUT_BUCKET"]

# Optional default for the tiler (can be overridden per-task from env)
DEFAULT_CREATE_OPTS = os.environ.get(
    "CREATE_OPTS",
    "TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=2"
)

# ---------------- HTTP helpers ----------------
def _cors_headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
    }

def _response(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {"statusCode": status, "headers": _cors_headers(), "body": json.dumps(body)}

def _parse_body(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accepts HTTP API v2 payloads:
    - event['body'] may be string, potentially base64-encoded.
    """
    body = event.get("body")
    if body is None:
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", "ignore")
    if isinstance(body, str):
        body = json.loads(body or "{}")
    return body if isinstance(body, dict) else {}

# ---------------- ECS utils ----------------
def _fmt_map(ui_format: str) -> str:
    """
    Map UI 'target_format' to tiler FORMAT_OPTION.
    UI may send: "TIFF", "JPEG2000", "RAW" (future)
    """
    ui = (ui_format or "").strip().upper()
    if ui in ("TIFF", "TIF", "GTIFF", "GEOTIFF"):
        return "tiff"
    if ui in ("JPEG2000", "JP2", "KEEP", "JPEG-2000"):
        return "keep"
    if ui in ("RAW", "ENVI"):
        return "raw"  # tiler can decide to raise if unsupported
    # Default to tiff (safest)
    return "tiff"

def _grid_from_tiles(tiles: int) -> int:
    if tiles <= 1:
        return 1
    # prefer perfect squares (2x2, 3x3, 4x4…)
    g = int(round(tiles ** 0.5))
    return max(1, g)

def _run_task_for_key(
    key: str,
    fmt: str,
    tiles_total: int,
    tiles_grid: int,
    job_id: str,
) -> Dict[str, Any]:
    # Per-task environment passed to container
    env = [
        {"name": "INPUT_BUCKET",  "value": INPUT_BUCKET},
        {"name": "OUTPUT_BUCKET", "value": OUTPUT_BUCKET},
        {"name": "INPUT_KEY",     "value": key},
        {"name": "FORMAT_OPTION", "value": fmt},
        {"name": "TILES_TOTAL",   "value": str(tiles_total)},
        {"name": "TILES_GRID",    "value": str(tiles_grid)},
        {"name": "JOB_ID",        "value": job_id},
        {"name": "CREATE_OPTS",   "value": DEFAULT_CREATE_OPTS},
    ]

    params = {
        "cluster": CLUSTER_ARN,
        "taskDefinition": TASK_DEF_ARN,
        "launchType": "FARGATE",
        "networkConfiguration": {
            "awsvpcConfiguration": {
                "subnets": SUBNET_IDS,
                "securityGroups": [SECURITY_GROUP_ID],
                "assignPublicIp": ASSIGN_PUBLIC_IP,  # "ENABLED" for public subnets
            }
        },
        "overrides": {
            "containerOverrides": [
                {"name": "tiler", "environment": env}
            ]
        }
    }

    try:
        resp = ecs.run_task(**params)
    except (BotoCoreError, ClientError) as e:
        return {"key": key, "error": f"ecs.run_task failed: {e.__class__.__name__}: {str(e)}"}

    failures = resp.get("failures") or []
    tasks = resp.get("tasks") or []
    if failures:
        return {"key": key, "error": f"RunTask failure: {failures}"}
    if not tasks:
        return {"key": key, "error": "RunTask returned no tasks"}

    arn = tasks[0].get("taskArn")
    return {"key": key, "taskArn": arn}

# ---------------- Lambda handler ----------------
def handler(event, _ctx):
    # Handle CORS preflight (OPTIONS)
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return _response(200, {"ok": True})

    body = _parse_body(event)
    keys: List[str] = body.get("keys") or []
    target_fmt = body.get("target_format") or body.get("format")  # UI may send either
    tiles = int(body.get("tiles") or body.get("tilesTotal") or 1)

    if not keys:
        return _response(400, {"error": "No input keys provided"})

    fmt = _fmt_map(target_fmt or "TIFF")
    grid = _grid_from_tiles(tiles)

    # Multi-file submission → one Fargate task per file
    job_id = f"convert-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
    results: List[Dict[str, Any]] = []

    for k in keys:
        r = _run_task_for_key(k, fmt, tiles, grid, job_id)
        results.append(r)

    # Summarize response for the UI
    ok = [r for r in results if "taskArn" in r]
    err = [r for r in results if "error" in r]

    status = 200 if ok else 500
    return _response(status, {
        "job_id": job_id,
        "submitted": len(results),
        "launched": len(ok),
        "failed": len(err),
        "items": results
    })
