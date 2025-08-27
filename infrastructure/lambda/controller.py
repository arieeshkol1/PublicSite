import os
import json
import time
import urllib.parse as up
import datetime as dt

import boto3
from botocore.exceptions import ClientError

# ===== ENV =====
REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
INPUT_BUCKET = os.environ.get("INPUT_BUCKET", "")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")               # Split SM
STATE_MACHINE_ARN_UNITE = os.environ.get("STATE_MACHINE_ARN_UNITE", "")   # Unite SM

sfn = boto3.client("stepfunctions", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)


# ===== helpers =====
def _resp(code: int, body_obj):
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body_obj),
    }


def _parse_json_body(event):
    b = event.get("body")
    if not b:
        return {}
    try:
        return json.loads(b)
    except Exception:
        return {}


def _console_sfn_link(exec_arn: str):
    return f"https://{REGION}.console.aws.amazon.com/states/home?region={REGION}#/executions/details/{up.quote(exec_arn, safe='')}"


def _console_logs_link(log_group: str | None):
    if not log_group:
        return None
    return f"https://{REGION}.console.aws.amazon.com/cloudwatch/home?region={REGION}#logsV2:log-groups/log-group/{up.quote(log_group, safe='')}"


# ===== split =====
def _split(event):
    if not STATE_MACHINE_ARN:
        return _resp(500, {"error": "STATE_MACHINE_ARN is not configured"})

    payload = _parse_json_body(event)
    input_bucket = payload.get("inputBucket") or INPUT_BUCKET
    input_key = payload.get("inputKey")
    output_bucket = payload.get("outputBucket") or OUTPUT_BUCKET
    params = payload.get("params") or {}
    tiles_total = int(params.get("tilesTotal", 16))
    tiles_grid = int(params.get("tilesGrid", max(1, int(tiles_total ** 0.5))))

    if not (input_bucket and input_key and output_bucket):
        return _resp(400, {"error": "inputBucket, inputKey, outputBucket are required"})

    job_id = payload.get("jobId") or f"split-job-{int(time.time()*1000)}"
    exec_input = {
        "jobId": job_id,
        "inputBucket": input_bucket,
        "inputKey": input_key,
        "outputBucket": output_bucket,
        "params": {"tilesTotal": tiles_total, "tilesGrid": tiles_grid},
    }

    print("SPLIT start", exec_input)

    try:
        resp = sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=job_id,
            input=json.dumps(exec_input),
        )
    except sfn.exceptions.ExecutionAlreadyExists:
        resp = sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            input=json.dumps(exec_input),
        )

    return _resp(200, {
        "executionArn": resp["executionArn"],
        "jobId": job_id,
        "expectedTiles": tiles_total,
        "links": {"execution": _console_sfn_link(resp["executionArn"])}
    })


# ===== unite =====
def _unite(event):
    if not STATE_MACHINE_ARN_UNITE:
        return _resp(500, {"error": "STATE_MACHINE_ARN_UNITE is not configured"})

    payload = _parse_json_body(event)
    output_bucket = payload.get("outputBucket") or OUTPUT_BUCKET

    tiles_prefix = payload.get("tilesPrefix")  # e.g. "tiles/<jobId>/"
    job_id = payload.get("jobId")
    manifest_key = payload.get("manifestKey")
    final_key = payload.get("finalKey")  # optional override

    # Extract jobId from manifestKey if present
    if manifest_key and not job_id:
        base = manifest_key.rsplit("/", 1)[-1]
        if base.endswith(".json"):
            job_id = base[:-5]

    if not tiles_prefix and job_id:
        tiles_prefix = f"tiles/{job_id}/"

    if not (tiles_prefix or job_id or manifest_key):
        return _resp(400, {"error": "Provide tilesPrefix or jobId or manifestKey"})

    if not job_id:
        # derive from tiles_prefix if possible
        parts = (tiles_prefix or "").strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "tiles":
            job_id = parts[1]
        else:
            job_id = f"job-{int(time.time()*1000)}"

    if not final_key:
        final_key = f"final/unite-{job_id}.jp2"

    exec_input = {
        "jobId": job_id,
        "outputBucket": output_bucket,
        "tilesPrefix": tiles_prefix,
        "manifestKey": manifest_key,
        "finalKey": final_key,
    }

    print("UNITE start", exec_input)

    try:
        resp = sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN_UNITE,
            name=f"unite-{job_id}",
            input=json.dumps(exec_input),
        )
    except sfn.exceptions.ExecutionAlreadyExists:
        resp = sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN_UNITE,
            input=json.dumps(exec_input),
        )

    return _resp(200, {
        "executionArn": resp["executionArn"],
        "jobId": job_id,
        "expectedFinalKey": final_key,
        "links": {"execution": _console_sfn_link(resp["executionArn"])}
    })


