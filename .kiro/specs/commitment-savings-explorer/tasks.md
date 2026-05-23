# Implementation Plan: Commitment Savings Explorer

## Overview

Transform the existing static committed-discount results into an interactive exploration experience. All data comes from the existing `sessionStorage` cache — no new backend API routes needed. The implementation replaces `_committedRenderRecommendations` with SP/RI Explorer UIs, redesigns the laddering section, adds dashboard widgets, and injects chart data into AI chat responses.

## Tasks

- [ ] 1. Implement SP Savings Explorer
  - [ ] 1.1 Create `_spExplorerRender(spRecommendations)` function in `members/members.js`
    - Replace the SP section of `_committedRenderRecommendations` with an interactive explorer UI
    - Render dropdowns for SP type (Compute SP, EC2 Instance SP), term (1yr, 3yr), and payment option (All Upfront, Partial Upfront, No Upfront)
    - Group recommendations by `planType` and allow independent selection within each group
    - Default selection: 1-year term, No Upfront payment
    - Display: hourly commitment, savings/hr, savings/month (savings/hr × 730), savings %, on-demand equivalent, upfront cost, break-even
    - Show "Immediate" for break-even when No Upfront is selected
    - Compute and display "Best Value" badge on option with highest `estimatedMonthlySavings × termInYears × 12`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ] 1.2 Create `_spExplorerSelectionChanged()` handler
    - Filter cached `spRecommendations` array by selected planType, term, and payment option
    - Update displayed savings card dynamically without API call
    - Handle case where no match exists (show "Not available" message)
    - _Requirements: 1.2, 10.1, 10.2_

  - [ ] 1.3 Create `_spExplorerToggleCompare()` for the "Compare All Options" table
    - Toggle a collapsible comparison table showing all 6 combinations (2 terms × 3 payment options) for the selected SP type
    - Columns: Term, Payment Option, Hourly Commitment, Monthly Savings, Savings %, Upfront Cost, Break-Even Months, Total Cost over Term
    - Highlight row with highest savings % in green, lowest total cost in blue
    - Hide toggle if fewer than 2 combinations available
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [ ]* 1.4 Write property tests for SP Explorer filtering and calculations
    - **Property 1: Explorer filtering returns the correct recommendation**
    - **Property 2: Savings per month equals savings per hour times 730**
    - **Property 3: Break-even calculation correctness**
    - **Property 5: Best Value badge placement**
    - **Property 6: SP grouping produces correct partitions**
    - **Property 12: Compare table row count and highlighting**
    - **Validates: Requirements 1.2, 1.3, 1.5, 2.2, 2.3, 2.4, 2.5, 11.1, 11.3**

- [ ] 2. Implement RI Savings Explorer
  - [ ] 2.1 Create `_riExplorerRender(riRecommendations)` function in `members/members.js`
    - Replace the RI section of `_committedRenderRecommendations` with an interactive explorer UI
    - Render dropdowns for instance type (populated from unique values in data), offering class (Standard, Convertible), term (1yr, 3yr), payment option (All Upfront, Partial Upfront, No Upfront)
    - Default selection: first instance type, Standard, 1-year, No Upfront
    - Display: monthly savings, savings %, recommended count, region, break-even, TCO
    - TCO = `upfrontCost + (monthlyRecurringCost × termInYears × 12)`
    - Show "Lowest TCO" badge on option with minimum TCO
    - Show Standard vs Convertible note when Standard saves >5% more
    - Disable options that don't exist in scan data with "Not available for this instance type" message
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ] 2.2 Create `_riExplorerSelectionChanged()` handler
    - Filter cached `riRecommendations` array by selected instanceType, offeringClass, term, and payment
    - Update displayed savings card dynamically without API call
    - Disable dropdown options that have no matching data
    - _Requirements: 3.2, 3.5, 10.1, 10.2_

  - [ ] 2.3 Create `_riExplorerToggleCompare()` for the "Compare All Options" table
    - Toggle a collapsible comparison table showing all available combinations for the selected instance type
    - Columns: Offering Class, Term, Payment Option, Monthly Savings, Savings %, Upfront Cost, Break-Even Months, TCO
    - Highlight row with lowest TCO in blue, highest savings % in green
    - Hide toggle if fewer than 2 combinations available for the instance type
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ]* 2.4 Write property tests for RI Explorer filtering and calculations
    - **Property 1: Explorer filtering returns the correct recommendation (RI variant)**
    - **Property 4: Total Cost of Ownership calculation**
    - **Property 5: Lowest TCO badge placement**
    - **Property 7: Instance type dropdown contains exactly the unique types**
    - **Property 8: Standard vs Convertible note threshold**
    - **Property 12: Compare table row count and highlighting (RI variant)**
    - **Validates: Requirements 3.2, 3.3, 3.5, 4.2, 4.3, 4.5, 4.6, 12.1, 12.3, 12.5**

