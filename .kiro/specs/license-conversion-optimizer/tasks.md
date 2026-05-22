# Implementation Plan: License Conversion Optimizer

## Overview

This plan implements the License Conversion Optimizer feature, adding portfolio analysis, conversion opportunity detection, feasibility scoring, and execution plan generation. The backend adds two new routes to the Member Handler Lambda (`POST /members/license-conversion/analyze` and `POST /members/license-conversion/plan`), and the frontend adds a new "License Conversion" wizard card to Act > Optimize with portfolio visualization, opportunity browsing, and plan execution guidance.

## Tasks

- [ ] 1. Implement Portfolio Builder module
  - [x] 1.1 Create `_build_licensing_portfolio` function in member-handler/lambda_function.py
    - Accept a cross-account boto3 session and account_id
    - Call `ec2:DescribeReservedInstances` with filter `state=active` to get EC2 RIs
    - Classify each RI by offering class (standard/convertible), instance family, term, payment option
    - Call `rds:DescribeReservedDBInstances` to get RDS RIs
    - Call `savingsplans:DescribeSavingsPlans` with filter `states=[active]` to get Savings Plans
    - Call `ec2:DescribeInstances` to detect running instances and their license models (LI vs BYOL)
    - Calculate `daysUntilExpiry` and `expiryUrgency` for each commitment
    - Calculate `monthlyRecurringCost` = `recurringHourly * 730` for RIs, `hourlyCommitment * 730` for SPs
    - Build summary with `totalCommitments`, `totalMonthlyCommitmentCost`, `totalOnDemandSpend`, `overallCoveragePercentage`, `serviceBreakdown`
    - Handle pagination for all API calls
    - _Requirements: 1.1, 1.3, 1.6_

  - [ ]* 1.2 Write property test for portfolio monetary totals consistency
    - **Property 3: Portfolio monetary totals are consistent**
    - Use Hypothesis to generate random lists of EC2 RIs, RDS RIs, and Savings Plans with random monthly costs
    - Assert `summary.totalMonthlyCommitmentCost` equals sum of all individual item costs within $0.01 tolerance
    - **Validates: Requirements 1.3**

  - [ ]* 1.3 Write property test for expiry urgency classification
    - **Property 11: Expiry urgency classification**
    - Use Hypothesis to generate random `daysUntilExpiry` values (0–1000)
    - Assert `expiryUrgency == 'expiring'` when `daysUntilExpiry < 30`
    - Assert `expiryUrgency == 'expiring_soon'` when `30 <= daysUntilExpiry < 60`
    - Assert `expiryUrgency == 'active'` when `daysUntilExpiry >= 60`
    - **Validates: Requirements 1.1**

  - [ ]* 1.4 Write property test for utilization threshold
    - **Property 12: Utilization threshold for underutilization flag**
    - Use Hypothesis to generate random `utilizationPct` values (0.0–100.0)
    - Assert `isUnderutilized == True` iff `utilizationPct < 80`
    - Assert `isUnderutilized == False` iff `utilizationPct >= 80`
    - **Validates: Requirements 1.1**

  - [ ]* 1.5 Write property test for coverage percentage bounds
    - **Property 10: Coverage percentage bounds**
    - Use Hypothesis to generate random `totalMonthlyCommitmentCost` and `totalOnDemandSpend` values (0–100000)
    - Assert `overallCoveragePercentage` is in range [0, 100]
    - Assert formula: `committed / (committed + onDemand) * 100` when total > 0, else 0
    - **Validates: Requirements 1.3**

- [ ] 2. Implement Utilization Analyzer
  - [x] 2.1 Create `_get_utilization_data` function in member-handler/lambda_function.py
    - Accept a cross-account session and portfolio dict
    - Call `ce:GetReservationUtilization` for the last 30 days, grouped by RI
    - Call `ce:GetSavingsPlansUtilization` for the last 30 days
    - Call `ce:GetCostAndUsage` to get on-demand spend by service
    - Map utilization percentages back to portfolio items
    - Set `isUnderutilized = True` for items with utilization < 80%
    - Handle Cost Explorer not activated gracefully (return partial results)
    - _Requirements: 1.1, 1.3_

