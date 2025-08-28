# index.html (updated)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>TSG JP2 Pipeline</title>
  <style>
    :root { --bg:#ffffff; --card:#ffffff; --muted:#475569; --text:#0f172a; --accent:#1e40af; --danger:#b91c1c; }
    html,body { height:100%; background:var(--bg); color:var(--text); font:14px/1.45 system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, "Helvetica Neue", Arial, "Apple Color Emoji", "Segoe UI Emoji"; }
    .wrap { max-width: 1080px; margin: 32px auto; padding: 0 16px; }
    .card { background: var(--card); border-radius: 16px; padding: 20px; box-shadow: 0 6px 24px rgba(2,6,23,.08); border:1px solid rgba(15,23,42,.08);}
    h1 { font-size: 22px; margin: 0 0 12px; }
    h2 { font-size: 16px; margin: 18px 0 10px; color: var(--muted); font-weight: 600; }
    .row { display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: center; }
    .btn { appearance:none; border:0; padding: 10px 14px; border-radius: 10px; background: var(--accent); color: #fff; font-weight: 700; cursor:pointer; }
    .btn[disabled] { opacity:.5; cursor:not-allowed; }
    .btn.outline { background: transparent; color: var(--accent); box-shadow: inset 0 0 0 2px var(--accent); }
    .danger { color: var(--danger); }
    .muted { color: var(--muted); }
    .grid { display:grid; gap: 16px; }
    .cols { display:grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width:980px){ .cols { grid-template-columns: 1fr; } }
    table { width:100%; border-collapse: collapse; }
    th, td { padding: 8px 8px; text-align: left; border-bottom: 1px solid rgba(15,23,42,.08); font-size: 12px; }
    th { color: var(--muted); font-weight: 600; }
    .toast { margin-top: 10px; padding: 10px 12px; border-radius: 8px; background: rgba(30,64,175,.06); border: 1px solid rgba(30,64,175,.25); color: var(--text); }
    .error { background: rgba(185,28,28,.08); border-color: rgba(185,28,28,.25); }
    .loader { width:18px; height:18px; border-radius: 50%; border: 3px solid rgba(15,23,42,.15); border-top-color: var(--accent); animation: spin 1s linear infinite; display:inline-block; vertical-align: -4px; }
    @keyframes spin { to { transform: rotate(360deg);} }
    .small { font-size: 12px; }
    .kbd { background: rgba(2,6,23,.04); border: 1px solid rgba(2,6,23,.08); border-bottom-width:2px; padding:2px 6px; border-radius: 6px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
    footer { color: var(--muted); font-size: 12px; margin-top: 18px; }
    .progress { width:100%; height:12px; background: rgba(2,6,23,.06); border-radius: 999px; overflow:hidden; }
    .bar { height:100%; width:0%; background: var(--accent); transition: width .35s ease; }
    .box { border:1px solid rgba(15,23,42,.12); border-radius: 10px; padding: 10px; min-height: 60px; }
    .list { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.35; white-space: pre-wrap; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="wrap grid">
    <div class="card">
      <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
        <img src="tsglogo.png" alt="TSG" style="height:32px; width:auto;" />
        <h1 style="margin:0;">TSG JP2 Pipeline</h1>
      </div>
      <div class="muted small" id="cfgInfo"></div>

      <h2>1) Choose a JP2 from Input Bucket</h2>
      <div class="row" style="grid-template-columns: 1fr auto;">
        <div class="muted small">Listing from <span class="kbd" id="bucketName"></span></div>
        <button class="btn outline" id="refreshBtn">Refresh</button>
      </div>
      <div id="filesArea" class="grid" style="margin-top: 10px;">
        <div class="muted small">Loading file list… <span class="loader"></span></div>
      </div>

      <h2>2) Split Settings</h2>
      <div class="row" style="grid-template-columns: 200px 1fr;">
        <label for="tilesSelect">Number of tiles</label>
        <select id="tilesSelect" style="width:160px; padding:8px; border-radius:8px; border:1px solid rgba(15,23,42,.15); background:transparent; color:var(--text);">
          <option value="9">9 (3×3)</option>
          <option value="16" selected>16 (4×4)</option>
          <option value="25">25 (5×5)</option>
          <option value="36">36 (6×6)</option>
        </select>
      </div>

      <div class="row" style="margin-top:14px;">
        <div class="small muted">Selected file: <span class="kbd" id="selectedKey">None</span></div>
        <button class="btn" id="splitBtn" disabled>Split</button>
      </div>

      <div id="result" class="toast" style="display:none;"></div>
      <div id="error" class="toast error" style="display:none;"></div>

      <h2>3) Status</h2>
      <div class="grid" style="gap:10px;">
        <div>
          <div class="small muted">Execution ARN</div>
          <input id="statusArn" type="text" placeholder="Execution ARN" style="width:100%; padding:8px; border-radius:8px; border:1px solid rgba(15,23,42,.15); background:transparent; color:var(--text);" />
        </div>

        <div class="progress"><div class="bar" id="progBar"></div></div>

        <div class="row" style="grid-template-columns: 120px 1fr;">
          <div class="muted small">State</div>
          <div class="small" id="stateText">—</div>
        </div>
        <div class="row" style="grid-template-columns: 120px 1fr;">
          <div class="muted small">Tiles</div>
          <div class="small" id="tilesText">—</div>
        </div>
        <div class="row" style="grid-template-columns: 120px 1fr;">
          <div class="muted small">Detail</div>
          <div class="small" id="detailText">—</div>
        </div>
        <div class="row" style="grid-template-columns: 120px 1fr;">
          <div class="muted small">Links</div>
          <div class="small" id="linksText">—</div>
        </div>

        <div class="cols">
          <div>
            <div class="small muted" style="margin-bottom:6px;">Step Functions Events</div>
            <div class="box"><div id="sfnEvents" class="list">—</div></div>
          </div>
          <div>
            <div class="small muted" style="margin-bottom:6px;">Files under <span class="kbd" id="filesPrefix">—</span></div>
            <div class="box"><div id="filesLive" class="list">—</div></div>
          </div>
        </div>
      </div>

      <h2>4) Unite (simulate)</h2>
      <div class="grid" style="gap:10px;">
        <div class="row" style="grid-template-columns: 1fr auto;">
          <div class="small muted">Job ID</div>
          <div class="small"><span class="kbd" id="jobIdText">—</span></div>
        </div>
        <div class="row" style="grid-template-columns: 1fr auto;">
          <div class="small muted">Final file (expected)</div>
          <div class="small"><span class="kbd" id="finalKeyText">—</span></div>
        </div>
        <div>
          <button class="btn" id="uniteBtn" disabled>Unite</button>
        </div>
      </div>

      <footer>TSG © Secure JP2 Pipeline</footer>
    </div>
  </div>

  <script>
    // ===== Fixed configuration (hidden) =====
    const API_BASE = "https://qmiu91xhgk.execute-api.us-east-1.amazonaws.com"; // add "/prod" if needed
    const INPUT_BUCKET  = "jp2-input-991105135552-us-east-1";
    const OUTPUT_BUCKET = "jp2-output-991105135552-us-east-1";

    // ===== DOM =====
    const $ = (id) => document.getElementById(id);
    const cfgInfoEl = $("cfgInfo");
    const filesArea = $("filesArea");
    const bucketNameEl = $("bucketName");
    const selectedKeyEl = $("selectedKey");
    const tilesSelect = $("tilesSelect");
    const splitBtn = $("splitBtn");
    const refreshBtn = $("refreshBtn");
    const resultEl = $("result");
    const errorEl = $("error");

    const statusArnEl = $("statusArn");
    const progBar = $("progBar");
    const stateText = $("stateText");
    const tilesText = $("tilesText");
    const detailText = $("detailText");
    const linksText = $("linksText");
    const sfnEvents = $("sfnEvents");
    const filesPrefixEl = $("filesPrefix");
    const filesLive = $("filesLive");

    const jobIdText = $("jobIdText");
    const finalKeyText = $("finalKeyText");
    const uniteBtn = $("uniteBtn");

    bucketNameEl.textContent = INPUT_BUCKET;
    cfgInfoEl.textContent = `Using fixed configuration • API hidden • Output: ${OUTPUT_BUCKET}`;

    let selectedKey = null;
    let pollHandle = null;
    // Saved from split response
    window.__lastJobId = null;
    window.__lastExpectedTiles = 0;
    window.__tilesPrefix = null;

    function humanSize(bytes){
      if (bytes === 0) return '0 B';
      const k = 1024; const sizes = ['B','KB','MB','GB','TB'];
      const i = Math.floor(Math.log(bytes)/Math.log(k));
      return parseFloat((bytes/Math.pow(k,i)).toFixed(2)) + ' ' + sizes[i];
    }

    function showError(msg){
      errorEl.textContent = msg; errorEl.style.display = 'block';
      resultEl.style.display = 'none';
    }
    function showResult(html){
      resultEl.innerHTML = html; resultEl.style.display = 'block';
      errorEl.style.display = 'none';
    }

    function renderTable(objs){
      if (!objs || objs.length === 0){
        filesArea.innerHTML = '<div class="muted small">No JP2 objects found in bucket.</div>';
        splitBtn.disabled = true; selectedKey = null; selectedKeyEl.textContent = 'None';
        return;
      }
      const rows = objs.map((o, idx) => `
        <tr>
          <td style="width:32px"><input type="radio" name="pick" value="${o.key}" ${idx===0?'checked':''}></td>
          <td><code>${o.key}</code></td>
          <td>${o.size != null ? humanSize(o.size) : ''}</td>
        </tr>`).join('');
      const html = `
        <table>
          <thead>
            <tr><th></th><th>Object Key</th><th>Size</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>`;
      filesArea.innerHTML = html;
      const first = objs[0];
      selectedKey = first ? first.key : null;
      selectedKeyEl.textContent = selectedKey || 'None';
      splitBtn.disabled = !selectedKey;
      filesArea.querySelectorAll('input[name="pick"]').forEach(r => {
        r.addEventListener('change', (e) => {
          selectedKey = e.target.value; selectedKeyEl.textContent = selectedKey;
          splitBtn.disabled = !selectedKey;
        });
      });
    }

    async function listInput(){
      filesArea.innerHTML = '<div class="muted small">Loading file list… <span class="loader"></span></div>';
      try {
        let resp = await fetch(`${API_BASE}/list-input?bucket=${encodeURIComponent(INPUT_BUCKET)}`);
        if (!resp.ok) resp = await fetch(`${API_BASE}/list?bucket=${encodeURIComponent(INPUT_BUCKET)}`);
        if (!resp.ok) throw new Error(`List failed (${resp.status})`);
        const data = await resp.json();
        const objs = (data.objects || data.Contents || []).map(x => ({
          key: x.key || x.Key,
          size: x.size ?? x.Size
        })).filter(o => o.key && /\.jp2$/i.test(o.key));
        renderTable(objs);
      } catch (err){
        console.error(err);
        showError(`Could not load files: ${err.message}.
Backend must expose GET /list-input?bucket=... (JSON: { objects:[{key,size}] }) or /list route.`);
      }
    }

    async function split(){
      if (!selectedKey) return;
      splitBtn.disabled = true; splitBtn.textContent = 'Splitting…';
      try {
        const total = parseInt(tilesSelect.value, 10) || 16;
        const grid = Math.round(Math.sqrt(total));
        const body = {
          inputBucket: INPUT_BUCKET,
          inputKey: selectedKey,
          outputBucket: OUTPUT_BUCKET,
          params: { tilesTotal: total, tilesGrid: grid }
        };
        const resp = await fetch(`${API_BASE}/split`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
        });
        if (!resp.ok) throw new Error(`Split failed (${resp.status})`);
        const data = await resp.json();

        const arn = data.executionArn || '(no arn)';
        const jobId = data.jobId || '';
        const expectedTiles = data.expectedTiles || total;

        // Save for progress & live listing
        window.__lastJobId = jobId;
        window.__lastExpectedTiles = expectedTiles;
        window.__tilesPrefix = jobId ? `tiles/${jobId}/` : '';

        filesPrefixEl.textContent = window.__tilesPrefix || '—';
        sfnEvents.textContent = '—';
        filesLive.textContent = '—';

        // Unite section setup
        jobIdText.textContent = jobId || '—';
        finalKeyText.textContent = jobId ? `final/unite-${jobId}.jp2` : '—';
        uniteBtn.disabled = !jobId;

        showResult(
          `Split started. Execution ARN:<br><code>${arn}</code><br>` +
          (jobId ? `Job ID:<br><code>${jobId}</code><br>` : '') +
          `<br><span class="small">Status updates below.</span>`
        );

        statusArnEl.value = arn;
        startAutoPoll();
      } catch (err){
        showError(err.message);
      } finally {
        splitBtn.disabled = !selectedKey; splitBtn.textContent = 'Split';
      }
    }

    // Unite (simulate)
    async function unite(){
      const jobId = window.__lastJobId;
      if (!jobId) return;
      uniteBtn.disabled = true; uniteBtn.textContent = 'Uniting…';
      try {
        const body = {
          outputBucket: OUTPUT_BUCKET,
          jobId: jobId,
        };
        const resp = await fetch(`${API_BASE}/unite`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
        });
        if (!resp.ok) throw new Error(`Unite failed (${resp.status})`);
        const data = await resp.json();

        const arn = data.executionArn || '(no arn)';
        const expectFinal = data.expectedFinalKey || `final/unite-${jobId}.jp2`;
        finalKeyText.textContent = expectFinal;

        // Start monitoring Unite execution
        statusArnEl.value = arn;
        startAutoPoll();
      } catch (err){
        showError(err.message);
      } finally {
        uniteBtn.disabled = false; uniteBtn.textContent = 'Unite';
      }
    }

    function setProgress(p){
      const clamped = Math.max(0, Math.min(100, Math.round(p)));
      progBar.style.width = clamped + '%';
    }

    function extractProgress(payload){
      let status = payload.status || payload.Status || 'UNKNOWN';
      let percent = payload.percent ?? payload.Percent ?? null;
      let detail = payload.detail || payload.Detail || '';
      let steps = payload.steps || payload.Steps || [];
      if (!percent && typeof payload.output === 'string'){
        try {
          const out = JSON.parse(payload.output);
          if (typeof out.percent === 'number') percent = out.percent;
          if (out.detail) detail = out.detail;
          if (Array.isArray(out.steps)) steps = out.steps;
          if (out.status) status = out.status;
        } catch(_){}}
      if (percent == null && Array.isArray(steps) && steps.length){
        const done = steps.filter(s => /done|ok|complete|finished/i.test(String(s))).length;
        percent = Math.round( (done/steps.length) * 100 );
      }
      if (percent == null){
        if (/RUNNING/i.test(status)) percent = 25; else
        if (/SUCCEEDED/i.test(status)) percent = 100; else
        if (/FAILED|TIMED_OUT|ABORTED/i.test(status)) percent = 100; else
          percent = 0;
      }
      return { status, percent, detail, steps };
    }

    // Read JSON body even on 500s so we can show error messages
    async function checkStatusOnce(arn){
      const url = `${API_BASE}/status/${encodeURIComponent(arn)}`;
      let resp, text;
      try {
        resp = await fetch(url);
        text = await resp.text();
      } catch (e) {
        return { status: 'ERROR', detail: `Network error: ${e.message}` };
      }
      let data = {};
      try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
      if (!resp.ok) {
        const msg = data.message || data.error || text || `HTTP ${resp.status}`;
        return {
          status: `HTTP_${resp.status}`,
          detail: String(msg).slice(0, 1200),
          output: JSON.stringify(data).slice(0, 1200)
        };
      }
      return data;
    }

    async function fetchSfnHistory(arn){
      try {
        const r = await fetch(`${API_BASE}/status-history/${encodeURIComponent(arn)}`);
        if (!r.ok) return null;
        return await r.json(); // {events:[{time,type,detail}], links:{sfn,logs?}}
      } catch { return null; }
    }

    async function listOutput(prefix){
      if (!prefix) return {objects:[]};
      try {
        const r = await fetch(`${API_BASE}/list-output?bucket=${encodeURIComponent(OUTPUT_BUCKET)}&prefix=${encodeURIComponent(prefix)}`);
        if (!r.ok) return {objects:[]};
        return await r.json(); // {objects:[{key,size}]}
      } catch { return {objects:[]}; }
    }

    function renderHistory(hist){
      if (!hist || !Array.isArray(hist.events) || hist.events.length === 0){
        sfnEvents.textContent = '—';
        return;
      }
      const lines = hist.events.map(e => {
        const t = (e.time || '').replace('T',' ').replace('Z','Z');
        const dt = e.detail ? ` — ${e.detail}` : '';
        return `[${t}] ${e.type}${dt}`;
      });
      sfnEvents.textContent = lines.join('\n');
      const links = [];
      if (hist.links && hist.links.sfn) links.push(`<a href="${hist.links.sfn}" target="_blank" rel="noopener">Execution</a>`);
      if (hist.links && hist.links.logs) links.push(`<a href="${hist.links.logs}" target="_blank" rel="noopener">CloudWatch Logs</a>`);
      linksText.innerHTML = links.length ? links.join(' · ') : '—';
    }

    // UPDATED: numeric sort by _<n>.jp2 suffix
    function renderFiles(objs){
      if (!objs || objs.length === 0){
        filesLive.textContent = '—';
        return;
      }
      const rx = /_(\d+)\.jp2$/i;
      const lines = objs
        .slice()
        .sort((a,b) => {
          const ak = String(a.key||''); const bk = String(b.key||'');
          const am = ak.match(rx); const bm = bk.match(rx);
          const ai = am ? parseInt(am[1], 10) : Number.MAX_SAFE_INTEGER;
          const bi = bm ? parseInt(bm[1], 10) : Number.MAX_SAFE_INTEGER;
          if (ai !== bi) return ai - bi;
          return ak.localeCompare(bk);
        })
        .map(o => `${o.key}${o.size!=null ? `  (${humanSize(o.size)})` : ''}`);
      filesLive.textContent = lines.join('\n');
    }

    async function pollStatus(){
      const arn = statusArnEl.value.trim();
      if (!arn) return;

      try {
        const data = await checkStatusOnce(arn);
        let { status, percent, detail } = extractProgress(data);

        // Tiles progress
        const jobId = (window.__lastJobId || '');
        const expected = (window.__lastExpectedTiles || 0);
        if (jobId && expected) {
          try {
            const pResp = await fetch(`${API_BASE}/status-progress?jobId=${encodeURIComponent(jobId)}&expected=${encodeURIComponent(expected)}`);
            if (pResp.ok) {
              const pJson = await pResp.json();
              if (typeof pJson.percent === 'number') percent = pJson.percent;
              if (typeof pJson.tilesCount === 'number') tilesText.textContent = `${pJson.tilesCount} / ${expected}`;
            }
          } catch {}
        } else {
          tilesText.textContent = '—';
        }

        stateText.textContent = status;
        detailText.textContent = detail || '';
        setProgress(percent);

        // History log (SFN events)
        const hist = await fetchSfnHistory(arn);
        if (hist) renderHistory(hist);

        // Live file list for current split job
        if (window.__tilesPrefix) {
          const out = await listOutput(window.__tilesPrefix);
          renderFiles(out.objects || out.Contents || []);
        }

        if (/SUCCEEDED|FAILED|TIMED_OUT|ABORTED/i.test(status)){
          stopAutoPoll();
        }
      } catch (err){
        showError(err.message);
        stopAutoPoll();
      }
    }

    function startAutoPoll(){
      stopAutoPoll();
      pollStatus();
      pollHandle = setInterval(pollStatus, 3000);
    }
    function stopAutoPoll(){
      if (pollHandle) { clearInterval(pollHandle); pollHandle = null; }
    }

    // Wire UI
    refreshBtn.addEventListener('click', listInput);
    splitBtn.addEventListener('click', split);
    uniteBtn.addEventListener('click', unite);
    statusArnEl.addEventListener('change', startAutoPoll);

    // boot
    listInput();
  </script>
