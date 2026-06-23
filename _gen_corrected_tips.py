#!/usr/bin/env python3
"""Produce a corrected tips JSON from the exported CSV.

SAFE, non-destructive normalizations only (no service-PK changes):
  - provider: fill from cloud (lowercased) when empty
  - level: default "2" when empty
  - actionType: default "advisory" when empty
  - tipId collision fix: the 'Blob Storage' row using azure-storage-002
    (a DIFFERENT tip than the 'Storage' azure-storage-002) is re-IDed to
    azure-blobstorage-001 so tipIds are globally unique.

Everything else is preserved verbatim. Writes:
  - tips-corrected.json   (full corrected dataset)
  - tips-changes.json     (audit log of what changed)
"""
import csv
import json

SRC = '_tips_export.csv'

with open(SRC, encoding='utf-8-sig', newline='') as f:
    rows = [dict(r) for r in csv.DictReader(f)]

def v(r, k): return (r.get(k) or '').strip()

changes = {'provider_filled': 0, 'level_filled': 0, 'actionType_filled': 0, 'tipId_reassigned': []}

for r in rows:
    # A. provider <- cloud
    if not v(r, 'provider') and v(r, 'cloud'):
        r['provider'] = v(r, 'cloud').lower()
        changes['provider_filled'] += 1
    # B. level default
    if not v(r, 'level'):
        r['level'] = '2'
        changes['level_filled'] += 1
    # C. actionType default
    if not v(r, 'actionType'):
        r['actionType'] = 'advisory'
        changes['actionType_filled'] += 1
    # D. tipId collision: Blob Storage / azure-storage-002 -> azure-blobstorage-001
    if v(r, 'service') == 'Blob Storage' and v(r, 'tipId') == 'azure-storage-002':
        r['tipId'] = 'azure-blobstorage-001'
        changes['tipId_reassigned'].append({
            'service': 'Blob Storage',
            'old_tipId': 'azure-storage-002',
            'new_tipId': 'azure-blobstorage-001',
        })

with open('tips-corrected.json', 'w', encoding='utf-8') as f:
    json.dump(rows, f, indent=2, ensure_ascii=False)

with open('tips-changes.json', 'w', encoding='utf-8') as f:
    json.dump(changes, f, indent=2, ensure_ascii=False)

print('tips-corrected.json written:', len(rows), 'records')
print('changes:', json.dumps(changes, indent=2))
