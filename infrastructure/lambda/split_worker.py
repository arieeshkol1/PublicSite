# infrastructure/lambda/split_worker.py
import json
import os
import time
import math
import shlex
import subprocess
from pathlib import Path
import tempfile

import boto3

s3 = boto3.client("s3")

OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "")

GDAL_TRANSLATE = os.environ.get("GDAL_TRANSLATE_BIN", "gdal_translate")
GDAL_INFO = os.environ.get("GDAL_INFO_BIN", "gdalinfo")

# Creation options for lossless JP2 with OpenJPEG, preserving georef boxes
# (NOTE: Requires OpenJPEG driver in the container)
JP2_CO = [
    "-co", "REVERSIBLE=YES",   # lossless
    "-co", "GMLJP2=YES",       # embed GML boxes when present
    "-co", "GeoJP2=YES"        # embed GeoTIFF-in-JP2 box when present
]

def run(cmd):
    print("[CMD]", " ".join(shlex.quote(c) for c in cmd))
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(p.stdout)
    if p.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}")

def gdal_info(path):
    cmd = [GDAL_INFO, "-json", path]
    print("[gdalinfo] reading", path)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(p.stdout)
    if p.returncode != 0:
        raise RuntimeError(f"gdalinfo failed for {path}")
    return json.loads(p.stdout)

def handler(event, _context):
    """
    Real splitter:
    - Downloads JP2 from S3 to local tmp
    - Uses gdalinfo to probe size
    - Splits into a grid (tilesGrid x tilesGrid) using gdal_translate -srcwin
    - Writes tiles to s3://<OUTPUT_BUCKET>/tiles/{jobId}/{base}_{seq}.jp2 (lossless)
    - Emits a manifest: s3://<OUTPUT_BUCKET>/manifests/{jobId}.json
    - Small/QI images: pass-through as a single 'tile' (no split) to avoid failures
    Inputs:
      event.jobId, event.inputBucket (optional), event.inputKey (required),
      event.outputBucket (optional), event.params.tilesTotal / tilesGrid
    """
    # -------- inputs --------
    job_id = event.get("jobId") or f"split-job-{int(time.time()*1000)}"
    input_key = event.get("inputKey") or ""
    input_bucket = event.get("inputBucket") or os.environ.get("INPUT_BUCKET")
    output_bucket = (OUTPUT_BUCKET or event.get("outputBucket") or os.environ.get("OUTPUT_BUCKET"))

    if not input_bucket or not input_key:
        raise RuntimeError("inputBucket + inputKey are required")
    if not output_bucket:
        raise RuntimeError("OUTPUT_BUCKET not set (env or event.outputBucket)")

    params = event.get("params") or {}
    tiles_total = int(params.get("tilesTotal", 16))
    grid = int(params.get("tilesGrid", max(1, int(math.sqrt(tiles_total)))))  # e.g., 4 → 4x4

    base = Path(input_key).stem or "tile"
    print(f"[SPLIT] job={job_id} src=s3://{input_bucket}/{input_key} out-bucket={output_bucket} grid={grid}x{grid}")

    # -------- temp workspace --------
    with tempfile.TemporaryDirectory() as td:
        local_src = os.path.join(td, base + ".jp2")
        # download
        print("[DL] ->", local_src)
        s3.download_file(input_bucket, input_key, local_src)

        # probe
        info = gdal_info(local_src)
        bands = info["bands"]
        size_x, size_y = info["size"]  # [x, y]
        print(f"[INFO] size={size_x}x{size_y} bands={len(bands)}")

        # -------- small image guard (pass-through) --------
        # If the image is too small for the requested grid, write a single "tile" that is the full image.
        # This prevents failures and avoids unnecessary re-windowing.
        min_tile_w = max(1, size_x // grid)
        min_tile_h = max(1, size_y // grid)
        too_small = (size_x < grid) or (size_y < grid) or (min_tile_w == 0) or (min_tile_h == 0)

        tile_keys = []

        if too_small or grid <= 1:
            # Pass-through (still lossless re-encode for diode-safety consistency)
            out_local = os.path.join(td, f"{base}_1.jp2")
            cmd = [GDAL_TRANSLATE, local_src, out_local] + JP2_CO
            run(cmd)
            out_key = f"tiles/{job_id}/{base}_1.jp2"
            print("[UP]", out_key)
            s3.upload_file(out_local, output_bucket, out_key, ExtraArgs={"ContentType": "image/jp2"})
            tile_keys.append(out_key)
            tiles_total = 1
            grid = 1

        else:
            # -------- grid split --------
            # Compute window sizes (last tile clamps to image edge)
            tile_w = size_x // grid
            tile_h = size_y // grid
            if tile_w < 1 or tile_h < 1:
                # Fallback to pass-through
                out_local = os.path.join(td, f"{base}_1.jp2")
                cmd = [GDAL_TRANSLATE, local_src, out_local] + JP2_CO
                run(cmd)
                out_key = f"tiles/{job_id}/{base}_1.jp2"
                print("[UP]", out_key)
                s3.upload_file(out_local, output_bucket, out_key, ExtraArgs={"ContentType": "image/jp2"})
                tile_keys.append(out_key)
                tiles_total = 1
                grid = 1
            else:
                seq = 0
                for r in range(grid):
                    for c in range(grid):
                        xoff = c * tile_w
                        yoff = r * tile_h
                        # width/height clamp on last row/col
                        w = tile_w if c < grid - 1 else (size_x - xoff)
                        h = tile_h if r < grid - 1 else (size_y - yoff)
                        if w <= 0 or h <= 0:
                            continue
                        seq += 1
                        out_local = os.path.join(td, f"{base}_{seq}.jp2")
                        cmd = [
                            GDAL_TRANSLATE,
                            "-srcwin", str(xoff), str(yoff), str(w), str(h),
                            local_src,
                            out_local,
                            *JP2_CO
                        ]
                        run(cmd)
                        out_key = f"tiles/{job_id}/{base}_{seq}.jp2"
                        print("[UP]", out_key, f"(win {xoff},{yoff} {w}x{h})")
                        s3.upload_file(out_local, output_bucket, out_key, ExtraArgs={"ContentType": "image/jp2"})
                        tile_keys.append(out_key)

                tiles_total = len(tile_keys)

        # -------- manifest --------
        manifest_key = f"manifests/{job_id}.json"
        manifest = {
            "jobId": job_id,
            "sourceKey": input_key,
            "baseName": base,
            "tilesTotal": tiles_total,
            "tilesGrid": grid,
            "tilesPrefix": f"tiles/{job_id}/",
            "tiles": tile_keys,
            "createdAt": int(time.time()),
            "lossless": True,
            "format": "JP2OpenJPEG",
            "notes": "Lossless split using gdal_translate -srcwin with REVERSIBLE=YES; small/QI images pass-through as single tile."
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
        "tilesTotal": tiles_total,
    }
