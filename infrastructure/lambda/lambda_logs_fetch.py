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

    now_ms = int(time.time()*1000)
    start  = now_ms - seconds*1000

    out = logs.filter_log_events(
        logGroupName=LOG_GROUP,
        startTime=start,
        endTime=now_ms,
        filterPattern=pattern,
        interleaved=True,
        limit=limit
    )
    lines = [{"ts":e["timestamp"],"msg":e.get("message",""),"stream":e.get("logStreamName","")}
             for e in out.get("events",[])]
    return _resp(200, {"lines": lines})
