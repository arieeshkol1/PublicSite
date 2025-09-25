# infrastructure/lambda/controller_split.py
import os, json, time, uuid, base64
import boto3

sfn = boto3.client("stepfunctions")

SPLIT_SFN_ARN = os.environ["SPLIT_SFN_ARN"]
INPUT_BUCKET  = os.environ.get("INPUT_BUCKET")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET")

def _cors():
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST",
    }

def _resp(code, body):
    return {"statusCode": code, "headers": _cors(), "body": json.dumps(body)}

def _parse_event(event):
    body = event.get("body")
    if body is None:
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", "ignore")
    if isinstance(body, str):
        body = json.loads(body or "{}")
    return body if isinstance(body, dict) else {}

def handler(event, _ctx):
    # CORS preflight
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return _resp(200, {"ok": True})

    body = _parse_event(event)

    # Required fields
    input_bucket  = (body.get("inputBucket")  or INPUT_BUCKET) or ""
    output_bucket = (body.get("outputBucket") or OUTPUT_BUCKET) or ""
    input_key     = body.get("inputKey") or ""
    if not input_bucket or not output_bucket or not input_key:
        return _resp(400, {"error": "Missing required fields (inputBucket, inputKey, outputBucket)"})

    # Params normalization
    params = body.get("params") or {}
    # defaults if missing
    tiles_total = params.get("tilesTotal", 1)
    tiles_grid  = params.get("tilesGrid") or int(max(1, (int(tiles_total) ** 0.5)))
    format_opt  = (params.get("formatOption") or "keep").lower()

    # *** CRITICAL: force everything to STRINGS so ECS env is valid ***
    params_norm = {
        "tilesTotal": str(int(tiles_total)),
        "tilesGrid":  str(int(tiles_grid)),
        "formatOption": str(format_opt),
    }

    # Prepare execution input (all strings where ECS needs env)
    job_id = body.get("jobId") or f"split-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
    sfn_input = {
        "jobId":        str(job_id),
        "inputBucket":  str(input_bucket),
        "inputKey":     str(input_key),
        "outputBucket": str(output_bucket),
        "params":       params_norm,
    }

    # Start Step Functions execution
    exec_name = job_id  # unique enough
    r = sfn.start_execution(
        stateMachineArn=SPLIT_SFN_ARN,
        name=exec_name,
        input=json.dumps(sfn_input)
    )

    # Minimal UX payload for the UI
    return _resp(200, {
        "jobId": job_id,
        "executionArn": r.get("executionArn"),
        "expectedTiles": int(params_norm["tilesGrid"]) ** 2,
        "links": {
            "execution": f"https://console.aws.amazon.com/states/home#/executions/details/{r.get('executionArn')}"
        }
    })
