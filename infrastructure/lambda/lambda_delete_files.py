import json
import os
import boto3

s3 = boto3.client("s3")
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]

def _resp(code, body):
    return {"statusCode": code, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        keys = body.get("keys") or []
        if not keys:
            return _resp(400, {"error":"missing keys"})
        completed, failed = 0, []
        for batch in chunks(keys, 1000):
            try:
                s3.delete_objects(
                    Bucket=OUTPUT_BUCKET,
                    Delete={"Objects":[{"Key": k} for k in batch], "Quiet": True}
                )
                completed += len(batch)
            except Exception as e:
                failed.extend([{"key": k, "error": str(e)} for k in batch])
        status = 200 if not failed else 207
        return _resp(status, {"completed": completed, "failed": failed})
    except Exception as e:
        return _resp(500, {"error": str(e)})
