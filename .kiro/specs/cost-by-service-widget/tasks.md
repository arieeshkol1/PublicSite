# Implementation Plan: Cost By Service Widget

## Overview

Add a stacked bar chart widget (`dash-cost-by-service`) to the Observe > Cost Analysis section that visualizes AWS service cost breakdown over time. The backend builds `dailyServiceBreakdown` from the existing DynamoDB cache and fetches `hourlyServiceBreakdown` from the Cost Explorer API on demand. The frontend renders a stacked bar chart with ECharts, supports daily/hourly toggle, and refreshes on tag filter changes.

## Tasks

- [ ] 1. Backend: Add daily service breakdown builder
  - [ ] 1.1 Add `_build_daily_service_breakdown(cache_items, tag_key=None, tag_value=None)` function to member-handler/lambda_function.py
    - Iterate cache items, extract `service_breakdown` map from each record
    - Skip items without `service_breakdown` field
    - When no tag filter: return services as-is per day
    - When tag filter active: compute proportional allocation — for each day, get total tag cost from `tag_breakdown[tag_key][tag_value]`, then allocate across services as `tag_cost * (service_cost / total_day_cost)`
    - Handle zero total cost for a day (return zero for all services, avoid division by zero)
    - Merge across multiple accounts by summing per service per day
    - Sort output array by date ascending
    - Return list of `{"date": "YYYY-MM-DD", "services": {"ServiceName": cost_float, ...}}`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2_

  - [ ]* 1.2 Write property test for daily service breakdown structure
    - **Property 1: Daily Service Breakdown Structure**
    - Generate random cache records with `service_breakdown` fields, verify output entries have `date` in YYYY-MM-DD format and `services` mapping strings to non-negative numbers
    - **Validates: Requirements 1.1, 1.2**

  - [ ]* 1.3 Write property test for date ordering invariant
    - **Property 2: Date Ordering Invariant**
    - Generate cache records in random order, verify output is sorted in strictly ascending date order
    - **Validates: Requirements 1.3**

  - [ ]* 1.4 Write property test for multi-account merge correctness
    - **Property 3: Multi-Account Merge Correctness**
    - Generate multi-account overlapping data, verify each service cost per date equals the sum across all accounts
    - **Validates: Requirements 1.4**

  - [ ]* 1.5 Write property test for proportional tag allocation
    - **Property 4: Proportional Tag Allocation**
    - Generate random service breakdowns + tag costs, verify allocated cost equals `T * (ci / C)` and sum of allocated costs equals `T` within floating-point tolerance
    - **Validates: Requirements 2.1**

- [ ] 2. Backend: Add hourly service breakdown fetcher
  - [ ] 2.1 Add `_fetch_hourly_service_breakdown(creds, tag_key=None, tag_value=None)` function to member-handler/lambda_function.py
    - Call Cost Explorer `get_cost_and_usage` with `Granularity='HOURLY'`, `GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}]`, time period = last 3 days
    - If tag filter active: add `Filter` with `{"Tags": {"Key": tag_key, "Values": [tag_value]}}` to the CE query
    - Transform CE response `ResultsByTime` into list of `{"hour": "YYYY-MM-DDTHH:00", "services": {"ServiceName": cost_float, ...}}`
    - Handle CE API errors: catch `DataUnavailableException` for hourly not enabled, return error indicator
    - Handle rate limiting / timeout: return 503-style error
    - _Requirements: 3.1, 3.2, 3.4_

  - [ ]* 2.2 Write property test for hourly breakdown structure
    - **Property 5: Hourly Breakdown Structure**
    - Generate random CE hourly response structures, verify transformation produces entries with `hour` in `YYYY-MM-DDTHH:00` format and `services` mapping strings to non-negative numbers
    - **Validates: Requirements 3.2**

- [ ] 3. Backend: Integrate into handle_dashboard_data
  - [ ] 3.1 Add `dailyServiceBreakdown` to the dashboard-data response in member-handler/lambda_function.py
    - Call `_build_daily_service_breakdown(cache_items, tag_key, tag_value)` where `tag_key`/`tag_value` come from existing query params
    - Add result to the response dict as `dailyServiceBreakdown`
    - Ensure this runs from cache only — no additional CE API calls for daily view
    - _Requirements: 1.1, 7.1, 7.2_

  - [ ] 3.2 Add hourly service breakdown endpoint support to member-handler/lambda_function.py
    - Check for `hourlyService=true` query parameter
    - When present: call `_fetch_hourly_service_breakdown` with credentials and tag filter params
    - Add result to response as `hourlyServiceBreakdown`
    - When not present: omit `hourlyServiceBreakdown` from response
    - _Requirements: 3.1, 3.2, 3.4_

- [ ] 4. Checkpoint - Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Frontend: Register widget and add HTML container
  - [ ] 5.1 Register `dash-cost-by-service` in `OBSERVE_WIDGET_SECTIONS` in members/members.js
    - Add `'dash-cost-by-service'` to the `observe-cost` array
    - _Requirements: 4.1_

  - [ ] 5.2 Add widget HTML container to the observe-cost section in members/index.html
    - Add `<div id="dash-cost-by-service" class="observe-widget" style="min-width:380px;">` with widget header, granularity toggle buttons (Daily/Hourly), and chart container div (height 280px)
    - _Requirements: 4.2, 4.3_

