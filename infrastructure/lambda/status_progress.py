# infrastructure/lambda/status_progress.py
import os, json, boto3

s3 = boto3.client("s3")
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]

def _resp(code, body):
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,x-api-key",
            "Access-Control-Allow-Methods": "OPTIONS,GET"
        },
        "body": json.dumps(body)
    }

def handler(event, _ctx):
    if (event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS"):
        return _resp(200, {"ok": True})

    qs = event.get("queryStringParameters") or {}
    job_id = qs.get("jobId")
    expected = int(qs.get("expected") or "0")
    if not job_id:
        return _resp(400, {"error":"missing jobId"})

    prefix = f"tiles/{job_id}/"
    count = 0
    token = None
    while True:
        kw = {"Bucket": OUTPUT_BUCKET, "Prefix": prefix, "ContinuationToken": token} if token else {"Bucket": OUTPUT_BUCKET, "Prefix": prefix}
        page = s3.list_objects_v2(**kw)
        for it in page.get("Contents") or []:
            if not it["Key"].endswith("/"):
                count += 1
        if page.get("IsTruncated"):
            token = page.get("NextContinuationToken")
        else:
            break

    percent = int(round((count/expected)*100)) if expected else 0
    return _resp(200, {"jobId": job_id, "tilesCount": count, "expected": expected, "percent": percent})
