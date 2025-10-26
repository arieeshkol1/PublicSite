#!/usr/bin/env python3
"""Fargate worker that powers convert / split / unite tasks.

This script downloads imagery from S3, invokes GDAL utilities inside the
container, and then writes results back to S3.  The original project relied on
an unversioned script baked into the container image; this version lives in the
repository so we can reason about and evolve it.

The worker supports three modes:
  * MODE=convert (default when launched by the Convert Lambda)
  * MODE=unite   (used by the Unite Step Function)
  * default split/tiling behaviour for Step Function jobs

The convert path is tuned to avoid the "Predictor=2 only allows BitsPerSample"
error that occurs with 12/15-bit inputs by aggressively sanitising the
CREATE_OPTS string and always forcing Predictor=1 + NBITS=16 when writing TIFF
outputs.
"""
from __future__ import annotations

import json
import math
import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import boto3

s3 = boto3.client("s3")


def _log(msg: str) -> None:
    print(f"[tiler] {msg}", flush=True)


def _run(cmd: Sequence[str]) -> str:
    pretty = " ".join(shlex.quote(c) for c in cmd)
    _log(f"RUN: {pretty}")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.stdout.decode("utf-8", "ignore")
    if out:
        print(out.rstrip(), flush=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode})\n{out}")
    return out


def _download(bucket: str, key: str, dst: str) -> None:
    _log(f"S3 GET s3://{bucket}/{key} -> {dst}")
    s3.download_file(bucket, key, dst)


def _upload(src: str, bucket: str, key: str, content_type: str | None = None) -> None:
    extra = {"ContentType": content_type} if content_type else {}
    size = os.path.getsize(src)
    _log(f"S3 PUT {src} ({size} bytes) -> s3://{bucket}/{key}")
    s3.upload_file(src, bucket, key, ExtraArgs=extra)


def _parse_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _split_opts(raw: str | None) -> List[str]:
    """Split CREATE_OPTS into GDAL -co arguments, sanitising predictor usage."""
    raw = (raw or "").strip()
    if not raw:
        return []
    parts: List[str] = []
    for chunk in re.split(r"[,\s]+", raw.replace(";", ",")):
        chunk = chunk.strip()
        if not chunk:
            continue
        lowered = chunk.lower()
        if lowered == "-co":
            continue
        if lowered.startswith("-co="):
            chunk = chunk[4:]
        elif lowered.startswith("-co") and len(chunk) > 3:
            chunk = chunk[3:]
            if chunk.startswith("="):
                chunk = chunk[1:]
        if chunk.startswith("-co "):
            chunk = chunk[4:]
        parts.append(chunk)
    return parts


def _sanitize_create_opts(raw: str | None,
                          predictor_policy: str | None,
                          ensure_nbits16: bool,
                          force_predictor: bool) -> List[str]:
    opts = _split_opts(raw)
    clean: List[str] = []
    predictor_seen = False
    for opt in opts:
        upper = opt.upper()
        if upper.startswith("PREDICTOR="):
            predictor_seen = True
            if force_predictor:
                clean.append("PREDICTOR=1")
            elif predictor_policy and predictor_policy.upper() == "DROP":
                continue
            else:
                clean.append(opt)
        else:
            clean.append(opt)
    if force_predictor:
        if not any(o.upper().startswith("PREDICTOR=") for o in clean):
            clean.append("PREDICTOR=1")
    elif predictor_policy and predictor_policy.upper() == "FORCE_1" and not predictor_seen:
        clean.append("PREDICTOR=1")
    if ensure_nbits16 and not any(o.upper().startswith("NBITS=") for o in clean):
        clean.append("NBITS=16")
    args: List[str] = []
    for opt in clean:
        args.extend(["-co", opt])
    return args


def _gdalinfo_driver(path: str) -> str:
    info = _run(["gdalinfo", path])
    for line in info.splitlines():
        line = line.strip()
        if line.startswith("Driver: "):
            return line.split("Driver: ")[-1]
    return ""


def _ensure_driver(path: str, expect: str) -> None:
    driver = _gdalinfo_driver(path)
    if expect not in driver:
        raise RuntimeError(f"Unexpected driver for {path}: {driver}")


