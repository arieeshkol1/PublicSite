# Design Document: Invoice Account Hierarchy

## Overview

This feature adds Account ID as a hierarchy level in the Invoice Explorer drilldown. The current hierarchy (Month > Service > Sub-service) becomes Month > Account > Service > Sub-service. The implementation touches three layers: the account ID resolution logic in the backend, a new account-level aggregation endpoint, and the frontend drilldown navigation and display components.

The Account ID is resolved from two sources with a priority order: the bill parser extracts it from uploaded invoice PDFs (authoritative source), and connected account metadata in DynamoDB provides the fallback. The resolved value is cached at sync time and served on subsequent reads.

### Key Design Decisions

1. **Resolve-once, cache-always** — Account ID is resolved at invoice sync/refresh time using the parser-first/metadata-fallback strategy. The resolved value is stored in the DynamoDB invoice cache and never re-resolved on reads. This avoids repeated parser calls and metadata lookups on every page load.

2. **Validation before acceptance** — Parsed Account IDs are validated against the provider's expected format (12-digit numeric for standard cloud accounts, UUID/alphanumeric for other providers) before being accepted. Invalid values trigger fallback to metadata rather than storing garbage.

3. **Account level does not skip for single accounts** — Even when a member has only one connected account, the Account level is still displayed in the hierarchy. This maintains a consistent navigation model and correctly handles the case where future accounts are added.

4. **Existing endpoint extension** — The `GET /members/invoices/list` endpoint gains a `groupByAccount` query parameter for the account-level aggregation view. This avoids adding a new endpoint while keeping backward compatibility (parameter is optional, defaults to per-invoice behavior).

5. **Frontend breadcrumb-driven navigation** — The drilldown state is managed via a breadcrumb trail that tracks the current hierarchy level and selected values. Navigating back pops the breadcrumb to the correct parent level.

6. **CSV column positioning** — The account_id column is inserted between month and service in exports to match the hierarchy order and provide a natural reading flow.

## Architecture

### Account ID Resolution Flow

```
┌────────────────────────┐
│   Invoice Sync/Refresh │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐      Valid format?     ┌──────────────────┐
│  Read account_id from  │───── Yes ─────────────▶│  Use parsed value │
│  Bill_Parser output    │                        └──────────────────┘
└───────────┬────────────┘
            │ No / "N/A" / empty / invalid format
            ▼
┌────────────────────────┐      Has value?        ┌──────────────────┐
│  Read Account_ID from  │───── Yes ─────────────▶│ Use metadata value│
│  Account_Metadata (DB) │                        └──────────────────┘
└───────────┬────────────┘
            │ No / empty
            ▼
┌────────────────────────┐
│   Set to "N/A"         │
└────────────────────────┘
```

### Drilldown Hierarchy State Machine

```
┌───────────┐  select month   ┌─────────────┐  select account  ┌─────────────┐  select service  ┌──────────────┐
│   Month   │ ──────────────▶ │   Account   │ ───────────────▶ │   Service   │ ────────────────▶ │ Sub-service  │
│   Level   │                 │   Level     │                  │   Level     │                   │   Level      │
└───────────┘                 └─────────────┘                  └─────────────┘                   └──────────────┘
      ▲                             ▲                                ▲
      │          back               │         back                   │          back
      └─────────────────────────────┴────────────────────────────────┘
```