</body>
</html>
```

---

# controller.py (updated)

```python
import os
import json
import time
import urllib.parse as up
import datetime as dt
import datetime as _dt
from decimal import Decimal as _Decimal

import boto3
from botocore.exceptions import ClientError

# ===== ENV =====
REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
INPUT_BUCKET = os.environ.get("INPUT_BUCKET", "")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")               # Split SM
STATE_MACHINE_ARN_UNITE = os.environ.get("STATE_MACHINE_ARN_UNITE", "")   # Unite SM

sfn = boto3.client("stepfunctions", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)

# ===== helpers =====
def _json_default(o):
    if isinstance(o, (_dt.datetime, _dt.date, _dt.time)):
        return o.isoformat()
    if isinstance(o, _Decimal):
        return float(o)
    return str(o)


def _resp(code: int, body_obj):
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body_obj, default=_json_default),
    }


def _parse_json_body(event):
    b = event.get("body")
    if not b:
        return {}
    try:
        return json.loads(b)
    except Exception:
        return {}


def _console_sfn_link(exec_arn: str):
    return f"https://{REGION}.console.aws.amazon.com/states/home?region={REGION}#/executions/details/{up.quote(exec_arn, safe='')}"


def _console_logs_link(log_group: str | None):
    if not log_group:
        return None
    return f"https://{REGION}.console.aws.amazon.com/cloudwatch/home?region={REGION}#logsV2:log-groups/log-group/{up.quote(log_group, safe='')}"


