# controller.py
import json
import os

def _resp(status, body, origin="*"):
    return {
        "statusCode": status,
        "headers": {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }

def handler(event, context):
    method = (event.get("requestContext", {})
                   .get("http", {})
                   .get("method", "GET")).upper()

    # Handle CORS preflight
    if method == "OPTIONS":
        return _resp(200, {"ok": True})

    path = event.get("rawPath", "")

    try:
        if path.endswith("/split") and method == "POST":
            # TODO: implement split logic or call Step Function
            return _resp(200, {"executionArn": "arn:aws:states:demo-split"})
        elif path.endswith("/unite") and method == "POST":
            return _resp(200, {"executionArn": "arn:aws:states:demo-unite"})
        elif path.startswith("/status") and method == "GET":
            return _resp(200, {"status": "RUNNING"})
        else:
            return _resp(404, {"error": "Not found"})
    except Exception as e:
        return _resp(500, {"error": str(e)})
