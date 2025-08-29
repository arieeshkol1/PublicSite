# infrastructure/lambda/split_worker.py
import json
import os
import time
from random import randint
from pathlib import Path

import boto3

s3 = boto3.client("s3")

# OUTPUT_BUCKET can be set in env; if not, we use the event's outputBucket.
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "")

def handler(event, _context):
    """
    Dummy splitter (baseline-compatible):
    - Reads: jobId, inputKey, params.tilesTotal (default 16), params.tilesGrid
    - Writes tiles to: tiles/{jobId}/{<basename>}_{seq}.jp2  (seq starts at 1)
    - Writes manifest to: manifests/{jobId}.json
    Return payload matches controller expectations.
    """
    # ---- inputs ----
    job_id = event.get("jobId") or f"split-job-{int(time.time()*1000)}"
    input_key = event.get("inputKey") or ""
    output_bucket = (OUTPUT_BUCKET or
                     event.get("outputBucket") or
                     os.environ.get("OUTPUT_BUCKET") or "")
    if not output_bucket:
        raise RuntimeError("OUTPUT_BUCKET not set (env or event.outputBucket)")

    base = Path(input_key).stem or "tile"
    params = event.get("params") or {}
    total = int(params.get("tilesTotal", 16))
    grid = int(params.get("tilesGrid", max(1, int(total ** 0.5))))

    print(f"[SPLIT] job={job_id} input={input_key} out-bucket={output_bucket} total={total} grid={grid}")

    # ---- write tiles (dummy content) ----
    for i in range(total):
        seq = i + 1
        key = f"tiles/{job_id}/{base}_{seq}.jp2"   # keep .jp2 for continuity; diode-safe tiles will be .tif later
        body = f"DUMMY TILE {seq} {time.time()}".encode("utf-8")
        s3.put_object(Bucket=output_bucket, Key=key, Body=body)
        if seq <= 3 or seq == total:
            print("wrote", key)
        time.sleep(0.05 + (randint(0, 30) / 1000.0))  # tiny stagger for visible progress

    # ---- write manifest ----
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
    s3.put_object(
        Bucket=output_bucket,
        Key=manifest_key,
        Body=json.dumps(manifest).encode("utf-8"),
        ContentType="application/json"
    )
    print("manifest", manifest_key)

    return {
        "status": "SUCCEEDED",
        "jobId": job_id,
        "manifestKey": manifest_key,
        "tilesTotal": total,
    }