def _create_opts_args(fmt: str, raw_opts: str | None, *, sanitize: bool = True) -> List[str]:
    opts = _split_opts(raw_opts)
    if not sanitize:
        args: List[str] = []
        for opt in opts:
            args.extend(["-co", opt])
        return args

    predictor_policy = os.getenv("PREDICTOR_POLICY") or "FORCE_1"
    sanitize_predictor = _parse_bool(os.getenv("SANITIZE_PREDICTOR"))
    force_16bit = _parse_bool(os.getenv("TIFF_FORCE_16BIT"))
    ensure_nbits = force_16bit or fmt == "tiff"
    force_predictor = sanitize_predictor or predictor_policy.upper() == "FORCE_1"
    return _sanitize_create_opts(raw_opts, predictor_policy, ensure_nbits, force_predictor)


def _enforce_tiff_safety(args: List[str]) -> List[str]:
    """Ensure Predictor=1 and NBITS=16 are present (and override conflicting values)."""
    if not args:
        return ["-co", "PREDICTOR=1", "-co", "NBITS=16"]

    normalised: List[str] = []
    seen_predictor = False
    seen_nbits = False
    i = 0
    while i < len(args):
        token = args[i]
        if token.lower() == "-co" and i + 1 < len(args):
            value = args[i + 1]
            upper = value.upper()
            if upper.startswith("PREDICTOR="):
                normalised.extend(["-co", "PREDICTOR=1"])
                seen_predictor = True
            elif upper.startswith("NBITS="):
                normalised.extend(["-co", "NBITS=16"])
                seen_nbits = True
            else:
                normalised.extend(["-co", value])
            i += 2
            continue

        upper = token.upper()
        if upper.startswith("PREDICTOR="):
            normalised.extend(["-co", "PREDICTOR=1"])
            seen_predictor = True
        elif upper.startswith("NBITS="):
            normalised.extend(["-co", "NBITS=16"])
            seen_nbits = True
        else:
            normalised.append(token)
        i += 1

    if not seen_predictor:
        normalised.extend(["-co", "PREDICTOR=1"])
    if not seen_nbits:
        normalised.extend(["-co", "NBITS=16"])
    return normalised


def _convert_to_tiff(src: str, dst: str, create_opts: List[str]) -> None:
    cmd = ["gdal_translate", "-of", "GTiff"]
    if _parse_bool(os.getenv("TIFF_FORCE_16BIT")):
        cmd += ["-ot", "UInt16"]
    cmd += create_opts
    cmd += [src, dst]

    # Belt-and-braces: even after upstream sanitisation, double-check no caller
    # managed to smuggle PREDICTOR=2 or an unexpected NBITS into the command.
    safe_cmd: List[str] = []
    i = 0
    while i < len(cmd):
        token = cmd[i]
        if token.lower() == "-co" and i + 1 < len(cmd):
            value = cmd[i + 1]
            upper = value.upper()
            if upper.startswith("PREDICTOR=") and upper != "PREDICTOR=1":
                safe_cmd.extend(["-co", "PREDICTOR=1"])
            elif upper.startswith("NBITS=") and upper != "NBITS=16":
                safe_cmd.extend(["-co", "NBITS=16"])
            else:
                safe_cmd.extend(["-co", value])
            i += 2
            continue
        safe_cmd.append(token)
        i += 1

    cmd = safe_cmd
    _run(cmd)
    if os.path.getsize(dst) < 1024:
        raise RuntimeError("TIFF output suspiciously small")
    _ensure_driver(dst, "GTiff")


def _convert_to_jp2(src: str, dst: str) -> None:
    _run(["gdal_translate", "-of", "JP2OpenJPEG", src, dst])
    if os.path.getsize(dst) < 1024:
        raise RuntimeError("JP2 output suspiciously small")
    _ensure_driver(dst, "JP2OpenJPEG")


def _convert_to_raw(src: str, dst_base: str) -> Tuple[str, str]:
    bin_path = dst_base + ".bin"
    _run(["gdal_translate", "-of", "ENVI", src, bin_path])
    hdr_path = dst_base + ".hdr"
    if not os.path.exists(hdr_path):
        raise RuntimeError("Expected ENVI .hdr output not found")
    if os.path.getsize(bin_path) < 1024:
        raise RuntimeError("RAW output suspiciously small")
    return bin_path, hdr_path


def _tiles_from_grid(total: int) -> int:
    if total <= 1:
        return 1
    return max(1, int(round(total ** 0.5)))