- [ ] 3. Implement Feasibility Scorer
  - [x] 3.1 Create `_calculate_feasibility_score` function in member-handler/lambda_function.py
    - Accept conversion_type, savings_percentage, utilization_current, utilization_projected, complexity, remaining_term_days, is_reversible
    - Implement weighted scoring: savings_potential (35%), utilization_improvement (25%), complexity_factor (20%), risk_factor (20%)
    - Savings score: `min(savings_percentage * 2, 100)`
    - Utilization score: based on delta between projected and current
    - Complexity score: low=100, medium=60, high=30
    - Risk score: base 80, -20 if not reversible, -15 if term > 365 days, +10 if term < 30 days
    - Return integer in range [0, 100]
    - _Requirements: 1.1, 1.3_

  - [ ]* 3.2 Write property test for feasibility score bounds and monotonicity
    - **Property 1: Feasibility score is bounded and monotonic with savings**
    - Use Hypothesis to generate random valid inputs (savings_percentage in [0,100], utilization in [0,100], complexity in {low, medium, high})
    - Assert score is always in range [0, 100]
    - For two inputs differing only in savings_percentage where a > b, assert score_a >= score_b
    - **Validates: Requirements 1.1, 1.3**

- [ ] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement Conversion Engine
  - [x] 5.1 Create `_identify_ri_exchange_opportunities` function in member-handler/lambda_function.py
    - Filter portfolio for Convertible RIs with utilization < 80%
    - For each underutilized RI, calculate remaining value using `_calculate_ri_exchange_value`
    - Query pricing cache for alternative instance types in the same family
    - Verify target value >= source remaining value (AWS exchange rule)
    - Generate ConversionOpportunity with type `ri_exchange`, savings estimate, and complexity
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 5.2 Create `_calculate_ri_exchange_value` helper function in member-handler/lambda_function.py
    - Accept RI dict and remaining_term_days
    - Calculate remaining_hours = remaining_term_days * 24
    - Calculate recurring_value = remaining_hours * hourly_rate * instance_count
    - Calculate remaining_upfront = fixedPrice * (remaining_hours / total_term_hours)
    - Return total remaining value (recurring + upfront)
    - _Requirements: 1.1, 1.4_

  - [ ]* 5.3 Write property test for RI exchange value constraint
    - **Property 2: RI exchange value constraint**
    - Use Hypothesis to generate random Convertible RI pairs with varying hourly rates, counts, and remaining terms
    - Assert that for every returned exchange opportunity, target value >= source remaining value
    - Assert opportunities violating the constraint are excluded
    - **Validates: Requirements 1.1, 1.4**

  - [x] 5.4 Create `_identify_ri_to_sp_migrations` function in member-handler/lambda_function.py
    - Filter portfolio for RIs with `daysUntilExpiry <= 90`
    - Calculate equivalent SP hourly commitment to cover the same workload
    - Compare RI effective rate vs SP rate for savings calculation
    - Set `timing = 'at_expiry'` with `timingDate` 1-2 days before expiration
    - If RI expires in < 3 days, set `timing = 'immediate'`
    - Only return opportunities where SP provides equal or better coverage at lower cost
    - _Requirements: 1.1, 1.3_

  - [ ]* 5.5 Write property test for RI-to-SP timing constraints
    - **Property 5: Timing constraints for RI-to-SP migrations**
    - Use Hypothesis to generate random expiry dates (1–90 days from now)
    - Assert `timingDate` is between 1 and 3 days before expiration
    - Assert `timing == 'at_expiry'` when expiry > 3 days
    - Assert `timing == 'immediate'` when expiry <= 3 days
    - **Validates: Requirements 1.1**

  - [x] 5.6 Create `_identify_on_demand_commitment_candidates` function in member-handler/lambda_function.py
    - Filter on-demand instances with `hasCoverage == False`
    - Check running hours in last 30 days (from utilization data)
    - Only recommend instances running >= 680 hours/month (93% uptime)
    - Calculate savings for both SP and RI options
    - Sort by estimated monthly savings descending
    - Ensure no instance appears in multiple opportunities
    - _Requirements: 1.1, 1.3_

  - [ ]* 5.7 Write property test for on-demand uptime threshold
    - **Property 6: On-demand commitment candidates meet uptime threshold**
    - Use Hypothesis to generate random running hours (0–730)
    - Assert only instances with >= 680 hours are recommended
    - Assert instances with < 680 hours are excluded
    - **Validates: Requirements 1.1**

  - [x] 5.8 Create `_identify_license_model_changes` function in member-handler/lambda_function.py
    - Identify instances using License Included that could switch to BYOL
    - Cross-reference with Windows/SQL Licensing Optimizer for detailed analysis
    - Set complexity to `high` for license model changes
    - Include prerequisite: "Verify Software Assurance coverage"
    - Add `crossReference` field pointing to existing optimizer
    - _Requirements: 1.1, 1.3_

  - [x] 5.9 Create `_identify_sp_upgrades` function in member-handler/lambda_function.py
    - Identify EC2 Instance SPs that could upgrade to Compute SPs for flexibility
    - Identify underutilized SPs that could be right-sized on renewal
    - Calculate savings/cost difference for each upgrade path
    - _Requirements: 1.1, 1.3_

