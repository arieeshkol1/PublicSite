# infrastructure/lambda/unite_worker.py
import os
import io
import re
import json
import time
import tempfile
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict, Optional

import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")

OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET")  # fallback to event's outputBucket
GDAL_ENABLED = os.environ.get("GDAL_ENABLED", "0") in ("1", "true", "TRUE")

# Paths for GDAL in a Lambda layer (adjust if you packaged differently)
GDALBUILDVRT = "/opt/bin/gdalbuildvrt"
GDAL_TRANSLATE = "/opt/bin/gdal_translate"


def _numeric_key(k: str) -> Tuple[int, str]:
    """
    Extract a numeric suffix from names like ..._<n>.jp2 for correct ordering.
    Returns a tuple (n or big, key) for sorting.
    """
    m = re.search(r'_(\d+)\.jp2$', k, re.IGNORECASE)
    if m:
        return (int(m.group(1)), k)
    # No numeric suffix → keep stable but after numbered ones
    return (10**12, k)


def _list_tiles_from_prefix(bucket: str, prefix: str) -> List[str]:
    """List all objects under prefix and return sorted tile keys (strings)."""
    out = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for it in page.get("Contents", []) or []:
            key = it.get("Key") or ""
            # Only take .jp2 tiles
            if key.lower().endswith(".jp2"):
                out.append(key)
    out.sort(key=_numeric_key)
    return out


def _load_manifest(bucket: str, key: str) -> Dict:
    """Download and parse a JSON manifest from S3."""
    obj = s3.get_object(Bucket=bucket, Key=key)
    data = obj["Body"].read()
    return json.loads(data.decode("utf-8"))


def _download_tiles(bucket: str, keys: List[str], work_dir: Path) -> List[Path]:
    """Download tiles to /tmp; returns local file paths."""
    local_paths = []
    for i, key in enumerate(keys, start=1):
        local = work_dir / Path(key).name
        s3.download_file(bucket, key, str(local))
        print(f"[{i}/{len(keys)}] downloaded {key} -> {local}")
        local_paths.append(local)
    return local_paths


def _run(cmd: List[str], cwd: Optional[Path] = None):
    print("RUN:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    print("STDOUT:", res.stdout[:2000])
    print("STDERR:", res.stderr[:2000])
    if res.returncode != 0:
        raise RuntimeError(f"Command failed ({res.returncode}): {' '.join(cmd)}")


def _gdal_unite(local_tiles: List[Path], out_path: Path):
    """
    Real mosaic using GDAL. Requires GDAL binaries in /opt/bin and
    a Lambda layer with appropriate shared libs.
    """
    with tempfile.TemporaryDirectory() as tdir:
        tdirp = Path(tdir)
        filelist = tdirp / "files.txt"
        with filelist.open("w", encoding="utf-8") as f:
            for p in local_tiles:
                f.write(str(p) + "\n")

        vrt = tdirp / "mosaic.vrt"
        _run([GDALBUILDVRT, "-input_file_list", str(filelist), str(vrt)])

        # Use OpenJPEG driver to produce a JP2
        _run([GDAL_TRANSLATE, "-of", "JP2OpenJPEG", str(vrt), str(out_path)])


def _stub_unite(final_fp: io.BytesIO, meta: Dict):
    """
    Stub: creates a non-image placeholder with a small header and JSON metadata.
    Keeps .jp2 suffix so your pipeline naming stays consistent.
    """
    header = b"TSG-UNITE-STUB\n"
    final_fp.write(header)
    final_fp.write(json.dumps(meta, indent=2).encode("utf-8"))


def handler(ev
