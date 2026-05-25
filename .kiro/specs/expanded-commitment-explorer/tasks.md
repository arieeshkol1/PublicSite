# Implementation Plan: Expanded Commitment Explorer

## Overview

This implementation expands the Committed Discounts system across five areas: broader RI service coverage (6 services), additional SP payment options (PartialUpfront) and plan types (SageMaker SP), removal of the deprecated laddering strategy (backend + frontend), AWS Free Tier usage tracking (backend API + frontend panel), and free tier alternative suggestions in RI recommendations. The backend is Python (Lambda) and the frontend is vanilla JavaScript.

## Tasks

- [ ] 1. Expand RI Recommendations Backend
  - [ ] 1.1 Extend `_get_ri_recommendations` to query all 6 RI-supported services
    - Add ElastiCache, MemoryDB, OpenSearch, and Redshift to the `services` list in `member-handler/lambda_function.py`
    - Add `service_display` mapping for all 6 services
    - Add instance detail extraction cases for `ElastiCacheInstanceDetails`, `MemoryDBInstanceDetails`, `ESInstanceDetails`, and `RedshiftInstanceDetails`
    - Each new service extracts `NodeType` or `InstanceClass` and `Region` from the service-specific detail key
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 1.2 Write property test for RI normalization completeness
    - **Property 1: RI recommendation normalization produces all required fields**
    - Generate random Cost Explorer API response objects for each of 6 services with varying instance detail structures
    - Verify output contains all required fields: service, instanceType, region, offeringClass, termInYears, paymentOption, recommendedCount, estimatedMonthlySavings, estimatedSavingsPercentage, upfrontCost, breakEvenMonths
    - Test file: `member-handler/tests/test_expanded_commitment_properties.py`
    - **Validates: Requirements 1.4, 2.2**

  - [ ]* 1.3 Write unit tests for expanded RI recommendations
    - Test RI recommendations for ElastiCache/MemoryDB/OpenSearch/Redshift with correct instance detail extraction
    - Test empty response handling per service (returns empty list with "no steady-state usage" message)
    - Test partial failure: one service fails, others succeed — verify successful services still returned
    - _Requirements: 1.4, 1.5_

- [ ] 2. Expand SP Recommendations Backend
  - [ ] 2.1 Add PartialUpfront payment option to `_get_sp_recommendations`
    - Add `PARTIAL_UPFRONT` entries to `term_payment_combos` list in `member-handler/lambda_function.py`
    - Expand from 4 to 6 combinations per plan type (1yr×3 payments + 3yr×3 payments)
    - Ensure break-even calculation uses `upfrontCost / estimatedMonthlySavings` for PartialUpfront
    - _Requirements: 2.1, 2.2, 2.5_

  - [ ] 2.2 Add SageMaker Savings Plans to `_get_sp_recommendations`
    - Add `'SageMakerSavingsPlans'` to the `plan_types` list
    - Handle `ClientError` gracefully for SageMaker (skip silently if no usage)
    - Omit SageMaker from response if no recommendations returned (no usage detected)
    - _Requirements: 3.1, 3.2, 3.6_

  - [ ]* 2.3 Write property test for break-even calculation correctness
    - **Property 4: Break-even calculation correctness for all payment options**
    - Generate random upfront costs (0.01–100000), monthly savings (0.01–10000), all 3 payment options
    - Verify: NoUpfront → break-even is null; PartialUpfront/AllUpfront → break-even = upfrontCost / monthlySavings rounded to 1 decimal
    - Test file: `member-handler/tests/test_expanded_commitment_properties.py`
    - **Validates: Requirements 2.5**

  - [ ]* 2.4 Write unit tests for expanded SP recommendations
    - Test PartialUpfront SP recommendations included in response
    - Test SageMaker SP data present when usage detected
    - Test SageMaker SP omitted when no usage detected
    - _Requirements: 2.1, 3.2, 3.6_

