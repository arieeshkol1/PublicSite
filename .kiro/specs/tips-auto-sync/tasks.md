# Implementation Plan: Tips Auto-Sync

## Overview

This plan implements a scheduled Lambda function (`Tips_Sync_Lambda`) that automatically fetches cost optimization tips from AWS FinOps sources (Cost Optimization Hub and Trusted Advisor cost_optimizing category) and syncs deltas to the `ViewMyBill-CostOptimizationTips` DynamoDB table. The implementation is structured as a new `tips-sync/` directory containing the Lambda code, with CI/CD integration into the existing deploy pipeline.

## Tasks

- [x] 1. Set up project structure and data models
  - [x] 1.1 Create the `tips-sync/` directory structure with `lambda_function.py`, `sources/__init__.py`, `sources/cost_optimization_hub.py`, `sources/trusted_advisor.py`, `sources/baseline_file.py`, `sync_engine.py`, `models.py`, `metrics.py`, and `tests/` directory. Include a `requirements.txt` with `boto3` (for local dev only, available in Lambda runtime).
    - _Requirements: 9.1_

  - [x] 1.2 Implement `tips-sync/models.py` with the `TipRecord` dataclass containing all required fields (`id`, `service`, `category`, `title`, `description`, `estimatedSavings`, `difficulty`, `automatedCheck`) plus sync fields (`contentHash`, `syncSource`, `lastSyncedAt`, `version`). Implement `compute_content_hash(title, description, estimatedSavings, automatedCheck)` using SHA-256. Implement `generate_tip_id(service, existing_ids)` that produces `{service_lowercase}-{sequential_number}` ensuring uniqueness.
    - _Requirements: 3.1, 4.1, 4.3_

  - [ ]* 1.3 Write property test for content hash determinism and sensitivity
    - **Property 1: Content hash determinism and sensitivity**
    - **Validates: Requirements 3.1**

  - [ ]* 1.4 Write property test for ID generation pattern and uniqueness
    - **Property 7: ID generation pattern and uniqueness**
    - **Validates: Requirements 4.3**

- [x] 2. Implement AWS source fetchers
  - [x] 2.1 Implement `tips-sync/sources/cost_optimization_hub.py` with `fetch_recommendations(client)` that calls `cost-optimization-hub:ListRecommendations` with pagination, normalizes each recommendation into a tip dict (mapping `source` → `service`, `recommendationType` → `category`, `estimatedMonthlySavings` → `estimatedSavings`), and sets default operational fields (`checkImplemented=False`, `actionType="advisory"`, `actionLabel="View Details"`, `level=3`). Handle API errors gracefully by logging and returning an empty list.
    - _Requirements: 2.1, 2.3, 4.1, 4.2_

  - [x] 2.2 Implement `tips-sync/sources/trusted_advisor.py` with `fetch_cost_checks(support_client)` that calls `support:DescribeTrustedAdvisorChecks` filtered to `cost_optimizing` category, then fetches results for each check via `support:DescribeTrustedAdvisorCheckResult`. Normalize each check into a tip dict (mapping `name` → `title`, `description` → `description`, extracting `estimatedMonthlySavings` from results). Set default operational fields. Handle API errors gracefully.
    - _Requirements: 2.2, 2.3, 4.1, 4.2_

  - [x] 2.3 Implement `tips-sync/sources/baseline_file.py` with `load_baseline_tips(file_path)` that reads the bundled `aws-cost-optimization-tips.json` file, parses it, and returns the list of tip dicts. On file-not-found or JSON parse error, log a warning and return an empty list.
    - _Requirements: 6.1, 6.3_

  - [ ]* 2.4 Write property test for schema compliance with defaults for new AWS-sourced tips
    - **Property 6: Schema compliance with defaults for new AWS-sourced tips**
    - **Validates: Requirements 4.1, 4.2**

- [x] 3. Implement sync engine (merge, delta detection, batch write)
  - [x] 3.1 Implement `tips-sync/sync_engine.py` — `merge_sources(baseline, coh, ta)` that merges tips from all sources with baseline file taking priority for duplicate IDs. Implement `compute_deltas(merged_tips, existing_tips)` that compares content hashes and classifies each tip as insert, update, or unchanged. Implement `apply_deltas(table, inserts, updates)` that writes to DynamoDB using conditional puts with version attribute, processing in batches of max 25 items, with exponential backoff retry for throttling errors.
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 6.2, 7.1, 7.2, 7.3_

  - [ ]* 3.2 Write property test for new tips classified as inserts
    - **Property 2: New tips are classified as inserts**
    - **Validates: Requirements 3.2**

  - [ ]* 3.3 Write property test for updates preserving operational fields
    - **Property 3: Updates preserve operational fields**
    - **Validates: Requirements 3.3**

  - [ ]* 3.4 Write property test for unchanged tips being skipped
    - **Property 4: Unchanged tips are skipped**
    - **Validates: Requirements 3.4**

  - [ ]* 3.5 Write property test for no-delete invariant
    - **Property 5: No-delete invariant**
    - **Validates: Requirements 3.5**

  - [ ]* 3.6 Write property test for source merge priority
    - **Property 8: Source merge priority**
    - **Validates: Requirements 6.2**

  - [ ]* 3.7 Write property test for batch size constraint
    - **Property 9: Batch size constraint**
    - **Validates: Requirements 7.3**

