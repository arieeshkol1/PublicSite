import json
import os
import boto3

s3 = boto3.client("s3")

def _resp(status: int, body: dict, origin: str = "*"):
    return {
        "statusCode": status,
        "headers": {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }

def handler(event, context):
    method = (event.get("requestContext", {})
                   .get("http", {})
                   .get("method", "GET")).upper()
    if method == "OPTIONS":
        return _resp(200, {"ok": True})

    params = event.get("queryStringParameters") or {}
    bucket = params.get("bucket") or os.environ.get("INPUT_BUCKET")
    prefix = params.get("prefix") or ""
    if not bucket:
        return _resp(400, {"error": "Missing 'bucket' query param or INPUT_BUCKET env"})

    objects = []
    paginator = s3.get_paginator("list_objects_v2")
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for it in page.get("Contents", []) or []:
                key = it["Key"]
                if key.lower().endswith(".jp2"):
                    objects.append({"key": key, "size": it.get("Size", 0)})
    except Exception as e:
        return _resp(500, {"error": f"List failed: {type(e).__name__}: {e}"})

    return _resp(200, {"objects": objects})
