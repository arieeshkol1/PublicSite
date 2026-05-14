# Implementation Plan: Committed Discount Analyzer

## Overview

This plan implements the Committed Discounts feature for the Act tab, adding RI/SP coverage analysis, purchase recommendations, P10 baseline calculation, laddering strategy generation, and expiring commitments tracking. The backend adds two new routes to the Member Handler Lambda (`POST /members/committed-discounts/scan` and `POST /members/committed-discounts/ladder`), and the frontend adds a new "Committed Discounts" section to the Act tab with navigation, panels, and a purchase guidance modal.

## Tasks

- [x] 1. Implement P10 Baseline Calculator module
  - [x] 1.1 Create `_calculate_p10_baseline` function in member-handler/lambda_function.py
    - Accept a Cost Explorer client and account ID
    - Call `ce:GetCostAndUsage` with HOURLY granularity for trailing 30 days, filtering to compute services (EC2, Fargate, Lambda)
    - Extract `UnblendedCost` amounts from each hourly period
    - Sort ascending, compute P10 = value at index `floor(len(values) * 0.10)`
    - Compute average = sum(values) / len(values)
    - Set `variabilityWarning = True` if P10 < 70% of average
    - Calculate safe commitment range: `[p10, min(p10 * 1.1, averageHourlySpend * 0.70)]`
    - Fallback: if < 7 days of hourly data, use DAILY granularity with note in response
    - Return dict with `p10HourlySpend`, `averageHourlySpend`, `variabilityWarning`, `safeCommitmentRange`, `granularity`, `dataPoints`
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ]* 1.2 Write property test for P10 baseline calculation
    - **Property 7: P10 baseline calculation correctness**
    - Use Hypothesis to generate random lists of hourly spend values (100–1000 items, values 0.01–100)
    - Assert P10 equals value at index `floor(len(values) * 0.10)` when sorted ascending
    - Assert variability warning is True iff `p10 < average * 0.70`
    - Assert `safeCommitmentRange.min <= safeCommitmentRange.max`
    - **Validates: Requirements 12.2, 12.3, 12.4**

- [x] 2. Implement SP and RI Recommendation Retrievers
  - [x] 2.1 Create `_get_sp_recommendations` function in member-handler/lambda_function.py
    - Accept a Cost Explorer client and average hourly spend
    - Query `ce:GetSavingsPlansPurchaseRecommendation` for ComputeSavingsPlans and EC2InstanceSavingsPlans types
    - Query all four term-payment combos: 1yr NoUpfront, 1yr AllUpfront, 3yr NoUpfront, 3yr AllUpfront
    - Normalize each recommendation into the standard response format (planType, termInYears, paymentOption, hourlyCommitment, estimatedMonthlySavings, estimatedSavingsPercentage, estimatedMonthlyOnDemandCost, breakEvenMonths, upfrontCost)
    - Calculate break-even: `upfrontCost / monthlySavings` for upfront options, null for NoUpfront
    - Flag as aggressive if `hourlyCommitment > averageHourlySpend * 0.70`
    - Handle empty API responses gracefully (return empty list with "insufficient history" message)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 2.2 Create `_get_ri_recommendations` function in member-handler/lambda_function.py
    - Accept a Cost Explorer client
    - Query `ce:GetReservationPurchaseRecommendation` for EC2 and RDS services
    - Query both Standard and Convertible offering classes
    - Query all three payment options (NoUpfront, PartialUpfront, AllUpfront) for 1yr and 3yr terms
    - Normalize each recommendation into the standard response format (service, instanceType, region, offeringClass, termInYears, paymentOption, recommendedCount, estimatedMonthlySavings, estimatedSavingsPercentage, breakEvenMonths, upfrontCost)
    - Include comparison note showing discount difference between Standard and Convertible
    - Handle empty API responses gracefully
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 2.3 Write property tests for recommendation modules
    - **Property 3: Recommendation response field completeness**
    - Generate random API response objects with varying field presence
    - Assert all required fields are present in normalized SP recommendations
    - Assert all required fields are present in normalized RI recommendations
    - **Validates: Requirements 3.3, 4.4**
    - **Property 4: Break-even calculation correctness**
    - Generate random upfront costs (0.01–100000) and monthly savings (0.01–10000)
    - Assert break-even = `upfrontCost / monthlySavings` rounded to 1 decimal
    - Assert break-even is null for NoUpfront options
    - Assert break-even is always positive when present
    - **Validates: Requirements 3.4, 4.5**
    - **Property 5: Aggressive commitment threshold detection**
    - Generate random hourly commitments (0.01–1000) and average spends (0.01–2000)
    - Assert aggressive flag is True iff `hourlyCommitment > averageHourlySpend * 0.70`
    - Assert no aggressive flag when averageHourlySpend is 0
    - **Validates: Requirements 3.5, 5.6, 10.5**