- [ ] 3. Remove Laddering Strategy — Backend
  - [ ] 3.1 Remove laddering backend code from `member-handler/lambda_function.py`
    - Delete `_generate_laddering_strategy()` function entirely
    - Delete `handle_committed_discount_ladder()` route handler
    - Remove the `/ladder` route from the routing table in `lambda_handler()`
    - Remove laddering strategy generation call from `handle_committed_discount_scan()`
    - Remove `ladderingStrategy` from the scan response payload
    - Add 404 handler for `/members/committed-discounts/ladder` returning `EndpointRemoved` error
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 3.2 Write property test for scan response excluding laddering
    - **Property 5: Scan response excludes laddering data**
    - Generate random scan scenarios with varying CE API responses
    - Verify response does NOT contain `ladderingStrategy` key or any "ladder"/"laddering" references
    - Verify top-level keys match expected schema
    - Test file: `member-handler/tests/test_expanded_commitment_properties.py`
    - **Validates: Requirements 4.3, 4.4, 12.4, 12.5**

  - [ ]* 3.3 Write unit tests for laddering removal
    - Test `/ladder` endpoint returns HTTP 404 with `EndpointRemoved` error code and correct message
    - Test scan response has no `ladderingStrategy` key
    - _Requirements: 4.5, 12.4_

- [ ] 4. Checkpoint — Verify backend RI/SP expansion and laddering removal
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement Free Tier Tracking — Backend
  - [ ] 5.1 Implement `_get_free_tier_usage` helper function
    - Create the function in `member-handler/lambda_function.py` that calls `freetier:GetFreeTierUsage` via paginator
    - Implement categorization logic: "in-use" (usage > 0), "unused" (usage = 0), "exceeded" (usage > limit)
    - Implement alert status: "approaching-limit" when usage >= 80% and not exceeded; "exceeded" when usage > limit
    - Calculate `usagePercentage` = actualUsage / limit × 100
    - Handle `AccessDeniedException` by raising `PermissionError('freetier:GetFreeTierUsage')`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ] 5.2 Implement `handle_committed_discount_free_tier` route handler
    - Create new route handler for `POST /members/committed-discounts/free-tier`
    - Accept `accountId` in request body, validate JWT and account ownership
    - Assume cross-account role, create freetier client, call `_get_free_tier_usage`
    - Build response with: scannedAt, accountId, benefits list, summary counts, eligibility info
    - Determine account eligibility (accountCreationDate, monthsRemaining, isWithin12Months)
    - Handle permission errors gracefully (return empty benefits with error message)
    - Register route in `lambda_handler()` routing table
    - _Requirements: 8.1, 8.2, 8.3, 8.5, 6.6, 11.3, 11.4_

  - [ ] 5.3 Add `freeTierSummary` to scan response
    - In `handle_committed_discount_scan`, after parallel data retrieval, attempt free tier summary
    - Create freetier client, call `_get_free_tier_usage`, compute summary counts
    - Set `freeTierSummary` to null if permission missing or API fails (non-blocking)
    - Include `freeTierSummary` in scan response payload
    - _Requirements: 12.6_

  - [ ]* 5.4 Write property test for free tier benefit categorization
    - **Property 6: Free tier benefit categorization correctness**
    - Generate random usage amounts (0–2000), limits (1–1000)
    - Verify category and alertStatus assignments match rules
    - Test file: `member-handler/tests/test_expanded_commitment_properties.py`
    - **Validates: Requirements 6.3, 6.4, 7.3, 7.4**

  - [ ]* 5.5 Write property test for free tier summary count aggregation
    - **Property 7: Free tier summary count aggregation**
    - Generate random benefits lists (0–20 items) with random categories
    - Verify: inUseCount + unusedCount + exceededCount === totalBenefitsTracked
    - Verify each count matches the count of benefits with that category
    - Test file: `member-handler/tests/test_expanded_commitment_properties.py`
    - **Validates: Requirements 7.6, 12.6**

  - [ ]* 5.6 Write unit tests for free tier backend
    - Test free tier route happy path with mixed benefit categories
    - Test free tier route with AccessDenied returns permission error message
    - Test free tier route with API unavailable returns empty benefits
    - Test freeTierSummary in scan response when permission available
    - Test freeTierSummary is null when permission missing
    - _Requirements: 8.1, 8.3, 8.5, 6.6_