- [ ] 3. Wire SP/RI Explorers into existing committed discounts flow
  - [ ] 3.1 Modify `_committedRenderRecommendations(data)` to call the new explorer functions
    - Replace the static SP table with `_spExplorerRender(data.spRecommendations)`
    - Replace the static RI table with `_riExplorerRender(data.riRecommendations)`
    - Keep the existing panel container and "Purchase Recommendations" header
    - Ensure explorers read from sessionStorage cache on re-render (Requirement 10.4: auto-refresh on rescan)
    - _Requirements: 10.1, 10.2, 10.4_

  - [ ] 3.2 Add explorer state variables and CSS styles
    - Add `_spExplorerState` and `_riExplorerState` in-memory state objects at module level
    - Add CSS styles in `members/members.css` for explorer dropdowns, savings cards, badges, compare tables, and responsive layout
    - _Requirements: 1.1, 3.1_

- [ ] 4. Checkpoint — Ensure SP/RI Explorers render correctly
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement Dashboard Integration — SP and RI Coverage Widgets
  - [ ] 5.1 Add SP Coverage and RI Coverage widget definitions to `DASH_WIDGET_DEFS`
    - Add `{ id: 'dash-sp-coverage', title: 'SP Coverage', height: 180, q: 'What is my Savings Plan coverage?' }`
    - Add `{ id: 'dash-ri-coverage', title: 'RI Coverage', height: 180, q: 'What is my Reserved Instance coverage?' }`
    - _Requirements: 5.1, 6.1_

  - [ ] 5.2 Create `_renderSPCoverageWidget(container)` function
    - Read `committedDiscounts_{accountId}` from sessionStorage for selected dashboard accounts
    - Display SP coverage % with progress bar (amber if <50%)
    - Display SP utilization % with progress bar (red if <80%, tooltip: "Underutilized — you are paying for unused commitment")
    - Include "View Details" link calling `_goToTab('act-tab','committed')`
    - Empty state: "No scan data — run a Committed Discounts scan in the Act tab" with link
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 10.3_

  - [ ] 5.3 Create `_renderRICoverageWidget(container)` function
    - Read from sessionStorage cache for selected dashboard accounts
    - Display RI coverage % (amber if <50%)
    - Display RI utilization % (red if <80%)
    - Display count of underutilized RIs (utilization <80%) as red badge
    - Include "View Details" link calling `_goToTab('act-tab','committed')`
    - Empty state same as SP widget
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 10.3_

  - [ ] 5.4 Wire widget rendering into `_buildDashWidgets` / dashboard load flow
    - Ensure `_renderSPCoverageWidget` and `_renderRICoverageWidget` are called when their widget containers are rendered
    - Follow the existing pattern used by other widgets (treemap, daily trend, etc.)
    - _Requirements: 5.1, 6.1_

  - [ ]* 5.5 Write property tests for coverage/utilization threshold styling
    - **Property 9: Coverage and utilization threshold styling**
    - **Validates: Requirements 5.3, 5.4, 6.2, 6.3, 6.4**

- [ ] 6. Implement Dashboard Integration — KPI Bar Commitment Savings Line
  - [ ] 6.1 Create `_getCommitmentSavingsForKPI(accountIds)` function
    - Iterate selected dashboard accounts, read sessionStorage cache for each
    - Sum `estimatedMonthlySavings` from all SP and RI recommendations
    - Return the sum, or null if no scan data exists
    - _Requirements: 7.1, 7.3, 7.4_

  - [ ] 6.2 Modify `renderDashboardWidgets()` to include commitment savings in KPI card
    - Add "Commitment Savings (estimated)" line item to the Potential Savings KPI card when value > 0
    - Omit the line entirely when no data (no zero placeholder)
    - Add tooltip: "Estimated savings if all recommended Savings Plans and Reserved Instances are purchased."
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 6.3 Write property test for KPI summation
    - **Property 10: Commitment savings KPI summation**
    - **Validates: Requirements 7.3**