- [x] 3. Implement Laddering Strategy Generator
  - [x] 3.1 Create `_generate_laddering_strategy` function in member-handler/lambda_function.py
    - Accept total hourly commitment, average hourly spend, and current date
    - Validate that totalHourlyCommitment does not exceed 70% of average hourly spend (set isAggressive flag if it does)
    - Divide total into 4 equal tranches, rounded to nearest $0.01/hr
    - Assign purchase dates at months 0, 3, 6, 9 from current date
    - Tranches 1–2: recommend ComputeSavingsPlans (flexibility)
    - Tranches 3–4: recommend EC2InstanceSavingsPlans (deeper discount)
    - Calculate cumulative commitment and estimated monthly savings at each tranche
    - Return dict with totalHourlyCommitment, averageHourlySpend, commitmentPercentage, isAggressive, aggressiveWarning, tranches array
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 3.2 Write property test for laddering strategy
    - **Property 6: Laddering strategy structural correctness**
    - Use Hypothesis to generate random total commitments (0.01–500) and random start dates
    - Assert exactly 4 tranches produced
    - Assert each tranche is within $0.01 of 25% of total
    - Assert sum of all tranche commitments equals total (within $0.01 tolerance)
    - Assert purchase dates at month offsets 0, 3, 6, 9
    - Assert cumulative commitment at tranche N = sum of tranches 1..N
    - Assert tranches 1–2 recommend ComputeSavingsPlans, tranches 3–4 recommend EC2InstanceSavingsPlans
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

- [x] 4. Implement Coverage/Utilization and Expiring Commitments modules
  - [x] 4.1 Create `_get_coverage_utilization` function in member-handler/lambda_function.py
    - Accept a Cost Explorer client
    - Call `ce:GetSavingsPlansCoverage` and `ce:GetSavingsPlansUtilization` for trailing 30 days
    - Call `ce:GetReservationCoverage` and `ce:GetReservationUtilization` for trailing 30 days
    - Aggregate overall percentages as weighted averages across time periods
    - Break down coverage by service (EC2, RDS, ElastiCache, Redshift, OpenSearch)
    - Flag items with utilization < 80% as underutilized
    - Handle empty API responses (return 0% with "insufficient history" message)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 4.2 Create `_get_expiring_commitments` function in member-handler/lambda_function.py
    - Accept Cost Explorer client, Savings Plans client, EC2 client, RDS client
    - Retrieve active RI and SP details with expiration dates
    - Filter to commitments expiring within 90 days of current date
    - Set urgency: "expiring_soon" if daysUntilExpiry < 30, "upcoming" if 30–90
    - Calculate coverage impact percentage for each expiring commitment
    - Return dict with `expiring` list, `nextExpiration`, `noUpcomingExpirations`
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [ ]* 4.3 Write property tests for coverage and expiring commitments
    - **Property 1: Coverage and utilization aggregation produces valid percentages**
    - Generate random lists of coverage periods with percentages (0–100), varying period counts (1–30)
    - Assert overall percentage is in [0, 100]
    - Assert each per-service percentage is in [0, 100]
    - **Validates: Requirements 2.1, 2.2, 2.3**
    - **Property 2: Underutilization flagging threshold**
    - Generate random lists of RI/SP items with utilization values (0–100)
    - Assert underutilized list contains exactly items with utilization < 80%
    - Assert items with utilization >= 80% are NOT in the underutilized list
    - **Validates: Requirement 2.4**
    - **Property 13: Expiring commitments filtering and urgency**
    - Generate random commitment lists with expiration dates (0–365 days from now)
    - Assert only commitments within 90 days are included
    - Assert urgency is "expiring_soon" for < 30 days, "upcoming" for 30–90
    - **Validates: Requirements 14.2, 14.3, 14.4**

