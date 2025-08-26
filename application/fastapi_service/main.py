from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

app = FastAPI(title="TSG Image Pipeline API")

# ------------ Request models (aligned with your CLI and UI) -------------
class SplitRequest(BaseModel):
    bucket: str                  # e.g. tsg-demo-dirty-in-991105135552
    key: str                     # e.g. tests/unzipped_scene/B04.jp2
    target_bucket: str           # e.g. tsg-white-stage-991105135552
    tile_size: int = 2048        # default tile size

class UniteRequest(BaseModel):
    bucket: str                  # tiles live here (white-stage)
    target_bucket: str           # output bucket (clean-out)
    manifest: Optional[str] = None       # e.g. manifests/B04.manifest.json
    tiles_prefix: Optional[str] = None   # e.g. tiles/B04/

    @field_validator("tiles_prefix")
    @classmethod
    def _one_of_manifest_or_prefix(cls, v, values):
        # Ensure at least one of (manifest, tiles_prefix) is provided
        if not v and not values.data.get("manifest"):
            raise ValueError("Provide either 'manifest' or 'tiles_prefix'")
        return v

# ------------------------ Health / root ------------------------
@app.get("/healthz")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"message": "TSG Image Pipeline API. Use /ui for the UI or /docs for Swagger."}

# ------------------------ Split / Unite ------------------------
@app.post("/split")
def split(req: SplitRequest):
    # TODO:
    # 1) s3://{req.bucket}/{req.key} -> stream/download JP2
    # 2) Validate header/size, open via OpenJPEG/kakadu/GDAL
    # 3) Tile to {req.tile_size} and write tiles/ + manifest to s3://{req.target_bucket}
    # 4) Return manifest key and tiles prefix
    return {
        "message": "split started",
        "input": {
            "bucket": req.bucket,
            "key": req.key,
            "tile_size": req.tile_size
        },
        "output": {
            "target_bucket": req.target_bucket,
            "tiles_prefix": f"tiles/{req.key.rsplit('/', 1)[-1].rsplit('.jp2', 1)[0]}/",
            "manifest": f"manifests/{req.key.rsplit('/', 1)[-1].rsplit('.jp2', 1)[0]}.manifest.json"
        }
    }

@app.post("/unite")
def unite(req: UniteRequest):
    # Guard: at least one of manifest / tiles_prefix must be present
    if not req.manifest and not req.tiles_prefix:
        raise HTTPException(status_code=400, detail="Provide either 'manifest' or 'tiles_prefix'")

    # TODO:
    # 1) If manifest: read it from s3://{req.bucket}/{req.manifest}
    #    else: list tiles under s3://{req.bucket}/{req.tiles_prefix}
    # 2) Validate checksums / order
    # 3) Merge & re-encode JP2; write to s3://{req.target_bucket}/<basename>.jp2
    # 4) Return output object key
    basename = None
    if req.manifest:
        basename = req.manifest.rsplit("/", 1)[-1].replace(".manifest.json", "")
    elif req.tiles_prefix:
        basename = req.tiles_prefix.strip("/").split("/", 1)[-1].rstrip("/").split("/")[-1]

    return {
        "message": "unite started",
        "input": {
            "bucket": req.bucket,
            "manifest": req.manifest,
            "tiles_prefix": req.tiles_prefix
        },
        "output": {
            "target_bucket": req.target_bucket,
            "object_key": f"{basename}.jp2" if basename else None
        }
    }

# ------------------- Static UI mount (already present) -------------------
from fastapi.staticfiles import StaticFiles
# The pipeline will push ui/index.html to /opt/tsg-ui/index.html
app.mount("/ui", StaticFiles(directory="/opt/tsg-ui", html=True), name="ui")
