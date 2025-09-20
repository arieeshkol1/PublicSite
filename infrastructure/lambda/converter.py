# File: lambda/convert.py
```python
import os, json, uuid
import boto3

INPUT_BUCKET = os.environ["INPUT_BUCKET"]
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]
SPLIT_SM_ARN = os.environ["SPLIT_SM_ARN"]

sfn = boto3.client("stepfunctions")

SUPPORTED = {"JPEG2", "TIFF", "RAW", "XML", "TXT", "JSON"}

def _resp(code: int, body: dict):
    return {"statusCode": code, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}

# Maps front-end target_format to Split task FORMAT_OPTION (adjust as your worker expects)
FORMAT_MAP = {
    "JPEG2": "JPEG2000",
    "TIFF": "TIFF",
    "RAW": "RAW",
    "XML": "XML",
    "TXT": "TXT",
    "JSON": "JSON",
}

# Default Split params if not supplied by client
DEFAULT_PARAMS = {
    "tilesTotal": 1,    # keep as 1 if you are not tiling, worker can ignore
    "tilesGrid": "1x1",
}

def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        return _resp(400, {"error": "Invalid JSON"})

    keys = body.get("keys") or []
    target = body.get("target_format")

    if not keys:
        return _resp(400, {"error": "No keys provided"})
    if target not in SUPPORTED:
        return _resp(400, {"error": "Unsupported target_format"})

    job_id = str(uuid.uuid4())
    format_option = FORMAT_MAP[target]

    # Start a Split execution per key (controller/status aggregates by jobId)
    for key in keys:
        input_payload = {
            "inputBucket": INPUT_BUCKET,
            "inputKey": key,
            "outputBucket": OUTPUT_BUCKET,
            "jobId": job_id,
            "params": { **DEFAULT_PARAMS, "formatOption": format_option },
        }
        sfn.start_execution(
            stateMachineArn=SPLIT_SM_ARN,
            name=f"convert-{job_id}-{uuid.uuid4().hex[:8]}",
            input=json.dumps(input_payload),
        )

    return _resp(200, {"job_id": job_id})