# Implementation Plan: Tag-Based Cost Filtering

## Overview

Add a global tag filter to the SlashMyBill Observe (dashboard) and Chat (AI query) tabs. Implementation uses Python scripts to modify the large backend and frontend files. Two new API Gateway routes are added for tag metadata retrieval, and existing endpoints gain tag filter support via query/body parameters.

## Tasks

- [x] 1. Backend: Add tag filter utility functions
  - [x] 1.1 Add `_build_tag_filter(tag_key, tag_value)` function to member-handler/lambda_function.py
    - Returns `{"Tags": {"Key": tag_key, "Values": [tag_value]}}` when both params are non-empty
    - Returns None when either param is falsy
    - Use a Python script to insert the function near other helper functions
    - _Requirements: 7.1, 7.2_

  - [x] 1.2 Add `_apply_filter_to_ce_call(base_params, tag_key, tag_value)` function to member-handler/lambda_function.py
    - Calls `_build_tag_filter` to get the filter expression
    - If no tag filter, returns base_params unchanged
    - If existing Filter in base_params, wraps both in `{"And": [existing, tag_filter]}`
    - If no existing Filter, sets Filter directly
    - Must not mutate the original base_params dict (create a copy)
    - _Requirements: 4.1, 4.2, 4.3, 7.1, 7.2, 7.3, 7.4_

  - [ ]* 1.3 Write property tests for `_build_tag_filter` and `_apply_filter_to_ce_call`
    - **Property 4: CE filter construction correctness** — for any non-empty key/value, output has correct structure
    - **Property 5: Filter composition with And expression** — existing filter + tag filter produces And expression
    - **Property 6: No-op on empty filter** — null/empty key or value returns base_params unchanged
    - **Property 7: Filter application immutability** — original base_params dict is never mutated
    - **Validates: Requirements 4.1, 4.2, 4.3, 7.1, 7.2, 7.3, 7.4**

- [x] 2. Backend: Add tag-keys endpoint
  - [x] 2.1 Add `handle_get_tag_keys(event)` function to member-handler/lambda_function.py
    - Authenticate via JWT (use existing `validate_token` pattern)
    - Parse `accountIds` from query string parameters
    - Verify account ownership using existing `_get_connected_accounts` helper
    - Assume role into each account (max 5) using existing STS pattern
    - Call `ce.get_tags(TimePeriod={last 30 days})` without TagKey filter
    - Merge, deduplicate, and sort all tag keys across accounts
    - Skip accounts where role assumption fails (log warning, continue)
    - Return `{"tagKeys": [sorted list]}`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 8.1, 8.2, 8.3, 9.2_

  - [x] 2.2 Add routing for `GET /members/tag-keys` in the Lambda handler's dispatch logic
    - Add path matching for `/members/tag-keys` with GET method
    - Route to `handle_get_tag_keys`
    - _Requirements: 1.1_

  - [ ]* 2.3 Write property tests for tag keys endpoint
    - **Property 1: Tag keys merge produces sorted deduplicated output** — union of all account tag key sets, sorted, no duplicates
    - **Property 3: Account ownership filtering** — only owned accounts contribute tag data
    - **Property 11: Resilience to partial account failures** — partial failures still return results from successful accounts
    - **Validates: Requirements 1.2, 1.3, 1.4, 8.2, 8.3, 9.2**

- [x] 3. Backend: Add tag-values endpoint
  - [x] 3.1 Add `handle_get_tag_values(event)` function to member-handler/lambda_function.py
    - Authenticate via JWT
    - Parse `accountIds` and `tagKey` from query string parameters
    - Return 400 error if `tagKey` is missing: `{"error": "tagKey parameter is required"}`
    - Verify account ownership
    - Assume role into each account (max 5)
    - Call `ce.get_tags(TimePeriod={last 30 days}, TagKey=tag_key)`
    - Merge, deduplicate, and sort all tag values across accounts
    - Skip accounts where role assumption fails (log warning, continue)
    - Return `{"tagValues": [sorted list]}`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 8.1, 8.2, 8.4, 9.3_

  - [x] 3.2 Add routing for `GET /members/tag-values` in the Lambda handler's dispatch logic
    - Add path matching for `/members/tag-values` with GET method
    - Route to `handle_get_tag_values`
    - _Requirements: 2.1_

  - [ ]* 3.3 Write property tests for tag values endpoint
    - **Property 2: Tag values merge produces sorted deduplicated output** — union of all account tag value sets, sorted, no duplicates
    - **Property 3: Account ownership filtering** — only owned accounts contribute tag data
    - **Property 11: Resilience to partial account failures** — partial failures still return results from successful accounts
    - **Validates: Requirements 2.2, 2.3, 8.2, 8.4, 9.3**