### Component Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Frontend (members.js)                                                   │
│                                                                          │
│  ┌─────────────────┐    ┌──────────────────┐    ┌───────────────────┐  │
│  │ Account Selector │    │ Breadcrumb Trail  │    │ Account Header    │  │
│  │ (existing)       │    │ Month>Acct>Svc    │    │ Badge (new)       │  │
│  └────────┬─────────┘    └──────────────────┘    └───────────────────┘  │
│           │                                                              │
│  ┌────────▼─────────────────────────────────────────────────────────┐   │
│  │              Invoice Table (renders current level)                 │   │
│  │  - Month level: shows months with totals                          │   │
│  │  - Account level: shows accounts with aggregated costs            │   │
│  │  - Service level: shows services for selected account+month       │   │
│  │  - Sub-service level: shows resources for selected service        │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│           │                                                              │
│  ┌────────▼─────────┐                                                   │
│  │ CSV Export Module │                                                   │
│  │ (includes acctId)│                                                   │
│  └──────────────────┘                                                   │
└─────────────────────┬───────────────────────────────────────────────────┘
                      │ API calls
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Backend (member-handler Lambda)                                         │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ invoice_drilldown.py                                              │   │
│  │                                                                    │   │
│  │  handle_invoice_list_request()  ─── groupByAccount=true ──▶ aggregate│  │
│  │  handle_service_breakdown_request()  (unchanged + accountId field) │   │
│  │  handle_resource_breakdown_request() (unchanged + accountId field) │   │
│  │                                                                    │   │
│  │  resolve_account_id()  ◀── NEW: parser → validate → metadata → N/A│   │
│  └───────────────────────────────────────────┬──────────────────────┘   │
│                                              │                           │
│  ┌───────────────────┐    ┌─────────────────▼───────────────────────┐   │
│  │ bill_parser.py     │    │ DynamoDB (MemberPortal-Invoices)         │   │
│  │ (extracts acct_id) │    │ - pk: memberEmail#accountId              │   │
│  └───────────────────┘    │ - sk: period#invoiceId                   │   │
│                            │ - accountId field in each record          │   │
│  ┌───────────────────┐    └──────────────────────────────────────────┘   │
│  │ DynamoDB           │                                                   │
│  │ (Accounts table)   │                                                   │
│  │ fallback source    │                                                   │
│  └───────────────────┘                                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### Component 1: Account ID Resolution Module

**Location:** `member-handler/invoice_drilldown.py` (new function)

**Purpose:** Resolves the authoritative Account ID for an invoice record using the parser-first/metadata-fallback strategy with format validation.

```python
def resolve_account_id(
    parsed_account_id: str | None,
    account_metadata_id: str | None,
    provider_key: str = 'aws'
) -> str:
    """
    Resolve the Account ID for an invoice record.

    Priority:
        1. parsed_account_id from Bill_Parser (if valid format and non-empty)
        2. account_metadata_id from DynamoDB Accounts table
        3. "N/A" as final fallback

    Args:
        parsed_account_id: Value extracted by bill_parser.py (may be "N/A" or empty).
        account_metadata_id: Value from MemberPortal-Accounts table.
        provider_key: Provider identifier for format validation (e.g., "aws", "azure").

    Returns:
        Resolved Account ID string.
    """
    ...


def validate_account_id_format(account_id: str, provider_key: str = 'aws') -> bool:
    """
    Validate that an account_id matches the expected format for the provider.

    - aws: exactly 12 digits
    - azure: UUID format (subscription/tenant ID)
    - gcp: lowercase letters, digits, hyphens (6-30 chars)
    - openai: alphanumeric with org- prefix or similar

    Args:
        account_id: The value to validate.
        provider_key: The provider type.

    Returns:
        True if the format is valid, False otherwise.
    """
    ...
```

### Component 2: Account-Level Aggregation

**Location:** `member-handler/invoice_drilldown.py` (extension to `handle_invoice_list_request`)

**Purpose:** When `groupByAccount=true` is passed, aggregates invoices by Account ID and returns per-account totals with service counts.

```python
def aggregate_by_account(
    invoice_items: list[dict],
) -> list[dict]:
    """
    Aggregate invoice line items by Account ID.

    For each distinct accountId, computes:
        - totalCost: sum of all line item costs for that account
        - serviceCount: number of distinct services with charges > 0
        - accountId: the account identifier

    Results are sorted by totalCost descending.

    Args:
        invoice_items: List of invoice record dicts, each with 'accountId',
                       'totalAmount', and 'serviceName' fields.

    Returns:
        List of aggregation dicts sorted by totalCost descending:
        [
            {
                "accountId": "123456789012",
                "totalCost": 1542.37,
                "serviceCount": 8,
                "currency": "USD"
            },
            ...
        ]
    """
    ...
```

### Component 3: API Response Shape Extension

**Endpoint:** `GET /members/invoices/list`

**New query parameter:** `groupByAccount` (optional, "true"/"false", default "false")

**Response when `groupByAccount=false` (default — existing behavior + accountId):**

