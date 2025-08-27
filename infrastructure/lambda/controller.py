import json
import os
import time
import urllib.parse as up
import boto3

INPUT_BUCKET = os.environ.get("INPUT_BUCKET", "")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")

sfn = boto3.client("stepfunctions")
s3 = boto3.client("s3")

def _resp(status, body, origin="*"):
    return {
        "statusCode": status,
        "headers": {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }

def _json(body):
    if isinstance(body, str):
        return json.loads(body)
    return body

def handler(event, context):
    method = (event.get("requestContext", {}).get("http", {}).get("method", "GET")).upper()
    if method == "OPTIONS":
        return _resp(200, {"ok": True})

    raw_path = event.get("rawPath", "")
    qs = event.get("queryStringParameters") or {}
    body = event.get("body")
    if body and event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    body_json = _json(body) if body else {}

    try:
        if raw_path.endswith("/split") and method == "POST":
            # Expect: { inputBucket, inputKey, outputBucket, params: { tilesTotal, tilesGrid } }
            job_id = f"job-{int(time.time()*1000)}"
            exec_input = {
                "jobId": job_id,
                "inputBucket": body_json.get("inputBucket", INPUT_BUCKET),
                "inputKey": body_json["inputKey"],
                "outputBucket": body_json.get("outputBucket", OUTPUT_BUCKET),
                "params": body_json.get("params", {}),
            }
            resp = sfn.start_execution(
                stateMachineArn=STATE_MACHINE_ARN,
                name=f"split-{job_id}",
                input=json.dumps(exec_input),
            )
            # Return ARN + jobId back to UI
            return _resp(200, {
                "executionArn": resp["executionArn"],
                "jobId": job_id,
                "expectedTiles": exec_input["params"].get("tilesTotal", 16)
            })

        elif raw_path.endswith("/unite") and method == "POST":
            # Stub for now
            return _resp(200, {"executionArn": "arn:aws:states:stub:unite"})

        elif raw_path.startswith("/status/") and method == "GET":
            # raw_path: /status/{jobIdOrArn}
            job_or_arn = raw_path.split("/status/", 1)[1]
            arn = up.unquote(job_or_arn)
            desc = sfn.describe_execution(executionArn=arn)
            out = {"status": desc["status"]}
            if "output" in desc:
                out["output"] = desc["output"]
            return _resp(200, out)

        elif raw_path.endswith("/status-progress") and method == "GET":
            # Optional: UI can call ?jobId=...&expected=16
            job_id = qs.get("jobId", "")
            expected = int(qs.get("expected", "16"))
            percent, count = _tiles_progress(OUTPUT_BUCKET, job_id, expected)
            return _resp(200, {"status": "RUNNING", "percent": percent, "tilesCount": count})

        else:
            return _resp(404, {"error": "Not found", "path": raw_path})
    except KeyError as e:
        return _resp(400, {"error": f"missing field: {e}"})
    except Exception as e:
        return _resp(500, {"error": f"{type(e).__name__}: {e}"})


def _tiles_progress(bucket, job_id, expected):
    if not job_id:
        return 0, 0
    prefix = f"tiles/{job_id}/"
    n = 0
    p = s3.get_paginator("list_objects_v2")
    for page in p.paginate(Bucket=bucket, Prefix=prefix):
        for it in page.get("Contents", []) or []:
            key = it["Key"].lower()
            if key.endswith((".tif", ".tiff", ".jp2", ".png", ".tile")):
                n += 1
    pct = int(min(100, (n / max(1, expected)) * 100))
    return pct, n