- [ ] 6. Checkpoint — Verify free tier backend implementation
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Remove Laddering Strategy — Frontend
  - [ ] 7.1 Remove laddering frontend code from `members/members.js`
    - Delete `_committedRenderLaddering()` function
    - Delete `_committedLadderCustom()`, `_committedLadderPreset()`, `_committedLadderTermChanged()`, `_committedLadderUpdatePresetLabels()` functions
    - Delete `_committedGetSavingsRate()` helper if only used by laddering
    - Delete `_committedLadderSelectedTerm`, `_committedLadderLastStrategy`, `_committedLadderLastBaseline` variables
    - Remove the call to `_committedRenderLaddering(data.ladderingStrategy, data.baseline)` in `_committedRenderResults()`
    - Remove the `committed-laddering-panel` HTML element reference
    - Remove the laddering modal HTML
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ] 7.2 Remove laddering CSS from `members/members.css`
    - Delete all `.cse-ladder-*` CSS classes
    - _Requirements: 5.1_

  - [ ]* 7.3 Write unit tests for laddering removal (frontend)
    - Test committed discounts section renders without laddering panel
    - Test no errors when scan response lacks `ladderingStrategy` field
    - _Requirements: 5.3, 5.5_

- [ ] 8. Implement RI Explorer Service Selector — Frontend
  - [ ] 8.1 Add service selector dropdown to RI Explorer in `members/members.js`
    - Add `selectedService: 'all'` to `_riExplorerState`
    - Extract unique services from RI data for dropdown options
    - Render service selector dropdown with "All Services" default
    - Implement `_riExplorerServiceChanged(service)` handler
    - Filter RI recommendations by selected service (or show all)
    - Re-populate instance type dropdown when service changes
    - Add "Service" column to RI Explorer comparison table
    - _Requirements: 1.6, 1.7_

  - [ ]* 8.2 Write property test for RI service filtering
    - **Property 2: RI Explorer service filtering returns correct subset**
    - Generate random arrays of 1–50 RI recommendations with 1–6 services, random service selections
    - Verify filtering returns exactly matching items, no items lost or duplicated
    - Test file: `members/tests/expanded-commitment-explorer.property.test.js`
    - **Validates: Requirements 1.6, 12.1**

  - [ ]* 8.3 Write unit tests for RI Explorer service selector
    - Test RI Explorer renders service selector with correct options
    - Test RI Explorer filters by service correctly
    - Test service selector only shows services with data
    - _Requirements: 1.6, 1.7_

- [ ] 9. Implement SP Explorer Expansion — Frontend
  - [ ] 9.1 Add PartialUpfront and SageMaker to SP Explorer in `members/members.js`
    - Add `'PartialUpfront'` to payment options array in SP Explorer
    - Add `'SageMakerSavingsPlans'` to plan type labels mapping
    - Render SageMaker as a distinct group with label "SageMaker Savings Plan"
    - Show SageMaker group only when SageMaker recommendations are present in data
    - Update SP Explorer comparison table to show all 6 term-payment combinations per type
    - _Requirements: 2.3, 2.4, 3.3, 3.4, 3.5_

  - [ ]* 9.2 Write property test for SP grouping with SageMaker
    - **Property 3: SP grouping produces correct partitions including SageMaker**
    - Generate random SP arrays (1–30 items) with 1–3 distinct planTypes including SageMaker
    - Verify grouping produces exactly N groups, no items lost or duplicated
    - Test file: `members/tests/expanded-commitment-explorer.property.test.js`
    - **Validates: Requirements 2.4, 3.4**

  - [ ]* 9.3 Write unit tests for SP Explorer expansion
    - Test SP Explorer shows PartialUpfront in payment dropdown
    - Test SP Explorer renders SageMaker group when data present
    - Test SP Explorer omits SageMaker group when data absent
    - _Requirements: 2.3, 3.4, 3.5_

