# Implementation Plan: SQL Platform Comparator

## Overview

Implement a side-by-side SQL Server platform cost comparison wizard in the Member Portal (Act > Optimize). The feature discovers SQL workloads (EC2 Windows+SQL and RDS SQL) in a customer account, queries AWS Pricing API for 4 deployment options per workload, displays a comparison matrix with savings calculations, and generates step-by-step migration plans for cheaper alternatives.

## Tasks

- [ ] 1. Backend — SQL Platform Compare Endpoint
  - [ ] 1.1 Add data models and platform constants to `member-handler/lambda_function.py`
    - Define platform identifier constants (PLATFORM_EC2_WIN_SQL_LI, PLATFORM_EC2_WIN_BYOL, PLATFORM_RDS_SQL_STANDARD, PLATFORM_RDS_SQL_ENTERPRISE)
    - Define VALID_PLATFORMS set and REGION_TO_LOCATION mapping
    - _Requirements: Data Models section, Platform Identifiers_

  - [ ] 1.2 Implement `discover_sql_workloads()` function in `member-handler/lambda_function.py`
    - Scan EC2 instances filtered by platform=windows, state=running across active regions
    - Detect SQL Server presence and edition via AMI descriptions (DescribeImages batch lookup)
    - Scan RDS instances filtered by engine prefix `sqlserver-*`
    - Resolve instance type specs (vCPUs, memory) via DescribeInstanceTypes
    - Map RDS instance classes to EC2 equivalent types (strip "db." prefix)
    - Implement 80-second timeout guard for multi-region scanning
    - _Requirements: Component 1 interface, Discovery Algorithm_

  - [ ] 1.3 Implement `calculate_platform_pricing()` function in `member-handler/lambda_function.py`
    - Query Pricing API (us-east-1) for EC2 Windows + SQL Standard (License Included)
    - Query Pricing API for EC2 Windows + SQL Enterprise (License Included)
    - Query Pricing API for EC2 Windows only (BYOL scenario, preInstalledSw=NA)
    - Query Pricing API for RDS SQL Server Standard and Enterprise
    - Cache results per instance type within invocation to avoid duplicate queries
    - Map EC2 instance types to RDS instance classes (prepend "db.")
    - _Requirements: Component 2 interface, Pricing Algorithm_

  - [ ] 1.4 Implement `build_comparison_matrix()` function in `member-handler/lambda_function.py`
    - Calculate monthly cost (hourly_rate × 730) for each of 4 options per workload
    - Determine current option based on workload's `current_platform_key`
    - Calculate savings_vs_current and savings_percent for each option
    - Flag cheapest option per workload (ties broken by first match)
    - Set savings_vs_current = 0 for the current option
    - _Requirements: Component 3 interface, Matrix Builder Algorithm_

  - [ ] 1.5 Implement `handle_sql_platform_compare()` route handler in `member-handler/lambda_function.py`
    - Validate JWT token and verify account ownership
    - Consume credits for the scan operation
    - Assume cross-account role with ExternalId
    - Orchestrate: discover_sql_workloads → calculate_platform_pricing → build_comparison_matrix
    - Return HTTP 200 with workloads comparison matrix or appropriate error responses (400/402/403/500)
    - Handle empty workloads case with informational message
    - _Requirements: Function 1 specification, Main Compare Algorithm_

  - [ ]* 1.6 Write property tests for `build_comparison_matrix()`
    - **Property 1: Four Options Per Workload** — every workload has exactly 4 options
    - **Property 2: Exactly One Current Option** — exactly one option per workload has isCurrent=true
    - **Property 3: Exactly One Cheapest Option** — exactly one option per workload has isCheapest=true
    - **Property 5: Zero Savings For Current Option** — current option always has savingsVsCurrent=0
    - **Validates: Correctness Properties 1, 2, 3, 5**

  - [ ]* 1.7 Write property tests for savings calculations
    - **Property 4: Consistent Monthly Cost Calculation** — monthlyCost = hourlyRate × 730
    - **Property 6: Savings Calculation Correctness** — savingsVsCurrent = currentMonthlyCost - option.monthlyCost
    - **Property 7: Savings Percentage Correctness** — savingsPercent = (savingsVsCurrent / currentMonthlyCost) × 100
    - **Validates: Correctness Properties 4, 6, 7**

  - [ ]* 1.8 Write unit tests for `discover_sql_workloads()`
    - Test EC2 Windows instance with SQL Server AMI detection
    - Test RDS SQL Server instance discovery and edition classification
    - Test filtering of non-SQL EC2 instances and non-SQL RDS instances
    - Test timeout guard behavior
    - _Requirements: Function 2 specification_

