# Implementation Plan: Audit Transaction Log

## Overview

Implement a comprehensive audit transaction logging system for the SlashMyCloudBill platform. The implementation covers: a Python decorator for automatic transaction capture, a DynamoDB table with GSIs and Streams, an audit evaluator Lambda powered by Bedrock Claude Opus, new admin-handler API routes, and a Transactions tab in the Admin panel frontend. Property-based tests using Hypothesis validate all 9 correctness properties.

## Tasks

- [x] 1. Create Transaction Logger module and DynamoDB table infrastructure
  - [x] 1.1 Create the `transaction_logger.py` shared module
    - Create `transaction_logger.py` in the project root (shared between handlers)
    - Implement `SENSITIVE_FIELDS` set with: password, token, jwt, secret, authorization, jwt_secret, password_hash, new_password, old_password
    - Implement `_sanitize(payload)` — deep-copy dict and recursively remove keys matching SENSITIVE_FIELDS at any nesting depth
    - Implement `_extract_user_email(event)` — extract email from JWT claims in headers or from request body, default to "unknown"
    - Implement `_extract_function_name(event)` — extract from `routeKey` field of the event
    - Implement `_persist_async(entry)` — write entry to DynamoDB `Audit_Transaction_Log` table, swallow all exceptions and log failures to CloudWatch
    - Implement `transaction_log(source_handler)` decorator factory that wraps handler functions: captures UUID v4 transaction_id, start/end timestamps, duration_ms, calls handler in try/except, builds entry dict, calls `_persist_async`, returns original handler response unchanged
    - Handle payload truncation: if request_payload or response_payload exceeds 100KB, truncate and add `_truncated: true` flag
    - Import and use: `functools`, `uuid`, `time`, `datetime`, `json`, `copy`, `logging`, `boto3`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.4, 7.1, 7.2, 7.3_

  - [x] 1.2 Add DynamoDB Transaction_Log_Table to CloudFormation stack
    - Add `TransactionLogTable` resource to `infrastructure/unified-stack.yaml` (or appropriate stack file)
    - Configure: TableName `Audit_Transaction_Log`, BillingMode PAY_PER_REQUEST
    - Key schema: `transaction_id` (HASH, String), `start_timestamp` (RANGE, String)
    - GSI `user-email-index`: partition key `user_email`, sort key `start_timestamp`, ProjectionType ALL
    - GSI `function-name-index`: partition key `function_name`, sort key `start_timestamp`, ProjectionType ALL
    - Enable TTL on `expiry_ttl` attribute
    - Enable DynamoDB Streams with StreamViewType `NEW_IMAGE`
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 1.3 Write property tests for transaction logger (Properties 1-5)
    - **Property 1: Transaction Entry Structural Completeness** — Generate random valid handler events, verify all required fields present and transaction_id is valid UUID v4
    - **Validates: Requirements 1.2, 1.4**
    - **Property 2: Error Status Capture** — Generate handlers that raise exceptions, verify status is "error" and response_payload contains exception message
    - **Validates: Requirements 1.3**
    - **Property 3: Decorator Transparency** — Generate handlers + mock DynamoDB failures, verify decorated function returns same value as undecorated
    - **Validates: Requirements 1.5, 7.1**
    - **Property 4: TTL Computation Correctness** — Generate timestamps, verify expiry_ttl equals start Unix timestamp + 7,776,000 seconds
    - **Validates: Requirements 2.4**
    - **Property 5: Sensitive Field Exclusion** — Generate payloads with sensitive fields at random nesting depths, verify none appear in sanitized output
    - **Validates: Requirements 7.3**
    - Create test file: `transaction_logger/tests/test_transaction_logger_props.py`
    - Use `hypothesis` with `@settings(max_examples=100)`
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 2.4, 7.1, 7.3_