```json
{
    "items": [
        {
            "invoiceId": "INV-2024-001",
            "accountId": "123456789012",
            "issuer": "Cloud Provider",
            "paymentDate": "2024-03-15",
            "paymentStatus": "Paid",
            "totalAmount": 542.37,
            "currency": "USD",
            "period": "2024-03"
        }
    ],
    "pagination": { "page": 1, "pageSize": 25, "totalItems": 12, "totalPages": 1 }
}
```

**Response when `groupByAccount=true`:**

```json
{
    "items": [
        {
            "accountId": "123456789012",
            "totalCost": 1542.37,
            "serviceCount": 8,
            "currency": "USD"
        },
        {
            "accountId": "987654321098",
            "totalCost": 876.22,
            "serviceCount": 5,
            "currency": "USD"
        }
    ],
    "pagination": { "page": 1, "pageSize": 25, "totalItems": 2, "totalPages": 1 }
}
```

**Endpoint:** `GET /members/invoices/services-breakdown`

**Updated response (accountId added):**

```json
{
    "accountId": "123456789012",
    "period": "2024-03",
    "totalAmount": 542.37,
    "services": [
        {
            "serviceName": "Elastic Compute Cloud",
            "amount": 300.26,
            "percentage": 55.4,
            "costExplanation": "...",
            "usageTypes": []
        }
    ]
}
```

### Component 4: Frontend Drilldown Navigation

**Location:** `members/members.js` (Invoice Explorer section)

**State model extension:**

```javascript
var _invState = {
    accountId: '',        // connected account selection (existing)
    month: '',            // currently drilled-into month
    drillAccount: '',     // currently drilled-into account within the month
    service: '',          // currently drilled-into service
    level: 'month',       // current hierarchy level: 'month' | 'account' | 'service' | 'subservice'
    breadcrumb: [],       // navigation trail: [{level, value, label}]
    // ... existing fields (search, sortBy, sortOrder, page, pageSize, etc.)
};
```

**Navigation functions:**

```javascript
function _drillToLevel(level, value, label) {
    // Push current level to breadcrumb, set new level + value
    // Trigger data reload for the new level
}

function _navigateBack(targetLevel) {
    // Pop breadcrumb back to targetLevel
    // Restore state for that level
    // Trigger data reload
}

function _renderBreadcrumb() {
    // Render clickable breadcrumb trail: Month > Account 123... > Service
    // Each segment clickable to navigate back to that level
}
```

### Component 5: Account Header Badge

**Location:** `members/members.js` and `members/members.css`

**HTML structure (injected dynamically):**

```html
<div id="inv-account-header" class="inv-account-badge" hidden>
    <span class="inv-badge-label">Account:</span>
    <span id="inv-account-badge-value" class="inv-badge-value"></span>
</div>
```

