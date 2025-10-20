import json, os, re, boto3
from typing import Dict, Any

s3 = boto3.client("s3")

HDR_NUM = re.compile(r"^\s*(\w[\w\s/]*)\s*=\s*(.*)$")
BRACES = re.compile(r"^\{(.*)\}$")

# ENVI data type -> (name, bytes per sample)
ENVI_DT = {
    "1": ("Byte", 1),
    "2": ("Int16", 2),
    "3": ("Int32", 4),
    "4": ("Float32", 4),
    "5": ("Float64", 8),
    "12": ("UInt16", 2),
    "13": ("UInt32", 4),
    "14": ("Int64", 8),
    "15": ("UInt64", 8),
}


def epsg_from_header(h: Dict[str, str]) -> int | None:
    pj = h.get("projection info", "")
    mapinfo = h.get("map info", "")
    if "UTM" in pj or "UTM" in mapinfo:
        m = re.search(r"zone\s*=\s*(\d+)", pj) or re.search(r",\s*(\d+)\s*,", mapinfo)
        south = ("south" in pj.lower()) or (", South" in mapinfo)
        if m:
            zone = int(m.group(1))
            return 32700 + zone if south else 32600 + zone
    return None


def parse_envi_hdr(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("envi"):
            continue
        m = HDR_NUM.match(line)
        if not m:
            continue
        k, v = m.group(1).strip().lower(), m.group(2).strip()
        bv = BRACES.match(v)
        if bv:
            v = bv.group(1).strip()
        out[k] = v
    return out


def build_json(h: Dict[str, str]) -> Dict[str, Any]:
    width = int(h.get("samples", "0"))
    height = int(h.get("lines", "0"))
    bands = int(h.get("bands", "1"))
    dtype, bps = ENVI_DT.get(h.get("data type", "12"), ("UInt16", 2))
    interleave = h.get("interleave", "bsq").upper()
    byte_order = h.get("byte order", "0")  # 0=LSB, 1=MSB
    byte_order = "LSB" if byte_order == "0" else "MSB"

    # GeoTransform from ENVI "map info"
    gt = None
    mi = h.get("map info")
    if mi:
        parts = [p.strip() for p in mi.split(',')]
        try:
            x_origin = float(parts[3])
            y_origin = float(parts[4])
            dx = float(parts[5])
            dy = float(parts[6]) if len(parts) > 6 else dx
            gt = [x_origin, dx, 0.0, y_origin, 0.0, -abs(dy)]
        except Exception:
            gt = None

    epsg = epsg_from_header(h)
    return {
        "width": width,
        "height": height,
        "bands": bands,
        "dtype": dtype,
        "bytesPerSample": bps,
        "interleave": interleave,
        "byteOrder": byte_order,
        "geoTransform": gt,
        "epsg": epsg,
    }


def _process_pair(bucket: str, bin_key: str, hdr_key: str, processed: list, errors: list):
    try:
        # parse .hdr
        hdr_obj = s3.get_object(Bucket=bucket, Key=hdr_key)
        hdr_text = hdr_obj["Body"].read().decode("utf-8", "ignore")
        parsed = parse_envi_hdr(hdr_text)
        meta = build_json(parsed)

        # write .raw and .json (copy server-side and then delete originals)
        raw_key = re.sub(r"\.bin$", ".raw", bin_key)
        json_key = re.sub(r"\.bin$", ".json", bin_key)
        s3.copy_object(Bucket=bucket, CopySource={"Bucket": bucket, "Key": bin_key}, Key=raw_key)
        s3.put_object(Bucket=bucket, Key=json_key, Body=json.dumps(meta, ensure_ascii=False).encode("utf-8"))

        # cleanup .bin and .hdr
        try:
            s3.delete_object(Bucket=bucket, Key=bin_key)
        except Exception:
            pass
        try:
            s3.delete_object(Bucket=bucket, Key=hdr_key)
        except Exception:
            pass

        processed.append({"raw": raw_key, "json": json_key})
    except Exception as e:
        errors.append({"bin": bin_key, "hdr": hdr_key, "error": str(e)})


def handler(event, _ctx):
    # Modes:
    # 1) S3 Event: OBJECT_CREATED for *.bin in the output bucket
    # 2) API single: body {bucket, bin_key, hdr_key}
    # 3) API batch:  body {bucket, prefix}

    # --- S3 Event ---
    if isinstance(event, dict) and "Records" in event:
        processed, errors = [], []
        for rec in event.get("Records", []):
            try:
                bkt = rec["s3"]["bucket"]["name"]
                key = rec["s3"]["object"]["key"]
                if not key.lower().endswith('.bin'):
                    continue
                hdr_key = re.sub(r"\.bin$", ".hdr", key)
                # ensure hdr exists
                try:
                    s3.head_object(Bucket=bkt, Key=hdr_key)
                except Exception:
                    errors.append({"bin": key, "hdr": hdr_key, "error": "hdr not found"})
                    continue
                _process_pair(bkt, key, hdr_key, processed, errors)
            except Exception as e:
                errors.append({"error": str(e)})
        return {"statusCode": 200, "body": json.dumps({"ok": True, "processed": processed, "errors": errors})}

    # --- API body modes ---
    body = event.get("body") if isinstance(event, dict) else None
    if isinstance(body, str):
        try:
            import json as _json
            body = _json.loads(body or '{}')
        except Exception:
            body = {}
    body = body or {}

    bucket = body.get("bucket") or os.getenv("DEFAULT_BUCKET")
    prefix = body.get("prefix")
    bin_key = body.get("bin_key")
    hdr_key = body.get("hdr_key")

    if not bucket:
        return {"statusCode": 400, "body": json.dumps({"error":"bucket or DEFAULT_BUCKET required"})}

    processed, errors = [], []

    if bin_key and hdr_key:
        _process_pair(bucket, bin_key, hdr_key, processed, errors)
    elif prefix:
        cont = None
        while True:
            kw = dict(Bucket=bucket, Prefix=prefix)
            if cont: kw["ContinuationToken"] = cont
            r = s3.list_objects_v2(**kw)
            for obj in r.get("Contents", []):
                key = obj["Key"]
                if key.lower().endswith('.bin'):
                    hkey = key[:-4] + '.hdr'
                    try:
                        s3.head_object(Bucket=bucket, Key=hkey)
                    except Exception:
                        errors.append({"bin": key, "hdr": hkey, "error": "hdr not found"})
                        continue
                    _process_pair(bucket, key, hkey, processed, errors)
            cont = r.get("NextContinuationToken")
            if not cont:
                break
    else:
        return {"statusCode": 400, "body": json.dumps({"error":"provide bin_key+hdr_key or prefix"})}

    return {"statusCode": 200, "body": json.dumps({"ok": True, "processed": processed, "errors": errors})}
