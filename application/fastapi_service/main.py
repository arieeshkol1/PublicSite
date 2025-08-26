from fastapi import FastAPI, UploadFile, HTTPException
from pydantic import BaseModel
import hashlib

app = FastAPI(title="TSG Image Pipeline API")

class SplitRequest(BaseModel):
    s3_uri: str
    tiles_x: int
    tiles_y: int
    target_bucket: str

class UniteRequest(BaseModel):
    manifest_uri: str
    target_bucket: str

@app.get("/healthz")
def health():
    return {"status": "ok"}

@app.post("/split")
def split(req: SplitRequest):
    # TODO: download JP2 from s3_uri, validate, split into tiles_x * tiles_y,
    #       convert each tile to RAW/TIFF, and write manifest + checksums to target_bucket
    return {"message": "split started", "request": req.dict()}

@app.post("/unite")
def unite(req: UniteRequest):
    # TODO: read manifest_uri, fetch tiles, validate checksums, merge and re-encode JP2
    return {"message": "unite started", "request": req.dict()}