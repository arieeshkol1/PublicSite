# Design Document

## Architecture Overview

The Admin Sync Dashboard extends three existing layers of the SlashMyCloudBill stack:

1. **Tips Sync Lambda** (`tips-sync/lambda_function.py`) — Enhanced to write a `SYNC_LOG#<timestamp>` record to DynamoDB after each run, in addition to the existing `SYNC_METADATA` record.
2. **Admin Handler Lambda** (`admin-handler/lambda_function.py`) — Extended with three new routes: `GET /admin/tips-sync/status`, `GET /admin/tips-sync/logs`, and `POST /admin/tips-sync/trigger`.
3. **Admin Frontend** (`admin/index.html`, `admin/admin.js`, `admin/admin.css`) — New "Tips Sync" tab with status cards, paginated history table, and manual trigger button.

All new endpoints reuse the existing JWT authentication mechanism in `admin-handler`. The DynamoDB table `ViewMyBill-CostOptimizationTips` stores sync log records alongside tips using the `service=SYSTEM` partition.

---

## Components

### 1. Sync Log Writer (tips-sync Lambda enhancement)

**Location:** `tips-sync/lambda_function.py`

Adds a `_write_sync_log` function called at the end of each sync run (both success and failure paths). This function writes a new item to the Tips_Table with:

- `service`: `"SYSTEM"`
- `tipId`: `"SYNC_LOG#<ISO-8601-timestamp>"` (e.g., `SYNC_LOG#2025-01-15T14:30:00.000Z`)

The existing `_write_sync_metadata` function remains unchanged, preserving backward compatibility.

### 2. Admin Handler - Sync Routes

**Location:** `admin-handler/lambda_function.py`

Three new route handlers added to the existing `routes` dict:

| Route | Handler | Description |
|-------|---------|-------------|
| `GET /admin/tips-sync/status` | `handle_get_sync_status` | Returns SYNC_METADATA record |
| `GET /admin/tips-sync/logs` | `handle_get_sync_logs` | Returns paginated sync log history |
| `POST /admin/tips-sync/trigger` | `handle_trigger_sync` | Invokes tips-sync Lambda asynchronously |

### 3. Admin Frontend - Tips Sync Tab

**Location:** `admin/index.html`, `admin/admin.js`, `admin/admin.css`

New tab added to the existing tab navigation. Follows the same patterns as existing tabs (Leads, Tips, Feedback, Subscribers, Schedules).

---

## Interfaces

### API Endpoints

#### GET /admin/tips-sync/status

**Request:**
```
GET /admin/tips-sync/status
Authorization: Bearer <jwt-token>
```

**Response (200):**
```json
{
  "status": {
    "lastSyncTimestamp": "2025-01-15T14:30:00.000Z",
    "triggerType": "scheduled",
    "sourcesQueried": ["cost-optimization-hub", "trusted-advisor", "baseline"],
    "sourcesSucceeded": ["cost-optimization-hub", "baseline"],
    "sourcesFailed": ["trusted-advisor"],
    "tipsInserted": 3,
    "tipsUpdated": 5,
    "tipsUnchanged": 42,
    "durationMs": 4500
  }
}
```

**Response (200, no sync executed):**
```json
{
  "status": null,
  "message": "No sync has been executed yet"
}
```

#### GET /admin/tips-sync/logs

**Request:**
```
GET /admin/tips-sync/logs
Authorization: Bearer <jwt-token>
```

**Response (200):**
```json
{
  "logs": [
    {
      "timestamp": "2025-01-15T14:30:00.000Z",
      "triggerType": "scheduled",
      "sourcesQueried": ["cost-optimization-hub", "trusted-advisor", "baseline"],
      "sourcesSucceeded": ["cost-optimization-hub", "baseline"],
      "sourcesFailed": ["trusted-advisor"],
      "tipsInserted": 3,
      "tipsUpdated": 5,
      "tipsUnchanged": 42,
      "durationMs": 4500,
      "status": "success"
    }
  ],
  "metadata": {
    "lastSyncTimestamp": "2025-01-15T14:30:00.000Z",
    "triggerType": "scheduled",
    "sourcesSucceeded": ["cost-optimization-hub", "baseline"],
    "sourcesFailed": ["trusted-advisor"],
    "tipsInserted": 3,
    "tipsUpdated": 5,
    "tipsUnchanged": 42,
    "durationMs": 4500
  }
}
```

