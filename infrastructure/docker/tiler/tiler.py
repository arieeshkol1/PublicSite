import os, sys, json, math, subprocess, tempfile, pathlib, boto3

def log(*a): print(*a, flush=True)

def run(cmd):
    log("RUN:", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.stdout: log("STDOUT:", p.stdout[:2000])
    if p.stderr: log("STDERR:", p.stderr[:2000])
    if p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(cmd)}")
    return p

def has_jp2_driver():
    # Look for JP2OpenJPEG in gdalinfo --formats (cheap check)
    p = subprocess.run(["gdalinfo", "--formats"], capture_output=True, text=True)
    return "JP2OpenJPEG" in (p.stdout or "") + (p.stderr or "")

def main():
    # Inputs from ECS environment overrides
    INPUT_BUCKET  = os.environ["INPUT_BUCKET"]
    INPUT_KEY     = os.environ["INPUT_KEY"]
    OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]
    JOB_ID        = os.environ["JOB_ID"]
    TILES_TOTAL   = int(os.environ.get("TILES_TOTAL", "16"))
    TILES_GRID    = int(os.environ.get("TILES_GRID", str(int(math.sqrt(TILES_TOTAL)) or 1)))
    FORMAT_OPTION = (os.environ.get("FORMAT_OPTION") or "tiff").lower()  # keep | tiff | raw

    s3 = boto3.client("s3")

    work = pathlib.Path("/tmp/work")
    outd = pathlib.Path("/tmp/out")
    work.mkdir(parents=True, exist_ok=True)
    outd.mkdir(parents=True, exist_ok=True)

    # 1) Download source
    src_local = work / pathlib.Path(INPUT_KEY).name
    log(f"Downloading s3://{INPUT_BUCKET}/{INPUT_KEY} -> {src_local}")
    s3.download_file(INPUT_BUCKET, INPUT_KEY, str(src_local))

    # 2) Inspect source to get size
    info = run(["gdalinfo", "-json", str(src_local)]).stdout
    meta = json.loads(info)
    size = meta["size"]
    width, height = int(size[0]), int(size[1])
    log(f"Image size: {width}x{height}")

    grid = TILES_GRID
    tile_w = math.ceil(width / grid)
    tile_h = math.ceil(height / grid)

    # 3) Decide effective output format
    effective = FORMAT_OPTION
    jp2_ok = has_jp2_driver()
    if effective == "keep":
        # If JP2 driver is missing, fallback to TIFF to avoid crash
        if not jp2_ok and src_local.suffix.lower() in (".jp2", ".j2k", ".jp2000"):
            log("JP2 driver missing; falling back to TIFF.")
            effective = "tiff"
    if effective == "keep":
        # "keep" means use same extension and driver as source if possible
        if src_local.suffix.lower() in (".tif", ".tiff"):
            driver = "GTiff"; ext = ".tif"
        elif src_local.suffix.lower() in (".jp2", ".j2k", ".jp2000"):
            driver = "JP2OpenJPEG"; ext = ".jp2"
        else:
            # Unknown → safe fallback
            driver = "GTiff"; ext = ".tif"
    elif effective == "tiff":
        driver = "GTiff"; ext = ".tif"
    elif effective == "raw":
        driver = "ENVI";  ext = ".bin"   # will also emit a .hdr
    else:
        log(f"Unknown FORMAT_OPTION={FORMAT_OPTION}; using TIFF.")
        driver = "GTiff"; ext = ".tif"

    # 4) Produce tiles
    base = pathlib.Path(INPUT_KEY).stem  # e.g., B04
    idx = 0
    tile_keys = []

    for gy in range(grid):
        for gx in range(grid):
            idx += 1
            xoff = gx * tile_w
            yoff = gy * tile_h
            w = min(tile_w, width - xoff)
            h = min(tile_h, height - yoff)
            if w <= 0 or h <= 0:
                continue

            if driver == "ENVI":
                # RAW (ENVI) -> .bin + .hdr; we store both
                out_bin = outd / f"{base}_{idx}.bin"
                run([
                    "gdal_translate",
                    "-of", "ENVI",
                    "-srcwin", str(xoff), str(yoff), str(w), str(h),
                    str(src_local), str(out_bin),
                ])
                # ENVI creates .hdr alongside; upload both
                out_hdr = out_bin.with_suffix(".hdr")
                # Upload
                s3.put_object(Bucket=OUTPUT_BUCKET,
                              Key=f"tiles/{JOB_ID}/{out_bin.name}",
                              Body=out_bin.read_bytes())
                if out_hdr.exists():
                    s3.put_object(Bucket=OUTPUT_BUCKET,
                                  Key=f"tiles/{JOB_ID}/{out_hdr.name}",
                                  Body=out_hdr.read_bytes())
                tile_keys.append(f"tiles/{JOB_ID}/{out_bin.name}")
                tile_keys.append(f"tiles/{JOB_ID}/{out_hdr.name}")
            else:
                # GTiff or JP2OpenJPEG
                out_file = outd / f"{base}_{idx}{ext}"
                of = "JP2OpenJPEG" if driver == "JP2OpenJPEG" else "GTiff"
                args = ["gdal_translate",
                        "-of", of,
                        "-srcwin", str(xoff), str(yoff), str(w), str(h)]
                if of == "GTiff":
                    # Reasonable defaults for tiling
                    args += ["-co", "TILED=YES",
                             "-co", "BIGTIFF=IF_SAFER",
                             "-co", "COMPRESS=LZW",
                             "-co", "PREDICTOR=2"]
                run(args + [str(src_local), str(out_file)])

                # Upload tile
                s3.put_object(
                    Bucket=OUTPUT_BUCKET,
                    Key=f"tiles/{JOB_ID}/{out_file.name}",
                    Body=out_file.read_bytes()
                )
                tile_keys.append(f"tiles/{JOB_ID}/{out_file.name}")

            log(f"wrote tile {idx} at {xoff},{yoff} size {w}x{h}")

    # 5) Manifest
    manifest = {
        "jobId": JOB_ID,
        "sourceKey": INPUT_KEY,
        "tilesTotal": TILES_TOTAL,
        "tilesGrid": grid,
        "effectiveFormat": effective,
        "driver": driver,
        "tilesPrefix": f"tiles/{JOB_ID}/",
        "tiles": tile_keys,
    }
    man_key = f"manifests/{JOB_ID}.json"
    s3.put_object(Bucket=OUTPUT_BUCKET, Key=man_key, Body=json.dumps(manifest, indent=2).encode("utf-8"))
    log("manifest:", man_key)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Make sure failure is visible in CloudWatch
        log("FATAL:", repr(e))
        sys.exit(1)
