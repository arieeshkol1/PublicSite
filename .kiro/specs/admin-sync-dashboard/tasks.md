# Implementation Plan: Admin Sync Dashboard

## Overview

Add sync log persistence to the tips-sync Lambda, three new admin API routes for sync status/logs/trigger, and a "Tips Sync" tab to the admin frontend. Implementation uses Python (backend) and vanilla JavaScript (frontend) matching the existing codebase.

## Tasks

- [ ] 1. Add sync log writer to tips-sync Lambda
  - [ ] 1.1 Add `_write_sync_log` function to `tips-sync/lambda_function.py`
    - Create function that writes a `SYNC_LOG#<ISO-timestamp>` record to the Tips_Table
    - Item fields: `service=SYSTEM`, `tipId=SYNC_LOG#<ts>`, `timestamp`, `triggerType`, `sourcesQueried`, `sourcesSucceeded`, `sourcesFailed`, `tipsInserted`, `tipsUpdated`, `tipsUnchanged`, `durationMs`, `status`
    - Include `errorMessage` field only when `status=failed`
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ] 1.2 Call `_write_sync_log` from `lambda_handler` success and failure paths
    - After `_write_sync_metadata` call, add `_write_sync_log` with `status="success"`
    - In the `except Exception` block, add `_write_sync_log` with `status="failed"` and `errorMessage=str(e)`
    - Wrap in try/except so log write failure doesn't break the sync
    - _Requirements: 1.1, 1.3, 1.4_

- [ ] 2. Add sync API routes to admin-handler Lambda
  - [ ] 2.1 Add `handle_get_sync_status` to `admin-handler/lambda_function.py`
    - Validate JWT token
    - Query Tips_Table for `Key={'service': 'SYSTEM', 'tipId': 'SYNC_METADATA'}`
    - Return the metadata record (stripped of DynamoDB keys) or `{"status": null, "message": "No sync has been executed yet"}`
    - _Requirements: 3.1, 3.2, 3.3, 8.1, 8.2_

  - [ ] 2.2 Add `handle_get_sync_logs` to `admin-handler/lambda_function.py`
    - Validate JWT token
    - Query Tips_Table with `service=SYSTEM` and `begins_with(tipId, 'SYNC_LOG#')`, `ScanIndexForward=False`
    - Also fetch SYNC_METADATA record
    - Return `{"logs": [...], "metadata": {...}}` with DynamoDB keys stripped
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 8.1, 8.2_

  - [ ] 2.3 Add `handle_trigger_sync` to `admin-handler/lambda_function.py`
    - Validate JWT token
    - Create Lambda client and invoke `slashmybill-tips-sync` with `InvocationType='Event'` and payload `{"manual": true}`
    - Return 202 on success, 500 on failure
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 8.1, 8.2_

  - [ ] 2.4 Register the three new routes in the `routes` dict
    - Add `'GET /admin/tips-sync/status': handle_get_sync_status`
    - Add `'GET /admin/tips-sync/logs': handle_get_sync_logs`
    - Add `'POST /admin/tips-sync/trigger': handle_trigger_sync`
    - _Requirements: 2.1, 3.1, 4.1_

- [ ] 3. Checkpoint
  - Ensure all backend code is syntactically correct and consistent with existing patterns, ask the user if questions arise.

- [ ] 4. Add Tips Sync tab to admin frontend
  - [ ] 4.1 Add "Tips Sync" tab button and tab content HTML to `admin/index.html`
    - Add `<button class="tab-btn" data-tab="sync">Tips Sync</button>` to the tab nav
    - Add `<div id="sync-tab" class="tab-content" hidden>` with status cards div, trigger button, and sync history table
    - Table columns: #, Timestamp, Trigger, Inserted, Updated, Unchanged, Duration, Sources, Status
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ] 4.2 Add Tips Sync JavaScript logic to `admin/admin.js`
    - Add `loadSyncData()` function that calls `GET /admin/tips-sync/logs`
    - Add `triggerSync()` function that calls `POST /admin/tips-sync/trigger` with button disable/enable
    - Add `renderSyncStatus()` to display status cards (last sync time, status, duration, sources)
    - Add `renderSyncTable()` with pagination (PS=15) and color-coded status column
    - Wire into `switchTab` to load sync data when tab is selected
    - Wire trigger button click handler
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 5. Add IAM permission for Lambda invoke
  - [ ] 5.1 Add `lambda:InvokeFunction` permission to admin-handler IAM role in infrastructure
    - Grant the admin-handler Lambda role permission to invoke `slashmybill-tips-sync`
    - Update the relevant CloudFormation template or IAM policy document
    - _Requirements: 4.1, 4.2_

- [ ] 6. Final checkpoint
  - Ensure all code is complete and wired together, ask the user if questions arise.

## Notes

- No property-based tests needed for this quick feature
- Backend is Python, frontend is vanilla JavaScript — matching existing patterns
- All three new routes reuse the existing `validate_token` auth mechanism
- The sync log records use the same DynamoDB table as tips (`ViewMyBill-CostOptimizationTips`) with `service=SYSTEM` partition
- Pagination in the frontend reuses the existing `pg()` and `pgNav()` helpers

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "2.2", "2.3"] },
    { "id": 1, "tasks": ["1.2", "2.4", "4.1"] },
    { "id": 2, "tasks": ["4.2", "5.1"] }
  ]
}
```
