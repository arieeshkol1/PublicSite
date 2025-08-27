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
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")

sfn = boto3.client("stepfunctions", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)


# ===== helpers =====
def _resp(code: int, body_obj):
    # Always CORS+JSON
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
    if event.get("isBase64Encoded"):
        # Most HTTP API JSON bodies are not base64-encoded; ignoring for brevity
        pass
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


# ===== endpoints =====
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

    exec_name = job_id
    try:
        resp = sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=exec_name,
            input=json.dumps(exec_input),
        )
    except sfn.exceptions.ExecutionAlreadyExists:
        resp = sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            input=json.dumps(exec_input),
        )

    return _resp(
        200,
        {
            "executionArn": resp["executionArn"],
            "jobId": job_id,
            "expectedTiles": tiles_total,
            "links": {"execution": _console_sfn_link(resp["executionArn"])},
        },
    )


def _status(execution_arn: str):
    try:
        d = sfn.describe_execution(executionArn=execution_arn)
        return _resp(200, d)
    except sfn.exceptions.ExecutionDoesNotExist:
        print("DescribeExecution: not found", execution_arn)
        return _resp(404, {"error": "Execution not found", "arn": execution_arn})
    except ClientError as e:
        # AccessDenied, throttling, etc. — return clean JSON with details
        code = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 500)
        print("DescribeExecution ClientError:", e)
        return _resp(code if code else 500, {
            "error": "DescribeExecution failed",
            "message": str(e),
            "arn": execution_arn
        })
    except Exception as e:
        print("DescribeExecution Exception:", repr(e))
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
        print("status-progress S3 ClientError:", e)
        return _resp(500, {"error": "S3 list failed", "message": str(e), "prefix": prefix})
    percent = int(min(100, round((count / expected) * 100))) if expected > 0 else None
    return _resp(200, {"jobId": job_id, "tilesPrefix": prefix, "tilesCount": count, "percent": percent})


def _status_detail(execution_arn: str):
    try:
        hist = sfn.get_execution_history(executionArn=execution_arn, maxResults=50, reverseOrder=True)
    except ClientError as e:
        print("GetExecutionHistory ClientError:", e)
        return _resp(500, {"error": "GetExecutionHistory failed", "message": str(e)})

    error = cause = failed_state = None
    function_arn = function_name = None

    for ev in hist.get("events", []):
        et = ev["type"]
        det = ev.get(f"{et[0].lower()}{et[1:]}EventDetails", {}) or {}

        if et in ("ExecutionFailed", "TaskFailed", "LambdaFunctionFailed") and not error:
            error = det.get("error")
            cause = det.get("cause")
            failed_state = det.get("name") or det.get("stateName")

        if et == "LambdaFunctionScheduled":
            fa = det.get("resource") or det.get("functionArn")
            if isinstance(fa, str):
                function_arn = fa
                if ":function:" in fa:
                    function_name = fa.split(":function:", 1)[1]

    log_group = f"/aws/lambda/{function_name}" if function_name else None
    return _resp(
        200,
        {
            "error": error,
            "cause": cause,
            "failedState": failed_state,
            "functionArn": function_arn,
            "functionName": function_name,
            "logGroup": log_group,
            "logLink": _console_logs_link(log_group),
            "sfnLink": _console_sfn_link(execution_arn),
        },
    )


def _status_history(execution_arn: str):
    try:
        hist = sfn.get_execution_history(executionArn=execution_arn, maxResults=100, reverseOrder=False)
    except ClientError as e:
        print("GetExecutionHistory ClientError:", e)
        return _resp(500, {"error": "GetExecutionHistory failed", "message": str(e)})

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

    return _resp(200, {"events": events, "links": {"sfn": _console_sfn_link(execution_arn), "logs": _console_logs_link(log_group)}})


def _list_output(qs):
    bucket = (qs or {}).get("bucket") or OUTPUT_BUCKET
    prefix = (qs or {}).get("prefix") or ""
    if not bucket:
        return _resp(400, {"error": "bucket is required"})

    out = []
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for it in page.get("Contents", []) or []:
                out.append({"key": it["Key"], "size": it.get("Size")})
    except ClientError as e:
        print("list-output S3 ClientError:", e)
        return _resp(500, {"error": "S3 list failed", "message": str(e), "bucket": bucket, "prefix": prefix})

    return _resp(200, {"objects": out})


def _unite(_event):
    return _resp(501, {"error": "Unite not implemented"})


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

        if raw_path.startswith("/status/") and method == "GET":
            arn = up.unquote(raw_path.split("/status/", 1)[1])
            return _status(arn)

        if raw_path == "/status-progress" and method == "GET":
            return _status_progress(qs)

        if raw_path.startswith("/status-detail/") and method == "GET":
            arn = up.unquote(raw_path.split("/status-detail/", 1)[1])
            return _status_detail(arn)

        if raw_path.startswith("/status-history/") and method == "GET":
            arn = up.unquote(raw_path.split("/status-history/", 1)[1])
            return _status_history(arn)

        if raw_path == "/list-output" and method == "GET":
            return _list_output(qs)

        if raw_path == "/unite" and method == "POST":
            return _unite(event)

        return _resp(404, {"error": f"No route for {method} {raw_path}"})
    except Exception as e:
        # Final safety net so API doesn't 500 without a JSON body
        print("UNHANDLED CONTROLLER EXCEPTION:", repr(e))
        return _resp(500, {"error": "controller exception", "message": str(e)})
