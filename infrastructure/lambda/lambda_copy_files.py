import json
import os
import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config

s3 = boto3.client("s3", config=Config(signature_version="s3v4"))
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]
INPUT_BUCKET = os.environ["INPUT_BUCKET"]

TRANSFER_CFG = TransferConfig(
    multipart_threshold=64*1024*1024,
    multipart_chunksize=64*1024*1024,
    max_concurrency=8,
    use_threads=True,
)

def _resp(code, body):
    return {"statusCode": code, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}

def copy_then_delete(key: str):
    src = {"Bucket": OUTPUT_BUCKET, "Key": key}
    s3.copy(src, INPUT_BUCKET, key, Config=TRANSFER_CFG, ExtraArgs={"ServerSideEncryption":"AES256"})
    # sanity: size check
    dst_h = s3.head_object(Bucket=INPUT_BUCKET, Key=key)
    src_h = s3.head_object(Bucket=OUTPUT_BUCKET, Key=key)
    if int(dst_h["ContentLength"]) != int(src_h["ContentLength"]):
        raise RuntimeError(f"Size mismatch: {key}")
    s3.delete_object(Bucket=OUTPUT_BUCKET, Key=key)

def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        keys = body.get("keys") or []
        if not keys:
            return _resp(400, {"error":"missing keys"})
        completed, failed = 0, []
        for k in keys:
            try:
                copy_then_delete(k)
                completed += 1
            except Exception as e:
                failed.append({"key": k, "error": str(e)})
        status = 200 if not failed else 207
        return _resp(status, {"completed": completed, "failed": failed})
    except Exception as e:
        return _resp(500, {"error": str(e)})
