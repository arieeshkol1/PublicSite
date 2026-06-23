#!/usr/bin/env python3
"""Produce tips-enriched.json: every tip gets an executable drilldown that runs
through the customer's connection (AWS assumed-role / Azure / GCP / OpenAI).

Resolution order for the drilldown of each tip:
  1. keep existing drilldownApis if already present
  2. existing per-service map (tips-sync/drilldown_data.get_drilldown_data)
  3. ALIASES (label variants -> canonical map key)
  4. GAP_MAP (newly authored, internet-verified provider CLIs)

Also applies the safe normalizations from the validation step:
  provider<-cloud, level/actionType defaults, tipId collision fix.
"""
import csv, json, sys, os

sys.path.insert(0, 'tips-sync')
import drilldown_data as dd
sys.path.insert(0, '.')
import importlib.util
spec = importlib.util.spec_from_file_location('gap', '_drilldown_gap_map.py')
gap = importlib.util.module_from_spec(spec); spec.loader.exec_module(gap)

MAPS = {'AWS': dd._AWS_MAP, 'AZURE': dd._AZURE_MAP, 'GCP': dd._GCP_MAP, 'OpenAI': dd._OPENAI_MAP}

def cloudkey(c):
    c = (c or '').strip()
    u = c.upper()
    if u == 'AWS': return 'AWS'
    if u == 'AZURE': return 'AZURE'
    if u == 'GCP': return 'GCP'
    if c.lower() == 'openai': return 'OpenAI'
    return c

def resolve(ck, svc):
    """Return (apis_list, instructions) or (None, None)."""
    m = MAPS.get(ck, {})
    if svc in m:
        d = m[svc]; return d.get('apis'), d.get('drilldownInstructions')
    alias = gap.ALIASES.get(ck, {}).get(svc)
    if alias and alias in m:
        d = m[alias]; return d.get('apis'), d.get('drilldownInstructions')
    if (ck, svc) in gap.GAP_MAP:
        d = gap.GAP_MAP[(ck, svc)]; return d.get('apis'), d.get('drilldownInstructions')
    # alias that points into GAP_MAP (e.g. Azure Log Analytics -> Azure Monitor)
    if alias and (ck, alias) in gap.GAP_MAP:
        d = gap.GAP_MAP[(ck, alias)]; return d.get('apis'), d.get('drilldownInstructions')
    return None, None

with open('_tips_export.csv', encoding='utf-8-sig', newline='') as f:
    rows = [dict(r) for r in csv.DictReader(f)]
def v(r,k): return (r.get(k) or '').strip()

stats = {'already': 0, 'filled': 0, 'still_missing': 0, 'provider_filled': 0,
         'level_filled': 0, 'actionType_filled': 0}
missing = []

for r in rows:
    ck = cloudkey(v(r,'cloud'))
    # safe normalizations
    if not v(r,'provider') and v(r,'cloud'):
        r['provider'] = v(r,'cloud').lower(); stats['provider_filled'] += 1
    if not v(r,'level'): r['level'] = '2'; stats['level_filled'] += 1
    if not v(r,'actionType'): r['actionType'] = 'advisory'; stats['actionType_filled'] += 1
    if v(r,'service') == 'Blob Storage' and v(r,'tipId') == 'azure-storage-002':
        r['tipId'] = 'azure-blobstorage-001'

    # drilldown
    r['checkConnection'] = {'AWS':'aws','AZURE':'azure','GCP':'gcp','OpenAI':'openai'}.get(ck, ck.lower())
    if v(r,'drilldownApis'):
        stats['already'] += 1
        r['checkImplemented'] = 'true'
        continue
    apis, instr = resolve(ck, v(r,'service'))
    if apis:
        r['drilldownApis'] = json.dumps(apis, ensure_ascii=False)
        if instr and not v(r,'drilldownInstructions'):
            r['drilldownInstructions'] = instr
        r['checkImplemented'] = 'true'
        stats['filled'] += 1
    else:
        stats['still_missing'] += 1
        missing.append((ck, v(r,'service'), v(r,'tipId')))

with open('tips-enriched.json', 'w', encoding='utf-8') as f:
    json.dump(rows, f, indent=2, ensure_ascii=False)

print(json.dumps(stats, indent=2))
print(f"\nTotal tips: {len(rows)}")
cov = stats['already'] + stats['filled']
print(f"Drilldown coverage: {cov}/{len(rows)} ({100*cov/len(rows):.1f}%)")
if missing:
    print(f"\nSTILL MISSING ({len(missing)}):")
    for ck, svc, tid in missing:
        print(f"  {ck} / {svc} / {tid}")
print("\nWrote tips-enriched.json")