- [ ] 6. Implement Deduplication and Savings Aggregation
  - [x] 6.1 Create `_deduplicate_opportunities` function in member-handler/lambda_function.py
    - Ensure no source commitment appears in more than one opportunity of the same type
    - Allow same source in different types (e.g., ri_exchange AND ri_to_sp)
    - _Requirements: 1.1_

  - [ ]* 6.2 Write property test for no duplicate recommendations
    - **Property 4: No duplicate recommendations across conversion types**
    - Use Hypothesis to generate random opportunity lists with overlapping source IDs
    - Assert at most one opportunity per source per type
    - Assert same source can appear in different types
    - **Validates: Requirements 1.1**

  - [x] 6.3 Create `_calculate_non_conflicting_savings` function in member-handler/lambda_function.py
    - Calculate total potential savings from the best non-conflicting set of opportunities
    - When two opportunities conflict (same source), pick the higher-scoring one
    - Return monthly, annual, and percentage of current spend
    - _Requirements: 1.3_

  - [ ]* 6.4 Write property test for savings non-negative
    - **Property 9: Savings calculations are non-negative**
    - Use Hypothesis to generate random cost pairs (current and target)
    - Assert `estimatedMonthlySavings >= 0`
    - Assert `estimatedAnnualSavings == estimatedMonthlySavings * 12`
    - Assert `savingsPercentage` in range [0, 100]
    - **Validates: Requirements 1.3**

- [ ] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement Plan Generator
  - [x] 8.1 Create `_generate_execution_plan` function in member-handler/lambda_function.py
    - Accept selected conversion IDs and portfolio
    - Validate each conversion ID exists and is still feasible
    - Detect conflicts (two conversions targeting same source)
    - Order steps by dependency (some must happen before others)
    - Generate step-by-step instructions for each conversion
    - Include AWS Console deep links for each step
    - Calculate execution timeline with parallel and sequential steps
    - Include rollback guidance for reversible conversions
    - Add warnings for irreversible actions
    - _Requirements: 1.1, 1.3, 1.6_

  - [ ]* 8.2 Write property test for execution plan step ordering
    - **Property 7: Execution plan step ordering respects dependencies**
    - Use Hypothesis to generate random dependency graphs (DAGs)
    - Assert if step B depends on step A, then A's stepNumber < B's stepNumber
    - Assert no circular dependencies exist
    - **Validates: Requirements 1.1**

  - [ ]* 8.3 Write property test for conflict detection
    - **Property 8: Conflict detection prevents double-conversion**
    - Use Hypothesis to generate random sets of selected conversions with overlapping source IDs
    - Assert conflicts are detected and reported
    - Assert only the higher-scoring conversion's steps are included
    - **Validates: Requirements 1.1**

