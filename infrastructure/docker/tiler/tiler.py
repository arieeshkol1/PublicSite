import os, math, json, uuid, tempfile, sys
from pathlib import Path
import boto3
from osgeo import gdal

s3 = boto3.client("s3")

def _translate(ds, xoff, yoff, w, h, driver, ext, dst_local, create_opts):
    opts = gdal.TranslateOptions(srcWin=[xoff, yoff, w, h], format=driver,
                                 creationOptions=create_opts if driver == "GTiff" else None)
    out = gdal.Translate(dst_local, ds, options=opts)
    if out is None:
        raise RuntimeError(f"gdal.Translate failed at window {xoff},{yoff},{w},{h}")

def main():
    # Inputs via env (overridden by Step Functions)
    input_bucket = os.environ["INPUT_BUCKET"]
    input_key    = os.environ["INPUT_KEY"]
    output_bucket= os.environ["OUTPUT_BUCKET"]
    job_id       = os.environ.get("JOB_ID") or f"job-{uuid.uuid4()}"
    tiles_total  = int(os.environ.get("TILES_TOTAL", "16"))
    n            = int(os.environ.get("TILES_GRID", str(int(round(math.sqrt(tiles_total))))))
    fmt          = (os.environ.get("FORMAT_OPTION","tiff") or "tiff").lower()
    create_opts  = (os.environ.get("CREATE_OPTS","TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=2")).split(",")

    if n*n != tiles_total: tiles_total = n*n

    # Download input (simple & reliable)
    local_in = "/tmp/in.jp2"
    s3.download_file(input_bucket, input_key, local_in)

    ds = gdal.Open(local_in)
    if ds is None: raise RuntimeError("GDAL failed to open input")
    xsize, ysize = ds.RasterXSize, ds.RasterYSize
    tile_w = math.ceil(xsize / n)
    tile_h = math.ceil(ysize / n)
    base = Path(input_key).stem

    # Driver/ext mapping
    if fmt == "keep": driver, ext = "JP2OpenJPEG", "jp2"
    elif fmt == "raw": driver, ext = "ENVI", "bin"
    else: driver, ext = "GTiff", "tif"

    prefix = f"tiles/{job_id}/"
    created = 0

    with tempfile.TemporaryDirectory() as tdir:
        for row in range(n):
            for col in range(n):
                xoff, yoff = col*tile_w, row*tile_h
                w = min(tile_w, xsize - xoff); h = min(tile_h, ysize - yoff)
                if w <= 0 or h <= 0: continue

                fname = f"{base}_{row}_{col}.{ext}"
                fout = os.path.join(tdir, fname)

                if driver == "ENVI":
                    # RAW .bin + .hdr
                    _translate(ds, xoff, yoff, w, h, driver, ext, fout, create_opts)
                    s3.upload_file(fout, output_bucket, prefix + fname)
                    hdr = fout[:-4] + ".hdr"
                    if os.path.exists(hdr):
                        s3.upload_file(hdr, output_bucket, prefix + f"{base}_{row}_{col}.hdr")
                else:
                    _translate(ds, xoff, yoff, w, h, driver, ext, fout, create_opts)
                    s3.upload_file(fout, output_bucket, prefix + fname)

                created += 1
                if created <= 3 or created == tiles_total:
                    print("wrote", f"s3://{output_bucket}/{prefix}{fname}")

        # manifest
        manifest = {
            "jobId": job_id,
            "input": {"bucket": input_bucket, "key": input_key, "size": [xsize, ysize]},
            "grid": {"n": n, "tile_w": tile_w, "tile_h": tile_h},
            "format": fmt,
            "prefix": prefix,
            "created": created
        }
        s3.put_object(Bucket=output_bucket, Key=prefix+"manifest.json",
                      Body=json.dumps(manifest).encode("utf-8"),
                      ContentType="application/json")

    print(json.dumps({"status":"OK","jobId":job_id,"created":created}))
    return 0

if __name__ == "__main__":
    sys.exit(main())