# ===== split =====
def _split(event):
    if not STATE_MACHINE_ARN:
        return _resp(500, {"error": "STATE_MACHINE_ARN is not configured"})

    payload = _parse_json_body(event)
    input_bucket = payload.get("inputBucket") or INPUT_BUCKET
    input_key = payload.get("inputKey")
    output_bucket = payload.get("outputBucket") or OUTPUT_BUCKET
    params = payload.get("params") or {}
    tiles_total = int(params.get("tilesTotal", 16))
    tiles_grid = int(params.get("tilesGrid", max(1, int(tiles_total ** 0.5))))

    if not (input_bucket and input_key and output_bucket):
        return _resp(400, {"error": "inputBucket, inputKey, outputBucket are required"})

    job_id = payload.get("jobId") or f"split-job-{int(time.time()*1000)}"
    exec_input = {
        "jobId": job_id,
        "inputBucket": input_bucket,
        "inputKey": input_key,
        "outputBucket": output_bucket,
        "params": {"tilesTotal": tiles_total, "tilesGrid": tiles_grid},
    }

    print("SPLIT start", exec_input)

    try:
        resp = sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=job_id,
            input=json.dumps(exec_input),
        )
    except sfn.exceptions.ExecutionAlreadyExists:
        resp = sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            input=json.dumps(exec_input),
        )

    return _resp(200, {
        "executionArn": resp["executionArn"],
        "jobId": job_id,
        "expectedTiles": tiles_total,
        "links": {"execution": _console_sfn_link(resp["executionArn"])}}
    )


