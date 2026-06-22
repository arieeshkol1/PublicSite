# Implementation Plan: Invoice Account Hierarchy

## Overview

Add Account ID as a hierarchy level in the Invoice Explorer drilldown. The current hierarchy (Month > Service > Sub-service) becomes Month > Account > Service > Sub-service. Implementation spans three layers: backend account ID resolution and aggregation in `invoice_drilldown.py`, API response shape extensions, and frontend drilldown navigation with account header badge and CSV export updates.

## Tasks

- [ ] 1. Backend: Account ID Resolution and Validation
  - [ ] 1.1 Implement `validate_account_id_format()` function in `member-handler/invoice_drilldown.py`
    - Add format validation for multiple providers: 12-digit numeric (generic cloud), UUID (subscription-based providers), alphanumeric with prefix patterns
    - Accept a `provider_key` parameter to select the correct regex pattern
    - Return `True`/`False` indicating format validity
    - Log a warning (with invalid value and expected format) when validation fails
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ] 1.2 Implement `resolve_account_id()` function in `member-handler/invoice_drilldown.py`
    - Accept `parsed_account_id`, `account_metadata_id`, and `provider_key` parameters
    - Priority: parsed value (if non-empty, not "N/A", and passes format validation) → metadata value → "N/A"
    - Discard parsed value and fall back to metadata when format validation fails
    - Return the resolved string value
    - _Requirements: 1.2, 1.3, 1.4, 4.1, 4.2, 4.3, 8.1, 8.2_

  - [ ]* 1.3 Write property test for Account ID resolution priority (Property 1)
    - **Property 1: Account ID Resolution Priority**
    - Generate random combinations of parsed values (valid, invalid, "N/A", empty, None) and metadata values across provider types
    - Verify resolution priority is always correct
    - **Validates: Requirements 1.2, 1.3, 1.4, 4.1, 4.2, 4.3, 8.1, 8.2**

  - [ ]* 1.4 Write unit tests for `validate_account_id_format()` and `resolve_account_id()`
    - Test valid/invalid formats per provider
    - Test fallback chain: parser → metadata → "N/A"
    - Test warning logging on validation failure
    - _Requirements: 8.1, 8.2, 8.3, 4.1, 4.2, 4.3_

- [ ] 2. Backend: Invoice Sync Integration and Cache Storage
  - [ ] 2.1 Integrate `resolve_account_id()` into the invoice sync/refresh flow in `member-handler/invoice_drilldown.py`
    - In `_fetch_invoices_from_cost_explorer()` and the refresh handler, call `resolve_account_id()` for each invoice record
    - Pass the bill parser's `account_id` output and the connected account metadata ID
    - Store the resolved `accountId` field in each DynamoDB invoice cache record written by `_write_invoice_cache()`
    - Resolve once at sync time; serve cached value on reads without re-resolving
    - _Requirements: 4.4, 4.5, 7.3_

  - [ ] 2.2 Update `_dynamo_item_to_dict()` to include `accountId` in the returned dictionary
    - Ensure the `accountId` field is read from the DynamoDB item and included in all invoice response objects
    - Default to "N/A" if the field is missing (backward compat for pre-existing cached records)
    - _Requirements: 1.1, 7.1_

- [ ] 3. Checkpoint - Verify backend resolution logic
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Backend: Account-Level Aggregation and API Extension
  - [ ] 4.1 Implement `aggregate_by_account()` function in `member-handler/invoice_drilldown.py`
    - Accept a list of invoice record dicts
    - Group by `accountId`, compute `totalCost` (sum of amounts) and `serviceCount` (distinct services with charges > 0)
    - Sort results by `totalCost` descending
    - Include `currency` field (from first record per account or default "USD")
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ] 4.2 Add `groupByAccount` query parameter support to `handle_invoice_list_request()`
    - Parse optional `groupByAccount` param from query string (defaults to "false")
    - When "true", fetch all invoice items for the account+month, call `aggregate_by_account()`, and return the grouped response
    - When value is invalid (not "true"/"false"), treat as "false"
    - Paginate the aggregated results
    - _Requirements: 7.4, 5.4_

  - [ ] 4.3 Add `accountId` field to `handle_service_breakdown_request()` response
    - Include the `accountId` key in the service breakdown response JSON
    - Source from the cached invoice data for that period
    - _Requirements: 7.2_

  - [ ]* 4.4 Write property test for Account Aggregation Correctness (Property 6)
    - **Property 6: Account Aggregation Correctness**
    - Generate random invoice record sets and verify totalCost equals sum of amounts per account, sorted descending
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 4.5 Write property test for Account Service Count Accuracy (Property 7)
    - **Property 7: Account Service Count Accuracy**
    - Generate random invoice sets and verify serviceCount equals distinct services with charges > 0 per account
    - **Validates: Requirements 5.3**

  - [ ]* 4.6 Write property test for GroupByAccount Aggregation Integrity (Property 9)
    - **Property 9: GroupByAccount Aggregation Integrity**
    - Verify sum of all per-account totalCost values equals sum of all individual invoice amounts
    - **Validates: Requirements 7.4**

