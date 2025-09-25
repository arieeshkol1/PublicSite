import os, json, time, uuid, base64
import boto3

sfn = boto3.client("stepfunctions")

SPLIT_SFN_ARN  = os.environ.get("SPLIT_SFN_ARN")   # not used here, kept for parity
UNITE_SFN_ARN  = os.environ["UNITE_SFN_ARN"]
OUTPUT_BUCKET  = os.environ.get("OUTPUT_BUCKET")

def _cors():
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
    }

def _resp(code, body):
    return {"statusCode": code, "headers": _cors(), "body": json.dumps(body)}

def _parse_event(e):
    body = e.get("body")
    if body is None: return {}
    if e.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", "ignore")
    if isinstance(body, str):
        body = json.loads(body or "{}")
    return body if isinstance(body, dict) else {}

def handler(event, _ctx):
    # CORS preflight
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return _resp(200, {"ok": True})

    body = _parse_event(event)
    job_id = (body.get("jobId") or "").strip()  # tiles folder name (from UI)
    out_bucket = (body.get("outputBucket") or OUTPUT_BUCKET or "").strip()

    if not job_id or not out_bucket:
        return _resp(400, {"error": "Missing fields (jobId, outputBucket)"})

    # Expected S3 layout
    tiles_prefix   = f"tiles/{job_id}/"
    final_key      = body.get("finalKey") or f"final/unite-{job_id}.jp2"
    format_option  = (body.get("formatOption") or "keep").lower()  # "keep"|"tiff"
    # Use a distinct Step Functions execution name so the UI can read history
    exec_name      = f"unite-{job_id}"

    sfn_input = {
        "mode": "unite",
        "jobId": job_id,                           # keep original id for UI
        "execName": exec_name,
        "outputBucket": out_bucket,
        "tilesPrefix": tiles_prefix,
        "finalKey": final_key,
        "formatOption": format_option,             # optional; container may ignore
    }

    r = sfn.start_execution(
        stateMachineArn=UNITE_SFN_ARN,
        name=exec_name,
        input=json.dumps(sfn_input),
    )

    return _resp(200, {
        "jobId": job_id,
        "executionArn": r.get("executionArn"),
        "expectedFinalKey": final_key,
        "links": {
            "execution": f"https://console.aws.amazon.com/states/home#/executions/details/{r.get('executionArn')}"
        }
    })