- [ ] 7. Checkpoint — Ensure dashboard widgets and KPI render correctly
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement Chat Integration — Savings Comparison Chart
  - [ ] 8.1 Create `_buildCommitmentChartData(answerText, existingChartData)` function
    - Detect commitment keywords (case-insensitive): "savings plan", "reserved instance", "commitment", "SP coverage", "RI coverage"
    - Read sessionStorage cache for the queried account(s)
    - Build bar chart data: Y-axis = monthly savings ($), X-axis = option labels (e.g., "1yr No Upfront", "3yr All Upfront")
    - Use distinct colors: blue (#6366f1) for 1yr terms, green (#10b981) for 3yr terms
    - For SP-specific responses: show all term/payment combos for the discussed SP type
    - For RI-specific responses: show all offering class/term/payment combos for the discussed instance type
    - Return null if no scan data or no commitment keywords detected
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ] 8.2 Inject chart data into AI response handling
    - Modify the `askAI` response handler (after `addAIMessage`) to call `_buildCommitmentChartData`
    - Append returned chartData entries to the existing `data.chartData` array before rendering
    - Ensure existing chart rendering logic handles the injected data seamlessly
    - _Requirements: 8.1, 10.5_

  - [ ]* 8.3 Write property test for chart injection keyword detection
    - **Property 11: Chart injection keyword detection**
    - **Validates: Requirements 8.1**

- [ ] 9. Verify Chat Navigation Links (existing implementation)
  - [ ] 9.1 Confirm `_addNavLinks` already handles "Go to Act → Committed Discounts" pattern
    - Verify the existing navMap in `_addNavLinks()` includes the committed discounts navigation
    - If not present, add the mapping: `{pattern: 'Go to Act → Committed Discounts', handler: "_goToTab('act-tab','committed')"}`
    - Ensure the link renders as a styled button consistent with other nav links
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [ ] 10. Redesign Laddering Strategy Section
  - [ ] 10.1 Rewrite `_committedRenderLaddering(strategy, baseline)` with new UI
    - Display commitment amounts in monthly terms ($/month) as primary unit, hourly ($/hr) as secondary detail
    - Add plain-language explanation at top: "Instead of buying your full commitment at once, stagger multiple 1-year (or 3-year) purchases across different dates..."
    - Display summary sentence: "Recommended: Buy 4 separate commitments of ~$X/month each, purchased 3 months apart → total savings ~$Y/month once all are active"
    - Clarify each purchase is a full 1-year or 3-year commitment — staggering is about WHEN you buy
    - Show aggressive warning in plain language when triggered
    - _Requirements: 13.1, 13.2, 13.6, 13.7, 13.8_

  - [ ] 10.2 Implement visual timeline with milestone markers
    - Render horizontal progress bar with 4 milestone markers (Purchase 1–4)
    - Each milestone shows: purchase date, incremental monthly commitment, commitment term (e.g., "1-year Compute SP")
    - Color coding: past dates in green, next upcoming in blue/highlighted, future in gray
    - Responsive: stack vertically on narrow screens
    - _Requirements: 14.1, 14.2, 14.3, 14.5_

  - [ ] 10.3 Implement summary table below timeline
    - Columns: Purchase #, Date, Commitment $/month, Term, Cumulative $/month, Est. Savings $/month, Plan Type
    - Each tranche displays: purchase number, recommended date, monthly commitment, term, cumulative commitment, estimated savings, plan type with rationale
    - _Requirements: 13.5, 14.4_

  - [ ] 10.4 Update the Customize modal for laddering
    - Accept input in monthly commitment ($/month) instead of hourly, convert internally using `hourly = monthly / 730`
    - Add three preset buttons: "Conservative (P10 floor)", "Moderate (60% of average)", "Aggressive (70% of average)" pre-filled with calculated values from baseline data
    - _Requirements: 13.3, 13.4_

  - [ ] 10.5 Add CSS styles for laddering timeline and redesigned section
    - Style the horizontal timeline, milestone markers, color coding, responsive stacking
    - Style the preset buttons, summary table, and plain-language explanation blocks
    - _Requirements: 14.1, 14.3, 14.5_

- [ ] 11. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- All data comes from existing `sessionStorage` cache — no new backend API routes needed
- The existing `_committedRenderRecommendations` function is replaced by the SP/RI Explorer UIs (Tasks 1–3)
- The existing `_committedRenderLaddering` function is rewritten with the new design (Task 10)
- Dashboard widgets follow the existing `DASH_WIDGET_DEFS` / `_addWidget` / `_buildDashWidgets` pattern
- Chat integration modifies the existing `askAI` response handling to inject chartData
- Property tests validate universal correctness properties from the design document