- [ ] 5. Checkpoint - Verify backend aggregation and API
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Frontend: Drilldown Hierarchy State and Navigation
  - [ ] 6.1 Extend `_invState` and drilldown state in `members/members.js` with account hierarchy level
    - Add `drillAccount` field to track selected account within a month
    - Add `level` field to track current hierarchy level: 'month' | 'account' | 'service' | 'subservice'
    - Add `breadcrumb` array to track navigation trail: `[{level, value, label}]`
    - _Requirements: 3.1, 3.5_

  - [ ] 6.2 Implement `_drillToLevel()`, `_navigateBack()`, and `_renderBreadcrumb()` functions
    - `_drillToLevel(level, value, label)`: push current level to breadcrumb, set new level + value, trigger data reload
    - `_navigateBack(targetLevel)`: pop breadcrumb to target level, restore state, trigger reload
    - `_renderBreadcrumb()`: render clickable breadcrumb trail (Month > Account 123... > Service), each segment navigable
    - Navigating back from service returns to account view for same month
    - _Requirements: 3.1, 3.4, 3.5_

  - [ ] 6.3 Implement account-level view rendering when drilling from month
    - When a month is selected, call the API with `groupByAccount=true` and the selected month filter
    - Render the account-level table showing Account ID, Total Cost (sorted descending), and Service Count for each account
    - Make each account row clickable to drill into service-level view
    - Display single-account scenario without skipping the account level
    - _Requirements: 3.2, 3.3, 5.1, 5.2, 5.3, 5.4_

- [ ] 7. Frontend: Account Header Badge
  - [ ] 7.1 Add Account Header badge HTML and CSS in `members/members.js` and `members/members.css`
    - Create `#inv-account-header` element with badge styling (`.inv-account-badge`)
    - Position above the invoice table
    - Show when `drillAccount` is non-empty; hide when no account is drilled into
    - Update badge text synchronously on selection change (DOM text update, < 100ms)
    - Persist across pagination, sort, and filter changes
    - Clear only on explicit back-navigation above account level
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [ ] 8. Frontend: CSV Export Extension
  - [ ] 8.1 Update `_exportInvoiceCSV()` to include Account ID column
    - Add "Account ID" column between "Month" and "Service" in the header row
    - Map `item.accountId` (or "N/A" if missing) into the corresponding cell for each row
    - Maintain correct column order: Month, Account ID, Service, Cost, Currency, Status, Date
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 8.2 Write property test for CSV Export Column Structure (Property 8)
    - **Property 8: CSV Export Column Structure**
    - Generate random invoice datasets, verify Account ID column positioned between Month and Service, "N/A" used when missing
    - **Validates: Requirements 6.1, 6.2, 6.3**

- [ ] 9. Checkpoint - Verify full frontend integration
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Integration: Wire Components Together
  - [ ] 10.1 Verify end-to-end drilldown flow across all hierarchy levels
    - Ensure month selection triggers account-level API call
    - Ensure account selection triggers service-breakdown API call with correct accountId
    - Ensure breadcrumb navigation works correctly at each level transition
    - Verify Account Header badge displays and hides correctly throughout the flow
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 2.1, 2.2, 2.3_

  - [ ]* 10.2 Write unit tests for frontend breadcrumb and header badge behavior
    - Test breadcrumb renders correctly at each hierarchy level
    - Test Account Header shows/hides based on drill state
    - Test single-account scenario still renders account level
    - _Requirements: 3.1, 3.4, 3.5, 2.1, 2.3_

  - [ ]* 10.3 Write integration tests for backend API flows
    - Test `groupByAccount=true` returns correctly shaped response
    - Test services-breakdown includes accountId field
    - Test refresh does not re-resolve cached Account IDs
    - Test invalid `groupByAccount` values default to "false"
    - _Requirements: 7.1, 7.2, 7.4, 4.5_

- [ ] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend is Python (`member-handler/invoice_drilldown.py`), frontend is vanilla JavaScript (`members/members.js`, `members/members.css`)
- The system is cloud-agnostic — validation supports multiple provider formats without referencing specific cloud service names

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "1.4", "2.1"] },
    { "id": 3, "tasks": ["2.2"] },
    { "id": 4, "tasks": ["4.1", "4.3"] },
    { "id": 5, "tasks": ["4.2", "4.4", "4.5"] },
    { "id": 6, "tasks": ["4.6", "6.1"] },
    { "id": 7, "tasks": ["6.2", "7.1", "8.1"] },
    { "id": 8, "tasks": ["6.3", "8.2"] },
    { "id": 9, "tasks": ["10.1"] },
    { "id": 10, "tasks": ["10.2", "10.3"] }
  ]
}
```