# ===== unite =====
def _unite(event):
    if not STATE_MACHINE_ARN_UNITE:
        return _resp(500, {"error": "STATE_MACHINE_ARN_UNITE is not configured"})

    payload = _parse_json_body(event)
    output_bucket = payload.get("outputBucket") or OUTPUT_BUCKET

    tiles_prefix = payload.get("tilesPrefix")  # e.g. "tiles/<jobId>/"
    job_id = payload.get("jobId")
    manifest_key = payload.get("manifestKey")
    final_key = payload.get("finalKey")  # optional override

    # Extract jobId from manifestKey if present
    if manifest_key and not job_id:
        base = manifest_key.rsplit("/", 1)[-1]
        if base.endswith(".json"):
            job_id = base[:-5]

    if not tiles_prefix and job_id:
        tiles_prefix = f"tiles/{job_id}/"

    if not (tiles_prefix or job_id or manifest_key):
        return _resp(400, {"error": "Provide tilesPrefix or jobId or manifestKey"})

    if not job_id:
        # derive from tiles_prefix if possible
        parts = (tiles_prefix or "").strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "tiles":
            job_id = parts[1]
        else:
            job_id = f"job-{int(time.time()*1000)}"

    if not final_key:
        final_key = f"final/unite-{job_id}.jp2"

    exec_input = {
        "jobId": job_id,
        "outputBucket": output_bucket,
        "tilesPrefix": tiles_prefix,
        "manifestKey": manifest_key,
        "finalKey": final_key,
    }

    print("UNITE start", exec_input)

    try:
        resp = sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN_UNITE,
            name=f"unite-{job_id}",
            input=json.dumps(exec_input),
        )
    except sfn.exceptions.ExecutionAlreadyExists:
        resp = sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN_UNITE,
            input=json.dumps(exec_input),
        )

    return _resp(200, {
        "executionArn": resp["executionArn"],
        "jobId": job_id,
        "expectedFinalKey": final_key,
        "links": {"execution": _console_sfn_link(resp["executionArn"])}}
    )


