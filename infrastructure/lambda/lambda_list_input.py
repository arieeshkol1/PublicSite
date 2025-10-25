# lambda_list_input.py
import json
import os
import re
import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")

UI_ORIGIN = os.environ.get("UI_ORIGIN", "*")  # e.g. https://jp2-ui-....s3.us-east-1.amazonaws.com
FN_NAME   = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "ListInputFn")

# Default allow-list (used when no ?exts= is provided and ?all= is false)
# Added "json" and "raw" to fix missing files in JSON+RAW filter.
DEFAULT_ALLOWED_EXTS = {"jp2", "tif", "tiff", "geotiff", "bin", "hdr", "json", "raw"}


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


def _get_ext(key: str) -> str:
    """Return lowercase file extension, or '' if none."""
    m = re.search(r"\.([^./\\]+)$", key)
    return m.group(1).lower() if m else ""


def _list_files_paged(
    bucket: str,
    prefix: str,
    max_keys: int,
    cursor: str | None,
    # allowed_exts=None means "no filtering by extension" (i.e., include ALL)
    allowed_exts: set[str] | None,
):
    req = {"Bucket": bucket, "Prefix": prefix}
    if cursor:
        req["ContinuationToken"] = cursor

    items = []
    cursor_next = None

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(**req, PaginationConfig={"PageSize": max_keys}):
        for it in page.get("Contents", []) or []:
            key = it["Key"]
            # skip S3 "folders"
            if key.endswith("/"):
                continue

            if allowed_exts is not None:
                ext = _get_ext(key)
                if ext not in allowed_exts:
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
    # Support both HTTP API (v2) and ALB/legacy event shapes.
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", "GET"))
    ).upper()

    if method == "OPTIONS":
        return _resp(200, {"ok": True})

    # Prefer queryStringParameters; if absent, try to parse from rawQueryString.
    params = event.get("queryStringParameters") or {}
    if not params and "rawQueryString" in event and event["rawQueryString"]:
        # Best-effort parse
        from urllib.parse import parse_qs
        parsed = parse_qs(event["rawQueryString"])
        params = {k: v[0] for k, v in parsed.items()}

    bucket   = params.get("bucket") or os.environ.get("INPUT_BUCKET")
    if not bucket:
        return _resp(400, {"error": "Missing 'bucket' param or INPUT_BUCKET env"})

    mode     = (params.get("type") or "file").lower()  # 'file' | 'folder'
    prefix   = params.get("prefix") or ""
    cursor   = params.get("cursor") or None
    max_keys = int(params.get("maxKeys") or "1000")

    # If all=true|1|yes -> include ALL extensions (no filtering)
    all_exts_flag = str(params.get("all") or "").lower() in {"1", "true", "yes"}

    # exts=json,raw (comma-separated). If provided, filter strictly by these.
    raw_exts = params.get("exts") or ""
    selected_exts = {
        e.strip().lower()
        for e in raw_exts.split(",")
        if e and e.strip()
    }

    # Decide filtering mode:
    # - If all_exts_flag: no filtering by ext (allowed_exts=None)
    # - Else if selected_exts: filter by selected_exts
    # - Else: filter by DEFAULT_ALLOWED_EXTS
    if all_exts_flag:
        allowed_exts = None  # None => include all
        filter_mode = "all"
    elif selected_exts:
        allowed_exts = selected_exts
        filter_mode = "exts"
    else:
        allowed_exts = DEFAULT_ALLOWED_EXTS
        filter_mode = "default-allowlist"

    try:
        if mode == "folder":
            items, cursor_next = _list_folders(bucket, prefix, max_keys, cursor)
        else:
            items, cursor_next = _list_files_paged(bucket, prefix, max_keys, cursor, allowed_exts)
    except ClientError as e:
        return _resp(
            500,
            {
                "error": f"S3 list failed: {e.response.get('Error', {}).get('Message', str(e))}",
                "bucket": bucket,
                "prefix": prefix,
            },
        )

    body = {"items": items, "objects": items}  # maintain both keys for UI variants
    if cursor_next:
        body["cursorNext"] = cursor_next

    # Debug footprint to validate filtering mode
    body["_debug"] = {
        "bucket": bucket,
        "prefix": prefix,
        "filter_mode": filter_mode,
        "all_exts": all_exts_flag,
        "selected_exts": sorted(selected_exts) if selected_exts else None,
        "count": len(items),
    }
    return _resp(200, body)
