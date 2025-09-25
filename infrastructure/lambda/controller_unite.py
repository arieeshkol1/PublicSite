import os, json, time, uuid, base64
import boto3
from botocore.exceptions import ClientError, BotoCoreError

sfn = boto3.client("stepfunctions")

SPLIT_SFN_ARN  = os.environ.get("SPLIT_SFN_ARN")   # not used, kept for parity
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

def _execution_arn_from_name(state_machine_arn: str, name: str) -> str:
    # arn:aws:states:{region}:{account}:stateMachine:{sm_name}
    parts = state_machine_arn.split(":")
    region = parts[3]
    account = parts[4]
    sm_name = parts[6]
    if sm_name.startswith("stateMachine:"):
        sm_name = sm_name.split("stateMachine:")[-1]
    if "stateMachine/" in sm_name:
        sm_name = sm_name.split("stateMachine/")[-1]
    # arn:aws:states:{region}:{account}:execution:{sm_name}:{name}
    return f"arn:aws:states:{region}:{account}:execution:{sm_name}:{name}"

def handler(event, _ctx):
    # CORS preflight
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return _resp(200, {"ok": True})

    try:
        body = _parse_event(event)
        job_id = (body.get("jobId") or "").strip()
        out_bucket = (body.get("outputBucket") or OUTPUT_BUCKET or "").strip()

        if not job_id or not out_bucket:
            return _resp(400, {"error": "Missing fields (jobId, outputBucket)"})

        tiles_prefix   = f"tiles/{job_id}/"
        final_key      = body.get("finalKey") or f"final/unite-{job_id}.jp2"
        format_option  = (body.get("formatOption") or "keep").lower()

        # Keep the same execution name for idempotency: unite-<jobId>
        exec_name = f"unite-{job_id}"
        sfn_input = {
            "mode": "unite",
            "jobId": job_id,
            "execName": exec_name,
            "outputBucket": out_bucket,
            "tilesPrefix": tiles_prefix,
            "finalKey": final_key,
            "formatOption": format_option,
        }

        try:
            r = sfn.start_execution(
                stateMachineArn=UNITE_SFN_ARN,
                name=exec_name,
                input=json.dumps(sfn_input),
            )
            exec_arn = r.get("executionArn")
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code == "ExecutionAlreadyExists":
                # Return the existing execution ARN to the UI so it can continue polling
                exec_arn = _execution_arn_from_name(UNITE_SFN_ARN, exec_name)
            else:
                # Bubble up any other SFN error
                return _resp(500, {"error": f"{code or 'ClientError'}: {str(e)}"})
        except (BotoCoreError, Exception) as e:
            return _resp(500, {"error": f"{type(e).__name__}: {str(e)}"})

        return _resp(200, {
            "jobId": job_id,
            "executionArn": exec_arn,
            "expectedFinalKey": final_key,
            "links": {
                "execution": f"https://console.aws.amazon.com/states/home#/executions/details/{exec_arn}"
            }
        })
    except Exception as e:
        return _resp(500, {"error": f"{type(e).__name__}: {str(e)}"})