# ===== status family =====
def _status(execution_arn: str):
    try:
        d = sfn.describe_execution(executionArn=execution_arn)
        return _resp(200, d)
    except sfn.exceptions.ExecutionDoesNotExist:
        return _resp(404, {"error": "Execution not found", "arn": execution_arn})
    except ClientError as e:
        code = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 500)
        return _resp(code or 500, {"error": "DescribeExecution failed", "message": str(e), "arn": execution_arn})
    except Exception as e:
        return _resp(500, {"error": "DescribeExecution exception", "message": str(e), "arn": execution_arn})


def _status_progress(qs):
    job_id = (qs or {}).get("jobId")
    expected = int((qs or {}).get("expected") or 0)
    if not job_id:
        return _resp(400, {"error": "jobId is required"})
    prefix = f"tiles/{job_id}/"
    count = 0
    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=OUTPUT_BUCKET, Prefix=prefix):
            for _ in page.get("Contents", []) or []:
                count += 1
    except ClientError as e:
        return _resp(500, {"error": "S3 list failed", "message": str(e), "prefix": prefix})
    percent = int(min(100, round((count / expected) * 100))) if expected > 0 else None
    return _resp(200, {"jobId": job_id, "tilesPrefix": prefix, "tilesCount": count, "percent": percent})