- [x] 4. Checkpoint — Core sync logic complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Lambda handler with concurrency guard and metrics
  - [x] 5.1 Implement `tips-sync/metrics.py` with `publish_success_metrics(duration_ms)`, `publish_failure_metric()`, and helper to publish to the `SlashMyBill/TipsSync` CloudWatch namespace using `cloudwatch:PutMetricData`.
    - _Requirements: 5.2, 5.4_

  - [x] 5.2 Implement `tips-sync/lambda_function.py` — the `lambda_handler(event, context)` entry point that: (1) detects trigger type (scheduled vs manual from `{"manual": true}`), (2) acquires SYNC_LOCK via DynamoDB conditional put with 15-min TTL, (3) on lock failure logs and exits gracefully, (4) fetches from all sources (COH, TA, baseline file) with graceful degradation if a source fails, (5) merges and computes deltas, (6) applies deltas, (7) writes SYNC_METADATA record with all stats, (8) releases lock, (9) publishes CloudWatch metrics. Uses structured JSON logging at INFO level for all operations.
    - _Requirements: 1.2, 1.3, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5, 5.1, 5.2, 5.3, 5.4, 10.1, 10.2_

  - [ ]* 5.3 Write unit tests for concurrent execution exit, source failure continuation, sync metadata writing, and manual trigger handling
    - Test `test_concurrent_execution_exits_gracefully` — validates Req 1.3
    - Test `test_source_failure_continues_with_remaining` — validates Req 2.3
    - Test `test_sync_metadata_written_on_completion` — validates Req 5.1
    - Test `test_manual_trigger_executes_full_sync` — validates Req 10.1
    - Test `test_manual_trigger_metadata_type` — validates Req 10.2
    - _Requirements: 1.3, 2.3, 5.1, 10.1, 10.2_

- [x] 6. Checkpoint — Lambda handler complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. CI/CD and infrastructure integration
  - [x] 7.1 Add `'tips-sync/**'` to the trigger paths in `.github/workflows/deploy.yml`. Add a new "Package Tips Sync Lambda" step that installs dependencies from `tips-sync/requirements.txt` into `.build-tips-sync/`, copies all Python source files, zips the package, and uploads to `s3://${STORAGE_BUCKET}/lambda-packages/tips-sync.zip`. Add a step to update the Lambda function code for `slashmybill-tips-sync`.
    - _Requirements: 9.1, 9.3_

  - [x] 7.2 Add a deploy step in `.github/workflows/deploy.yml` that creates the EventBridge Scheduler rule `slashmybill-tips-sync-daily` with schedule `cron(0 2 * * ? *)` targeting the Tips Sync Lambda ARN, if it does not already exist. Include the IAM role creation for the scheduler to invoke the Lambda.
    - _Requirements: 1.1, 9.2_

  - [x] 7.3 Add a deploy step that creates the `slashmybill-tips-sync` Lambda function if it doesn't exist, with the IAM execution role containing: DynamoDB read/write on `ViewMyBill-CostOptimizationTips`, `support:DescribeTrustedAdvisorChecks`, `support:DescribeTrustedAdvisorCheckResult`, `cost-optimization-hub:ListRecommendations`, `cost-optimization-hub:GetRecommendation`, `cloudwatch:PutMetricData`, and CloudWatch Logs permissions. Set runtime to Python 3.12, timeout 300s, memory 256MB.
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 7.4 Bundle the `knowledge-base/aws-cost-optimization-tips.json` file into the Lambda deployment package so it's available at runtime as the Tips_Source_File.
    - _Requirements: 6.1_

- [x] 8. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- All property tests should be placed in `tips-sync/tests/test_properties.py` using `pytest` with `hypothesis`
- Unit tests should be placed in `tips-sync/tests/test_unit.py`
- The Lambda function name is `slashmybill-tips-sync` in the Platform_Account (991105135552, us-east-1)
- The DynamoDB table is `ViewMyBill-CostOptimizationTips` with PK `service` and SK `tipId`
- Deploy by pushing to main branch with changes in `tips-sync/` directory

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "1.4", "2.1", "2.2", "2.3"] },
    { "id": 3, "tasks": ["2.4", "3.1"] },
    { "id": 4, "tasks": ["3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "5.1"] },
    { "id": 5, "tasks": ["5.2"] },
    { "id": 6, "tasks": ["5.3", "7.1", "7.2", "7.3", "7.4"] }
  ]
}
```