#### POST /admin/tips-sync/trigger

**Request:**
```
POST /admin/tips-sync/trigger
Authorization: Bearer <jwt-token>
```

**Response (202):**
```json
{
  "message": "Sync triggered successfully. It will run in the background."
}
```

**Response (500):**
```json
{
  "error": "ServerError",
  "message": "Failed to trigger sync: <error-description>",
  "code": 500
}
```

---

## Data Models

### Sync Log Record (DynamoDB Item)

```python
{
    "service": "SYSTEM",                          # Partition key
    "tipId": "SYNC_LOG#2025-01-15T14:30:00.000Z", # Sort key
    "timestamp": "2025-01-15T14:30:00.000Z",
    "triggerType": "scheduled",                   # "scheduled" | "manual"
    "sourcesQueried": ["cost-optimization-hub", "trusted-advisor", "baseline"],
    "sourcesSucceeded": ["cost-optimization-hub", "baseline"],
    "sourcesFailed": ["trusted-advisor"],
    "tipsInserted": 3,
    "tipsUpdated": 5,
    "tipsUnchanged": 42,
    "durationMs": 4500,
    "status": "success",                          # "success" | "failed"
    "errorMessage": None                          # Present only when status="failed"
}
```

### SYNC_METADATA Record (existing, unchanged)

```python
{
    "service": "SYSTEM",
    "tipId": "SYNC_METADATA",
    "lastSyncTimestamp": "2025-01-15T14:30:00.000Z",
    "triggerType": "scheduled",
    "sourcesQueried": ["cost-optimization-hub", "trusted-advisor", "baseline"],
    "sourcesSucceeded": ["cost-optimization-hub", "baseline"],
    "sourcesFailed": ["trusted-advisor"],
    "tipsInserted": 3,
    "tipsUpdated": 5,
    "tipsUnchanged": 42,
    "durationMs": 4500
}
```

---

## Implementation Details

### Tips Sync Lambda Changes

```python
def _write_sync_log(
    table,
    trigger_type: str,
    sources_queried: list,
    sources_succeeded: list,
    sources_failed: list,
    tips_inserted: int,
    tips_updated: int,
    tips_unchanged: int,
    duration_ms: int,
    status: str,
    error_message: str = None,
) -> None:
    """Write a SYNC_LOG record to the Tips_Table for historical tracking."""
    now = datetime.now(timezone.utc).isoformat()

    log_item = {
        "service": "SYSTEM",
        "tipId": f"SYNC_LOG#{now}",
        "timestamp": now,
        "triggerType": trigger_type,
        "sourcesQueried": sources_queried,
        "sourcesSucceeded": sources_succeeded,
        "sourcesFailed": sources_failed,
        "tipsInserted": tips_inserted,
        "tipsUpdated": tips_updated,
        "tipsUnchanged": tips_unchanged,
        "durationMs": duration_ms,
        "status": status,
    }

    if error_message:
        log_item["errorMessage"] = error_message

    table.put_item(Item=log_item)
```

The `lambda_handler` function is modified to call `_write_sync_log` in two places:
1. After successful sync (status="success"), right after `_write_sync_metadata`
2. In the `except` block for unrecoverable errors (status="failed")

### Admin Handler Changes