- [ ] 10. Implement Free Tier Tracker Panel — Frontend
  - [ ] 10.1 Implement `_committedRenderFreeTier` and `_committedScanFreeTier` in `members/members.js`
    - Create `_committedScanFreeTier()` async function that calls `POST /members/committed-discounts/free-tier`
    - Cache response in `sessionStorage` as `freeTier_{accountId}`
    - Create `_committedRenderFreeTier(freeTierData)` function
    - Render summary line: total benefits, in use, approaching limit, exceeded
    - Render each benefit as a row: service icon, description, progress bar, usage/limit text, alert badge
    - Progress bar colors: green (< 80%), amber (80–100%), red (> 100%)
    - Render "Opportunities" subsection for unused benefits
    - Render empty state when no data (explain permission requirement with template link)
    - Position panel after coverage/utilization, before SP/RI recommendations
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 8.4_

  - [ ] 10.2 Add Free Tier Tracker CSS styles to `members/members.css`
    - Add styles for free tier panel layout, progress bars, alert badges, opportunities section
    - Style progress bar colors: green default, amber for approaching-limit, red for exceeded
    - Style empty state and permission instructions
    - _Requirements: 7.2, 7.3, 7.4_

  - [ ]* 10.3 Write unit tests for Free Tier Tracker panel
    - Test Free Tier Tracker renders with sample data
    - Test Free Tier Tracker shows empty state when no data
    - Test amber progress bar for approaching-limit benefits
    - Test red progress bar for exceeded benefits
    - Test "Opportunities" section shows unused benefits
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 11. Implement Free Tier Alternative Callouts — Frontend
  - [ ] 11.1 Implement `_checkFreeTierAlternative` function in `members/members.js`
    - Create function that checks if an RI recommendation has a free-tier-eligible alternative
    - Check conditions: recommendedCount === 1, instance type starts with "t", service is EC2 or RDS
    - Check instance type is NOT already free-tier-eligible (t2.micro, t3.micro, db.t2.micro, db.t3.micro)
    - Check account eligibility: isWithin12Months must be true for time-limited benefits
    - Return alternative object with: currentType, freeTierType, riMonthlySavings, freeTierMonthlySavings, eligibilityMonthsRemaining, disclaimer
    - Return null if conditions not met
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6_

  - [ ] 11.2 Render free tier alternative callouts in RI Explorer
    - Call `_checkFreeTierAlternative` for each displayed RI recommendation
    - Render "💡 Free Tier Alternative" callout when alternative exists
    - Show savings comparison: RI savings vs free tier savings
    - Show disclaimer text about workload validation
    - Show expiry note when monthsRemaining < 3 and > 0
    - Show caveat when eligibility cannot be determined
    - _Requirements: 9.2, 9.4, 9.5, 10.3, 10.5_

  - [ ]* 11.3 Write property test for free tier alternative eligibility
    - **Property 8: Free tier alternative eligibility determination**
    - Generate random RI recommendations with varying counts (1–10), instance types (t2.*, m5.*, etc.), services, eligibility states
    - Verify alternative suggested if and only if all conditions met
    - Test file: `members/tests/expanded-commitment-explorer.property.test.js`
    - **Validates: Requirements 9.1, 9.3, 9.6, 10.1, 10.2, 10.4**

  - [ ]* 11.4 Write property test for free tier savings comparison
    - **Property 9: Free tier alternative savings comparison calculation**
    - Generate random RI recommendations with on-demand costs (1–5000), monthly savings (1–2000)
    - Verify freeTierMonthlySavings >= riMonthlySavings always holds
    - Test file: `members/tests/expanded-commitment-explorer.property.test.js`
    - **Validates: Requirements 9.5**

  - [ ]* 11.5 Write property test for eligibility expiry note threshold
    - **Property 10: Free tier eligibility expiry note threshold**
    - Generate random monthsRemaining values (0–12), random isWithin12Months booleans
    - Verify expiry note shown if and only if monthsRemaining < 3 AND > 0 AND isWithin12Months === true
    - Test file: `members/tests/expanded-commitment-explorer.property.test.js`
    - **Validates: Requirements 10.3**

  - [ ]* 11.6 Write unit tests for free tier alternative callouts
    - Test callout appears for qualifying t-family single-instance RI
    - Test callout does NOT appear for multi-instance RI (count > 1)
    - Test callout does NOT appear for non-t-family instances
    - Test callout does NOT appear when account past 12-month eligibility
    - Test callout shows caveat when eligibility unknown
    - Test RDS free tier alternative for db.t2.micro/db.t3.micro
    - _Requirements: 9.1, 9.3, 10.2, 10.5_