- [ ] 4. Checkpoint - Backend tag endpoints
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Backend: Add tag filter support to dashboard-data endpoint
  - [x] 5.1 Modify `handle_dashboard_data` to extract `tagKey` and `tagValue` from query params
    - Parse `tagKey` and `tagValue` from `queryStringParameters`
    - Strip whitespace, treat empty as None
    - _Requirements: 4.1, 4.3_

  - [x] 5.2 Apply `_apply_filter_to_ce_call` to all Cost Explorer calls in dashboard-data
    - Apply tag filter to daily cost, monthly cost, service breakdown, and all other CE queries
    - Do NOT apply tag filter to the Tag Distribution widget data (costByTag)
    - Pass `tag_key` and `tag_value` through to each CE call site
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 5.3 Write unit tests for dashboard-data tag filter integration
    - Test that tagKey/tagValue params are correctly extracted
    - Test that CE calls include the Tags filter when params are present
    - Test that Tag Distribution data is NOT filtered
    - Test that missing/empty params result in no filter applied
    - _Requirements: 4.1, 4.3, 4.4_

- [x] 6. Backend: Add tag filter support to ai-query endpoint
  - [x] 6.1 Modify `handle_ai_query` to extract `tagKey` and `tagValue` from request body
    - Parse from JSON body: `body.get('tagKey', '').strip() or None`
    - Parse from JSON body: `body.get('tagValue', '').strip() or None`
    - _Requirements: 5.1, 5.2_

  - [x] 6.2 Apply tag filter to all CE calls within AI query data gathering
    - Pass tag_key and tag_value to `_gather_account_data` or equivalent function
    - Use `_apply_filter_to_ce_call` on each CE query within the AI data gathering
    - Include tag filter context in the AI prompt so the response mentions the active filter
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]* 6.3 Write unit tests for ai-query tag filter integration
    - Test that tagKey/tagValue are extracted from body
    - Test that CE calls include Tags filter when params present
    - Test that AI prompt includes filter context
    - _Requirements: 5.1, 5.2, 5.3_

- [ ] 7. Checkpoint - Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Frontend: Add tag filter UI component
  - [x] 8.1 Add global state variables and cache structures to members/members.js
    - Add `var globalTagFilter = { key: null, value: null };`
    - Add `var tagKeysCache = null;` and `var tagKeysCacheTime = 0;`
    - Add `var tagValuesCache = {};` and `var tagValuesCacheTime = {};`
    - Add `var TAG_CACHE_TTL = 300000;` (5 minutes)
    - Use a Python script to insert at the top of the file with other globals
    - _Requirements: 3.1, 6.1, 6.2_

  - [x] 8.2 Add `initTagFilter(containerId)` function to members/members.js
    - Render two cascading dropdowns: Tag Key and Tag Value
    - Tag Key dropdown has "All (no filter)" as default option
    - Tag Value dropdown starts disabled with "Select key first" placeholder
    - On key change: fetch values, enable value dropdown, update globalTagFilter.key
    - On value change: update globalTagFilter.value, call onTagFilterChange()
    - On key cleared to "All": reset both to null, disable value dropdown, call onTagFilterChange()
    - _Requirements: 1.1, 1.5, 2.1, 2.4, 3.1, 3.2, 3.3_

  - [x] 8.3 Add `_loadTagKeys(selectElement)` and `_loadTagValues(key, selectElement)` helper functions
    - `_loadTagKeys`: Check cache TTL, fetch from `/members/tag-keys?accountIds=...` if expired, populate dropdown
    - `_loadTagValues`: Check cache TTL per key, fetch from `/members/tag-values?accountIds=...&tagKey=...` if expired, populate dropdown
    - Handle timeout (10s) — fall back to "All" only option
    - Handle empty results — show info message for keys, "No values found" for values
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 9.1_

  - [x] 8.4 Add `getTagFilterParams()`, `getTagFilterBody()`, `clearTagFilter()`, and `onTagFilterChange()` functions
    - `getTagFilterParams()`: Returns `tagKey=X&tagValue=Y` URL string or empty string
    - `getTagFilterBody()`: Returns `{tagKey, tagValue}` object or empty object
    - `clearTagFilter()`: Resets globalTagFilter to {key: null, value: null}
    - `onTagFilterChange()`: Invalidates dashDataCache, triggers loadDashboardData() if on Observe tab
    - _Requirements: 3.1, 3.2, 4.5_

  - [x] 8.5 Add tag filter container div to the Observe tab HTML in members/index.html
    - Add a `<div id="tag-filter-container">` in the dashboard header area
    - Call `initTagFilter('tag-filter-container')` during dashboard initialization
    - _Requirements: 1.1_

  - [ ]* 8.6 Write unit tests for frontend tag filter state management
    - **Property 8: Cascading validity invariant** — if key is null then value is null
    - **Property 9: Partial key selection produces no filter params** — key set but value null returns empty
    - **Validates: Requirements 3.1, 3.2**

