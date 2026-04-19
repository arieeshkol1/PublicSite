# Implementation Plan: FinOps Settings Healthcheck

## Overview

This plan implements a FinOps Settings audit feature across four layers: backend healthcheck scan/fix endpoints in `member-handler/lambda_function.py`, frontend UI in the Configure tab with dashboard and Act tab integrations, cross-account role template permission updates, and knowledge base / AI chat awareness. Python scripts are used for modifications to the large `member-handler/lambda_function.py` and `members/members.js` files.

## Tasks

- [ ] 1. Backend — Account type detection and check function scaffolding
  - [x] 1.1 Create a Python script `_add_healthcheck_backend.py` that adds the `_detect_account_type(org_client, account_id)` helper function to `member-handler/lambda_function.py`. The function calls `organizations:DescribeOrganization`, compares `MasterAccountId` with `account_id`, returns `('management', None)` if they match, `('linked', None)` if they differ, and `('linked', 'Organization data unavailable')` on `AccessDeniedException` or `('linked', 'Account is not part of an AWS Organization')` on `AWSOrganizationsNotInUseException`.
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ] 1.2 In the same script, add the 12 individual check functions to `member-handler/lambda_function.py`. Each function takes the appropriate boto3 client(s) and returns a checklist item dict with `id`, `name`, `status`, `description`, `guidance`, `fixAction`, `fixLabel`, and `details`:
    - `_check_cost_allocation_tags(ce_client)` — calls `ce:ListCostAllocationTags(Type=UserDefined)`, returns pass/warning/fail based on active tag count
    - `_check_aws_generated_tags(ce_client)` — calls `ce:ListCostAllocationTags(Type=AWSGenerated)`, checks `aws:createdBy` status
    - `_check_anomaly_detection(ce_client)` — calls `ce:GetAnomalyMonitors`, pass if ≥1 monitor exists
    - `_check_hourly_granularity(ce_client)` — probes `ce:GetCostAndUsage` with HOURLY granularity
    - `_check_ce_preferences(ce_client)` — calls `ce:GetPreferences`, checks RightsizingRecommendations
    - `_check_cur_reports(cur_client)` — calls `cur:DescribeReportDefinitions`, pass if ≥1 report
    - `_check_tag_backfill(ce_client)` — calls `ce:ListCostAllocationTagBackfillHistory`, pass/warning/fail based on completion state
    - `_check_linked_billing_access(org_client)` — checks organization settings for linked account billing access
    - `_check_budgets(budgets_client, account_id)` — calls `budgets:DescribeBudgets`, pass if ≥1 budget
    - `_check_tag_coverage(tagging_client)` — calls `tag:GetResources`, computes coverage %, pass >80%, warning 50-80%, fail <50%
    - `_check_compute_optimizer(co_client)` — calls `compute-optimizer:GetEnrollmentStatus`, pass if Active
    - `_check_tag_activation_status(ce_client)` — read-only `ce:ListCostAllocationTags` for linked accounts, warning on AccessDeniedException
    - _Requirements: 2.1–2.3, 3.1–3.2, 4.1–4.2, 5.1–5.3, 6.1–6.2, 7.1–7.2, 8.1–8.2, 9.1–9.2, 10.1–10.2, 11.1–11.3, 12.1–12.2, 13.1–13.2, 14.1–14.2, 15.1–15.3, 16.1–16.3_

  - [x] 1.3 Run the Python script to apply the changes to `member-handler/lambda_function.py`
    - _Requirements: 1.1–1.4, 2.1–2.3, 3.1–3.2, 4.1–4.2, 5.1–5.3, 6.1–6.2, 7.1–7.2, 8.1–8.2, 9.1–9.2, 10.1–10.2, 11.1–11.3, 12.1–12.2, 13.1–13.2, 14.1–14.2, 15.1–15.3, 16.1–16.3_

  - [ ]* 1.4 Write property test for account type classification
    - **Property 1: Account type classification is correct**
    - **Validates: Requirements 1.2, 1.3**

  - [ ]* 1.5 Write property tests for checklist item status classification
    - **Property 2: Checklist item status classification follows threshold rules**
    - **Validates: Requirements 2.3, 8.2, 11.3**