def _status_detail_or_history(execution_arn: str, history=False):
    try:
        hist = sfn.get_execution_history(executionArn=execution_arn, maxResults=100, reverseOrder=not history)
    except ClientError as e:
        return _resp(500, {"error": "GetExecutionHistory failed", "message": str(e)})

    if history:
        events = []
        log_group = None
        for ev in hist.get("events", []):
            et = ev["type"]
            when = ev.get("timestamp")
            when_s = when.isoformat() if isinstance(when, dt.datetime) else str(when)
            det_key = f"{et[0].lower()}{et[1:]}EventDetails"
            d = ev.get(det_key, {}) or {}

            if et == "LambdaFunctionScheduled":
                fa = d.get("resource") or d.get("functionArn")
                if isinstance(fa, str) and ":function:" in fa:
                    fn_name = fa.split(":function:", 1)[1]
                    log_group = f"/aws/lambda/{fn_name}"

            detail = None
            if "error" in d or "cause" in d:
                detail = json.dumps({k: d[k] for k in ("error", "cause") if k in d})[:2000]
            elif "name" in d:
                detail = d["name"]

            events.append({"time": when_s, "type": et, "detail": detail})

        return _resp(200, {"events": events, "links": {
            "sfn": _console_sfn_link(execution_arn),
            "logs": _console_logs_link(log_group)
        }})

    # detail mode: find last failure + lambda logs hint
    error = cause = failed_state = None
    function_name = None
    for ev in hist.get("events", []):
        et = ev["type"]
        det = ev.get(f"{et[0].lower()}{et[1:]}EventDetails", {}) or {}
        if et in ("ExecutionFailed", "TaskFailed", "LambdaFunctionFailed") and not error:
            error = det.get("error")
            cause = det.get("cause")
            failed_state = det.get("name") or det.get("stateName")
        if et == "LambdaFunctionScheduled":
            fa = det.get("resource") or det.get("functionArn")
            if isinstance(fa, str) and ":function:" in fa:
                function_name = fa.split(":function:", 1)[1]
    log_group = f"/aws/lambda/{function_name}" if function_name else None
    return _resp(200, {
        "error": error, "cause": cause, "failedState": failed_state,
        "logGroup": log_group, "logLink": _console_logs_link(log_group),
        "sfnLink": _console_sfn_link(execution_arn)
    })