- [ ] 2. Backend — Migration Plan Endpoint
  - [ ] 2.1 Implement migration plan templates in `member-handler/lambda_function.py`
    - Define MIGRATION_TEMPLATES dict with all valid (source, target) pairs
    - Include steps, risks, prerequisites, complexity, and duration for each pair
    - Cover all 7 migration paths: EC2→BYOL, EC2→RDS Std, EC2→RDS Ent, RDS Std→EC2, RDS Std→BYOL, RDS Ent→BYOL, RDS Ent→RDS Std
    - _Requirements: Migration Plan Generation Algorithm, MIGRATION_TEMPLATES_

  - [ ] 2.2 Implement `generate_migration_plan()` function in `member-handler/lambda_function.py`
    - Select template based on (source_platform, target_platform) pair
    - Customize step actions with actual instance ID, type, region, RDS class
    - Generate AWS Console deep links for backup/provision/cleanup steps
    - Calculate monthly and annual savings
    - Assign step numbers (1-based, consecutive)
    - Mark step reversibility (cleanup steps are not reversible)
    - _Requirements: Component 4 interface, Function 5 specification_

  - [ ] 2.3 Implement `handle_sql_migration_plan()` route handler in `member-handler/lambda_function.py`
    - Validate JWT token and verify account ownership
    - Validate input: accountId, instanceId, sourcePlatform, targetPlatform
    - Reject same source/target platform (HTTP 400)
    - Validate platforms against VALID_PLATFORMS set
    - Return migration plan JSON response
    - _Requirements: Migration Plan Flow sequence diagram, Error Scenario 6_

  - [ ]* 2.4 Write property tests for `generate_migration_plan()`
    - **Property 8: Migration Plan Safety** — every plan has at least one backup step
    - **Property 9: Annual Savings Consistency** — annual = monthly × 12
    - **Validates: Correctness Properties 8, 9**

  - [ ]* 2.5 Write unit tests for migration plan generation
    - Test all 7 migration template paths produce valid plans
    - Test step customization with instance details
    - Test AWS Console link generation
    - Test invalid source/target pair rejection
    - _Requirements: Function 5 specification, Error Scenario 6_

- [ ] 3. Checkpoint — Backend verification
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. API Gateway and Deployment Configuration
  - [ ] 4.1 Add routes to `member-handler/lambda_function.py` routes dict
    - Add `'POST /members/sql/compare': handle_sql_platform_compare`
    - Add `'POST /members/sql/migration-plan': handle_sql_migration_plan`
    - _Requirements: Files to Modify section_

  - [ ] 4.2 Add API Gateway routes to `.github/workflows/deploy.yml`
    - Add `"POST /members/sql/compare"` to MEMBER_ROUTES array
    - Add `"POST /members/sql/migration-plan"` to MEMBER_ROUTES array
    - _Requirements: Files to Modify section_

- [ ] 5. Frontend — SQL Platform Comparator UI
  - [ ] 5.1 Add SQL Platform Comparator wizard card to Act > Optimize section in `members/members.js`
    - Render card with title, description, and account selector dropdown
    - Implement "Compare" button to trigger POST /members/sql/compare
    - Handle loading state with progress indicator
    - Handle empty state ("No SQL Server workloads found")
    - Handle error states (403, 402, 500)
    - _Requirements: Component 5, Frontend examples_

  - [ ] 5.2 Implement comparison table rendering in `members/members.js`
    - Display per-workload rows with instance details (ID, type, vCPUs, memory, region, edition)
    - Show 4 option columns with monthly cost for each
    - Highlight cheapest option with visual badge
    - Show savings vs current (amount and percentage) for each option
    - Display "Migrate" button for options cheaper than current
    - _Requirements: Component 5, API Contract response format_

  - [ ] 5.3 Implement migration plan panel in `members/members.js`
    - On "Migrate" button click, call POST /members/sql/migration-plan
    - Render plan header with title, complexity badge, duration estimate, and savings
    - Display numbered steps list with step type indicators
    - Show AWS Console deep links as clickable buttons where available
    - Display risks and prerequisites sections
    - _Requirements: Component 5, Migration Plan API Contract_

  - [ ] 5.4 Add styles for SQL Platform Comparator in `members/members.css`
    - Style comparison table with responsive layout
    - Style cheapest option badge (green highlight)
    - Style savings indicators (green for positive, red for negative)
    - Style migration plan panel with step cards
    - Style complexity badges (low=green, medium=yellow, high=red)
    - _Requirements: Files to Modify section_

  - [ ] 5.5 Bump asset versions in `members/index.html`
    - Update `members.js?v=XX` version number
    - Update `members.css?v=XX` version number
    - _Requirements: Files to Modify section_

- [ ] 6. Final Checkpoint — Full integration verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements from the design document for traceability
- Checkpoints ensure incremental validation of backend before frontend work
- Property tests validate universal correctness properties from the design
- Unit tests validate specific examples and edge cases
- The implementation language is Python (backend) and vanilla JavaScript (frontend), matching the existing codebase
- Migration templates cover 7 valid source→target pairs (excluding same-to-same and EC2 BYOL as source)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1"] },
    { "id": 2, "tasks": ["1.4", "2.2"] },
    { "id": 3, "tasks": ["1.5", "1.8", "2.3"] },
    { "id": 4, "tasks": ["1.6", "1.7", "2.4", "2.5", "4.1"] },
    { "id": 5, "tasks": ["4.2"] },
    { "id": 6, "tasks": ["5.1", "5.4"] },
    { "id": 7, "tasks": ["5.2"] },
    { "id": 8, "tasks": ["5.3", "5.5"] }
  ]
}
```
