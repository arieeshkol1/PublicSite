# Implementation Plan: Custom Data Source Wizard

## Overview

Implement a guided multi-step wizard for the SlashMyBill Custom Dashboard that enables members to build tabular data views from Cost_Cache_Table. The implementation extends the existing `dashboard-handler` Lambda with new API routes for data source CRUD and query execution, adds new frontend wizard modules in vanilla JavaScript, and removes the "table" widget type from the Widget Builder.

## Tasks

- [x] 1. Update constants and set up backend interfaces
  - [x] 1.1 Update constants.py to remove "table" widget type and add data source constants
    - Remove `"table"` from `SUPPORTED_WIDGET_TYPES` frozenset
    - Add `MAX_DATASOURCE_NAME_LENGTH`, `MAX_DATASOURCES_PER_MEMBER`, `DATASOURCE_PAGE_SIZE`, `DATASOURCE_MAX_TOTAL_ROWS`
    - Add `DATASOURCE_AVAILABLE_ATTRIBUTES`, `DATASOURCE_FILTER_OPERATORS`, `DATASOURCE_ATTRIBUTE_TYPES`, `DATASOURCE_TIMEFRAME_PRESETS`
    - _Requirements: 11.1, 3.1, 4.1, 5.4_

  - [x] 1.2 Create datasource_store.py with DataSourceStore class
    - Implement `save()` method: validate name (1-100 chars), generate UUID, write to DashboardLayouts table with `DATASOURCE#{id}` sort key prefix
    - Implement `get()` method: retrieve by member_email pk and datasource_id sk, return 404 if not found or wrong partition
    - Implement `list_all()` method: query by member_email pk with sk `begins_with("DATASOURCE#")`, sort by created_at desc
    - Implement `delete()` method: verify ownership via pk match, delete item, return True/False
    - Enforce member isolation: all operations scoped to member_email partition key
    - _Requirements: 7.5, 7.6, 8.1, 8.3, 8.5, 10.3_

  - [x] 1.3 Create datasource_query.py with DataSourceQueryEngine class
    - Implement `execute()` method: orchestrate ownership verification, DynamoDB query, filtering, projection, pagination
    - Implement `_verify_ownership()`: query MemberPortal-Accounts table, reject with PermissionError if any account not owned
    - Implement `_build_query_params()`: construct DynamoDB query with pk="{email}#{accountId}" and sk range "DAILY#{start_date}" to "DAILY#{end_date}"
    - Implement `_apply_filters()`: apply filter conditions (equals, not_equals, greater_than, less_than) server-side
    - Implement `_project_attributes()`: return only selected attribute columns from records
    - Implement `_paginate()`: paginate with max 500 per page, cap at 10,000 total records
    - Resolve timeframe presets (last_7d, last_30d, last_90d, current_month, previous_month) to concrete date ranges
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 2. Extend Lambda router with data source API routes
  - [x] 2.1 Add data source route handlers to lambda_function.py
    - Add `_handle_list_accounts()`: query MemberPortal-Accounts for connected accounts, return account_id, account_name, cloud_provider
    - Add `_handle_datasource_query()`: parse body, validate config, call DataSourceQueryEngine.execute()
    - Add `_handle_save_datasource()`: parse body, call DataSourceStore.save()
    - Add `_handle_list_datasources()`: call DataSourceStore.list_all()
    - Add `_handle_delete_datasource()`: extract ID from path, call DataSourceStore.delete()
    - Wire routes in the main router: GET /dashboard/accounts, POST /dashboard/datasources/query, PUT /dashboard/datasources, GET /dashboard/datasources, DELETE /dashboard/datasources/{id}
    - Handle all error cases with proper HTTP status codes (400, 401, 403, 404, 503)
    - _Requirements: 2.1, 9.1, 9.2, 7.5, 8.1, 8.5, 10.1, 10.2_