- [x] 5. Checkpoint - Ensure all core backend modules pass tests
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement Committed Discount Scan route orchestrator
  - [x] 6.1 Create `handle_committed_discount_scan` function in member-handler/lambda_function.py
    - Register route `POST /members/committed-discounts/scan` in the lambda_handler routing
    - Validate JWT token and verify account ownership via `_verify_account_ownership`
    - Validate accountId is exactly 12 digits
    - Assume cross-account role using `_assume_role_for_account`
    - Permission pre-check: attempt lightweight `ce:GetSavingsPlansCoverage` with 1-day range; if AccessDenied, return 403 with required IAM actions list
    - Use `concurrent.futures.ThreadPoolExecutor` to parallelize: coverage/utilization, SP recommendations, RI recommendations, P10 baseline, expiring commitments
    - Cross-reference rightsizing recommendations (check if any RI instance types overlap with pending rightsizing)
    - Generate default laddering strategy using P10 baseline
    - Detect organization sharing context (check if multiple accounts connected, if management account)
    - Assemble and return complete scan response within 30-second timeout
    - Handle partial failures: if one module fails, return successful data with error note on failed section
    - Handle timeout: if approaching 25s, return collected data with incomplete results note
    - _Requirements: 10.1, 10.2, 10.3, 2.1, 2.2, 2.5, 8.3, 13.1, 13.2, 15.1, 15.2, 15.3_

  - [x] 6.2 Create `handle_committed_discount_ladder` function in member-handler/lambda_function.py
    - Register route `POST /members/committed-discounts/ladder` in the lambda_handler routing
    - Validate JWT token and verify account ownership
    - Validate `totalHourlyCommitment` > 0 (return 400 if not)
    - Retrieve average hourly spend for the account (call P10 baseline or cached value)
    - If averageHourlySpend is 0, return 400 InsufficientData error
    - Call `_generate_laddering_strategy` with user-specified commitment
    - Return laddering strategy with aggressive warning if commitment > 70% of average
    - _Requirements: 10.4, 10.5, 5.1, 5.6_

  - [ ]* 6.3 Write property tests for scan orchestrator helpers
    - **Property 8: Diverse workload Compute SP highlighting**
    - Generate random service spend distributions (1–10 services, values 0–10000)
    - Assert Compute SP highlighted iff more than 2 services have > 10% of total spend
    - **Validates: Requirement 6.2**
    - **Property 9: Total cost of ownership calculation**
    - Generate random terms (1,3), upfront costs (0–50000), monthly costs (0–5000)
    - Assert TCO = `upfrontCost + (monthlyCost * termYears * 12)`
    - **Validates: Requirement 6.4**
    - **Property 10: Annual savings aggregation**
    - Generate random lists of recommendations (0–20 items) with monthly savings (0–5000)
    - Assert annual savings = `sum(monthlySavings) * 12`
    - **Validates: Requirement 6.5**
    - **Property 11: Database SP inclusion threshold**
    - Generate random RDS/ElastiCache monthly spend values (0–1000)
    - Assert Database SP included iff combined spend > $50
    - **Validates: Requirement 11.2**
    - **Property 12: Rightsize-first warning correctness**
    - Generate random RI instance types and rightsizing instance types with varying overlap
    - Assert warning triggered iff at least one instance type appears in both sets
    - **Validates: Requirements 13.2, 13.3**

