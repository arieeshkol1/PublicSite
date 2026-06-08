# Implementation Plan: Widget Builder Dashboard

## Overview

Implement a self-service Widget Builder Dashboard with a Python Lambda backend (Generic Query Engine + Layout Store) and a JavaScript frontend (Chart.js rendering + drag-and-drop grid). The backend uses DynamoDB for persistence and supports cross-provider data sources (AWS, Azure, GCP, OpenAI). Authentication reuses the existing Cognito JWT flow.

## Tasks

- [x] 1. Set up project structure and core interfaces
  - [x] 1.1 Create backend directory structure and Lambda handler skeleton
    - Create `dashboard-handler/` directory with `lambda_function.py`, `query_engine.py`, `layout_store.py`, `auth.py`, `validators.py`, and `__init__.py`
    - Set up `requirements.txt` with boto3, python-jose dependencies
    - Implement the main `lambda_handler` function that routes `/dashboard/query`, `/dashboard/layouts` (GET/PUT/DELETE) to the appropriate module
    - Include JWT extraction from Authorization header and delegate to auth module
    - _Requirements: 8.1, 8.2_

  - [x] 1.2 Create frontend directory structure and HTML scaffold
    - Create `dashboard/` directory with `index.html`, `dashboard.js`, `dashboard.css`, `widget-builder.js`, `widget-renderer.js`, `data-source-picker.js`, `grid-manager.js`
    - Set up `index.html` with Chart.js CDN (~65KB), a grid library CDN, and module script tags
    - Include basic layout: widget palette sidebar, main grid area, config panel overlay
    - _Requirements: 1.1, 6.1_

  - [x] 1.3 Define shared configuration constants and data models
    - Create `dashboard-handler/constants.py` with SUPPORTED_WIDGET_TYPES, SUPPORTED_AGGREGATIONS, SUPPORTED_DATA_SOURCES, SUPPORTED_OPERATORS, GRID_COLS=12, MAX_ROWS=48, MAX_WIDGETS=20, MAX_LAYOUTS=10, MAX_FILTERS=20
    - Create `dashboard-handler/models.py` with WidgetConfig, GridPosition, Layout dataclass definitions
    - _Requirements: 1.3, 5.1, 6.1, 6.5, 7.5, 7.6_

- [x] 2. Implement widget configuration validation
  - [x] 2.1 Implement validate_widget_config function
    - Create `dashboard-handler/validators.py` with `validate_widget_config(config: dict) -> tuple[bool, str | None]`
    - Validate required top-level fields: type, dataSource, aggregation
    - Validate widget type is in supported set (bar, line, pie, table, kpi, gauge)
    - Validate aggregation is in supported set (sum, avg, max, min, count)
    - Validate dataSource has required sub-fields: source, accountIds, dateRange
    - Handle null/non-object/unparseable inputs gracefully
    - Ensure no side effects or mutations to input configuration
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x]* 2.2 Write property test for validation purity
    - **Property 9: Validation Purity**
    - Generate random Widget_Config inputs and verify the input object is identical before and after calling validate_widget_config
    - **Validates: Requirements 5.5**

  - [x]* 2.3 Write property test for invalid config rejection
    - **Property 10: Invalid Config Rejection**
    - Generate configs missing required fields, with unsupported widget types, or unsupported aggregation types, and verify validate_widget_config returns failure with descriptive error
    - **Validates: Requirements 1.3, 5.2, 5.3, 5.4**

  - [x] 2.4 Implement date range resolution
    - Create `resolve_date_range(date_range: dict) -> tuple[str, str]` in `dashboard-handler/validators.py`
    - Support relative ranges (7d, 30d, 90d, 12m) computed from today's date
    - Support absolute ranges with start/end in YYYY-MM-DD format
    - Reject ranges where start >= end (return 400)
    - Reject ranges exceeding 365 days (return 400)
    - _Requirements: 2.4, 2.5, 2.6_

  - [x]* 2.5 Write property test for date range validity
    - **Property 8: Date Range Validity**
    - Generate random valid date range configurations (relative and absolute) and verify resolved output always has start_date < end_date and span ≤ 365 days
    - **Validates: Requirements 2.4, 2.5**