# ===== main handler =====
def handler(event, _context):
    try:
        method = (event.get("requestContext") or {}).get("http", {}).get("method", "GET")
        raw_path = event.get("rawPath") or "/"
        qs = event.get("queryStringParameters") or {}

        if method == "OPTIONS":
            return _resp(200, {"ok": True})

        if raw_path == "/split" and method == "POST":
            return _split(event)

        if raw_path == "/unite" and method == "POST":
            return _unite(event)

        if raw_path.startswith("/status/") and method == "GET":
            arn = up.unquote(raw_path.split("/status/", 1)[1])
            return _status(arn)

        if raw_path == "/status-progress" and method == "GET":
            return _status_progress(qs)

        if raw_path.startswith("/status-detail/") and method == "GET":
            arn = up.unquote(raw_path.split("/status-detail/", 1)[1])
            return _status_detail_or_history(arn, history=False)

        if raw_path.startswith("/status-history/") and method == "GET":
            arn = up.unquote(raw_path.split("/status-history/", 1)[1])
            return _status_detail_or_history(arn, history=True)

        if raw_path == "/list-output" and method == "GET":
            bucket = qs.get("bucket") or OUTPUT_BUCKET
            prefix = qs.get("prefix") or ""
            out = []
            try:
                paginator = s3.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                    for it in page.get("Contents", []) or []:
                        out.append({"key": it["Key"], "size": it.get("Size")})
            except ClientError as e:
                return _resp(500, {"error": "S3 list failed", "message": str(e), "bucket": bucket, "prefix": prefix})
            return _resp(200, {"objects": out})

        return _resp(404, {"error": f"No route for {method} {raw_path}"})
    except Exception as e:
        return _resp(500, {"error": "controller exception", "message": str(e)})