- [ ] 2. Backend — Scan endpoint (`POST /members/healthcheck/scan`)
  - [ ] 2.1 Create a Python script `_add_healthcheck_scan.py` that adds the `handle_healthcheck_scan(event)` function to `member-handler/lambda_function.py`. The function: validates JWT via `validate_token(event)`, parses `accountId` from body, validates 12-digit format, verifies account ownership via `_verify_account_ownership`, assumes cross-account role via `_assume_role_for_account`, detects account type, runs the appropriate checklist (9 checks for management, 6 for linked) with each check wrapped in try/except (failures produce `"error"` status), computes `settingsScore` as `{passed, total}`, stores results in DynamoDB under `healthcheckResults.{accountId}`, and returns the full response.
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 25.1, 25.2_

  - [ ] 2.2 In the same script, add the route `'POST /members/healthcheck/scan': handle_healthcheck_scan` to the `routes` dict in `lambda_handler()`
    - _Requirements: 18.1_

  - [x] 2.3 Run the Python script to apply the changes
    - _Requirements: 18.1–18.6, 25.1, 25.2_

  - [ ]* 2.4 Write property test for scan resilience
    - **Property 4: Scan resilience — individual check failures do not block other checks**
    - **Validates: Requirements 18.5**

  - [ ]* 2.5 Write property test for scan idempotence
    - **Property 5: Scan idempotence — same inputs produce same outputs**
    - **Validates: Requirements 18.6**

  - [ ]* 2.6 Write property test for result schema completeness
    - **Property 8: Scan result schema completeness**
    - **Validates: Requirements 18.3, 25.2**

- [ ] 3. Backend — Fix endpoint (`POST /members/healthcheck/fix`)
  - [ ] 3.1 Create a Python script `_add_healthcheck_fix.py` that adds the `handle_healthcheck_fix(event)` function to `member-handler/lambda_function.py`. The function: validates JWT, parses `accountId`, `fixAction`, and optional `params` from body, verifies account ownership, assumes cross-account role, detects account type (reuses cached result from DynamoDB if available), validates that `fixAction` is applicable to the detected account type, executes the corresponding AWS API call (`activate_user_tags`, `activate_aws_tags`, `create_anomaly_monitor`, `enable_rightsizing`, `start_tag_backfill`, `enroll_compute_optimizer`), updates the specific checklist item in DynamoDB `healthcheckResults.{accountId}`, and returns the updated item.
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 25.3_

  - [ ] 3.2 In the same script, add the route `'POST /members/healthcheck/fix': handle_healthcheck_fix` to the `routes` dict
    - _Requirements: 19.1_

  - [x] 3.3 Run the Python script to apply the changes
    - _Requirements: 19.1–19.6, 25.3_

  - [ ]* 3.4 Write property test for fix action account type validation
    - **Property 6: Fix action account type validation**
    - **Validates: Requirements 19.6**

  - [ ]* 3.5 Write property test for score computation and color coding
    - **Property 3: Score computation and color coding are consistent**
    - **Validates: Requirements 17.3, 23.2**

- [x] 4. Checkpoint — Backend core complete
  - Ensure all backend functions are syntactically correct and the Lambda handler routes are wired. Ask the user if questions arise.