- [x] 7. Update CloudFormation template with Cost Explorer permissions
  - [x] 7.1 Update `handle_generate_template` in member-handler/lambda_function.py
    - Add the following IAM actions to the cross-account role policy: `ce:GetSavingsPlansPurchaseRecommendation`, `ce:GetReservationPurchaseRecommendation`, `ce:GetSavingsPlansUtilization`, `ce:GetSavingsPlansCoverage`, `ce:GetReservationUtilization`, `ce:GetReservationCoverage`, `ce:GetCostAndUsage`
    - Ensure these are included in the generated CloudFormation YAML template
    - Add `savingsplans:DescribeSavingsPlans` for expiring commitments retrieval
    - _Requirements: 8.1, 8.2_

  - [ ]* 7.2 Write property test for CloudFormation template permissions
    - **Property 14: CloudFormation template includes all required CE permissions**
    - Generate random 12-digit account IDs and random email addresses
    - Assert generated template includes all 7 required CE IAM actions
    - **Validates: Requirement 8.1**

- [x] 8. Checkpoint - Ensure all backend routes and template updates pass tests
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement Frontend - Navigation and Section Structure
  - [x] 9.1 Add "Committed Discounts" navigation button and section container to members/index.html
    - Add a 💰 Committed Discounts button to the Act tab navigation bar (after Scheduler button)
    - Add `act-section-committed` div container with empty state prompting account selection and scan
    - Include sub-section containers for: coverage/utilization panel, recommendations table, laddering timeline, expiring commitments, purchase guidance modal
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 9.2 Update `_switchActSection` in members/members.js to handle the new section
    - Add `committed` to the list of Act sections toggled by `_switchActSection`
    - Show/hide `act-section-committed` based on active section
    - Add navigation pattern for AI tab links: `_goToTab('act-tab','committed')`
    - _Requirements: 1.2_

- [x] 10. Implement Frontend - Scan Trigger and API Integration
  - [x] 10.1 Create `_committedDiscountScan` function in members/members.js
    - Add account selector and "Scan" button to the committed discounts section
    - On scan click, call `POST /members/committed-discounts/scan` with selected accountId
    - Show loading spinner during scan (up to 30 seconds)
    - On success, cache results in `sessionStorage` keyed by `committedDiscounts_{accountId}`
    - Display `scannedAt` timestamp and "Rescan" button
    - On error, display appropriate error message (permission error with template update link, timeout with retry suggestion)
    - Handle permission pre-check failure: show required IAM actions and link to Configure tab
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 10.1, 10.3, 2.5, 8.2_

  - [x] 10.2 Implement sessionStorage caching logic
    - On section load, check `sessionStorage` for cached results for selected account
    - If cached, display immediately without API call
    - On "Rescan" click, clear cache for that account and trigger fresh scan
    - On account change, check cache for new account or show empty state
    - _Requirements: 9.1, 9.2, 9.3_

- [x] 11. Implement Frontend - Coverage/Utilization and Recommendations Panels
  - [x] 11.1 Create coverage/utilization summary card renderer
    - Display summary card at top: current SP coverage %, RI coverage %, SP utilization %, RI utilization %
    - Show per-service breakdown (EC2, RDS, ElastiCache, Redshift, OpenSearch)
    - Highlight underutilized items with specific utilization percentage
    - Show total estimated annual savings and recommended commitment level (60–70% of baseline)
    - Display P10 baseline vs average hourly spend with safe commitment zone indicator
    - Show variability warning when applicable
    - _Requirements: 6.5, 12.3, 12.4_

  - [x] 11.2 Create SP and RI recommendations comparison table renderer
    - Render comparison table with columns: Type (SP/RI), Term, Payment Option, Monthly Cost, Monthly Savings, Savings %, Break-Even Months
    - Highlight Compute SP as "Recommended for flexibility" when diverse workloads detected (>2 services with significant spend)
    - Show Standard vs Convertible RI side-by-side with discount difference
    - Show total cost of ownership for each payment option over full term
    - Include Database SP recommendations when account has >$50/mo RDS/ElastiCache spend
    - Clearly label Database SP section
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 11.2, 11.3, 11.4_

