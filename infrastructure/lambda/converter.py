# converter.py — hardened convert launcher (TIFF->RAW) via ECS
import os, json, time, uuid
from typing import Dict, Any, List
import boto3
from botocore.exceptions import ClientError

ecs = boto3.client("ecs")
s3 = boto3.client("s3")

# === ENV ===
CLUSTER_ARN = os.environ.get("CONVERT_CLUSTER_ARN") or os.environ.get("ECS_CLUSTER_ARN") or ""
TASK_DEF_ARN = os.environ.get("CONVERT_TASK_DEF_ARN") or os.environ.get("TASK_DEF_ARN") or ""
SUBNETS = (os.environ.get("SUBNET_IDS") or "").split(",") if os.environ.get("SUBNET_IDS") else []
SEC_GROUPS = (os.environ.get("SECURITY_GROUP_IDS") or "").split(",") if os.environ.get("SECURITY_GROUP_IDS") else []
ASSIGN_PUBLIC_IP = os.environ.get("ASSIGN_PUBLIC_IP","DISABLED")

OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET","")
INPUT_BUCKET  = os.environ.get("INPUT_BUCKET","")

def _resp(code:int, body:Dict[str,Any]):
    return {
        "statusCode": code,
        "headers": {
            "Content-Type":"application/json",
            "Access-Control-Allow-Origin":"*",
            "Access-Control-Allow-Headers":"Content-Type",
            "Access-Control-Allow-Methods":"OPTIONS,GET,POST",
        },
        "body": json.dumps(body)
    }

def _json(event) -> Dict[str,Any]:
    try:
        if event.get("body"):
            return json.loads(event["body"])
    except Exception:
        pass
    return {}

def _validate_inputs(payload:Dict[str,Any]) -> Dict[str,Any]:
    # required: keys (tiles or a single object), format must be RAW
    keys = payload.get("keys") or []
    key  = payload.get("key")
    if key and not keys:
        keys = [key]
    if not keys:
        raise ValueError("Missing 'keys' list or 'key'")
    # enforce RAW
    fmt = (payload.get("format") or payload.get("fmt") or "raw").lower()
    if fmt in ("jp2","jpeg2000","jp2000"):
        raise ValueError("format=jp2 is not allowed for convert; use /split for JP2 tiling")
    if fmt not in ("raw","tiff","tif"):
        # We allow tiff as an intermediate, but we ALWAYS require RAW emission as final safe artifact.
        fmt = "raw"
    tiles = int(payload.get("tiles") or 16)
    if tiles < 1:
        tiles = 1
    # preview is OFF unless explicitly allowed
    preview = bool(payload.get("preview")) and False  # force False
    return {"keys":keys, "fmt":fmt, "tiles":tiles, "preview":preview}

def _launch_task(job_id:str, item_key:str, fmt:str, tiles:int) -> Dict[str,Any]:
    # All tasks receive explicit "no JP2 under convert" and "RAW required" flags
    overrides = {
        "containerOverrides": [{
            "name": os.environ.get("CONVERT_CONTAINER_NAME","converter"),
            "environment": [
                {"name":"INPUT_BUCKET", "value": INPUT_BUCKET},
                {"name":"OUTPUT_BUCKET","value": OUTPUT_BUCKET},
                {"name":"JOB_ID","value": job_id},
                {"name":"ITEM_KEY","value": item_key},
                {"name":"TILES","value": str(tiles)},
                {"name":"PREVIEW","value": "false"},
                {"name":"OUTPUT_FMT","value": fmt},          # raw or tiff
                {"name":"REQUIRE_RAW","value": "true"},      # must emit .bin + .hdr
                {"name":"DISALLOW_JP2_UNDER_CONVERT","value":"true"},
                {"name":"OUTPUT_LAYOUT","value":"flat"},     # flat under tiles/<jobId>/
            ]
        }]
    }
    netconf = {"assignPublicIp": ASSIGN_PUBLIC_IP}
    if SUBNETS: netconf["subnets"] = SUBNETS
    if SEC_GROUPS: netconf["securityGroups"] = SEC_GROUPS

    resp = ecs.run_task(
        cluster=CLUSTER_ARN,
        taskDefinition=TASK_DEF_ARN,
        launchType="FARGATE",
        networkConfiguration={"awsvpcConfiguration": netconf},
        overrides=overrides,
        count=1,
    )
    return resp

def handler(event, context):
    try:
        if event.get("httpMethod") == "OPTIONS":
            return _resp(200, {"ok": True})
        if event.get("httpMethod") not in ("POST","GET"):
            return _resp(405, {"error":"method not allowed"})

        payload = _json(event) if event.get("httpMethod")=="POST" else {}
        v = _validate_inputs(payload)

        job_id = f"convert-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
        # Launch per key
        results: List[Dict[str,Any]] = []
        for k in v["keys"]:
            r = _launch_task(job_id, k, v["fmt"], v["tiles"])
            results.append(r)

        # Write a small manifest that encodes RAW requirement
        manifest_key = f"manifests/{job_id}.json"
        manifest = {
            "job_id": job_id,
            "keys": v["keys"],
            "tiles": v["tiles"],
            "format_requested": v["fmt"],
            "require_raw": True,
            "output_expectation": {
                "raw_pairs": v["tiles"],   # .bin & .hdr per tile
                "layout": "tiles/{job_id}/",
                "forbid_jp2_under_convert": True
            },
            "created_at": int(time.time())
        }
        s3.put_object(Bucket=OUTPUT_BUCKET, Key=manifest_key, Body=json.dumps(manifest).encode("utf-8"), ContentType="application/json")

        ok = [x for x in results if x.get("tasks")]
        err = [] if ok else results
        return _resp(200 if ok else 502, {
            "job_id": job_id,
            "launched": len(ok),
            "failed": len(err),
            "manifest": {"bucket": OUTPUT_BUCKET, "key": manifest_key},
            "items": [{"tasks": [t.get("taskArn") for t in r.get("tasks", [])]} for r in results]
        })
    except ValueError as ve:
        return _resp(400, {"error": str(ve)})
    except ClientError as ce:
        return _resp(502, {"error":"AWS error", "message": str(ce)})
    except Exception as e:
        return _resp(500, {"error":"converter exception", "message": str(e)})