```

---

# split\_worker.py (updated)

```python
# infrastructure/lambda/split_worker.py
import json
import os
import time
import boto3
from random import randint
from pathlib import Path

s3 = boto3.client("s3")
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]

def handler(event, context):
    """
    Dummy tiler:
    - Reads jobId, inputKey, params.tilesTotal (default 16), params.tilesGrid
    - Writes tiles at `tiles/{jobId}/{<basename>}_{seq}.jp2` (seq starts at 1)
    - Writes manifest at `manifests/{jobId}.json`
    """
    print("EVENT:", json.dumps(event))
    job_id = event.get("jobId") or f"job-{int(time.time()*1000)}"
    input_key = event.get("inputKey") or ""
    base = Path(input_key).stem or "tile"

    params = event.get("params") or {}
    total = int(params.get("tilesTotal", 16))
    grid = int(params.get("tilesGrid", max(1, int(total ** 0.5))))
    print(f"Split start job={job_id} total={total} grid={grid} base={base}")

    # Simulate tiling work and upload numerically named tiles starting at 1
    for i in range(total):
        seq = i + 1
        key = f"tiles/{job_id}/{base}_{seq}.jp2"
        body = f"DUMMY TILE {seq} {time.time()}".encode("utf-8")
        s3.put_object(Bucket=OUTPUT_BUCKET, Key=key, Body=body)
        print("wrote", key)
        time.sleep(0.1 + (randint(0, 50) / 1000.0))

    manifest_key = f"manifests/{job_id}.json"
    tiles = [f"tiles/{job_id}/{base}_{seq}.jp2" for seq in range(1, total + 1)]
    manifest = {
        "jobId": job_id,
        "sourceKey": input_key,
        "baseName": base,
        "tilesTotal": total,
        "tilesGrid": grid,
        "tilesPrefix": f"tiles/{job_id}/",
        "tiles": tiles,
        "createdAt": int(time.time()),
    }
    s3.put_object(Bucket=OUTPUT_BUCKET, Key=manifest_key, Body=json.dumps(manifest).encode("utf-8"))
    print("manifest", manifest_key)

    return {
        "status": "SUCCEEDED",
        "jobId": job_id,
        "manifestKey": manifest_key,
        "tilesTotal": total,
    }
```
