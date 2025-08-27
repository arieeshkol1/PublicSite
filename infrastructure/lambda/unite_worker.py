import os
import json
import time
import boto3

s3 = boto3.client("s3")

OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]

def handler(event, context):
    """
    Simulated 'unite':
      - Accepts tilesPrefix OR jobId (and optionally finalKey).
      - Lists tiles under tilesPrefix (e.g., tiles/<jobId>/).
      - Writes a single final object: final/unite-<jobId>.jp2
      - Returns finalKey and tilesCount.
    """
    print("EVENT:", json.dumps(event))
    job_id = event.get("jobId")
    tiles_prefix = event.get("tilesPrefix")
    final_key = event.get("finalKey")

    # Derive jobId/tilesPrefix from manifestKey if provided
    manifest_key = event.get("manifestKey")
    if manifest_key and not job_id:
        # expect manifests/<jobId>.json
        base = manifest_key.rsplit("/", 1)[-1]
        if base.endswith(".json"):
            job_id = base[:-5]  # strip .json

    # If still missing tilesPrefix, derive from jobId
    if not tiles_prefix and job_id:
        tiles_prefix = f"tiles/{job_id}/"

    if not tiles_prefix:
        # as a last resort, try to infer from params
        params = event.get("params") or {}
        maybe_job = params.get("jobId")
        if maybe_job:
            job_id = job_id or maybe_job
            tiles_prefix = f"tiles/{job_id}/"

    if not tiles_prefix:
        return {
            "status": "FAILED",
            "error": "tilesPrefix or jobId (or manifestKey) is required"
        }

    # derive job_id from tiles_prefix if missing
    if not job_id:
        parts = tiles_prefix.strip("/").split("/")
        # expect ["tiles", "<jobId>", ...]
        if len(parts) >= 2 and parts[0] == "tiles":
            job_id = parts[1]
        else:
            job_id = f"job-{int(time.time()*1000)}"

    # default finalKey
    if not final_key:
        final_key = f"final/unite-{job_id}.jp2"

    # Count tiles
    tiles_count = 0
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=OUTPUT_BUCKET, Prefix=tiles_prefix):
        for _ in page.get("Contents", []) or []:
            tiles_count += 1

    # Write a small simulated JP2 (placeholder bytes)
    payload = f"UNITE SIMULATION • job={job_id} • tiles={tiles_count} • {time.time()}\n".encode("utf-8")
    s3.put_object(Bucket=OUTPUT_BUCKET, Key=final_key, Body=payload)

    print(f"UNITE wrote: s3://{OUTPUT_BUCKET}/{final_key}  (from prefix {tiles_prefix}, tiles={tiles_count})")

    return {
        "status": "SUCCEEDED",
        "jobId": job_id,
        "tilesPrefix": tiles_prefix,
        "tilesCount": tiles_count,
        "finalKey": final_key,
    }