- [x] 3. Implement filter pipeline
  - [x] 3.1 Implement apply_filter and filter pipeline
    - Create `dashboard-handler/filters.py` with `apply_filter(item: dict, filter_config: dict) -> bool`
    - Implement operators: eq, neq, gt, lt, contains (case-insensitive substring)
    - Return False for items where the referenced field is not present
    - Return False for gt/lt/eq when value is not comparable (e.g., gt on non-numeric string)
    - Create `apply_filters(data: list[dict], filters: list[dict]) -> list[dict]` that applies all filters conjunctively (AND logic)
    - Enforce maximum 20 filters per query
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x]* 3.2 Write property test for filter monotonicity
    - **Property 3: Filter Monotonicity**
    - Generate random data sets and filter lists, verify filtered result size ≤ original data size
    - **Validates: Requirements 4.2**

  - [x]* 3.3 Write property test for filter completeness
    - **Property 4: Filter Completeness**
    - Generate random data sets and filters, verify every item in the filtered result satisfies ALL filter conditions simultaneously
    - **Validates: Requirements 3.2, 4.4**

- [x] 4. Implement aggregation and dimension grouping
  - [x] 4.1 Implement dimension grouping and aggregation functions
    - Create `dashboard-handler/aggregation.py` with `group_by_dimensions(data: list[dict], dimensions: list[str]) -> dict`
    - Implement `aggregate(items: list[dict], aggregation_type: str) -> float` supporting sum, avg, max, min, count
    - Handle avg returning 0 for groups with no numeric values
    - Enforce maximum 3 dimensions per query
    - Create `format_for_chart(aggregated: dict, widget_type: str) -> dict` returning Chart.js-compatible structure with labels and datasets
    - _Requirements: 3.1, 3.3, 3.4, 3.7_

  - [x]* 4.2 Write property test for aggregation partition consistency
    - **Property 5: Aggregation Partition Consistency**
    - Generate random data sets and dimensions, verify sum of aggregate(group, 'sum') across all groups equals aggregate(unpartitioned_data, 'sum')
    - **Validates: Requirements 3.5**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement Generic Query Engine
  - [x] 6.1 Implement data source resolution and query execution
    - Create `dashboard-handler/query_engine.py` with `QueryEngine` class
    - Implement `execute(member_email, widget_config)` orchestrating the full pipeline: validate → resolve date range → verify account ownership → fetch data → filter → dimension → aggregate → format
    - Implement `_resolve_data_source` routing to cost_cache, invoices, openai_usage, commitments, business_metrics
    - For cost_cache: query DynamoDB Cost_Cache_Table with pk="{email}#{account_id}", sk begins_with "DAILY#" and date range
    - For invoices: query MemberPortal-Invoices table
    - For openai_usage: call OpenAI provider API with 30s timeout
    - Use DynamoDB query operations (not scan) with partition key and sort key range conditions
    - _Requirements: 3.1, 3.6, 10.1, 10.2, 12.1, 12.5_

  - [x] 6.2 Implement cross-provider data normalization
    - Create normalization functions that transform raw provider data into common schema: date, service_name, cost_amount, currency, cloud_provider, account_id
    - Handle AWS (Cost_Cache_Table service_breakdown), Azure (Azure Cost Mgmt API), GCP (GCP Billing API), OpenAI (usage API)
    - On provider failure during cross-provider query, return available data from successful providers with error indicator for failed ones
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 11.3_

  - [x]* 6.3 Write property test for provider data normalization
    - **Property 12: Provider Data Normalization**
    - Generate raw data mimicking each provider format, verify normalization produces records with consistent field structure processable by the filter/aggregation pipeline
    - **Validates: Requirements 10.3**

  - [x] 6.4 Implement account ownership verification
    - Add `_verify_account_ownership(member_email, account_ids)` to QueryEngine
    - Query MemberPortal-Accounts table to confirm each account_id has memberEmail matching the authenticated member
    - If any account is not owned, reject entire query with 403 (no partial results)
    - Filter all query results server-side to include only owned account data
    - _Requirements: 8.3, 8.4, 8.5, 9.5_

  - [x]* 6.5 Write property test for query data isolation
    - **Property 1: Query Data Isolation**
    - Generate queries with mixed account ownership, verify result contains only data from accounts owned by the querying member
    - **Validates: Requirements 8.3, 8.4, 8.5, 9.2**