- [x] 2. Integrate transaction logger into existing handlers
  - [x] 2.1 Apply `@transaction_log` decorator to `member-handler/lambda_function.py`
    - Import `transaction_log` from shared module
    - Wrap each handler function in the routes dict with `@transaction_log('member-handler')`
    - Ensure decorator is applied to handler functions (not lambda_handler itself) so route dispatch still works
    - Verify no change to existing handler behavior
    - _Requirements: 1.1, 7.1, 7.2_

  - [x] 2.2 Apply `@transaction_log` decorator to `admin-handler/lambda_function.py`
    - Import `transaction_log` from shared module
    - Wrap each handler function in the routes dict with `@transaction_log('admin-handler')`
    - Ensure decorator is applied to handler functions so route dispatch still works
    - Exclude the transaction log read endpoints themselves from decoration to avoid recursive logging
    - _Requirements: 1.1, 7.1, 7.2_

- [x] 3. Checkpoint - Verify transaction logging works
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement Audit Evaluator Lambda
  - [x] 4.1 Create `audit-evaluator/lambda_function.py`
    - Create `audit-evaluator/` directory and `lambda_function.py`
    - Implement `lambda_handler(event, context)` — process DynamoDB Stream records
    - Filter for `INSERT` events only
    - Implement `_unmarshall(image)` — convert DynamoDB Stream NewImage format to plain dict
    - Implement `_evaluate_with_bedrock(entry)` — invoke Bedrock Claude Opus (`us.anthropic.claude-opus-4-0-20250514`) with structured prompt containing function_name, duration_ms, request_payload, response_payload
    - Parse Bedrock response JSON: extract score (int 0-100), accuracy_assessment, timing_assessment, improvement_suggestions
    - Implement `_update_entry_with_evaluation(transaction_id, start_timestamp, evaluation)` — update the DynamoDB item with audit fields and set audit_status to "completed"
    - Implement retry logic: up to 3 retries with exponential backoff (2s, 4s, 8s) on Bedrock failures
    - On final failure: set audit_status to "failed" with error details
    - Handle malformed Bedrock JSON: parse what's available, null missing fields, mark as "failed"
    - Configure Lambda timeout at 60s in CloudFormation
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 4.2 Add Audit Evaluator Lambda to CloudFormation stack
    - Add Lambda function resource with Python 3.12 runtime
    - Configure DynamoDB Stream as event source (TransactionLogTable stream ARN)
    - Set batch size to 1, starting position LATEST
    - Add IAM role with permissions: DynamoDB read/write on Transaction_Log_Table, Bedrock InvokeModel
    - Set Lambda timeout to 60s
    - Add environment variables: TABLE_NAME, BEDROCK_MODEL_ID
    - _Requirements: 3.1_

  - [ ]* 4.3 Write property tests for audit evaluator (Properties 6-7)
    - **Property 6: Audit Evaluation Parsing** — Generate valid Bedrock JSON responses with score, accuracy_assessment, timing_assessment, improvement_suggestions; verify parser extracts all fields with score as int in [0, 100]
    - **Validates: Requirements 3.2**
    - **Property 7: Audit Prompt Completeness** — Generate Transaction_Entry dicts, verify the built prompt string contains function_name, duration_ms, request_payload, and response_payload values
    - **Validates: Requirements 3.3**
    - Create test file: `audit-evaluator/tests/test_audit_evaluator_props.py`
    - Use `hypothesis` with `@settings(max_examples=100)`
    - _Requirements: 3.2, 3.3_