- [ ] 6. Frontend: Implement `_renderCostByService` function
  - [ ] 6.1 Add `_renderCostByService(dailyData, hourlyData)` function to members/members.js
    - Store daily data in module-level variable `_dashServiceDaily` for toggle reuse
    - Determine top 8 services by total cost across all days, group rest into "Other"
    - Build ECharts stacked bar series — one series per service
    - Assign colors from existing `_treemapColors` palette
    - Configure x-axis with date categories, y-axis with USD formatting
    - Configure tooltip to show service name, cost as USD with 2 decimal places, and percentage of day total
    - Add legend below chart with service names and colors
    - Initialize ECharts instance on the chart container div
    - Attach window resize listener to call `chart.resize()`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 6.2 Write property test for top-8 service grouping
    - **Property 6: Top-8 Service Grouping**
    - Generate random service data with >8 services, verify exactly 8 named series plus "Other" where "Other" equals sum of non-top-8 services
    - **Validates: Requirements 5.2**

  - [ ]* 6.3 Write property test for tooltip formatter correctness
    - **Property 7: Tooltip Formatter Correctness**
    - Generate random tooltip params (service name, cost value, day total), verify output contains service name, USD with 2 decimal places, and correct percentage within 0.1% tolerance
    - **Validates: Requirements 5.4**

- [ ] 7. Frontend: Implement granularity toggle
  - [ ] 7.1 Add granularity toggle logic to members/members.js
    - Default to daily granularity on initial render
    - On hourly click: fetch hourly data via `api('GET', '/members/dashboard-data?hourlyService=true')`, show loading indicator during fetch, re-render chart with hourly data
    - On daily click: restore chart from cached `_dashServiceDaily` without re-fetching
    - Persist selected granularity in `sessionStorage.setItem('costByServiceGran', 'daily'|'hourly')`
    - On initial render: check sessionStorage and restore last selection
    - Handle hourly fetch errors: display "Enable hourly granularity in AWS Cost Explorer settings" or "Unable to load hourly data. Try again." with retry button
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 3.3_

- [ ] 8. Frontend: Wire widget into render dispatch and handle tag filter refresh
  - [ ] 8.1 Add dispatch entry in `_renderVisibleSectionCharts` in members/members.js
    - Add: `if (toRender.indexOf('dash-cost-by-service') !== -1) _renderCostByService(data.dailyServiceBreakdown || [], data.hourlyServiceBreakdown || []);`
    - _Requirements: 4.4_

  - [ ] 8.2 Ensure tag filter change triggers widget re-render
    - Verify that `onTagFilterChange()` → `loadDashboardData()` → `_renderVisibleSectionCharts()` flow includes the new widget
    - Display loading indicator while filtered data loads
    - Show "No data available for selected tag" empty state when all days have zero cost
    - _Requirements: 8.1, 8.2, 8.3, 2.3_

- [ ] 9. Frontend: Add CSS styles for the widget
  - [ ] 9.1 Add styles for `dash-cost-by-service` widget to members/members.css
    - Style the granularity toggle buttons (active state, hover)
    - Style the loading indicator
    - Style the empty-state message
    - Ensure responsive behavior at 380px minimum width
    - _Requirements: 4.2, 4.3_

- [ ] 10. Checkpoint - Frontend complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Integration: Wire everything together
  - [ ] 11.1 Verify end-to-end data flow
    - Confirm `dailyServiceBreakdown` appears in dashboard-data API response
    - Confirm widget renders from API data on page load
    - Confirm hourly toggle fetches and renders hourly data
    - Confirm tag filter change refreshes the widget with filtered data
    - Confirm empty states display correctly for no-data scenarios
    - _Requirements: All_

  - [ ] 11.2 Bump JS version in members/index.html
    - Update `v=` version number in script/css references
    - _Requirements: N/A (deployment hygiene)_

- [ ] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Backend file (member-handler/lambda_function.py) is very large — use Python scripts for modifications
- Frontend file (members/members.js) is very large — use Python scripts for modifications
- The `_treemapColors` palette is already defined at line ~4005 in members.js — reuse directly
- Follow existing patterns: `_renderMonthly` for stacked bar charts, `_renderDailyTrend`/`_renderHourlyTrend` for daily/hourly toggle
- The `service_breakdown` field already exists in cache records — no schema changes needed
- Tag filtering uses proportional allocation from existing `tag_breakdown` cache field
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "5.1", "5.2"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "2.1", "9.1"] },
    { "id": 2, "tasks": ["2.2", "3.1"] },
    { "id": 3, "tasks": ["3.2", "6.1"] },
    { "id": 4, "tasks": ["6.2", "6.3", "7.1"] },
    { "id": 5, "tasks": ["8.1", "8.2"] },
    { "id": 6, "tasks": ["11.1", "11.2"] }
  ]
}
```