- [x] 3. Checkpoint - Backend implementation complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Backend property-based and unit tests
  - [ ]* 4.1 Write property test for timeframe validation (Property 1)
    - **Property 1: Timeframe validation rejects invalid date ranges**
    - Generate random date pairs; verify start > end or span > 365 days is rejected; verify valid pairs pass
    - **Validates: Requirements 4.4, 4.5, 4.6**

  - [ ]* 4.2 Write property test for operator-type mapping (Property 2)
    - **Property 2: Operator-type mapping correctness**
    - Generate random attributes from DATASOURCE_AVAILABLE_ATTRIBUTES; verify correct operator lists returned per type
    - **Validates: Requirements 5.4**

  - [ ]* 4.3 Write property test for attribute projection (Property 3)
    - **Property 3: Attribute projection returns only selected columns**
    - Generate random records and attribute subsets; verify projected rows contain exactly specified keys
    - **Validates: Requirements 6.1, 9.5**

  - [ ]* 4.4 Write property test for sort ordering (Property 4)
    - **Property 4: Sort produces correctly ordered results**
    - Generate random row lists and column names; verify ascending/descending ordering and stability
    - **Validates: Requirements 6.3**

  - [ ]* 4.5 Write property test for data source name validation (Property 5)
    - **Property 5: Data source name validation**
    - Generate random strings of varying length; verify empty or >100 rejected, 1-100 accepted
    - **Validates: Requirements 7.3, 7.4**

  - [ ]* 4.6 Write property test for ownership verification (Property 6)
    - **Property 6: Ownership verification rejects unowned accounts**
    - Generate random account ID sets with owned/unowned mixes; verify partial unowned rejects entire query
    - **Validates: Requirements 9.1, 9.2**

  - [ ]* 4.7 Write property test for server-side filter correctness (Property 7)
    - **Property 7: Server-side filter correctness**
    - Generate random records and filter conditions; verify all output satisfies filter, no valid records excluded
    - **Validates: Requirements 9.4**

  - [ ]* 4.8 Write property test for pagination bounds (Property 8)
    - **Property 8: Pagination bounds**
    - Generate random-length record lists and page numbers; verify max 500 per page, 10K cap, correct index ranges
    - **Validates: Requirements 9.6**

  - [ ]* 4.9 Write property test for member data isolation (Property 9)
    - **Property 9: Member data isolation**
    - Generate random member emails and configs; verify list/get operations return only matching partition items
    - **Validates: Requirements 10.3**

  - [ ]* 4.10 Write unit tests for datasource_store.py
    - Test CRUD operations with mocked DynamoDB (save, get, list_all, delete)
    - Test name validation edge cases (empty, exactly 100 chars, 101 chars)
    - Test 404 on get/delete for non-existent or wrong-partition items
    - _Requirements: 7.3, 7.4, 7.5, 8.5, 10.3_

  - [ ]* 4.11 Write unit tests for datasource_query.py
    - Test query execution with mocked DynamoDB tables
    - Test ownership verification rejects unowned accounts
    - Test filter application for each operator type
    - Test pagination with various result set sizes
    - Test timeframe preset resolution to date ranges
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 4.12 Write unit tests for data source Lambda routes
    - Test all 5 route handlers with valid/invalid inputs
    - Test auth failure returns 401, ownership failure returns 403
    - Test malformed body returns 400
    - Test not-found returns 404
    - _Requirements: 10.1, 10.2, 2.1, 8.1_

- [x] 5. Checkpoint - Backend tests complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement frontend wizard module
  - [x] 6.1 Create datasource-wizard.js with multi-step wizard logic
    - Implement wizard state management: currentStep, wizardConfig (accounts, attributes, timeframe, filters)
    - Implement `open()` / `close()` functions for wizard overlay show/hide
    - Implement `renderStep1_Accounts()`: fetch GET /dashboard/accounts, render account list with checkboxes and "Select All" toggle
    - Implement `renderStep2_Attributes()`: render attribute checkboxes with defaults (date, service, cost_amount pre-selected)
    - Implement `renderStep3_Timeframe()`: render preset radio buttons (default "Last 30 days") and custom date range pickers
    - Implement `renderStep4_Filters()`: render "Add Filter" button, dynamic filter rows with attribute/operator/value inputs
    - Implement step navigation: nextStep(), prevStep(), goToStep() with per-step validation
    - Implement `runQuery()`: POST to /dashboard/datasources/query with current config
    - Implement `saveDataSource()`: prompt for name, validate, PUT to /dashboard/datasources
    - Handle loading states, error display, and 401 redirect to login
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1-2.7, 3.1-3.6, 4.1-4.6, 5.1-5.8, 7.1-7.7_

  - [x] 6.2 Create result-table.js with tabular display logic
    - Implement `render()`: build HTML table from query response rows with dynamic columns
    - Implement `sort()`: toggle ascending/descending on column header click, client-side sort
    - Implement `refresh()`: re-execute query with current config, show loading indicator
    - Implement `renderPagination()`: page controls for navigating paginated results
    - Implement `showLoading()`, `showEmpty()`, `showError()` states
    - Display row count (total_count from response)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [x] 6.3 Create saved-datasources.js with saved data sources panel
    - Implement `render()`: fetch GET /dashboard/datasources, display list with name and creation date
    - Implement `runSaved()`: execute saved configuration via POST /dashboard/datasources/query, show ResultTable
    - Implement `deleteSaved()`: show confirmation dialog, call DELETE /dashboard/datasources/{id}, refresh list
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 7. Integrate wizard into dashboard HTML and handle table widget deprecation
  - [x] 7.1 Update dashboard/index.html to load new modules and add wizard entry point
    - Add script tags for datasource-wizard.js, result-table.js, saved-datasources.js
    - Add "New Data Source" button in the Custom Dashboard section
    - Add wizard overlay container HTML structure (hidden by default)
    - Add saved data sources panel section
    - _Requirements: 1.1, 8.1, 11.3_

  - [~] 7.2 Update dashboard.js to remove "table" from widget palette and add legacy table widget handling
    - Remove "table" option from the widget type selector/palette in the frontend
    - Add read-only rendering for existing "table" widgets with migration notice text
    - Wire "New Data Source" button click to DataSourceWizard.open()
    - Initialize SavedDataSources.render() on dashboard load
    - _Requirements: 11.1, 11.2, 11.3_

- [x] 8. Checkpoint - Frontend implementation complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Final checkpoint - Full integration verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Backend uses Python (pytest + hypothesis for PBT), frontend uses vanilla JavaScript
- The existing `auth.py` and `query_engine.py` modules are reused for authentication and DynamoDB query patterns
- All data source configs stored in DashboardLayouts table with `DATASOURCE#{id}` sort key prefix
- Property tests validate universal correctness properties defined in the design document
- The "table" widget removal includes backward-compatible read-only rendering for existing layouts

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["2.1"] },
    { "id": 3, "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8", "4.9", "4.10", "4.11", "4.12"] },
    { "id": 4, "tasks": ["6.1", "6.2", "6.3"] },
    { "id": 5, "tasks": ["7.1", "7.2"] }
  ]
}
```