- [x] 7. Implement Layout Store
  - [x] 7.1 Implement Layout Store CRUD operations
    - Create `dashboard-handler/layout_store.py` with `LayoutStore` class
    - Implement `save_layout(member_email, layout)`: PutItem with pk=member_email, sk=LAYOUT#{layout_id}, include updated_at ISO 8601 UTC timestamp
    - Implement `get_layout(member_email, layout_id)`: Query with pk + sk, return 404 if not found (not revealing existence under other members)
    - Implement `list_layouts(member_email)`: Query pk=member_email, sk begins_with "LAYOUT#", order by updated_at descending
    - Implement `delete_layout(member_email, layout_id)`: DeleteItem scoped to member's partition key
    - Enforce max 10 layouts per member (409 on 11th)
    - Enforce max 20 widgets per layout (400 on exceed)
    - Enforce layout name 1-64 characters
    - Handle name collision by overwriting existing layout with same name, updating timestamp
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10_

  - [x] 7.2 Implement grid position validation in Layout Store
    - Create `validate_grid_positions(widgets)` function
    - Verify x, y are non-negative integers; w, h are integers ≥ 1
    - Verify x + w ≤ 12 and y + h ≤ 48
    - Detect overlapping widgets (no two widgets occupy same grid cell)
    - Reject placement with error if bounds exceeded or overlap detected
    - _Requirements: 6.3, 6.4, 6.5_

  - [x]* 7.3 Write property test for grid validity
    - **Property 7: Grid Validity**
    - Generate random valid layouts, verify no two widgets occupy the same cell, no widget extends beyond 12-column boundary, all positions are non-negative with w,h ≥ 1
    - **Validates: Requirements 6.3, 6.4, 6.5**

  - [x]* 7.4 Write property test for layout isolation
    - **Property 2: Layout Isolation**
    - Generate layouts for multiple members, verify list_layouts returns only layouts belonging to the querying member
    - **Validates: Requirements 7.2, 9.1, 9.3**

  - [x]* 7.5 Write property test for layout persistence round-trip
    - **Property 6: Layout Persistence Round-trip**
    - Generate random valid layouts, save then load, verify widget configurations, grid positions, and layout name are identical
    - **Validates: Requirements 7.1, 7.4**

  - [x]* 7.6 Write property test for widget limit enforcement
    - **Property 11: Widget Limit Enforcement**
    - Generate layouts with more than 20 widgets, verify Layout_Store rejects the save operation
    - **Validates: Requirements 7.5**

- [x] 8. Implement authentication middleware
  - [x] 8.1 Implement JWT validation and auth middleware
    - Create `dashboard-handler/auth.py` with `verify_jwt(token: str) -> str | None`
    - Validate Cognito JWT signature, expiration, and issuer against configured User Pool
    - Return member_email on success, None on failure
    - Return 401 for missing/invalid/expired tokens
    - Return 503 if Cognito service is unavailable or validation times out (>5 seconds)
    - Distinguish token expiry from other auth failures in response body
    - _Requirements: 8.1, 8.2, 8.6, 11.1_

  - [x] 8.2 Implement data isolation enforcement in all operations
    - Ensure Layout Store uses member_email as partition key in all DynamoDB operations
    - Ensure Query Engine includes member_email as partition key condition in every query
    - Return 404 (not 403) when a layout operation targets a layout_id under different member's partition
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 9. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement Widget Builder UI - Core
  - [x] 10.1 Implement widget palette and type selection
    - In `dashboard/widget-builder.js`, implement the widget palette displaying 6 types: bar chart, line chart, pie chart, table, KPI card, gauge
    - On type selection, create a new widget instance and add to grid in empty/unconfigured state
    - Restrict to exactly 6 supported types
    - Enforce max 20 widgets on grid; show error if limit reached
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 10.2 Implement data source picker and configuration panel
    - In `dashboard/data-source-picker.js`, implement source picker showing: cost_cache, invoices, openai_usage, commitments, business_metrics
    - Display account selector filtered to authenticated member's owned accounts
    - Show message and disable query when no accounts available for selected source
    - Implement date range selector with relative (7d, 30d, 90d, 12m) and absolute options, defaulting to 30d
    - Implement filter builder (field, operator, value) and dimension selector
    - Implement aggregation type selector (sum, avg, max, min, count)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 10.3 Implement Chart.js widget rendering
    - In `dashboard/widget-renderer.js`, implement `render(containerEl, widgetConfig, data)` using Chart.js
    - Support rendering bar, line, pie chart types from labels/datasets response format
    - Implement table rendering for table widget type
    - Implement KPI card and gauge rendering
    - Handle responsive sizing and aspect ratio within grid cells
    - _Requirements: 3.1_

