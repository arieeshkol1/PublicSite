#!/usr/bin/env python3
"""Compute which (cloud, service) pairs lack drilldown coverage."""
import csv, sys, os
from collections import defaultdict

sys.path.insert(0, os.path.join('tips-sync'))
import drilldown_data as dd

MAPS = {'AWS': dd._AWS_MAP, 'AZURE': dd._AZURE_MAP, 'GCP': dd._GCP_MAP, 'OpenAI': dd._OPENAI_MAP}
print("Existing map coverage (service count per cloud):")
for cl, m in MAPS.items():
    print(f"  {cl:7s}: {len(m)} services -> {sorted(m.keys())}")

with open('_tips_export.csv', encoding='utf-8-sig', newline='') as f:
    rows = list(csv.DictReader(f))
def v(r,k): return (r.get(k) or '').strip()

# Normalize cloud label to map key
def cloudkey(c):
    c = c.strip()
    if c.upper() == 'AWS': return 'AWS'
    if c.upper() == 'AZURE': return 'AZURE'
    if c.upper() == 'GCP': return 'GCP'
    if c.lower() == 'openai': return 'OpenAI'
    return c

# Per (cloud, service): how many tips, how many already have drilldownApis, covered by map?
pairs = defaultdict(lambda: {'tips':0, 'has_dd':0})
for r in rows:
    ck = cloudkey(v(r,'cloud'))
    svc = v(r,'service')
    key = (ck, svc)
    pairs[key]['tips'] += 1
    if v(r,'drilldownApis'):
        pairs[key]['has_dd'] += 1

covered, gap = [], []
for (ck, svc), st in sorted(pairs.items()):
    in_map = ck in MAPS and svc in MAPS[ck]
    (covered if in_map else gap).append((ck, svc, st['tips'], st['has_dd']))

print(f"\n=== (cloud,service) pairs COVERED by existing map: {len(covered)} ===")
print(f"=== (cloud,service) pairs NOT covered (need research): {len(gap)} ===\n")
tips_in_gap = sum(g[2] for g in gap)
print(f"Tips affected by gap: {tips_in_gap} of {len(rows)}\n")
for ck, svc, n, hasdd in gap:
    print(f"  {ck:7s} {svc:38s} tips={n:3d} has_drilldown={hasdd}")