- [ ] 9. Frontend: Integrate tag filter with dashboard data loading
  - [x] 9.1 Modify `loadDashboardData()` to include tag filter params in the API request
    - Call `getTagFilterParams()` and append to the request URL
    - Ensure Tag Distribution widget uses unfiltered data (skip tag params for that specific call or use cached unfiltered data)
    - _Requirements: 4.1, 4.4, 4.5_

  - [x] 9.2 Add cache invalidation on account selector change
    - When account selection changes, clear tagKeysCache and tagValuesCache
    - Reset globalTagFilter to null/null
    - Reload tag keys for new account selection
    - _Requirements: 6.5_

  - [ ]* 9.3 Write unit tests for dashboard integration
    - **Property 12: Cache hit avoids redundant API calls** — cached data within TTL is reused
    - **Validates: Requirements 6.3, 6.4**

- [ ] 10. Frontend: Integrate tag filter with AI chat
  - [x] 10.1 Modify the AI query submission function to include tag filter in request body
    - Call `getTagFilterBody()` and merge into the POST payload
    - Only include tagKey/tagValue if both are non-empty
    - _Requirements: 5.1, 5.2_

  - [x] 10.2 Ensure tag filter state persists across Observe ↔ Chat tab switches
    - globalTagFilter is a module-level variable — verify it is NOT reset on tab switch
    - If tag filter UI is re-rendered on tab switch, restore selected values from globalTagFilter
    - _Requirements: 3.4_

  - [ ]* 10.3 Write unit tests for AI chat integration
    - **Property 10: Filter persistence across tab switches** — switching tabs does not modify globalTagFilter
    - **Validates: Requirement 3.4**

- [ ] 11. Checkpoint - Frontend complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Pipeline: Add new API Gateway routes
  - [x] 12.1 Add GET /members/tag-keys route to .github/workflows/deploy.yml
    - Add API Gateway route creation for `GET /members/tag-keys` pointing to member-handler Lambda
    - Use API Gateway ID `l2fd4h481h`
    - Follow existing route pattern in the deploy workflow
    - _Requirements: 1.1_

  - [x] 12.2 Add GET /members/tag-values route to .github/workflows/deploy.yml
    - Add API Gateway route creation for `GET /members/tag-values` pointing to member-handler Lambda
    - Use API Gateway ID `l2fd4h481h`
    - Follow existing route pattern in the deploy workflow
    - _Requirements: 2.1_

- [ ] 13. Version bump and final wiring
  - [x] 13.1 Bump JS version in members/index.html
    - Update `v=88` to `v=89` (or current+1) in the script/css references
    - _Requirements: N/A (deployment hygiene)_

  - [x] 13.2 Verify all components are wired together
    - Confirm tag filter init is called on dashboard load
    - Confirm tag params flow through to dashboard-data and ai-query endpoints
    - Confirm Tag Distribution widget is excluded from filtering
    - Confirm new routes are in deploy workflow
    - _Requirements: All_

- [ ] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Backend file (member-handler/lambda_function.py) is 13000+ lines — use Python scripts for modifications
- Frontend file (members/members.js) is 8000+ lines — use Python scripts for modifications
- `ce:GetTags` is already covered by the ReadOnlyAccess managed policy on the cross-account role
- The dashboard-data and ai-query endpoints already exist — only need tag param extraction and filter application
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