def _split_tiles(src: str, out_dir: str, base: str, grid: int, fmt: str, create_opts: List[str]) -> List[Tuple[str, str, str]]:
    info = _run(["gdalinfo", src])
    width = height = None
    for line in info.splitlines():
        line = line.strip()
        if line.startswith("Size is"):
            width, height = [int(x.strip()) for x in line.replace("Size is", "").split(",")]
            break
    if not width or not height:
        raise RuntimeError("Could not determine raster size from gdalinfo")

    cols = rows = grid
    tile_w = math.ceil(width / cols)
    tile_h = math.ceil(height / rows)

    if fmt == "tiff":
        ext = ".tif"
        content_type = "image/tiff"
        base_cmd = ["gdal_translate", "-of", "GTiff"] + create_opts
    elif fmt == "keep":
        ext = ".jp2"
        content_type = "image/jp2"
        base_cmd = ["gdal_translate", "-of", "JP2OpenJPEG"]
    else:
        raise NotImplementedError("RAW tiling not implemented")

    out: List[Tuple[str, str, str]] = []
    idx = 0
    for r in range(rows):
        for c in range(cols):
            idx += 1
            xoff = c * tile_w
            yoff = r * tile_h
            xsize = min(tile_w, width - xoff)
            ysize = min(tile_h, height - yoff)
            dst = os.path.join(out_dir, f"{base}_{idx}{ext}")
            cmd = base_cmd + [
                "-srcwin", str(xoff), str(yoff), str(xsize), str(ysize),
                src, dst,
            ]
            _run(cmd)
            if os.path.getsize(dst) < 512:
                raise RuntimeError(f"Tile {idx} looks empty ({dst})")
            if fmt == "tiff":
                _ensure_driver(dst, "GTiff")
            out.append((dst, f"{base}_{idx}{ext}", content_type))
    return out


