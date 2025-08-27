import json
import os
import time
import boto3
from random import randint

s3 = boto3.client("s3")
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]

def handler(event, context):
    """
    Dummy tiler:
    - Reads jobId, params.tilesTotal (default 16), params.tilesGrid
    - Writes `tiles/{jobId}/tile-XXXX.tile` placeholder objects
    - Writes manifest at `manifests/{jobId}.json`
    """
    print("EVENT:", json.dumps(event))
    job_id = event.get("jobId") or f"job-{int(time.time()*1000)}"
    params = event.get("params") or {}
    total = int(params.get("tilesTotal", 16))
    grid = int(params.get("tilesGrid", max(1, int(total ** 0.5))))
    print(f"Split start job={job_id} total={total} grid={grid}")

    # Simulate tile creation (write small objects)
    for i in range(total):
        key = f"tiles/{job_id}/tile-{i:04d}.tile"
        body = f"DUMMY TILE {i} {time.time()}".encode("utf-8")
        s3.put_object(Bucket=OUTPUT_BUCKET, Key=key, Body=body)
        print("wrote", key)
        # tiny sleep to simulate progress
        time.sleep(0.2 + (randint(0, 50) / 1000.0))

    manifest_key = f"manifests/{job_id}.json"
    manifest = {
        "jobId": job_id,
        "tilesTotal": total,
        "tilesGrid": grid,
        "tilesPrefix": f"tiles/{job_id}/",
        "createdAt": int(time.time()),
    }
    s3.put_object(Bucket=OUTPUT_BUCKET, Key=manifest_key, Body=json.dumps(manifest).encode("utf-8"))
    print("manifest", manifest_key)

    # Return shape for DescribeExecution->output if needed
    return {
        "status": "SUCCEEDED",
        "jobId": job_id,
        "manifestKey": manifest_key,
        "tilesTotal": total,
    }
