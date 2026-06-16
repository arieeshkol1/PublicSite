# Implementation Plan: OpenAI Forecast & Daily Token Usage

## Overview

Two-part delivery: (1) commit and push the already-implemented `_answer_openai_forecast` function to trigger production deploy via GitHub Actions; (2) build the per-user daily token usage enrichment pipeline — a new `fetch_per_user_daily_usage` method on the AI Vendor Connector, a new `_enrich_daily_token_usage` writer in `provider_invoices.py`, and wiring into the existing `generate_openai_service_breakdown` flow. Python backend across two Lambda packages (`member-handler`, `agent-action`), with shared connector access via layer.

## Tasks

- [x] 1. Commit and push the forecast function to production
  - [x] 1.1 Commit `_answer_openai_forecast` and push to main
    - Stage `member-handler/lambda_function.py` containing the forecast function (line ~7961)
    - Commit with message: "feat: add OpenAI forecast chat function"
    - Push to `main` branch (triggers GitHub Actions production deploy)
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3_

- [ ] 2. Implement `fetch_per_user_daily_usage` on AIVendorConnector
  - [x] 2.1 Add `fetch_per_user_daily_usage` method to `agent-action/connectors/ai_vendor_connector.py`
    - Add method to `AIVendorConnector` class
    - Accept params: `api_key`, `organization_id`, `start_date` (YYYY-MM-DD), `end_date` (YYYY-MM-DD)
    - Convert date strings to Unix timestamps (midnight UTC) for `start_time`/`end_time` params
    - Build endpoint: `/v1/organization/usage/completions?group_by=user_id&group_by=model&bucket_width=1d&start_time={ts}&end_time={ts}`
    - Reuse existing `_make_openai_request` for authenticated GET requests
    - Handle pagination: follow `next_page` token while `has_more=true`, cap at 100 pages with warning log
    - Parse each bucket: convert `start_time` epoch back to `YYYY-MM-DD` date string
    - Flatten `results` array into records: `{date, user_id, model, input_tokens, output_tokens, input_cached_tokens, num_model_requests}`
    - Default missing/null token fields to 0; ensure all numeric fields are non-negative integers
    - Return `[]` on PermissionError (401/403) or RuntimeError (5xx/network) — never raise
    - On 5xx mid-pagination: return records collected so far
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.4, 8.1, 8.2, 8.3, 8.4, 8.5, 10.1, 10.2, 10.3, 10.4_

  - [ ]* 2.2 Write property test for date-to-timestamp round-trip (Property 3)
    - **Property 3: Date-to-timestamp round-trip**
    - *For any* valid ISO date string (YYYY-MM-DD), converting to a Unix timestamp (midnight UTC) and converting back SHALL produce the original date string
    - Use `hypothesis` with `st.dates()` strategy
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [ ]* 2.3 Write property test for pagination completeness (Property 4)
    - **Property 4: Pagination completeness**
    - *For any* sequence of paginated API responses where each page has `has_more=true` except the last, the fetcher SHALL return the union of all records from all pages with no omissions
    - Mock `_make_openai_request` to return generated pages; verify record count matches sum of all page results
    - **Validates: Requirements 5.3, 5.5**

  - [ ]* 2.4 Write property test for token count non-negativity (Property 5)
    - **Property 5: Token counts are non-negative integers**
    - *For any* parsed usage record, all numeric fields (`input_tokens`, `output_tokens`, `input_cached_tokens`, `num_model_requests`) SHALL be non-negative integers
    - Generate responses with missing, null, negative, and float values; verify output always contains non-negative ints
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

  - [ ]* 2.5 Write property test for returned dates within range (Property 11)
    - **Property 11: Returned dates within requested range**
    - *For any* usage fetch with given start_date and end_date, all `date` values in returned records SHALL satisfy `start_date <= date < end_date`
    - **Validates: Requirements 6.4**

