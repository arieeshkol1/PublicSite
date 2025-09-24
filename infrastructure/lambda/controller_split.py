# infrastructure/lambda/controller_split.py
import os, json, time, uuid, base64, boto3

sfn = boto3.client("stepfunctions")

STATE_MACHINE_ARN = os.environ.get("SPLIT_SFN_ARN")  # passed from CDK

def _cors():
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,x-api-key",
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
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return _resp(200, {"ok": True})

    body = _parse_event(event)
    input_bucket  = body.get("inputBucket") or os.environ.get("INPUT_BUCKET")
    output_bucket = body.get("outputBucket") or os.environ.get("OUTPUT_BUCKET")
    input_key     = body.get("inputKey")
    params        = body.get("params") or {}

    if not input_bucket or not input_key or not output_bucket:
        return _resp(400, {"error": "Missing required fields (inputBucket, inputKey, outputBucket)"})

    job_id = body.get("jobId") or f"split-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
    tiles_total = int(params.get("tilesTotal") or 1)
    tiles_grid  = int(params.get("tilesGrid") or max(1, int(tiles_total**0.5)))
    fmt         = (params.get("formatOption") or "keep").lower()

    sfn_input = {
        "jobId": job_id,
        "inputBucket": input_bucket,
        "inputKey": input_key,
        "outputBucket": output_bucket,
        "params": {
            "tilesTotal": tiles_total,
            "tilesGrid": tiles_grid,
            "formatOption": fmt,
        },
    }

    try:
        r = sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            input=json.dumps(sfn_input),
            name=f"{job_id}".replace("_", "-")
        )
    except Exception as e:
        return _resp(500, {"error": f"start_execution failed: {type(e).__name__}: {e}"})

    return _resp(200, {
        "jobId": job_id,
        "executionArn": r["executionArn"],
        "expectedTiles": tiles_total,
        "links": {"execution": f"https://console.aws.amazon.com/states/home#/executions/details/{r['executionArn']}"}
    })