- [ ] 9. Implement Analyze Endpoint Handler
  - [x] 9.1 Create `handle_license_conversion_analyze` function in member-handler/lambda_function.py
    - Validate JWT token and extract member identity
    - Parse `accountId` from request body and validate (12 digits)
    - Verify account ownership via `_verify_account_ownership`
    - Assume cross-account role via `_assume_cross_account_role`
    - Validate required permissions via `_validate_conversion_permissions`
    - Call `_build_licensing_portfolio` to build portfolio
    - Call `_get_utilization_data` for utilization metrics
    - Build pricing cache via `_build_pricing_cache`
    - Run all 5 conversion identifiers in parallel using ThreadPoolExecutor
    - Score and rank all opportunities by feasibility score
    - Calculate total potential savings
    - Return portfolio + opportunities JSON response
    - Handle timeout gracefully (return partial results if approaching 120s)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 9.2 Create `handle_license_conversion_plan` function in member-handler/lambda_function.py
    - Validate JWT token and extract member identity
    - Parse `accountId` and `selectedConversions` from request body
    - Verify account ownership
    - Validate each conversion ID exists
    - Call `_generate_execution_plan` with selected conversions
    - Return execution plan JSON response
    - _Requirements: 1.1, 1.3, 1.6_

  - [x] 9.3 Wire route handlers into the Lambda router in member-handler/lambda_function.py
    - Add route matching for `POST /members/license-conversion/analyze`
    - Add route matching for `POST /members/license-conversion/plan`
    - Follow existing routing pattern in the Lambda function
    - _Requirements: 1.1_

- [ ] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement Frontend - License Conversion Wizard Card
  - [x] 11.1 Add License Conversion wizard card to Act > Optimize in members/members.js
    - Add "🔄 License Conversion" card alongside existing optimization wizards
    - Include description: "Analyze your licensing portfolio and find conversion opportunities"
    - Add "Analyze Portfolio" button that triggers the analyze API call
    - Add account selector dropdown (reuse existing pattern)
    - Cache analysis results in `sessionStorage` keyed by `licenseConversion_{accountId}`
    - Invalidate cache after 1 hour or on manual "Re-analyze" click
    - _Requirements: 9.1, 9.4_

  - [x] 11.2 Implement Portfolio Overview Panel in members/members.js
    - Display total commitments count, coverage percentage, and monthly commitment cost
    - Show service breakdown (EC2, RDS, Lambda, etc.) with visual bars
    - Highlight expiring commitments with warning icons
    - Show underutilized commitments with alert indicators
    - Display on-demand spend that could be committed
    - _Requirements: 1.6, 9.4_

  - [x] 11.3 Implement Conversion Opportunities Panel in members/members.js
    - Render opportunities as sortable cards (by score, savings, complexity)
    - Show feasibility score with color-coded badges (green >= 80, yellow >= 50, red < 50)
    - Display source description, target description, monthly savings, and complexity
    - Add checkboxes for selecting opportunities for plan generation
    - Show timing indicators (immediate, at_expiry with date, scheduled)
    - Add "View Details" expandable section for each opportunity
    - Include cross-reference links to Windows/SQL Licensing Optimizer where applicable
    - Add "Generate Execution Plan for Selected" button
    - _Requirements: 1.6, 9.1, 9.4_

  - [x] 11.4 Implement Execution Plan View in members/members.js
    - Display plan as a step-by-step checklist with progress tracking
    - Show each step's action, description, instructions, and AWS Console link
    - Display timing dependencies and scheduled dates
    - Show warnings for each step prominently
    - Render timeline as a Gantt-style visualization
    - Display total estimated savings from the plan
    - Show conflicts if any were detected
    - _Requirements: 1.6, 9.4_