- [x] 5. Implement Admin Handler transaction log routes
  - [x] 5.1 Add `handle_get_transactions` to `admin-handler/lambda_function.py`
    - Add route `'GET /admin/transactions': handle_get_transactions` to routes dict
    - Implement `handle_get_transactions(event)`:
      - Validate JWT token using existing `validate_token()` pattern
      - Parse query params: page, page_size (default 50), user_email, function_name, status, score_min, score_max, date_from, date_to, search
      - If `user_email` filter provided: query `user-email-index` GSI
      - If `function_name` filter provided: query `function-name-index` GSI
      - Otherwise: scan Transaction_Log_Table
      - Apply server-side filtering for status, score range, date range
      - Implement pagination with page/page_size
      - Return JSON with `transactions` array and `pagination` metadata (total_count, page, page_size, total_pages)
    - _Requirements: 4.1, 4.2, 4.4, 5.1, 5.2, 8.1, 8.2_

  - [x] 5.2 Add `handle_get_transaction_detail` to `admin-handler/lambda_function.py`
    - Add route `'GET /admin/transactions/detail': handle_get_transaction_detail` to routes dict
    - Implement `handle_get_transaction_detail(event)`:
      - Validate JWT token
      - Parse query params: `transaction_id`, `start_timestamp`
      - Get item from Transaction_Log_Table using partition key + sort key
      - Return full Transaction_Entry including all audit evaluation fields
      - Return 404 if not found
    - _Requirements: 4.3, 6.2, 8.1, 8.2_

  - [ ]* 5.3 Write property tests for filter logic (Properties 8-9)
    - **Property 8: Filter Correctness** — Generate sets of Transaction_Entries and random filter combinations (text search, date range, score range, status, source_handler); verify every result satisfies ALL active predicates and no qualifying entry is excluded
    - **Validates: Requirements 5.1, 5.2**
    - **Property 9: Score-to-Color Mapping** — Generate integer scores 0-100; verify color function returns "green" for ≥70, "yellow" for 40-69, "red" for ≤39
    - **Validates: Requirements 6.1**
    - Create test file: `admin-handler/tests/test_filter_props.py`
    - Use `hypothesis` with `@settings(max_examples=100)`
    - _Requirements: 5.1, 5.2, 6.1_

- [x] 6. Checkpoint - Verify backend API works end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Admin Frontend Transactions tab
  - [x] 7.1 Add Transactions tab button and content section to `admin/index.html`
    - Add `<button class="tab-btn" data-tab="transactions">Transactions</button>` to the tab nav
    - Add `<div id="transactions-tab" class="tab-content">` section with:
      - Search bar input (text filter)
      - Filter row: date range pickers (start/end), score range inputs (min/max), status dropdown (all/success/error), source_handler dropdown (all/member-handler/admin-handler)
      - Table element with sortable column headers: #, user_email, function_name, duration_ms, score, status, start_timestamp
      - Pagination controls (prev/next buttons, page indicator)
      - Detail modal markup for showing full entry + audit evaluation
    - _Requirements: 4.1, 4.2, 5.1, 5.2_

  - [x] 7.2 Add Transactions tab styles to `admin/admin.css`
    - Style the transactions table following existing table patterns
    - Style filter row with flexbox layout
    - Style score badge: green background for ≥70, yellow for 40-69, red for ≤39
    - Style "Pending" indicator badge
    - Style the detail modal (overlay, centered card, scrollable content)
    - Style pagination controls
    - Ensure responsive layout for smaller screens
    - _Requirements: 6.1, 6.3_

  - [x] 7.3 Implement Transactions tab JavaScript logic in `admin/admin.js`
    - Add `loadTransactions(page, filters)` function — calls `GET /admin/transactions` with query params
    - Add `loadTransactionDetail(transaction_id, start_timestamp)` function — calls `GET /admin/transactions/detail`
    - Implement `renderTransactionsTable(data)` — populates table rows with transaction data
    - Implement `getScoreBadgeColor(score)` — returns "green" for ≥70, "yellow" for 40-69, "red" for ≤39
    - Implement search input handler with debounce (300ms)
    - Implement filter change handlers for all filter controls
    - Implement row click handler to open detail modal
    - Implement pagination button handlers (next/prev page)
    - Implement tab activation handler following existing pattern
    - Implement `renderDetailModal(entry)` — shows full payloads formatted as JSON and audit evaluation fields
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document using Hypothesis
- Unit tests validate specific examples and edge cases
- The transaction_logger.py module is shared between member-handler and admin-handler via a common import path
- Frontend follows existing admin panel patterns: vanilla HTML/CSS/JS, tab navigation, table rendering
- DynamoDB Streams trigger is decoupled from the request path — audit evaluation happens asynchronously

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1", "2.2"] },
    { "id": 2, "tasks": ["4.1", "4.2"] },
    { "id": 3, "tasks": ["4.3", "5.1", "5.2"] },
    { "id": 4, "tasks": ["5.3", "7.1"] },
    { "id": 5, "tasks": ["7.2", "7.3"] }
  ]
}
```
