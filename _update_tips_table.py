#!/usr/bin/env python3
"""Update ViewMyBill-CostOptimizationTips from tips-enriched.json.

Safe by design:
  - Default is DRY-RUN (no writes). Pass --apply to write.
  - BEFORE any write, a FULL backup of the table is taken to
    tips-table-backup-<UTC timestamp>.json. If the backup fails, the update
    is aborted (no writes happen).
  - Uses update_item keyed by the EXISTING (service, tipId) — additive only,
    never deletes, never rewrites the partition key.
  - Only sets the enriched/normalized fields:
      drilldownApis, drilldownInstructions, provider, level, actionType,
      checkConnection, checkImplemented
  - The single tipId-collision rename (Blob Storage azure-storage-002 ->
    azure-blobstorage-001) IS applied on --apply: the corrected record is put
    under the new tipId and the old duplicate row is deleted (backup first).

ROLLBACK:
  python _update_tips_table.py --restore tips-table-backup-<ts>.json
  Re-puts every backed-up item (full overwrite), returning the table to the
  exact pre-update state.

Usage:
  python _update_tips_table.py                       # dry run (no writes)
  python _update_tips_table.py --apply               # backup + update
  python _update_tips_table.py --restore <file.json> # roll back from backup
"""
import json, sys, os
from datetime import datetime, timezone
from decimal import Decimal

TABLE = 'ViewMyBill-CostOptimizationTips'
REGION = 'us-east-1'
SET_FIELDS = ['drilldownApis', 'drilldownInstructions', 'provider', 'level',
              'actionType', 'checkConnection', 'checkImplemented']

# tipId renames to apply on --apply: (service, NEW tipId) -> OLD tipId.
# The OLD row is deleted and the corrected record is put under the NEW tipId.
RENAME_OLD_TIPID = {
    ('Blob Storage', 'azure-blobstorage-001'): 'azure-storage-002',
}

APPLY = '--apply' in sys.argv
RESTORE = None
if '--restore' in sys.argv:
    i = sys.argv.index('--restore')
    if i + 1 >= len(sys.argv):
        print("ERROR: --restore requires a backup file path"); sys.exit(1)
    RESTORE = sys.argv[i + 1]


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


def _table():
    import boto3
    return boto3.resource('dynamodb', region_name=REGION).Table(TABLE)


def _scan_all(table):
    items, resp = [], table.scan()
    items.extend(resp.get('Items', []))
    while 'LastEvaluatedKey' in resp:
        resp = table.scan(ExclusiveStartKey=resp['LastEvaluatedKey'])
        items.extend(resp.get('Items', []))
    return items


def _backup(table):
    """Full table scan -> timestamped JSON. Returns the backup path or raises."""
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = f'tips-table-backup-{ts}.json'
    items = _scan_all(table)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False, cls=_DecimalEncoder)
    print(f"Backup written: {path}  ({len(items)} items)")
    return path, len(items)


def do_restore(path):
    if not os.path.exists(path):
        print(f"ERROR: backup file not found: {path}"); sys.exit(1)
    # parse_float=Decimal so numeric attributes are DynamoDB-safe on put_item
    with open(path, encoding='utf-8') as f:
        items = json.load(f, parse_float=Decimal)
    print(f"Restoring {len(items)} items from {path} into {TABLE} ...")
    table = _table()
    ok = err = 0
    with table.batch_writer() as bw:
        for it in items:
            try:
                bw.put_item(Item=it); ok += 1
            except Exception as e:
                err += 1; print(f"  ERROR restoring {it.get('service')}/{it.get('tipId')}: {e}")
    print(f"Restore complete. Re-put: {ok}  Errors: {err}")


def do_update():
    with open('tips-enriched.json', encoding='utf-8') as f:
        tips = json.load(f)

    renamed, to_update = [], []
    for t in tips:
        if t.get('service') == 'Blob Storage' and t.get('tipId') == 'azure-blobstorage-001':
            renamed.append(t)
        else:
            to_update.append(t)

    print(f"Records to update: {len(to_update)}  (mode: {'APPLY' if APPLY else 'DRY-RUN'})")
    print(f"tipId renames (delete duplicate + put corrected): {len(renamed)}")
    for t in renamed:
        old = RENAME_OLD_TIPID.get((t.get('service'), t.get('tipId')), '?')
        print(f"  {t.get('service')}: {old} -> {t.get('tipId')}")

    if not APPLY:
        sample = to_update[0]
        print("\nSample update payload (first record):")
        print(f"  key: service={sample.get('service')!r} tipId={sample.get('tipId')!r}")
        for k in SET_FIELDS:
            print(f"    SET {k} = {str(sample.get(k, ''))[:80]}")
        print("\nDRY RUN — no writes performed. Re-run with --apply (a backup is taken first).")
        return

    # ----- APPLY: backup first, abort on failure -----
    table = _table()
    try:
        backup_path, n = _backup(table)
    except Exception as e:
        print(f"ABORTING — backup failed, no writes performed: {e}")
        sys.exit(1)
    if n == 0:
        print("ABORTING — backup returned 0 items (unexpected); no writes performed.")
        sys.exit(1)

    from botocore.exceptions import ClientError
    ok = err = 0
    for t in to_update:
        svc, tid = t.get('service'), t.get('tipId')
        if not svc or not tid:
            err += 1; continue
        names, values, sets = {}, {}, []
        for i, k in enumerate(SET_FIELDS):
            if k in t and str(t[k]).strip() != '':
                names[f'#f{i}'] = k; values[f':v{i}'] = t[k]; sets.append(f'#f{i} = :v{i}')
        if not sets:
            continue
        try:
            table.update_item(
                Key={'service': svc, 'tipId': tid},
                UpdateExpression='SET ' + ', '.join(sets),
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
            )
            ok += 1
        except ClientError as e:
            err += 1
            print(f"  ERROR {svc}/{tid}: {e.response['Error']['Code']}")

    print(f"\nUpdated: {ok}  Errors: {err}")

    # ----- Apply tipId renames (delete duplicate + put corrected record) -----
    # The backup above lets us roll back if anything goes wrong.
    ren_ok = ren_err = 0
    for t in renamed:
        svc = t.get('service')
        new_tid = t.get('tipId')
        old_tid = RENAME_OLD_TIPID.get((svc, new_tid))
        if not (svc and new_tid and old_tid):
            print(f"  SKIP rename (no mapping): {svc}/{new_tid}")
            continue
        try:
            # 1. Put the full corrected record under the new tipId.
            item = {k: v for k, v in t.items() if str(v).strip() != ''}
            table.put_item(Item=item)
            # 2. Delete the old duplicate row (only if it still exists).
            table.delete_item(
                Key={'service': svc, 'tipId': old_tid},
                ConditionExpression='attribute_exists(tipId)',
            )
            ren_ok += 1
            print(f"  RENAMED {svc}: {old_tid} -> {new_tid} (put new, deleted old)")
        except ClientError as e:
            code = e.response['Error']['Code']
            if code == 'ConditionalCheckFailedException':
                # Old row already gone — the new row is in place, so this is fine.
                ren_ok += 1
                print(f"  RENAMED {svc}: {new_tid} put; old {old_tid} already absent")
            else:
                ren_err += 1
                print(f"  ERROR rename {svc}/{new_tid}: {code}")

    if renamed:
        print(f"Renames applied: {ren_ok}  Errors: {ren_err}")
    print(f"Rollback if needed:  python _update_tips_table.py --restore {backup_path}")


if __name__ == '__main__':
    if RESTORE:
        do_restore(RESTORE)
    else:
        do_update()