- [x] 11. Implement Widget Builder UI - Grid and Layout
  - [x] 11.1 Implement drag-and-drop grid layout manager
    - In `dashboard/grid-manager.js`, implement 12-column grid with max 48 rows
    - Implement drag-and-drop repositioning updating widget gridPosition (x, y, w, h)
    - Prevent placement beyond column 12 or row 48 boundaries with error indication
    - Prevent widget overlap with error indication
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 11.2 Implement layout save/load and API integration
    - In `dashboard/dashboard.js`, implement `saveLayout()` calling PUT /dashboard/layouts
    - Implement `loadLayout(layoutId)` calling GET /dashboard/layouts
    - Implement parallel data fetching for up to 12 widgets simultaneously
    - Wire widget config changes to query endpoint calls and re-render
    - _Requirements: 7.1, 7.2, 12.4_

  - [x] 11.3 Implement error handling and resilience in UI
    - Handle 401 responses: preserve config in localStorage, show re-auth prompt without navigation
    - Display "No data available" state with retry button for empty query results
    - Implement offline detection with 15-second retry intervals (3 attempts max) then manual retry
    - Render partial data on provider failures with inline warning indicating which source is unavailable
    - _Requirements: 11.1, 11.2, 11.4, 11.5, 11.6_

- [x] 12. Infrastructure and wiring
  - [x] 12.1 Create DashboardLayouts DynamoDB table definition
    - Add DashboardLayouts table to CloudFormation/infrastructure with pk (String) partition key and sk (String) sort key
    - Configure provisioned/on-demand capacity appropriate for layout CRUD pattern
    - _Requirements: 7.1_

  - [x] 12.2 Wire API Gateway routes and Lambda permissions
    - Add /dashboard/query (POST), /dashboard/layouts (GET, PUT), /dashboard/layouts/{id} (DELETE) routes to API Gateway
    - Configure Lambda permissions for DynamoDB access (Cost_Cache_Table, MemberPortal-Invoices, MemberPortal-Accounts, DashboardLayouts)
    - Configure timeout settings (30s for provider API calls)
    - _Requirements: 12.2, 12.3_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties defined in the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python (hypothesis for property tests, pytest for unit tests)
- Frontend uses JavaScript (fast-check for property tests if needed)
- The DashboardLayouts table uses single-table design with pk=member_email, sk=LAYOUT#{layout_id}

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "2.4"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.5", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "4.1"] },
    { "id": 4, "tasks": ["4.2", "6.1", "7.1"] },
    { "id": 5, "tasks": ["6.2", "6.4", "7.2", "8.1"] },
    { "id": 6, "tasks": ["6.3", "6.5", "7.3", "7.4", "7.5", "7.6", "8.2"] },
    { "id": 7, "tasks": ["10.1", "10.2", "10.3"] },
    { "id": 8, "tasks": ["11.1", "11.2", "12.1", "12.2"] },
    { "id": 9, "tasks": ["11.3"] }
  ]
}
```