- [x] 12. Implement Frontend - Laddering Timeline and Expiring Commitments
  - [x] 12.1 Create laddering strategy timeline renderer
    - Display 4 tranches as a visual timeline with purchase dates, hourly commitment, cumulative amount, and estimated monthly savings
    - Show recommended plan type for each tranche (Compute SP vs EC2 Instance SP)
    - Show rationale for each tranche recommendation
    - Add "Customize" button that opens input for custom hourly commitment
    - On custom commitment submit, call `POST /members/committed-discounts/ladder` and re-render
    - Show aggressive warning if commitment > 70% of average
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 10.4, 10.5_

  - [x] 12.2 Create expiring commitments timeline renderer
    - Display commitments expiring in next 90 days with monthly value and coverage impact
    - Show "⚠️ Expiring Soon" badge for commitments expiring within 30 days
    - Calculate and display coverage gap percentage for each expiring commitment
    - Show "No upcoming expirations" message when none exist
    - _Requirements: 14.2, 14.3, 14.4, 14.5_

- [x] 13. Implement Frontend - Rightsize Warning, Organization Sharing, and Purchase Guidance
  - [x] 13.1 Create rightsize-first warning renderer
    - Display prominent warning when rightsizing recommendations overlap with commitment targets
    - List specific instances with current type and recommended type
    - Provide link to Service Optimization → Resize section
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [x] 13.2 Create organization sharing awareness note
    - Display note when member has multiple connected accounts explaining RI/SP sharing
    - Show management account tip about purchasing from payer account
    - _Requirements: 15.1, 15.2, 15.4_

  - [x] 13.3 Create purchase guidance modal
    - Add "How to Purchase" button for each recommendation
    - Display step-by-step instructions for SP purchase (Cost Explorer → Savings Plans → Purchase)
    - Display step-by-step instructions for RI purchase (EC2/RDS console → Reserved Instances → Purchase)
    - Include direct link to relevant AWS console page using account's region
    - Include warning about non-refundable commitments and recommend laddering approach
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 13.4 Write property test for AWS console link construction
    - **Property 15: AWS console link construction**
    - Generate random AWS region strings and service types
    - Assert SP links contain `/cost-management/home#/savings-plans/purchase`
    - Assert EC2 RI links contain `/ec2/v2/home#ReservedInstances`
    - Assert RDS RI links contain `/rds/home#reserved-instances`
    - Assert all links contain the correct region code
    - **Validates: Requirement 7.3**

- [x] 14. Checkpoint - Ensure all frontend and backend integration works
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Wire everything together and final integration
  - [x] 15.1 Register both new routes in lambda_handler routing table
    - Add `POST /members/committed-discounts/scan` → `handle_committed_discount_scan`
    - Add `POST /members/committed-discounts/ladder` → `handle_committed_discount_ladder`
    - Ensure CORS headers are included in responses
    - Verify route matching works with the existing path/method routing logic
    - _Requirements: 10.1, 10.4_

  - [x] 15.2 Add Database SP threshold logic to scan orchestrator
    - Check if RDS + ElastiCache monthly spend > $50
    - If yes, include Database SP recommendations via RI recommendation API for RDS/ElastiCache
    - If no, omit database SP section from response
    - _Requirements: 11.1, 11.2_

  - [ ]* 15.3 Write integration tests for end-to-end scan flow
    - Test: authenticate → scan → verify complete response structure
    - Test: permission pre-check failure returns clear error
    - Test: partial failure (SP succeeds, RI fails) returns partial data
    - Test: ladder route rejects commitment <= 0
    - Test: ladder route warns when commitment > 70% of average
    - Test: frontend navigation click shows committed section, hides others
    - _Requirements: 10.1, 10.3, 10.4, 10.5, 1.2_

- [x] 16. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (15 properties total)
- Unit tests validate specific examples and edge cases
- The backend uses Python (matching existing member-handler/lambda_function.py)
- The frontend uses vanilla JavaScript (matching existing members/members.js)
- All Cost Explorer API calls use the existing cross-account STS AssumeRole pattern via `_assume_role_for_account`