- [x] 12. Implement Frontend Styles and HTML Updates
  - [x] 12.1 Add License Conversion styles to members/members.css
    - Style feasibility score badges (color-coded circles)
    - Style portfolio overview panel with service breakdown bars
    - Style opportunity cards with hover effects and selection state
    - Style execution plan steps with timeline connector lines
    - Style Gantt-style timeline visualization
    - Style warning and risk indicators
    - Ensure responsive layout for all new panels
    - _Requirements: 9.1, 9.4_

  - [x] 12.2 Update members/index.html version parameter
    - Bump `members.js?v=XX` query parameter to bust cache
    - _Requirements: 9.5_

- [x] 13. Add API Gateway Routes
  - [x] 13.1 Add route resources to infrastructure/viewmybill-stack.yaml
    - Add `MemberLicenseConversionAnalyzeRoute` for `POST /members/license-conversion/analyze`
    - Add `MemberLicenseConversionPlanRoute` for `POST /members/license-conversion/plan`
    - Both routes target the existing `MemberIntegration`
    - _Requirements: 1.1_

  - [x] 13.2 Update .github/workflows/deploy.yml with new routes
    - Add the two new POST routes to the deployment workflow
    - Follow existing route addition pattern
    - _Requirements: 1.1_

- [ ] 14. Implement Unit Tests
  - [ ]* 14.1 Write unit tests for Portfolio Builder in member-handler/tests/
    - Mock EC2, RDS, and Savings Plans API responses
    - Test correct classification of RIs by offering class
    - Test monthly cost calculation accuracy
    - Test pagination handling
    - Test empty portfolio scenario
    - _Requirements: 1.1, 1.3_

  - [ ]* 14.2 Write unit tests for Conversion Engine in member-handler/tests/
    - Mock portfolio and utilization data
    - Test RI exchange identification with known RI parameters
    - Test RI-to-SP migration timing logic
    - Test on-demand candidate detection with various running hours
    - Test license model change detection
    - Test deduplication logic
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 14.3 Write unit tests for Plan Generator in member-handler/tests/
    - Test step ordering with known dependency graphs
    - Test conflict detection with overlapping conversions
    - Test timeline generation
    - Test invalid conversion ID handling
    - _Requirements: 1.1, 1.3_

  - [ ]* 14.4 Write unit tests for endpoint handlers in member-handler/tests/
    - Test authentication validation
    - Test account ownership verification
    - Test permission validation error responses
    - Test partial results on timeout
    - Test all error scenarios from the design
    - _Requirements: 1.1, 1.5_

- [ ] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation uses Python throughout (matching the existing member-handler Lambda)
- Frontend uses vanilla JavaScript following the existing members.js patterns
- All AWS API calls use the existing cross-account STS AssumeRole pattern

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "2.1", "3.2"] },
    { "id": 2, "tasks": ["5.1", "5.2", "5.4", "5.6", "5.8", "5.9"] },
    { "id": 3, "tasks": ["5.3", "5.5", "5.7", "6.1"] },
    { "id": 4, "tasks": ["6.2", "6.3"] },
    { "id": 5, "tasks": ["6.4", "8.1"] },
    { "id": 6, "tasks": ["8.2", "8.3", "9.1", "9.2"] },
    { "id": 7, "tasks": ["9.3", "11.1", "13.1", "13.2"] },
    { "id": 8, "tasks": ["11.2", "11.3", "11.4", "12.1"] },
    { "id": 9, "tasks": ["12.2", "14.1", "14.2", "14.3", "14.4"] }
  ]
}
```
