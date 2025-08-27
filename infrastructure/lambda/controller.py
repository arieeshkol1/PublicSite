import json, os, re, uuid

def _resp(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}

def handler(event, context):
    route = (event.get("requestContext", {}).get("http", {}).get("path") or "").lower()
    method = (event.get("requestContext", {}).get("http", {}).get("method") or "").upper()

    if route == "/split" and method == "POST":
        body = json.loads(event.get("body") or "{}")
        input_key = body.get("inputKey")
        tile_size = int(body.get("tileSize") or 2048)
        if not input_key:
            return _resp(400, {"error":"inputKey required"})
        # stub: return job id only
        return _resp(200, {"jobId": f"split-{uuid.uuid4().hex[:8]}", "tileSize": tile_size})

    if route == "/unite" and method == "POST":
        body = json.loads(event.get("body") or "{}")
        manifest_key = body.get("manifestKey")
        if not manifest_key:
            return _resp(400, {"error":"manifestKey required"})
        return _resp(200, {"jobId": f"unite-{uuid.uuid4().hex[:8]}"})

    m = re.match(r"^/status/([A-Za-z0-9\-]+)$", route)
    if m and method == "GET":
        return _resp(200, {"jobId": m.group(1), "state": "SUCCEEDED", "outputKey": None})

    return _resp(404, {"error":"not found"})