```python
# New routes added to the routes dict:
routes = {
    # ... existing routes ...
    'GET /admin/tips-sync/status': handle_get_sync_status,
    'GET /admin/tips-sync/logs': handle_get_sync_logs,
    'POST /admin/tips-sync/trigger': handle_trigger_sync,
}


def handle_get_sync_status(event):
    """Return the current SYNC_METADATA record."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    table = dynamodb.Table(TIPS_TABLE_NAME)
    try:
        response = table.get_item(
            Key={'service': 'SYSTEM', 'tipId': 'SYNC_METADATA'}
        )
        item = response.get('Item')
        if not item:
            return create_response(200, {
                'status': None,
                'message': 'No sync has been executed yet'
            })
        # Remove DynamoDB keys from response
        item.pop('service', None)
        item.pop('tipId', None)
        return create_response(200, {'status': _decimal_to_native(item)})
    except ClientError as e:
        logger.error(f"DynamoDB error getting sync status: {e}")
        return create_error_response(500, 'ServerError', 'Failed to retrieve sync status')


def handle_get_sync_logs(event):
    """Return sync log history and current metadata."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    table = dynamodb.Table(TIPS_TABLE_NAME)
    try:
        # Query for SYNC_LOG# records using begins_with on sort key
        response = table.query(
            KeyConditionExpression='service = :sys AND begins_with(tipId, :prefix)',
            ExpressionAttributeValues={
                ':sys': 'SYSTEM',
                ':prefix': 'SYNC_LOG#',
            },
            ScanIndexForward=False,  # Descending order by tipId (which contains timestamp)
        )
        logs = _decimal_to_native(response.get('Items', []))

        # Remove DynamoDB keys from each log record
        for log in logs:
            log.pop('service', None)
            log.pop('tipId', None)

        # Get SYNC_METADATA
        meta_response = table.get_item(
            Key={'service': 'SYSTEM', 'tipId': 'SYNC_METADATA'}
        )
        metadata = meta_response.get('Item')
        if metadata:
            metadata.pop('service', None)
            metadata.pop('tipId', None)
            metadata = _decimal_to_native(metadata)

        return create_response(200, {'logs': logs, 'metadata': metadata})
    except ClientError as e:
        logger.error(f"DynamoDB error getting sync logs: {e}")
        return create_error_response(500, 'ServerError', 'Failed to retrieve sync logs')


def handle_trigger_sync(event):
    """Invoke the tips-sync Lambda asynchronously."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth

    try:
        lambda_client = boto3.client('lambda', region_name='us-east-1')
        lambda_client.invoke(
            FunctionName='slashmybill-tips-sync',
            InvocationType='Event',
            Payload=json.dumps({'manual': True}),
        )
        return create_response(202, {
            'message': 'Sync triggered successfully. It will run in the background.'
        })
    except Exception as e:
        logger.error(f"Failed to trigger sync: {e}")
        return create_error_response(500, 'ServerError', f'Failed to trigger sync: {str(e)}')
```

### Frontend Implementation

The frontend follows the existing admin panel patterns:

```javascript
// ============================================================
// Tips Sync Tab
// ============================================================
var syncLogs = [];
var syncMetadata = null;
var syncPage = 1;
var syncLoading = false;

async function loadSyncData() {
    try {
        showL();
        var d = await api('GET', '/admin/tips-sync/logs');
        syncLogs = d.logs || [];
        syncMetadata = d.metadata || null;
        syncPage = 1;
        renderSyncStatus();
        renderSyncTable();
    } catch (e) {
        notify('Failed to load sync data.', 'error');
    } finally {
        hideL();
    }
}

async function triggerSync() {
    var btn = $('trigger-sync-btn');
    if (syncLoading) return;
    syncLoading = true;
    btn.disabled = true;
    btn.textContent = 'Triggering...';
    try {
        await api('POST', '/admin/tips-sync/trigger');
        notify('Sync triggered successfully. It will run in the background.', 'success');
    } catch (e) {
        notify('Failed to trigger sync: ' + (e.message || 'Unknown error'), 'error');
    } finally {
        syncLoading = false;
        btn.disabled = false;
        btn.textContent = 'Trigger Manual Sync';
    }
}

function renderSyncStatus() {
    var el = $('sync-status-cards');
    if (!el || !syncMetadata) {
        if (el) el.innerHTML = '<p style="color:#8b949e;">No sync has been executed yet.</p>';
        return;
    }
    var m = syncMetadata;
    var statusColor = (m.sourcesFailed && m.sourcesFailed.length === 0) ? '#10b981' : '#f59e0b';
    el.innerHTML = '...'; // Status cards HTML
}

function renderSyncTable() {
    var tbody = $('sync-tbody');
    var empty = $('sync-empty');
    if (!syncLogs.length) { empty.hidden = false; tbody.innerHTML = ''; return; }
    empty.hidden = true;
    var page = pg(syncLogs, syncPage);
    // Render rows with color-coded status
    tbody.innerHTML = page.map(function(log, idx) {
        var statusClass = log.status === 'success' ? 'color:#10b981' : 'color:#ef4444';
        return '<tr>...</tr>';
    }).join('');
    pgNav('sync-pagination', syncLogs.length, syncPage, function(x) { syncPage = x; renderSyncTable(); });
}
```