- [ ] 3. Checkpoint - Verify connector method
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement `_enrich_daily_token_usage` in provider_invoices.py
  - [x] 4.1 Add `_enrich_daily_token_usage` function to `member-handler/provider_invoices.py`
    - Accept params: `member_email`, `account_id`, `api_key`, `organization_id`, `period` (YYYY-MM)
    - Parse period to compute `start_date` (first of month) and `end_date` (first of next month)
    - Instantiate `AIVendorConnector` and call `fetch_per_user_daily_usage(api_key, organization_id, start_date, end_date)`
    - If fetcher returns empty list, return 0 immediately (no DynamoDB writes)
    - Batch-write records to `MemberPortal-Invoices` table using `batch_writer()`
    - Each item: `pk={member_email}#{account_id}`, `sk=DAILY#{date}#{user_id}#{model}`
    - Include fields: `input_tokens`, `output_tokens`, `input_cached_tokens`, `num_model_requests`, `date`, `user_id`, `model`, `account_id`
    - Set `ttl` = `int(time.time()) + 2_592_000` (30 days)
    - Return count of records written
    - Wrap entire function body in try/except: on ANY exception, log warning and return 0 (never raises)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 9.1, 9.2, 9.3_

  - [ ]* 4.2 Write property test for DynamoDB key pattern correctness (Property 6)
    - **Property 6: DynamoDB key pattern correctness**
    - *For any* usage record written, pk SHALL match `{email}#{account_id}` and sk SHALL match regex `^DAILY#\d{4}-\d{2}-\d{2}#.+#.+$`
    - Generate random emails, account_ids, dates, user_ids, models; verify key format
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 4.3 Write property test for TTL correctness (Property 7)
    - **Property 7: TTL is 30 days from write time**
    - *For any* record written, `ttl` SHALL be within `[now + 2_592_000 - 1, now + 2_592_000 + 1]`
    - **Validates: Requirements 7.4**

  - [ ]* 4.4 Write property test for enrichment idempotence (Property 8)
    - **Property 8: Enrichment idempotence**
    - *For any* set of usage records, running the writer twice with the same input SHALL produce identical DynamoDB state
    - Mock DynamoDB table; verify second run doesn't change record count or values
    - **Validates: Requirements 7.5**

  - [ ]* 4.5 Write property test for enrichment never raises (Property 9)
    - **Property 9: Enrichment never raises**
    - *For any* exception during execution (API failures, DynamoDB errors, malformed data), the function SHALL return an integer (0) without propagating
    - Inject random exceptions at each failure point; verify function returns 0
    - **Validates: Requirements 9.2, 4.3**

- [ ] 5. Wire enrichment into `generate_openai_service_breakdown`
  - [x] 5.1 Call `_enrich_daily_token_usage` after breakdown completes
    - In `generate_openai_service_breakdown`, after the existing breakdown logic produces `rows`
    - Extract `api_key` and `organization_id` from `auth_context` / `credentials`
    - Call `_enrich_daily_token_usage(member_email, account_id, api_key, organization_id, period)`
    - Wrap in try/except so enrichment failure never affects the breakdown return value
    - Log enrichment result count at debug level
    - _Requirements: 9.1, 9.2, 9.4_

- [ ] 6. Final checkpoint - Verify end-to-end integration
  - Ensure all tests pass, ask the user if questions arise.

  - [ ]* 6.1 Write property test for forecast formula correctness (Property 1)
    - **Property 1: Forecast formula correctness**
    - *For any* valid MTD cost (≥0), previous month total (≥0), days_in_prev (>0), day_of_month (1..N), days_in_month (≥ day_of_month), projected SHALL equal `MTD + ((days_in_month - day_of_month) × (prev_total / days_in_prev))` rounded to 2 decimal places
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.6**

  - [ ]* 6.2 Write property test for forecast monotonically above MTD (Property 2)
    - **Property 2: Forecast projection is monotonically above MTD**
    - *For any* non-negative MTD cost and non-negative previous month daily average, projected >= MTD
    - **Validates: Requirements 2.5**

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each major phase
- Property tests validate the correctness properties from the design document using `hypothesis`
- Python is the implementation language for all backend code
- The connector lives in `agent-action/` but `provider_invoices.py` is in `member-handler/` — the enrichment writer instantiates the connector directly (both lambdas share the connectors package via layer)
- Push to `main` triggers production deploy via GitHub Actions
- Task 1 is a standalone git operation; Tasks 2–5 form the enrichment pipeline

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5"] },
    { "id": 3, "tasks": ["4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "4.4", "4.5"] },
    { "id": 5, "tasks": ["5.1"] },
    { "id": 6, "tasks": ["6.1", "6.2"] }
  ]
}
```
