import os, json, time, uuid, base64
from typing import Any, Dict, List, Tuple
import boto3
from botocore.exceptions import BotoCoreError, ClientError

ecs = boto3.client("ecs")

# ---------- helpers ----------
def _cors() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
    }

def _resp(code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {"statusCode": code, "headers": _cors(), "body": json.dumps(body)}

def _parse_event(event: Dict[str, Any]) -> Dict[str, Any]:
    body = event.get("body")
    if body is None:
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", "ignore")
    if isinstance(body, str):
        body = json.loads(body or "{}")
    return body if isinstance(body, dict) else {}

def _fmt_map(fmt: str) -> str:
    u = (fmt or "").strip().upper()
    if u in ("TIFF", "TIF", "GTIFF", "GEOTIFF"): return "tiff"
    if u in ("JPEG2000", "JP2", "KEEP", "JPEG-2000"): return "keep"
    if u in ("RAW", "ENVI"): return "raw"
    return "tiff"

def _grid(tiles: int) -> int:
    if tiles <= 1: return 1
    g = int(round(tiles ** 0.5))
    return max(1, g)

# ---------- config ----------
REQ_ENVS = [
    "ECS_CLUSTER_ARN", "TASK_DEF_ARN", "SUBNET_IDS", "SECURITY_GROUP_ID",
    "INPUT_BUCKET", "OUTPUT_BUCKET"
]

# Hard-safe default create opts (prevents GDAL predictor error)
SAFE_CREATE_OPTS = "TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=1"

# If the container supports it, these further enforce safety
EXTRA_SAFETY_ENVS = {
    "PREDICTOR_POLICY": "FORCE_1",      # ask entrypoint to drop any PREDICTOR=2 it might add
    "TIFF_FORCE_16BIT": "true",         # upcast 12-bit → 16-bit when applicable
    "SANITIZE_PREDICTOR": "1",          # generic flag many wrappers use
}

def _cfg() -> Tuple[Dict[str, Any], List[str]]:
    missing: List[str] = []
    env = os.environ
    for k in REQ_ENVS:
        if not env.get(k): missing.append(k)
    subnets = [s for s in (env.get("SUBNET_IDS") or "").split(",") if s]
    if not subnets: missing.append("SUBNET_IDS(empty)")

    # If CREATE_OPTS env exists but includes PREDICTOR=2, remove it here and force 1.
    create_opts_raw = env.get("CREATE_OPTS", SAFE_CREATE_OPTS)
    create_opts_clean = ",".join([
        kv for kv in (x.strip() for x in create_opts_raw.split(","))
        if kv and not kv.upper().startswith("PREDICTOR=")
    ])
    if create_opts_clean:
        create_opts_clean = create_opts_clean + ",PREDICTOR=1"
    else:
        create_opts_clean = SAFE_CREATE_OPTS

    return {
        "cluster": env.get("ECS_CLUSTER_ARN"),
        "task_def": env.get("TASK_DEF_ARN"),
        "subnets": subnets,
        "sg": env.get("SECURITY_GROUP_ID"),
        "assign_public_ip": env.get("ASSIGN_PUBLIC_IP", "DISABLED"),
        "input_bucket": env.get("INPUT_BUCKET"),
        "output_bucket": env.get("OUTPUT_BUCKET"),
        "create_opts": create_opts_clean,
    }, missing


def _run_task(cfg: Dict[str, Any], key: str, fmt: str, tiles_total: int, tiles_grid: int, job_id: str) -> Dict[str, Any]:
    env = [
        {"name": "INPUT_BUCKET",  "value": cfg["input_bucket"]},
        {"name": "OUTPUT_BUCKET", "value": cfg["output_bucket"]},
        {"name": "INPUT_KEY",     "value": key},
        {"name": "FORMAT_OPTION", "value": fmt},
        {"name": "TILES_TOTAL",   "value": str(tiles_total)},
        {"name": "TILES_GRID",    "value": str(tiles_grid)},
        {"name": "JOB_ID",        "value": job_id},
        {"name": "CREATE_OPTS",   "value": cfg["create_opts"]},
    ]

    # Add extra safety envs to override any hardcoded predictor=2 in the container
    for k, v in EXTRA_SAFETY_ENVS.items():
        env.append({"name": k, "value": v})

    params = {
        "cluster": cfg["cluster"],
        "taskDefinition": cfg["task_def"],
        "launchType": "FARGATE",
        "networkConfiguration": {
            "awsvpcConfiguration": {
                "subnets": cfg["subnets"],
                "securityGroups": [cfg["sg"]],
                "assignPublicIp": cfg["assign_public_ip"],
            }
        },
        "overrides": {"containerOverrides": [{"name": "tiler", "environment": env}]}
    }
    try:
        r = ecs.run_task(**params)
    except (BotoCoreError, ClientError) as e:
        return {"key": key, "error": f"ecs.run_task failed: {e.__class__.__name__}: {str(e)}"}

    if r.get("failures"):
        return {"key": key, "error": f"RunTask failure: {r['failures']}"}
    tasks = r.get("tasks") or []
    if not tasks:
        return {"key": key, "error": "RunTask returned no tasks"}
    return {"key": key, "taskArn": tasks[0].get("taskArn")}


# ---------- handler ----------
def handler(event, _ctx):
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return _resp(200, {"ok": True})

    cfg, missing = _cfg()
    if missing:
        return _resp(500, {"error": "Missing required environment variables", "missing": missing})

    body = _parse_event(event)
    keys = body.get("keys") or ([] if not body.get("key") else [body["key"]])
    if not keys:
        return _resp(400, {"error": "No input keys provided"})

    fmt = _fmt_map(body.get("target_format") or body.get("format") or "TIFF")
    tiles = int(body.get("tiles") or body.get("tilesTotal") or 1)
    grid = _grid(tiles)

    job_id = f"convert-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
    results = [_run_task(cfg, k, fmt, tiles, grid, job_id) for k in keys]

    ok = [r for r in results if "taskArn" in r]
    err = [r for r in results if "error" in r]
    return _resp(200 if ok else 502, {
        "job_id": job_id,
        "submitted": len(results),
        "launched": len(ok),
        "failed": len(err),
        "items": results
    })
