import json
import os
import boto3

s3 = boto3.client("s3")
UI_ORIGIN = os.environ.get("UI_ORIGIN", "*")  # e.g. https://jp2-ui-...s3.us-east-1.amazonaws.com

def _resp(status: int, body: dict, origin: str = UI_ORIGIN):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,x-api-key",
        },
        "body": json.dumps(body),
        "isBase64Encoded": False,
    }

def handler(event, context):
    method = (event.get("requestContext", {})
                   .get("http", {})
                   .get("method", "GET")).upper()
    if method == "OPTIONS":
        return _resp(200, {"ok": True})

    params = event.get("queryStringParameters") or {}
    bucket  = params.get("bucket") or os.environ.get("INPUT_BUCKET")
    if not bucket:
        return _resp(400, {"error": "Missing 'bucket' param or INPUT_BUCKET env"})

    mode   = (params.get("type") or "file").lower()   # 'file' | 'folder'
    prefix = params.get("prefix") or ""
    cursor = params.get("cursor") or None
    max_keys = int(params.get("maxKeys") or "1000")

    req = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": max_keys}
    if cursor:
        req["ContinuationToken"] = cursor

    items, cursor_next = [], None
    allowed_exts = ("jp2", "tif", "tiff", "geotiff", "bin", "hdr")

    try:
        if mode == "folder":
            req["Delimiter"] = "/"
            page = s3.list_objects_v2(**req)
            for p in page.get("CommonPrefixes", []) or []:
                key = p.get("Prefix")
                if key:
                    items.append({"key": key, "type": "folder"})
            if page.get("IsTruncated"):
                cursor_next = page.get("NextContinuationToken")
        else:
            page = s3.list_objects_v2(**req)
            for it in page.get("Contents", []) or []:
                key = it["Key"]
                ext = key.lower().rsplit(".", 1)[-1] if "." in key else ""
                if ext not in allowed_exts:
                    continue  # skip irrelevant files (e.g. JSON manifests)
                items.append({"key": key, "size": it.get("Size", 0), "type": "file"})
            if page.get("IsTruncated"):
                cursor_next = page.get("NextContinuationToken")

    except Exception as e:
        return _resp(500, {"error": f"List failed: {type(e).__name__}: {e}"})

    body = {"items": items}
    if cursor_next:
        body["cursorNext"] = cursor_next
    return _resp(200, body)