- [ ] 5. Infrastructure — Cross-account role template and API Gateway routes
  - [ ] 5.1 Create a Python script `_update_cf_template.py` that modifies the `handle_generate_template` function in `member-handler/lambda_function.py` to add the new IAM permissions to the `SlashMyBillBillingAccess` policy: `ce:GetAnomalyMonitors`, `ce:GetAnomalySubscriptions`, `ce:ListCostAllocationTagBackfillHistory`, `compute-optimizer:GetEnrollmentStatus`, `organizations:DescribeOrganization`, `ce:UpdateCostAllocationTagsStatus`, `ce:CreateAnomalyMonitor`, `ce:CreateAnomalySubscription`, `ce:StartCostAllocationTagBackfill`, `compute-optimizer:UpdateEnrollmentStatus`. Ensure all existing permissions are preserved.
    - _Requirements: 20.1, 20.2, 20.3_

  - [x] 5.2 Run the Python script to apply the template changes
    - _Requirements: 20.1–20.3_

  - [ ]* 5.3 Write property test for CloudFormation template permissions superset
    - **Property 7: CloudFormation template permissions are a superset of existing permissions**
    - **Validates: Requirements 20.2, 20.3**

  - [x] 5.4 Add API Gateway routes for `POST /members/healthcheck/scan` and `POST /members/healthcheck/fix` to `infrastructure/viewmybill-stack.yaml`, targeting the existing `MemberIntegration`, following the same pattern as existing member routes
    - _Requirements: 18.1, 19.1_

- [-] 6. Frontend — Configure tab left-nav and FinOps Settings section
  - [ ] 6.1 Create a Python script `_add_finops_settings_ui.py` that modifies `members/members.js` to add the FinOps Settings UI. Add a `switchToFinOpsSettings()` function that activates the Configure tab and shows the FinOps Settings sub-section. Add a left-nav to the Configure tab with "AWS Accounts" and "FinOps Settings" buttons. Add the FinOps Settings content area with: account selector dropdown (populated from connected accounts), score display bar with color coding (green ≥80%, amber 50-79%, red <50%), account type badge, checklist items container, and "Scan Settings" button.
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 1.5_

  - [ ] 6.2 In the same script, add `scanFinOpsSettings(accountId)` function that calls `POST /members/healthcheck/scan`, displays loading state during scan, and renders the checklist items with status icons (✅/⚠️/❌), names, descriptions, guidance text, and fix buttons where applicable. Add `fixFinOpsSetting(accountId, fixAction, params)` function that calls `POST /members/healthcheck/fix`, shows loading on the individual item, updates the item status on success, and recalculates the score without a full rescan.
    - _Requirements: 2.4, 2.5, 3.3, 3.4, 4.3, 4.4, 4.5, 4.6, 6.3, 6.4, 8.3, 8.4, 8.5, 13.3, 13.4, 14.3, 14.4, 17.4, 17.5, 17.6, 17.7_

  - [ ] 6.3 In the same script, add CSS styles to `members/members.css` for the Configure tab left-nav layout, FinOps Settings section, score bar, checklist items, status icons, fix buttons, loading states, and error banners. Follow the existing dark theme styling patterns.
    - _Requirements: 17.1, 17.3, 17.4, 17.7_

  - [ ] 6.4 Run the Python script to apply all frontend changes
    - _Requirements: 17.1–17.7_

  - [ ] 6.5 Add the notification banner for members whose accounts were connected before this update, advising them to update their CloudFormation stack to enable fix actions. Show this when a fix action returns a 403 permission error.
    - _Requirements: 20.4_

- [ ] 7. Frontend — Observe dashboard KPI card and Act tab integration
  - [ ] 7.1 Create a Python script `_add_finops_dashboard.py` that modifies `members/members.js` to add a "FinOps Score" KPI card to the `dash-kpi-bar` div. The card shows the settings score (e.g., "7/9") with color coding (green ≥80%, amber 50-79%, red <50%), and clicking it navigates to Configure → FinOps Settings via `switchToFinOpsSettings()`. If no scan results exist, show "Not scanned" with a "Scan →" link. Load data from `healthcheckResults` in the member's DynamoDB record (included in dashboard data response).
    - _Requirements: 23.1, 23.2, 23.3, 23.4_

  - [ ] 7.2 In the same script, add Act tab integration: when the waste scan runs, check for cached healthcheck results (within 24 hours). If failing items exist, inject a "⚙️ FinOps Settings" summary card into `act-cards-grid` showing the count of failing settings, the score, the top 3 failing items, and a "Fix in Settings →" button. If no scan exists, show "Run a FinOps Settings scan in Configure → FinOps Settings".
    - _Requirements: 24.1, 24.2, 24.3, 24.4, 24.5_

  - [ ] 7.3 Run the Python script to apply the changes
    - _Requirements: 23.1–23.4, 24.1–24.5_

