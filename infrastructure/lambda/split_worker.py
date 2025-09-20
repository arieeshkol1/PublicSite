# infrastructure/lambda/split_worker.py
import os, json, math, time, shlex, tempfile, subprocess
from pathlib import Path
import boto3

s3 = boto3.client("s3")

# Optional env overrides
OUTPUT_BUCKET_ENV = os.environ.get("OUTPUT_BUCKET")
INPUT_BUCKET_ENV  = os.environ.get("INPUT_BUCKET")

def _run(cmd: str) -> str:
    p = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode("utf-8", "ignore")
    if p.returncode != 0:
        raise RuntimeError(f"[GDAL ERROR]\nCMD: {cmd}\nOUT:\n{out}")
    return out

def _assert_driver(path: str, expect: str):
    info = _run(f"gdalinfo {shlex.quote(path)}")
    if f"Driver: {expect}" not in info:
        raise RuntimeError(f"Unexpected driver. Wanted '{expect}', got:\n{info[:2000]}")

def _download(bucket: str, key: str, to_path: str):
    s3.download_file(bucket, key, to_path)

def _upload(path: str, bucket: str, key: str, content_type: str | None):
    extra = {"ContentType": content_type} if content_type else None
    s3.upload_file(path, bucket, key, ExtraArgs=(extra or {}))

def _raster_size(src_path: str) -> tuple[int,int]:
    info = _run(f"gdalinfo {shlex.quote(src_path)}")
    # Looks for: "Size is 12000, 8000"
    for line in info.splitlines():
        line = line.strip()
        if line.startswith("Size is"):
            w, h = line.replace("Size is", "").strip().split(",")
            return int(w), int(h)
    raise RuntimeError("Could not parse raster size from gdalinfo")

def _convert_only_to_tiff(src_path: str, dst_path: str):
    _run(
        f"gdal_translate -of GTiff "
        f"-co TILED=YES -co COMPRESS=LZW -co PREDICTOR=2 -co BIGTIFF=IF_SAFER "
        f"{shlex.quote(src_path)} {shlex.quote(dst_path)}"
    )
    if os.path.getsize(dst_path) < 1024:
        raise RuntimeError("TIFF too small; conversion likely failed")
    _assert_driver(dst_path, "GTiff/GeoTIFF")

def _convert_only_to_jp2(src_path: str, dst_path: str):
    # Re-encode to JP2 (sanitization) rather than rename
    _run(f"gdal_translate -of JP2OpenJPEG {shlex.quote(src_path)} {shlex.quote(dst_path)}")
    if os.path.getsize(dst_path) < 1024:
        raise RuntimeError("JP2 too small; conversion likely failed")
    _assert_driver(dst_path, "JP2OpenJPEG/JPEG-2000 part 1 (ISO/IEC 15444-1)")

def _split_to_tiles(src_path: str, out_dir: str, base: str, grid: int, fmt: str):
    W, H = _raster_size(src_path)
    cols = rows = grid
    tile_w = math.ceil(W / cols)
    tile_h = math.ceil(H / rows)

    if fmt == "tiff":
        of, ext, ct, co = "GTiff", ".tif", "image/tiff", "-co TILED=YES -co COMPRESS=LZW -co PREDICTOR=2 -co BIGTIFF=IF_SAFER"
    elif fmt == "keep":
        of, ext, ct, co = "JP2OpenJPEG", ".jp2", "image/jp2", ""
    else:
        raise NotImplementedError("RAW/other tiling not implemented")

    out_files: list[tuple[str,str,str]] = []  # (local_path, s3_key, content_type)
    idx = 0
    for r in range(rows):
        for c in range(cols):
            idx += 1
            xoff = c * tile_w
            yoff = r * tile_h
            xsize = min(tile_w, W - xoff)
            ysize = min(tile_h, H - yoff)
            dst = os.path.join(out_dir, f"{base}_{idx}{ext}")
            cmd = (
                f"gdal_translate -of {of} {co} "
                f"-srcwin {xoff} {yoff} {xsize} {ysize} "
                f"{shlex.quote(src_path)} {shlex.quote(dst)}"
            )
            _run(cmd)
            if os.path.getsize(dst) < 1024:
                raise RuntimeError(f"Tile {idx} too small; write failed")
            if fmt == "tiff":
                _assert_driver(dst, "GTiff/GeoTIFF")
            out_files.append((dst, f"{base}_{idx}{ext}", ct))
    return out_files  # list of tuples

