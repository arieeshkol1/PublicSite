# lambda_logs_fetch.py
import os, json, time, boto3
logs = boto3.client("logs")
LOG_GROUP = os.environ["LOG_GROUP_CONVERT"]

def _resp(code, body):
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
        },
        "body": json.dumps(body),
    }

def handler(event, _):
    if event.get("requestContext",{}).get("http",{}).get("method") == "OPTIONS":
        return _resp(200, {"ok": True})
    qs = event.get("queryStringParameters") or {}
    pattern = qs.get("q") or ""
    seconds = int(qs.get("sinceSec") or 900)
    limit   = int(qs.get("limit") or 200)
    now = int(time.time()*1000)
    out = logs.filter_log_events(
        logGroupName=LOG_GROUP,
        startTime=now - seconds*1000,
        endTime=now,
        filterPattern=pattern,
        interleaved=True,
        limit=limit
    )
    return _resp(200, {"lines":[{"ts":e["timestamp"],"msg":e["message"],"stream":e["logStreamName"]}
                                for e in out.get("events",[])]})