- [ ] 12. Checkpoint — Verify all frontend implementations
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Integration Wiring and Final Verification
  - [ ] 13.1 Wire free tier summary into committed discounts render flow
    - In `_committedRenderResults()`, call `_committedRenderFreeTier` with scan response's `freeTierSummary` or cached free tier data
    - Add "Scan Free Tier" button that triggers `_committedScanFreeTier()`
    - Pass eligibility data from free tier response to `_checkFreeTierAlternative` calls in RI Explorer
    - Ensure sessionStorage caching works for both scan and free tier data
    - _Requirements: 7.1, 8.4, 9.1, 12.6_

  - [ ] 13.2 Update IAM template generation for free tier permission
    - In the CloudFormation template generation code, add `freetier:GetFreeTierUsage` to the cross-account role policy
    - Ensure existing `ce:GetReservationPurchaseRecommendation` permission covers all 6 services (already does — verify)
    - _Requirements: 11.1, 11.2_

  - [ ]* 13.3 Write integration tests
    - Test full scan flow: mock all 6 RI services + 3 SP types + free tier → verify complete response structure
    - Test free tier route: mock freetier API → verify response with correct categorization
    - Test scan with partial failure: mock one RI service failing → verify other services still returned
    - Test frontend: scan → cache → RI Explorer with service selector → filter → display updates
    - Test frontend: scan → cache → SP Explorer with PartialUpfront → selection change → correct display
    - Test frontend: free tier scan → cache → Free Tier Tracker renders with progress bars
    - _Requirements: 1.1, 2.1, 3.1, 6.1, 8.1, 12.1_

- [ ] 14. Final Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python (Hypothesis for property tests, pytest for unit tests)
- Frontend uses JavaScript (fast-check for property tests)
- The existing `member-handler/lambda_function.py` and `members/members.js` are the primary files being modified
- Free tier feature is non-blocking: if permissions are missing, the scan still returns all commitment data

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "3.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.2", "2.3", "2.4", "3.2", "3.3"] },
    { "id": 2, "tasks": ["5.1", "7.1"] },
    { "id": 3, "tasks": ["5.2", "5.3", "7.2"] },
    { "id": 4, "tasks": ["5.4", "5.5", "5.6", "7.3", "8.1", "9.1"] },
    { "id": 5, "tasks": ["8.2", "8.3", "9.2", "9.3", "10.1"] },
    { "id": 6, "tasks": ["10.2", "10.3", "11.1"] },
    { "id": 7, "tasks": ["11.2", "11.3", "11.4", "11.5", "11.6"] },
    { "id": 8, "tasks": ["13.1", "13.2"] },
    { "id": 9, "tasks": ["13.3"] }
  ]
}
```