- [x] 8. Checkpoint — Frontend complete
  - Ensure all frontend changes are syntactically correct and the Configure tab left-nav, FinOps Settings section, dashboard KPI card, and Act tab card are wired. Ask the user if questions arise.

- [ ] 9. Backend — Dashboard data and AI chat integration
  - [ ] 9.1 Create a Python script `_add_healthcheck_integrations.py` that modifies `member-handler/lambda_function.py` to include `healthcheckResults` in the response of `handle_dashboard_data()` so the frontend can render the FinOps Score KPI card and Act tab card from cached data.
    - _Requirements: 25.4, 23.1_

  - [ ] 9.2 In the same script, update the AI data-gathering pipeline (in `handle_ai_query` or the relevant data assembly function) to include the latest `healthcheckResults` from the member's DynamoDB record when building the AI context.
    - _Requirements: 22.1_

  - [ ] 9.3 In the same script, update the Bedrock prompt's `SLASHMYBILL PLATFORM FEATURES` section to include "Configure → FinOps Settings: Check and fix AWS billing best practices (cost allocation tags, anomaly detection, rightsizing, hourly granularity)".
    - _Requirements: 22.5_

  - [ ] 9.4 Run the Python script to apply the changes
    - _Requirements: 22.1, 22.5, 25.4_

- [ ] 10. Knowledge base — FinOps settings tips
  - [ ] 10.1 Add new tips to `knowledge-base/aws-cost-optimization-tips.json` with category `finops-settings`, service `General`, `implementedInHealthcheck: true`, `actionType: deep-link`, `actionTarget: configure:finops-settings`. Add one tip per healthcheck item (cost allocation tags, AWS-generated tags, anomaly detection, hourly granularity, CE preferences, CUR reports, tag backfill, linked billing access, budgets, tag coverage, compute optimizer, tag activation status). Each tip includes `automatedCheck`, `accountTypeScope` (management/linked/both), and `actionLabel`.
    - _Requirements: 21.1, 21.2, 21.3, 21.4_

  - [ ] 10.2 Update `knowledge-base/seed-dynamodb.py` to include the new healthcheck tips when seeding the DynamoDB table
    - _Requirements: 21.5_

- [x] 11. Checkpoint — All integrations wired
  - Ensure all backend integrations (dashboard data, AI chat, knowledge base) are complete and consistent. Ask the user if questions arise.

- [ ] 12. Final wiring and error handling
  - [ ] 12.1 Verify that the scan endpoint handles all error cases per the design: STS `AccessDeniedException` returns 403, `ExpiredTokenException` retries once then 403, role not found returns 403. Verify fix endpoint returns 400 for unknown fixAction, 400 for wrong account type, 400 for missing params, 403 for permission denied, 429 for throttling, 500 for AWS API errors.
    - _Requirements: 18.4, 18.5, 19.5, 19.6_

  - [ ] 12.2 Verify that the frontend handles scan errors (error banner with retry), fix errors (inline error on checklist item), network errors (toast), and auth errors (redirect to login).
    - _Requirements: 17.7, 2.5, 4.6, 8.5_

  - [ ] 12.3 Add guidance text and deep-links for manual-only checklist items: hourly granularity (manual in AWS console), CUR reports (manual setup), linked billing access (manual in Organizations console), budgets (link to Plan → Budget), tag coverage (link to Plan → Tag Resources), tag activation status (guidance to ask management admin).
    - _Requirements: 5.4, 7.3, 7.4, 9.3, 10.3, 10.4, 11.4, 12.3, 15.4, 16.4_

- [x] 13. Final checkpoint — Ensure all tests pass
  - Ensure all code changes are syntactically correct, all routes are wired, all integrations are connected, and all property tests pass. Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Python scripts are used for modifications to `member-handler/lambda_function.py` and `members/members.js` due to their large file sizes
- All property tests should be placed in `member-handler/tests/test_healthcheck.py` using `pytest` with `hypothesis`
- Deploy by pushing to main branch; API Gateway ID: l2fd4h481h