def handler(event, _ctx):
    """
    Expected event (same contract your UI/controller use):
    {
      "jobId": "...",                                # optional
      "inputBucket": "jp2-input-...",                # REQUIRED for real conversion
      "inputKey": "path/file.jp2",                   # REQUIRED
      "outputBucket": "jp2-output-...",              # REQUIRED (or env OUTPUT_BUCKET)
      "params": {
        "tilesTotal": 1,                             # 1 = no split (convert-only)
        "tilesGrid": 1,                              # optional; derived from tilesTotal if missing
        "formatOption": "tiff"                       # "keep" | "tiff" | "raw"(TODO)
      }
    }
    """
    t0 = time.time()
    job_id = event.get("jobId") or f"split-job-{int(time.time()*1000)}"
    input_bucket  = event.get("inputBucket") or INPUT_BUCKET_ENV
    input_key     = event.get("inputKey") or ""
    output_bucket = (OUTPUT_BUCKET_ENV or
                     event.get("outputBucket") or
                     os.environ.get("OUTPUT_BUCKET"))

    if not input_bucket:
        raise RuntimeError("inputBucket missing (event.inputBucket or env INPUT_BUCKET)")
    if not input_key:
        raise RuntimeError("inputKey missing")
    if not output_bucket:
        raise RuntimeError("outputBucket missing (event.outputBucket or env OUTPUT_BUCKET)")

    base = Path(input_key).stem or "image"
    params = event.get("params") or {}
    tiles_total = int(params.get("tilesTotal") or 1)       # CRITICAL: int()
    tiles_grid  = int(params.get("tilesGrid") or max(1, int(math.sqrt(tiles_total))))
    fmt         = (params.get("formatOption") or "keep").lower()

    print(f"[SPLIT] job={job_id} in={input_bucket}/{input_key} out-bucket={output_bucket} "
          f"tilesTotal={tiles_total} grid={tiles_grid} fmt={fmt}")

    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "in.jp2")
        _download(input_bucket, input_key, src)

        # === 1) Convert-only ===
        if tiles_total == 1:
            if fmt == "tiff":
                dst = os.path.join(td, f"{base}.tif")
                _convert_only_to_tiff(src, dst)
                out_key = f"converted/{base}.tif"
                _upload(dst, output_bucket, out_key, "image/tiff")
                dur = int((time.time() - t0) * 1000)
                return {
                    "status": "SUCCEEDED",
                    "jobId": job_id,
                    "expectedTiles": 1,
                    "tilesCount": 1,
                    "output_key": out_key,
                    "output_size": os.path.getsize(dst),
                    "duration_ms": dur
                }
            elif fmt == "keep":
                dst = os.path.join(td, f"{base}.jp2")
                _convert_only_to_jp2(src, dst)
                out_key = f"converted/{base}.jp2"
                _upload(dst, output_bucket, out_key, "image/jp2")
                dur = int((time.time() - t0) * 1000)
                return {
                    "status": "SUCCEEDED",
                    "jobId": job_id,
                    "expectedTiles": 1,
                    "tilesCount": 1,
                    "output_key": out_key,
                    "output_size": os.path.getsize(dst),
                    "duration_ms": dur
                }
            else:
                raise NotImplementedError("convert-only RAW not implemented")

        # === 2) Real tiling ===
        tiles_dir = os.path.join(td, "tiles")
        os.makedirs(tiles_dir, exist_ok=True)
        out_files = _split_to_tiles(src, tiles_dir, base, tiles_grid, fmt)

        uploaded = 0
        for local_path, fname, ct in out_files:
            s3_key = f"tiles/{job_id}/{fname}"
            _upload(local_path, output_bucket, s3_key, ct)
            uploaded += 1
            if uploaded <= 3 or uploaded == len(out_files):
                print("uploaded", s3_key)

        # Write manifest (optional, unchanged contract)
        manifest_key = f"manifests/{job_id}.json"
        manifest = {
            "jobId": job_id,
            "sourceKey": input_key,
            "baseName": base,
            "tilesTotal": len(out_files),
            "tilesGrid": tiles_grid,
            "tilesPrefix": f"tiles/{job_id}/",
            "tiles": [f"tiles/{job_id}/{fname}" for _, fname, _ in out_files],
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
            "tilesTotal": len(out_files),
        }