### HTML Structure (new tab)

```html
<!-- Tips Sync Tab -->
<div id="sync-tab" class="tab-content" hidden>
    <div id="sync-status-cards" style="display:flex;gap:16px;margin-bottom:12px;flex-wrap:wrap;"></div>
    <div class="tab-toolbar">
        <button id="trigger-sync-btn" class="btn btn-primary btn-sm">⚡ Trigger Manual Sync</button>
    </div>
    <div class="table-wrapper">
        <table id="sync-table" class="data-table">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Timestamp</th>
                    <th>Trigger</th>
                    <th>Inserted</th>
                    <th>Updated</th>
                    <th>Unchanged</th>
                    <th>Duration</th>
                    <th>Sources</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody id="sync-tbody"></tbody>
        </table>
        <div id="sync-empty" class="empty-state" hidden>
            <p>No sync history available yet.</p>
        </div>
    </div>
</div>
```

---

## Error Handling

| Scenario | Component | Behavior |
|----------|-----------|----------|
| DynamoDB write failure for sync log | Tips Sync Lambda | Log error, do not fail the overall sync (non-fatal) |
| All sources fail during sync | Tips Sync Lambda | Write log with status="failed", return 500 |
| SYNC_METADATA not found | Admin Handler | Return `{"status": null, "message": "..."}` with 200 |
| No SYNC_LOG records exist | Admin Handler | Return `{"logs": [], "metadata": ...}` with 200 |
| Lambda invoke fails | Admin Handler | Return 500 with error description |
| Missing/invalid JWT | Admin Handler | Return 401 with auth error message |
| Network error on frontend | Admin Frontend | Display error notification, re-enable trigger button |
| API returns 401 | Admin Frontend | Show authentication error (existing pattern) |

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Sync log record completeness

*For any* sync execution (success or failure), the resulting sync log record SHALL have `service="SYSTEM"`, a `tipId` matching the pattern `SYNC_LOG#<valid-ISO-8601-timestamp>`, and contain all required fields: `timestamp`, `triggerType`, `sourcesQueried`, `sourcesSucceeded`, `sourcesFailed`, `tipsInserted`, `tipsUpdated`, `tipsUnchanged`, `durationMs`, and `status`.

**Validates: Requirements 1.1, 1.2**

### Property 2: Failed sync log includes error details

*For any* sync execution that fails with an unrecoverable error, the resulting sync log record SHALL have `status` set to `"failed"` and an `errorMessage` field containing a non-empty string describing the error.

**Validates: Requirements 1.3**

### Property 3: Log query returns only SYNC_LOG records

*For any* set of items in the Tips_Table (including tips, SYNC_METADATA, SYNC_LOCK, and SYNC_LOG records), the `/admin/tips-sync/logs` endpoint SHALL return only items whose `tipId` begins with `SYNC_LOG#`, excluding all other SYSTEM records and tip records.

**Validates: Requirements 2.1**

### Property 4: Logs are sorted by timestamp descending

*For any* set of sync log records returned by the `/admin/tips-sync/logs` endpoint, for all consecutive pairs of records (log[i], log[i+1]), the timestamp of log[i] SHALL be greater than or equal to the timestamp of log[i+1].

**Validates: Requirements 2.2**

### Property 5: Pagination displays at most 15 records per page

*For any* number of sync log records N, the rendered sync history table SHALL display at most 15 records on any given page, and the total number of pages SHALL equal ceil(N / 15).

**Validates: Requirements 6.3**

### Property 6: Authentication enforcement on sync endpoints

*For any* request to a `/admin/tips-sync/*` route that has a missing, malformed, or expired JWT token, the Admin_Handler SHALL return a 401 status code with an authentication error message, regardless of the specific sync route requested.

**Validates: Requirements 8.1, 8.2**
