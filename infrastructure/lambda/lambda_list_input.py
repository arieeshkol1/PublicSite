import json
import os
import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")
UI_ORIGIN = os.environ.get("UI_ORIGIN", "*")  # e.g. https://jp2-ui-....s3.us-east-1.amazonaws.com
FN_NAME = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "ListInputFn")

ALLOWED_EXTS = {"jp2", "tif", "tiff", "geotiff", "bin", "hdr"}

def _resp(status: int, body: dict, origin: str = UI_ORIGIN):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,x-api-key",
            # debug header to prove which code runs
            "x-source-fn": FN_NAME,
        },
        "body": json.dumps(body),
        "isBase64Encoded": False,
    }

def _list_files_paged(bucket: str, prefix: str, max_keys: int, cursor: str | None, all_exts: bool):
    req = {"Bucket": bucket, "Prefix": prefix}
    if cursor:
        req["ContinuationToken"] = cursor

    items = []
    cursor_next = None
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(**req, PaginationConfig={"PageSize": max_keys}):
        for it in page.get("Contents", []) or []:
            key = it["Key"]
            if not all_exts:
                ext = key.lower().rsplit(".", 1)[-1] if "." in key else ""
                if ext not in ALLOWED_EXTS:
                    continue
            items.append({"key": key, "size": it.get("Size", 0), "type": "file"})
        if page.get("IsTruncated"):
            cursor_next = page.get("NextContinuationToken")

    return items, cursor_next

def _list_folders(bucket: str, prefix: str, max_keys: int, cursor: str | None):
    req = {"Bucket": bucket, "Prefix": prefix, "Delimiter": "/"}
    if cursor:
        req["ContinuationToken"] = cursor

    items = []
    cursor_next = None

    page = s3.list_objects_v2(**req)
    for p in page.get("CommonPrefixes", []) or []:
        key = p.get("Prefix")
        if key:
            items.append({"key": key, "type": "folder"})
    if page.get("IsTruncated"):
        cursor_next = page.get("NextContinuationToken")

    return items, cursor_next

def handler(event, _context):
    method = (event.get("requestContext", {})
                    .get("http", {})
                    .get("method", "GET")).upper()
    if method == "OPTIONS":
        return _resp(200, {"ok": True})

    params   = event.get("queryStringParameters") or {}
    bucket   = params.get("bucket") or os.environ.get("INPUT_BUCKET")
    if not bucket:
        return _resp(400, {"error": "Missing 'bucket' param or INPUT_BUCKET env"})

    mode     = (params.get("type") or "file").lower()  # 'file' | 'folder'
    prefix   = params.get("prefix") or ""
    cursor   = params.get("cursor") or None
    max_keys = int(params.get("maxKeys") or "1000")
    all_exts = str(params.get("all") or "").lower() in {"1", "true", "yes"}

    try:
        if mode == "folder":
            items, cursor_next = _list_folders(bucket, prefix, max_keys, cursor)
        else:
            items, cursor_next = _list_files_paged(bucket, prefix, max_keys, cursor, all_exts)
    except ClientError as e:
        return _resp(500, {
            "error": f"S3 list failed: {e.response.get('Error', {}).get('Message', str(e))}",
            "bucket": bucket, "prefix": prefix
        })

    body = {"items": items, "objects": items}  # expose both keys for any UI variant
    if cursor_next:
        body["cursorNext"] = cursor_next
    # tiny debug footprint to validate filtering mode
    body["_debug"] = {"bucket": bucket, "prefix": prefix, "all_exts": all_exts, "count": len(items)}
    return _resp(200, body)