**Behavior:**
- Shown when `_invState.drillAccount` is non-empty (account selected in hierarchy)
- Hidden when no account is drilled into
- Updated synchronously on account selection change (< 100ms since it's a DOM text update)
- Persists across pagination, sort, and filter changes (only cleared on explicit back-navigation)

### Component 6: CSV Export Extension

**Location:** `members/members.js` (`_exportInvoiceCSV` function)

**Column order:** `Month, Account ID, Service, Cost, Currency, Status, Date`

```javascript
function _exportInvoiceCSV() {
    var headers = ['Month', 'Account ID', 'Service', 'Cost', 'Currency', 'Status', 'Date'];
    var rows = _currentInvoiceData.map(function(item) {
        return [
            item.period || '',
            item.accountId || 'N/A',    // literal "N/A" when missing
            item.serviceName || '',
            item.totalAmount || 0,
            item.currency || 'USD',
            item.paymentStatus || '',
            item.paymentDate || ''
        ];
    });
    // ... existing CSV generation logic
}
```

## Data Models

### Invoice Cache Record (DynamoDB — updated)

```json
{
    "pk": "member@email.com#123456789012",
    "sk": "2024-03#INV-001",
    "accountId": "123456789012",
    "invoiceId": "INV-001",
    "period": "2024-03",
    "totalAmount": 542.37,
    "currency": "USD",
    "paymentDate": "2024-03-15",
    "paymentStatus": "Paid",
    "issuer": "Cloud Provider",
    "serviceName": "Elastic Compute Cloud",
    "ttl": 1718000000
}
```

The `accountId` field is populated at sync time via `resolve_account_id()` and served directly on reads.

### Account Aggregation Response Model

```json
{
    "accountId": "123456789012",
    "totalCost": 1542.37,
    "serviceCount": 8,
    "currency": "USD"
}
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Bill parser returns invalid format account_id | Log warning with invalid value and expected format, fall back to metadata |
| Account metadata record missing | Fall back to "N/A" |
| Both sources unavailable | Set accountId to "N/A", invoice still displayed normally |
| groupByAccount with no invoice data | Return empty items array with pagination showing 0 total |
| Invalid groupByAccount value (not "true"/"false") | Treat as "false" (default behavior) |
| CSV export with "N/A" account_id | Write literal string "N/A" in the cell |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Account ID Resolution Priority

*For any* invoice record, if the Bill_Parser provides a non-empty, non-"N/A" account_id that passes format validation for the provider, the resolved account_id must equal the parsed value; otherwise, if account metadata provides a value, the resolved account_id must equal the metadata value; otherwise, the resolved account_id must be "N/A".

**Validates: Requirements 1.2, 1.3, 1.4, 4.1, 4.2, 4.3, 8.1, 8.2**

### Property 2: API Response Account ID Presence

*For any* response from the GET /members/invoices/list endpoint, every item object in the response must contain an "accountId" key with a non-null string value.

**Validates: Requirements 1.1, 7.1**

### Property 3: Account Header Persistence

*For any* sequence of pagination, sorting, or filtering operations performed while an account is selected in the drilldown hierarchy, the Account_Header badge must remain visible and display the selected Account_ID.

**Validates: Requirements 2.2**

### Property 4: Hierarchy Navigation Consistency

*For any* valid navigation path through the drilldown hierarchy, navigating back from any level must return to the immediate parent level (service→account, account→month) while preserving the parent context values.

**Validates: Requirements 3.1, 3.4**

### Property 5: Month-to-Account Drilldown Completeness

*For any* set of invoice records and any selected month, the account-level view must display all distinct Account_IDs that have at least one invoice record in that month, and no Account_IDs that lack records in that month.

**Validates: Requirements 3.2**

### Property 6: Account Aggregation Correctness

*For any* set of invoice records within a month, the account-level aggregation must produce totals where each account's totalCost equals the sum of all invoice amounts for that account, and accounts are sorted by totalCost descending.

**Validates: Requirements 5.1, 5.2**

### Property 7: Account Service Count Accuracy

*For any* account in the aggregation view, the serviceCount value must equal the count of distinct service names with charges greater than zero for that account in the selected month.

**Validates: Requirements 5.3**

### Property 8: CSV Export Column Structure

*For any* CSV export of invoice data, the output must contain an "Account ID" column positioned immediately after the "Month" column and immediately before the "Service" column, with a value in every row (using "N/A" when no account_id is available).

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 9: GroupByAccount Aggregation Integrity

*For any* set of invoice records, when the groupByAccount parameter is "true", the sum of all per-account totalCost values in the response must equal the sum of all individual invoice amounts, and each account's totalCost must equal the sum of its constituent invoices.

**Validates: Requirements 7.4**


## Testing Strategy

### Property-Based Tests

Property-based tests target the pure logic functions where input variation reveals edge cases:

- **Account ID resolution** (Properties 1): Generate random combinations of parsed values (valid format, invalid format, "N/A", empty, None) and metadata values (present, absent) across all provider types. Verify resolution priority is always correct. ~100 iterations.
- **Account aggregation** (Properties 6, 7, 9): Generate random lists of invoice records with varying account IDs, service names, and amounts. Verify sum correctness, sort order, and service counts. ~100 iterations.
- **CSV column structure** (Property 8): Generate random invoice datasets and export to CSV. Verify column ordering and "N/A" handling. ~100 iterations.

### Unit Tests (Example-Based)

- Account header badge shows/hides based on selection state
- Breadcrumb renders correctly at each hierarchy level
- Service breakdown response includes accountId field
- Single-account scenario still renders account level
- Invalid groupByAccount values default to "false"
- Warning logged on format validation failure

### Integration Tests

- End-to-end sync flow resolves and caches Account ID
- groupByAccount=true API call returns correctly shaped response
- Cost Explorer synced data uses STS role account ID
- Refresh does not re-resolve cached Account IDs
