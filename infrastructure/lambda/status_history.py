# infrastructure/lambda/status_history.py
import os, json, urllib.parse, boto3

sfn = boto3.client("stepfunctions")

SPLIT_SFN_ARN = os.environ["SPLIT_SFN_ARN"]  # e.g., arn:aws:states:us-east-1:111122223333:stateMachine:SplitStateMachineXYZ

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

def _exec_arn_from_job(job_id: str) -> str:
    # Build execution ARN from State Machine ARN + job name
    # stateMachine ARN: arn:aws:states:{region}:{account}:stateMachine:{sm_name}
    parts = SPLIT_SFN_ARN.split(":")
    region = parts[3]
    account = parts[4]
    sm_name = parts[6].split("stateMachine/")[-1] if "stateMachine/" in parts[6] else parts[6]
    # Some CDK ARNs have ":" form with name at end; normalize name
    if sm_name.startswith("stateMachine:"):
        sm_name = sm_name.split("stateMachine:")[-1]
    return f"arn:aws:states:{region}:{account}:execution:{sm_name}:{job_id}"

def _format_events(history):
    out = []
    for ev in history.get("events", []):
        et = ev.get("type")
        ts = ev.get("timestamp")
        detail = None
        # Surface short details where useful
        if "executionFailedEventDetails" in ev:
            detail = ev["executionFailedEventDetails"].get("cause") or ev["executionFailedEventDetails"].get("error")
        elif "lambdaFunctionFailedEventDetails" in ev:
            detail = ev["lambdaFunctionFailedEventDetails"].get("cause") or ev["lambdaFunctionFailedEventDetails"].get("error")
        elif "lambdaFunctionSucceededEventDetails" in ev:
            detail = ev["lambdaFunctionSucceededEventDetails"].get("output")
            if detail and len(detail) > 300:
                detail = detail[:300] + "…"
        out.append({"time": ts.isoformat() if hasattr(ts, "isoformat") else str(ts), "type": et, "detail": detail})
    return out

def handler(event, _ctx):
    if (event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS"):
        return _resp(200, {"ok": True})

    route = (event.get("requestContext", {}).get("http", {}).get("path") or "").lower()
    path_params = event.get("pathParameters") or {}
    qs = event.get("queryStringParameters") or {}

    try:
        # 1) /status-history/{jobId}  (UI calls this)
        if "/status-history/" in route and "proxy" in path_params or "jobId" in path_params or path_params:
            # HttpApi often maps as {proxy+}. Try any param present.
            job_id = path_params.get("jobId") or next(iter(path_params.values()), None)
            if not job_id:
                return _resp(400, {"error": "missing jobId in path"})
            exec_arn = _exec_arn_from_job(job_id)
            hist = sfn.get_execution_history(executionArn=exec_arn, reverseOrder=True)
            return _resp(200, {"executionArn": exec_arn, "events": _format_events(hist)})

        # 2) /status-detail/{executionArn} (optional path used by UI on unite flow)
        if "/status-detail/" in route and path_params:
            raw = next(iter(path_params.values()), None)
            if not raw:
                return _resp(400, {"error":"missing executionArn in path"})
            exec_arn = urllib.parse.unquote(raw)
            hist = sfn.get_execution_history(executionArn=exec_arn, reverseOrder=True)
            return _resp(200, {"executionArn": exec_arn, "events": _format_events(hist)})

        # 3) Fallback: if provided via query (?arn=...)
        if qs.get("arn"):
            exec_arn = qs["arn"]
            hist = sfn.get_execution_history(executionArn=exec_arn, reverseOrder=True)
            return _resp(200, {"executionArn": exec_arn, "events": _format_events(hist)})

        return _resp(400, {"error":"unsupported route; provide /status-history/{jobId} or /status-detail/{executionArn} or ?arn="})
    except sfn.exceptions.ExecutionDoesNotExist as e:
        return _resp(404, {"error": "execution not found", "detail": str(e)})
    except Exception as e:
        return _resp(500, {"error": f"{type(e).__name__}: {e}"})