def _list_s3_keys(bucket: str, prefix: str) -> List[str]:
    keys: List[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            key = obj.get("Key")
            if key and not key.endswith("/"):
                keys.append(key)
    return keys


def _build_vrt(vrt_path: str, tiles: Iterable[str]) -> None:
    list_path = vrt_path + ".txt"
    with open(list_path, "w", encoding="utf-8") as fh:
        for path in tiles:
            fh.write(f"{path}\n")
    _run(["gdalbuildvrt", "-input_file_list", list_path, vrt_path])


def _run_convert() -> None:
    bucket_in = os.getenv("INPUT_BUCKET") or ""
    bucket_out = os.getenv("OUTPUT_BUCKET") or ""
    key = os.getenv("INPUT_KEY") or ""
    fmt = (os.getenv("FORMAT_OPTION") or "tiff").lower()
    tiles_total = int(os.getenv("TILES_TOTAL") or "1")
    grid = int(os.getenv("TILES_GRID") or _tiles_from_grid(tiles_total))
    job_id = os.getenv("JOB_ID") or f"convert-{int(time.time()*1000)}"
    create_opts = _create_opts_args(fmt, os.getenv("CREATE_OPTS"))
    if fmt == "tiff":
        create_opts = _enforce_tiff_safety(create_opts)

    if not bucket_in or not bucket_out or not key:
        raise RuntimeError("INPUT_BUCKET, OUTPUT_BUCKET and INPUT_KEY are required")

    base = Path(key).stem or "image"
    with tempfile.TemporaryDirectory() as td:
        src_path = os.path.join(td, "input.jp2")
        _download(bucket_in, key, src_path)

        if tiles_total <= 1:
            if fmt == "tiff":
                dst = os.path.join(td, f"{base}.tif")
                _convert_to_tiff(src_path, dst, create_opts)
                out_key = f"converted/{base}.tif"
                _upload(dst, bucket_out, out_key, "image/tiff")
                _log(f"JOB {job_id}: wrote {out_key}")
            elif fmt == "keep":
                dst = os.path.join(td, f"{base}.jp2")
                _convert_to_jp2(src_path, dst)
                out_key = f"converted/{base}.jp2"
                _upload(dst, bucket_out, out_key, "image/jp2")
                _log(f"JOB {job_id}: wrote {out_key}")
            elif fmt == "raw":
                dst_base = os.path.join(td, base)
                bin_path, hdr_path = _convert_to_raw(src_path, dst_base)
                bin_key = f"converted/{base}.bin"
                hdr_key = f"converted/{base}.hdr"
                _upload(bin_path, bucket_out, bin_key, "application/octet-stream")
                _upload(hdr_path, bucket_out, hdr_key, "text/plain")
                _log(f"JOB {job_id}: wrote {bin_key} (+hdr)")
            else:
                raise RuntimeError(f"Unsupported format option: {fmt}")
            return

        # tiling workflow
        tiles_dir = os.path.join(td, "tiles")
        os.makedirs(tiles_dir, exist_ok=True)
        tiles = _split_tiles(src_path, tiles_dir, base, grid, fmt, create_opts)
        for local_path, filename, content_type in tiles:
            out_key = f"tiles/{job_id}/{filename}"
            _upload(local_path, bucket_out, out_key, content_type)
        manifest = {
            "jobId": job_id,
            "sourceKey": key,
            "baseName": base,
            "tilesTotal": len(tiles),
            "tilesGrid": grid,
            "tilesPrefix": f"tiles/{job_id}/",
            "tiles": [f"tiles/{job_id}/{fname}" for _, fname, _ in tiles],
            "createdAt": int(time.time()),
        }
        manifest_key = f"manifests/{job_id}.json"
        tmp_manifest = os.path.join(td, "manifest.json")
        with open(tmp_manifest, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh)
        _upload(tmp_manifest, bucket_out, manifest_key, "application/json")
        _log(f"JOB {job_id}: wrote {len(tiles)} tiles + manifest {manifest_key}")


def _run_unite() -> None:
    bucket = os.getenv("OUTPUT_BUCKET") or ""
    prefix = os.getenv("TILES_PREFIX") or ""
    job_id = os.getenv("JOB_ID") or ""
    final_key = os.getenv("FINAL_KEY") or ""
    fmt = (os.getenv("FORMAT_OPTION") or "keep").lower()
    create_opts = _create_opts_args(fmt, os.getenv("CREATE_OPTS"), sanitize=False)

    if not prefix:
        raise RuntimeError("TILES_PREFIX is required for unite mode")
    if not bucket:
        raise RuntimeError("OUTPUT_BUCKET is required for unite mode")
    if not job_id:
        parts = prefix.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "tiles":
            job_id = parts[1]
        else:
            job_id = f"job-{int(time.time()*1000)}"
    if not final_key:
        ext = ".tif" if fmt == "tiff" else ".jp2"
        final_key = f"final/unite-{job_id}{ext}"

    keys = _list_s3_keys(bucket, prefix)
    if not keys:
        raise RuntimeError(f"No tiles found under {prefix}")

    with tempfile.TemporaryDirectory() as td:
        local_tiles: List[str] = []
        for key in keys:
            if not key.lower().endswith((".tif", ".tiff", ".jp2")):
                continue
            local_path = os.path.join(td, key.rsplit("/", 1)[-1])
            _download(bucket, key, local_path)
            local_tiles.append(local_path)
        if not local_tiles:
            raise RuntimeError("No raster tiles to unite")

        vrt_path = os.path.join(td, "mosaic.vrt")
        _build_vrt(vrt_path, local_tiles)

        if fmt == "tiff":
            final_path = os.path.join(td, "mosaic.tif")
            cmd = ["gdal_translate", vrt_path, final_path, "-of", "GTiff"] + create_opts
            if _parse_bool(os.getenv("TIFF_FORCE_16BIT")):
                cmd += ["-ot", "UInt16"]
            _run(cmd)
            content_type = "image/tiff"
            _ensure_driver(final_path, "GTiff")
        elif fmt == "keep":
            final_path = os.path.join(td, "mosaic.jp2")
            _run(["gdal_translate", vrt_path, final_path, "-of", "JP2OpenJPEG"])
            content_type = "image/jp2"
            _ensure_driver(final_path, "JP2OpenJPEG")
        else:
            raise RuntimeError(f"Unsupported unite format: {fmt}")

        _upload(final_path, bucket, final_key, content_type)
        _log(f"UNITE job {job_id}: wrote {final_key}")


def _run_split_default() -> None:
    _log("MODE not specified -> defaulting to convert/split workflow")
    _run_convert()


def main() -> None:
    mode = (os.getenv("MODE") or "").strip().lower()
    if mode == "convert":
        _run_convert()
    elif mode == "unite":
        _run_unite()
    else:
        _run_split_default()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - top-level fail-safe logging
        _log(f"ERROR: {exc}")
        raise
infrastructure/stack.py