# ===== status family =====
def _status(execution_arn: str):
    try:
        d = sfn.describe_execution(executionArn=execution_arn)
        return _resp(200, d)
    except sfn.exceptions.ExecutionDoesNotExist:
        return _resp(404, {"error": "Execution not found", "arn": execution_arn})
    except ClientError as e:
        code = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 500)
        return _resp(code or 500, {"error": "DescribeExecution failed", "message": str(e), "arn": execution_arn})
    except Exception as e:
        return _resp(500, {"error": "DescribeExecution exception", "message": str(e), "arn": execution_arn})


def _status_progress(qs):
    job_id = (qs or {}).get("jobId")
    expected = int((qs or {}).get("expected") or 0)
    if not job_id:
        return _resp(400, {"error": "jobId is required"})
    prefix = f"tiles/{job_id}/"
    count = 0
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=OUTPUT_BUCKET, Prefix=prefix):
            for _ in page.get("Contents", []) or []:
                count += 1
    except ClientError as e:
        return _resp(500, {"error": "S3 list failed", "message": str(e), "prefix": prefix})
    percent = int(min(100, round((count / expected) * 100))) if expected > 0 else None
    return _resp(200, {"jobId": job_id, "tilesPrefix": prefix, "tilesCount": count, "percent": percent})


def _status_detail_or_history(execution_arn: str, history=False):
    try:
        hist = sfn.get_execution_history(executionArn=execution_arn, maxResults=100, reverseOrder=not history)
    except ClientError as e:
        return _resp(500, {"error": "GetExecutionHistory failed", "message": str(e)})

    if history:
        events = []
        log_group = None
        for ev in hist.get("events", []):
            et = ev["type"]
            when = ev.get("timestamp")
            when_s = when.isoformat() if isinstance(when, dt.datetime) else str(when)
            det_key = f"{et[0].lower()}{et[1:]}EventDetails"
            d = ev.get(det_key, {}) or {}

            if et == "LambdaFunctionScheduled":
                fa = d.get("resource") or d.get("functionArn")
                if isinstance(fa, str) and ":function:" in fa:
                    fn_name = fa.split(":function:", 1)[1]
                    log_group = f"/aws/lambda/{fn_name}"

            detail = None
            if "error" in d or "cause" in d:
                detail = json.dumps({k: d[k] for k in ("error", "cause") if k in d})[:2000]
            elif "name" in d:
                detail = d["name"]

            events.append({"time": when_s, "type": et, "detail": detail})

        return _resp(200, {"events": events, "links": {
            "sfn": _console_sfn_link(execution_arn),
            "logs": _console_logs_link(log_group)
        }})

    # detail mode: find last failure + lambda logs hint
    error = cause = failed_state = None
    function_name = None
    for ev in hist.get("events", []):
        et = ev["type"]
        det = ev.get(f"{et[0].lower()}{et[1:]}EventDetails", {}) or {}
        if et in ("ExecutionFailed", "TaskFailed", "LambdaFunctionFailed") and not error:
            error = det.get("error")
            cause = det.get("cause")
            failed_state = det.get("name") or det.get("stateName")
        if et == "LambdaFunctionScheduled":
            fa = det.get("resource") or det.get("functionArn")
            if isinstance(fa, str) and ":function:" in fa:
                function_name = fa.split(":function:", 1)[1]
    log_group = f"/aws/lambda/{function_name}" if function_name else None
    return _resp(200, {
        "error": error, "cause": cause, "failedState": failed_state,
        "logGroup": log_group, "logLink": _console_logs_link(log_group),
        "sfnLink": _console_sfn_link(execution_arn)
    })


# ===== main handler =====
def handler(event, _context):
    try:
        method = (event.get("requestContext") or {}).get("http", {}).get("method", "GET")
        raw_path = event.get("rawPath") or "/"
        qs = event.get("queryStringParameters") or {}

        if method == "OPTIONS":
            return _resp(200, {"ok": True})

        if raw_path == "/split" and method == "POST":
            return _split(event)

        if raw_path == "/unite" and method == "POST":
            return _unite(event)

        if raw_path.startswith("/status/") and method == "GET":
            arn = up.unquote(raw_path.split("/status/", 1)[1])
            return _status(arn)

        if raw_path == "/status-progress" and method == "GET":
            return _status_progress(qs)

        if raw_path.startswith("/status-detail/") and method == "GET":
            arn = up.unquote(raw_path.split("/status-detail/", 1)[1])
            return _status_detail_or_history(arn, history=False)

        if raw_path.startswith("/status-history/") and method == "GET":
            arn = up.unquote(raw_path.split("/status-history/", 1)[1])
            return _status_detail_or_history(arn, history=True)

        if raw_path == "/list-output" and method == "GET":
            bucket = qs.get("bucket") or OUTPUT_BUCKET
            prefix = qs.get("prefix") or ""
            out = []
            try:
                paginator = s3.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                    for it in page.get("Contents", []) or []:
                        out.append({"key": it["Key"], "size": it.get("Size")})
            except ClientError as e:
                return _resp(500, {"error": "S3 list failed", "message": str(e), "bucket": bucket, "prefix": prefix})
            return _resp(200, {"objects": out})

        return _resp(404, {"error": f"No route for {method} {raw_path}"})
    except Exception as e:
        return _resp(500, {"error": "controller exception", "message": str(e)})
