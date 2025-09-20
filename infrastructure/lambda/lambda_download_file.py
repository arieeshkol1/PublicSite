import json
import os
import boto3
from botocore.config import Config

s3 = boto3.client("s3", config=Config(signature_version="s3v4"))
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]

def _resp(code, body):
    return {"statusCode": code, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}

def presign(key: str, seconds: int = 3600) -> str:
    return s3.generate_presigned_url(
        ClientMethod='get_object',
        Params={'Bucket': OUTPUT_BUCKET, 'Key': key},
        ExpiresIn=seconds
    )

def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        keys = body.get("keys") or []
        if not keys:
            return _resp(400, {"error":"missing keys"})
        if len(keys) == 1:
            return _resp(200, {"url": presign(keys[0])})
        else:
            return _resp(200, {"urls": [presign(k) for k in keys]})
    except Exception as e:
        return _resp(500, {"error": str(e)})
