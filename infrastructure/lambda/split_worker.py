# infrastructure/lambda/split_worker.py
import json
import os
import time
import boto3
from random import randint
from pathlib import Path


s3 = boto3.client("s3")
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]


def handler(event, context):
"""
Dummy tiler:
- Reads jobId, inputKey, params.tilesTotal (default 16), params.tilesGrid
- Writes tiles at `tiles/{jobId}/{<basename>}_{seq}.jp2` (seq starts at 1)
- Writes manifest at `manifests/{jobId}.json`
"""
print("EVENT:", json.dumps(event))
job_id = event.get("jobId") or f"job-{int(time.time()*1000)}"
input_key = event.get("inputKey") or ""
base = Path(input_key).stem or "tile"


params = event.get("params") or {}
total = int(params.get("tilesTotal", 16))
grid = int(params.get("tilesGrid", max(1, int(total ** 0.5))))
print(f"Split start job={job_id} total={total} grid={grid} base={base}")


# Simulate tiling work and upload numerically named tiles starting at 1
for i in range(total):
seq = i + 1
key = f"tiles/{job_id}/{base}_{seq}.jp2"
body = f"DUMMY TILE {seq} {time.time()}".encode("utf-8")
s3.put_object(Bucket=OUTPUT_BUCKET, Key=key, Body=body)
print("wrote", key)
time.sleep(0.1 + (randint(0, 50) / 1000.0))


manifest_key = f"manifests/{job_id}.json"
tiles = [f"tiles/{job_id}/{base}_{seq}.jp2" for seq in range(1, total + 1)]
manifest = {
"jobId": job_id,
"sourceKey": input_key,
"baseName": base,
"tilesTotal": total,
"tilesGrid": grid,
"tilesPrefix": f"tiles/{job_id}/",
"tiles": tiles,
"createdAt": int(time.time()),
}
s3.put_object(Bucket=OUTPUT_BUCKET, Key=manifest_key, Body=json.dumps(manifest).encode("utf-8"))
print("manifest", manifest_key)


return {
"status": "SUCCEEDED",
"jobId": job_id,
"manifestKey": manifest_key,
"tilesTotal": total,
}
