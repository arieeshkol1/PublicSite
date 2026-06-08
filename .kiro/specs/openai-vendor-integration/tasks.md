# Implementation Plan: OpenAI Vendor Integration

## Overview

Extends SlashMyBill to support OpenAI as an AI Vendor connection. Implementation proceeds: registry enhancement → OpenAI connector → credential storage → connection wizard API → nightly sync Lambda → usage dashboard API → frontend wizard + dashboard → optimization recommendations → tips seed script → infrastructure. Python backend (Lambda), JavaScript frontend (members.js), CloudFormation infrastructure.

## Tasks

- [x] 1. Enhance Provider Registry with vendor_type support
  - [x] 1.1 Refactor `connectors/__init__.py` to store vendor_type metadata
    - Change `_CONNECTORS` dict to store `{'class': ConnectorClass, 'vendor_type': str}` instead of just the class
    - Update `register_connector()` to accept optional `vendor_type` parameter (default: `'cloud_provider'`)
    - Update `get_connector()` to extract class from the new dict structure
    - Update `_load_connectors()` — existing AWS, Azure, GCP connectors register with `vendor_type='cloud_provider'`
    - Add `list_providers(vendor_type=None)` filtering — return only providers matching vendor_type if specified, else all
    - If a connector is registered without vendor_type, default to `'cloud_provider'`
    - _Requirements: 1.1, 1.4, 1.5, 1.6_

  - [ ]* 1.2 Write property test for registry vendor_type filtering (Property 1)
    - **Property 1: Registry vendor_type storage and filtering**
    - For any set of connector registrations with assigned vendor_type values, `list_providers(vendor_type=X)` returns exactly the set of provider names registered with vendor_type X
    - Connectors registered without explicit vendor_type must default to `cloud_provider`
    - **Validates: Requirements 1.1, 1.5, 1.6**

- [x] 2. Implement OpenAI Connector
  - [x] 2.1 Create `connectors/openai_connector.py` implementing ProviderConnector interface
    - Implement `OpenAIConnector` class extending `ProviderConnector`
    - `authenticate(credentials)`: decrypt API key via KMS `decrypt_credential()`, validate `sk-` prefix and 40–200 char length, return auth context with `api_key` and `org_name`
    - `test_connection(auth_context, account_id)`: call `GET /v1/models` with Bearer token, return success with models list or failure with error detail
    - `get_cost_data(auth_context, account_id, start_date, end_date)`: call OpenAI Usage API with date range, handle retries, return raw usage records
    - Register with `register_connector('openai', OpenAIConnector, vendor_type='ai_vendor')` at module level
    - Constants: `OPENAI_BASE_URL`, `REQUEST_TIMEOUT=30`, `MAX_RETRIES=3`
    - _Requirements: 1.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 14.1, 14.3, 14.4, 14.5, 14.6, 14.7_

  - [x] 2.2 Implement API key format validation in OpenAI connector
    - Accept keys starting with `sk-org-` or `sk-proj-` with total length 40–200 chars
    - Reject keys that don't match format without making external API call
    - Return structured error result indicating format is invalid
    - _Requirements: 2.3, 2.5, 3.1, 3.6_

  - [ ]* 2.3 Write property test for API key format validation (Property 2)
    - **Property 2: API key format validation**
    - For any string, validation must accept iff it starts with `sk-org-` or `sk-proj-` and has total length between 40 and 200 characters inclusive
    - Strings failing this check must be rejected without external API call
    - **Validates: Requirements 2.3, 2.5, 3.1, 3.6**

  - [x] 2.4 Implement retry logic with exponential backoff for OpenAI API calls
    - Handle HTTP 429 with `Retry-After` header: wait specified duration, retry up to 3 times
    - Handle HTTP 429 without `Retry-After`: exponential backoff starting at 1s, up to 3 attempts
    - Handle HTTP 5xx: retry up to 3 times with backoff
    - On HTTP 401: update connection status to `failed`, return key-revoked error
    - On other HTTP errors: return error with status code, don't change connection status
    - After exhausting retries: update connection status to `failed`, return unavailability error
    - _Requirements: 14.3, 14.4, 14.5, 14.6, 14.7_

  - [ ]* 2.5 Write property test for nightly sync retry with exponential backoff (Property 16)
    - **Property 16: Nightly sync retry with exponential backoff**
    - For any transient error (HTTP 429 or 5xx), system retries up to 3 times with 2s base exponential backoff (2s, 4s, 8s)
    - After exhausting retries, account sync marked as failed without affecting other accounts
    - **Validates: Requirements 13.6**

- [x] 3. Implement secure credential storage (KMS encryption)
  - [x] 3.1 Add KMS encrypt/decrypt integration for OpenAI API keys
    - Use existing `connectors/kms_helpers.py` `encrypt_credential()` and `decrypt_credential()` with encryption context containing member email and accountId
    - Store encrypted key in `credentials.encryptedApiKey` field in DynamoDB Accounts table
    - Never store plaintext key in any field or log output
    - Never cache decrypted value beyond request scope
    - Handle KMS encryption failure: do not persist record, return error
    - Handle KMS decryption failure: return "credentials inaccessible" error, never expose ciphertext
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 3.2 Write property test for encrypted credential storage (Property 3)
    - **Property 3: Encrypted credential storage**
    - For any valid API key stored via the connector, the DynamoDB record `credentials.encryptedApiKey` contains KMS-encrypted ciphertext
    - No field in stored record or log output may contain the plaintext key value
    - **Validates: Requirements 4.1, 4.2**

- [x] 4. Checkpoint - Verify registry and connector core
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement connection wizard backend API
  - [x] 5.1 Add `handle_add_openai()` route to member-handler Lambda
    - Add `POST /members/accounts/add-openai` route to `member-handler/lambda_function.py`
    - Accept JSON body: `{ "apiKey": "...", "connectionName": "..." (optional, max 64 chars) }`
    - Validate API key format (frontend validation already done, backend re-validates)
    - Call OpenAI `GET /v1/models` to verify key works
    - Encrypt API key via KMS with member email + accountId context
    - Store record in MemberPortal-Accounts with `cloudProvider='openai'`, `vendorType='ai_vendor'`, `connectionStatus='connected'`, `lastTestedAt` timestamp
    - Return success with connection details or error with failure reason
    - _Requirements: 1.2, 2.6, 2.7, 2.8, 5.1_

  - [x] 5.2 Add `handle_test_openai_connection()` route to member-handler Lambda
    - Add `POST /members/accounts/test-openai-connection` route
    - Accept JSON body: `{ "accountId": "..." }`
    - Decrypt stored API key, call OpenAI `GET /v1/models`
    - Update `connectionStatus` to `connected` or `failed` with `lastTestedAt` timestamp
    - On failure: store failure reason (max 200 chars) in record
    - _Requirements: 5.1, 5.2, 5.4_

  - [ ]* 5.3 Write property test for failure reason truncation (Property 4)
    - **Property 4: Failure reason truncation**
    - For any connection test failure reason string, the value stored and displayed must be at most 200 characters
    - **Validates: Requirements 5.2**

  - [x] 5.4 Add `handle_openai_usage()` route to member-handler Lambda
    - Add `POST /members/accounts/openai-usage` route
    - Accept JSON body: `{ "accountId": "...", "dateRange": 7|30|90 }`
    - Query Cost_Cache_Table with PK `{memberEmail}#{accountId}` and SK prefix `OPENAI_DAILY#`
    - If cache hit: aggregate and return usage data, cost-by-model, trends
    - If cache miss: decrypt key, call OpenAI Usage API, normalize, return data
    - Return within 10 seconds or return timeout error
    - _Requirements: 6.3, 6.5, 7.2, 8.1, 9.1_

- [x] 6. Implement cost normalizer and aggregation functions
  - [x] 6.1 Add `normalize_openai()` function to `cost_normalizer.py`
    - Transform OpenAI Usage API response into common cost schema: `{date, service_name, cost_amount, currency, cloud_provider, account_id, input_tokens, output_tokens}`
    - Parse Unix timestamps to ISO dates, extract model name as service_name
    - Handle per-project breakdowns if available in response
    - _Requirements: 14.2, 14.8_

  - [ ]* 6.2 Write property test for normalization round-trip (Property 17)
    - **Property 17: OpenAI usage data normalization round-trip**
    - For any valid OpenAI usage API response, normalizing then formatting back and re-normalizing produces equivalent records
    - **Validates: Requirements 14.2, 14.8**

  - [x] 6.3 Implement cost-by-model aggregation function
    - Group costs by model name, sort by cost descending, return top 20 models
    - Compute percentage of total spend for each model
    - Format costs to 2 decimal places, percentages to 1 decimal place
    - Percentages must sum to approximately 100% (within floating-point tolerance)
    - _Requirements: 7.1, 7.2, 7.4_

  - [ ]* 6.4 Write property test for cost-by-model aggregation (Property 5)
    - **Property 5: Cost-by-model aggregation**
    - For any set of usage records with model names/costs: groups by model, returns ≤20 sorted descending, percentages sum to ~100%
    - **Validates: Requirements 7.1, 7.2, 7.4**

  - [x] 6.5 Implement time bucket aggregation (daily/weekly/monthly)
    - Aggregate daily cost data into weekly buckets (7-day intervals starting Monday) or monthly buckets (calendar months)
    - Total spend must be preserved across aggregation levels
    - _Requirements: 8.2, 8.3_

  - [ ]* 6.6 Write property test for time bucket aggregation (Property 6)
    - **Property 6: Time bucket aggregation preserves total spend**
    - For any daily cost data series, aggregating into weekly or monthly buckets preserves total spend within floating-point tolerance
    - **Validates: Requirements 8.3**

  - [x] 6.7 Implement period-over-period percentage change calculation
    - Calculate `(current - previous) / previous × 100` rounded to 1 decimal place
    - Handle zero previous period: report as positive infinity or "new spend" sentinel
    - _Requirements: 8.4_

  - [ ]* 6.8 Write property test for period-over-period change (Property 7)
    - **Property 7: Period-over-period percentage change**
    - For any current/previous period totals (previous > 0), result equals `(current - previous) / previous × 100` rounded to 1 decimal place
    - **Validates: Requirements 8.4**

  - [x] 6.9 Implement project cost grouping with 50-entry cap
    - Group costs by project name/API key identifier
    - Sort by cost descending, return top 50
    - Include indicator if more than 50 entries exist
    - Display absolute cost (2 decimal places) and percentage of total (1 decimal place)
    - _Requirements: 9.1, 9.2, 9.5_

  - [ ]* 6.10 Write property test for project cost grouping (Property 8)
    - **Property 8: Project cost grouping and cap**
    - For any set of project usage records: groups by project, sorts descending, returns ≤50 entries, includes indicator if truncated
    - **Validates: Requirements 9.1, 9.2, 9.5**

- [x] 7. Checkpoint - Verify data processing layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement nightly sync Lambda
  - [x] 8.1 Create `openai-sync-handler/lambda_function.py`
    - Scan Accounts table for `cloudProvider='openai'`, `connectionStatus='connected'`
    - For each account: read `lastSyncedAt` (default: 90 days ago for first sync), decrypt API key, call OpenAI Usage API for incremental date range, normalize response, batch write to Cost_Cache_Table with `OPENAI_DAILY#` SK prefix, update `lastSyncedAt`
    - Handle per-account errors: retry 3x with 2s base exponential backoff for transient errors
    - On invalid key (401): update `connectionStatus='failed'`, skip account, continue others
    - On retry exhaustion: mark sync failed for account, continue others
    - Lambda timeout: 900 seconds, Memory: 256 MB
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8_

  - [ ]* 8.2 Write property test for incremental sync date range (Property 14)
    - **Property 14: Incremental sync date range**
    - For any account with stored `lastSyncedAt`, sync requests start_date = lastSyncedAt date, end_date = current date
    - For accounts without `lastSyncedAt`, start_date = 90 days before current date
    - **Validates: Requirements 13.2, 13.3**

  - [ ]* 8.3 Write property test for cache key format (Property 15)
    - **Property 15: Cache key format**
    - For any member email, account ID, and date, PK = `{memberEmail}#{accountId}` and SK = `OPENAI_DAILY#{date}` in YYYY-MM-DD format
    - **Validates: Requirements 13.4**

- [x] 9. Implement optimization recommendations engine
  - [x] 9.1 Create recommendation engine logic in member-handler
    - Analyze usage patterns from cached data to generate 0–10 recommendations
    - Order by estimated monthly savings descending
    - Each recommendation: title (max 80 chars), description (max 300 chars), estimated_monthly_savings (dollars, 2 decimal places), difficulty (easy/medium/hard)
    - _Requirements: 11.1, 11.4, 11.5_

  - [x] 9.2 Implement model-switch recommendation rule
    - Trigger when >50% of token spend is on GPT-4 AND average output length ≤500 tokens
    - Recommend switching to lower-cost model with estimated savings
    - Do NOT recommend if either condition is not met
    - _Requirements: 11.2_

  - [ ]* 9.3 Write property test for model-switch recommendation (Property 10)
    - **Property 10: Model-switch recommendation rule**
    - For any usage pattern: recommendation fires iff GPT-4 > 50% spend AND avg output ≤ 500 tokens
    - **Validates: Requirements 11.2**

  - [x] 9.4 Implement prompt optimization recommendation rule
    - Trigger when input:output token ratio exceeds 4:1 across billing period
    - Recommend prompt optimization with estimated savings
    - Do NOT recommend if ratio is 4:1 or lower
    - _Requirements: 11.3_

  - [ ]* 9.5 Write property test for prompt optimization recommendation (Property 11)
    - **Property 11: Prompt optimization recommendation rule**
    - For any usage pattern: recommendation fires iff input:output ratio > 4:1
    - **Validates: Requirements 11.3**

  - [ ]* 9.6 Write property test for recommendation format and ordering (Property 12)
    - **Property 12: Recommendation format and ordering**
    - For any set of generated recommendations: ≤10 items, sorted by savings descending, title ≤80 chars, description ≤300 chars, difficulty in {easy, medium, hard}
    - **Validates: Requirements 11.1, 11.4**

- [x] 10. Implement rate limit utilization display logic
  - [x] 10.1 Add rate limit data retrieval and warning logic
    - Extract RPM and TPM utilization from OpenAI API response headers or rate limit endpoints
    - Calculate utilization percentage per model tier
    - Flag warning if utilization exceeds 80%
    - Return "unavailable" message if rate limit data not provided by API for key type
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 10.2 Write property test for rate limit warning threshold (Property 9)
    - **Property 9: Rate limit warning threshold**
    - For any utilization value: warning displayed iff utilization > 80%
    - **Validates: Requirements 10.3**

- [x] 11. Checkpoint - Verify backend logic complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Implement tips filter enhancement and seed script
  - [x] 12.1 Add `OPENAI_SERVICE_MAPPING` to `tips_filter.py`
    - Add OpenAI keyword-to-service mapping dict with keys: gpt-4, gpt4, gpt-4o, gpt-3.5, gpt-3, chatgpt, openai, token, tokens, prompt, embedding, fine-tune, finetune, batch, cache, dall-e, whisper, tts, general, cost, billing, save, efficient, optimize
    - Register in `PROVIDER_MAPPINGS['openai']`
    - _Requirements: 12.3_

  - [ ]* 12.2 Write property test for tips search relevance (Property 13)
    - **Property 13: OpenAI tips search relevance**
    - For any question containing at least one keyword from `OPENAI_SERVICE_MAPPING`, `_search_tips(question, provider='openai')` returns 1–5 tips with matching service field
    - **Validates: Requirements 12.3**

  - [x] 12.3 Create `scripts/seed_openai_tips.py` seed script
    - Define at least 10 OpenAI optimization tips covering 5 categories: model selection, prompt length reduction, caching strategies, batch API usage, fine-tuning cost tradeoffs
    - Each tip: `provider='openai'`, fields: service, tipId, category, title, description, estimatedSavings, difficulty
    - Use `batch_writer(overwrite_by_pkeys=['service', 'tipId'])` for idempotent writes
    - Exit with non-zero code and log error if table unreachable or writes fail
    - _Requirements: 12.1, 12.2, 12.4, 12.5_

- [x] 13. Implement frontend Connection Wizard
  - [x] 13.1 Add "Add AI Vendor" flow to Configure tab in `members/members.js`
    - Add "Add AI Vendor" button alongside existing "Add Cloud Account"
    - Show vendor selection with OpenAI option
    - API Key input field with client-side format validation (`sk-org-` or `sk-proj-` prefix, 40–200 chars)
    - Optional connection name input (max 64 chars)
    - Inline validation error for invalid format before backend submission
    - Loading indicator with 15-second timeout
    - Success confirmation on valid key saved
    - Error state with retry option on failure (auth failure, timeout, network error)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [x] 13.2 Add connection status display and "Test Connection" to Configure tab
    - Display each OpenAI connection with name, status (connected/failed/pending), lastTestedAt
    - "Test Connection" button calls `POST /members/accounts/test-openai-connection`
    - Show loading indicator during test, disable button to prevent concurrent requests
    - Update display on success/failure with failure reason
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 14. Implement frontend Usage Dashboard
  - [x] 14.1 Add OpenAI token usage time-series chart to Observe tab
    - Line chart showing daily input tokens vs output tokens
    - Date range selector: 7 / 30 / 90 days (default 30)
    - Loading indicator while data fetches
    - Empty state message if no data for period
    - Error state with retry action on load failure
    - _Requirements: 6.1, 6.2, 6.4, 6.5, 6.6_

  - [x] 14.2 Add cost-by-model bar chart to Observe tab
    - Bar chart sorted by cost descending, up to 20 models
    - Dollar amount (2 decimal places) and percentage (1 decimal place) per model
    - Error state preserving other dashboard sections
    - Empty state if no model usage in period
    - _Requirements: 7.1, 7.3, 7.4, 7.5, 7.6_

  - [x] 14.3 Add spend trends line chart with granularity toggle
    - Line chart: daily/weekly/monthly toggle
    - Default to daily, last 30 days, max 90 days
    - Re-render within 1 second when switching granularity (client-side aggregation)
    - Show total spend and period-over-period percentage change
    - Empty state and error state with retry
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 14.4 Add cost-per-project table to Observe tab
    - Table sorted by cost descending, top 50 entries
    - Show absolute cost (2 decimal places) and percentage of total (1 decimal place)
    - Note about Organization-level key if project data unavailable
    - Error state with retry, indication if >50 entries truncated
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 14.5 Add rate limit utilization gauges to Observe tab
    - Display RPM and TPM utilization percentages per model tier
    - Warning indicator (color/icon) when >80% utilization
    - "Unavailable" message if rate limit data not provided for key type
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 14.6 Add optimization recommendations panel to Observe tab
    - Display 0–10 recommendations sorted by estimated monthly savings descending
    - Each: title, description, estimated_monthly_savings, difficulty badge
    - Empty state message when no recommendations apply
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 15. Checkpoint - Verify frontend integration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Update infrastructure (CloudFormation + API Gateway)
  - [x] 16.1 Add OpenAI Sync Lambda and EventBridge schedule to `viewmybill-stack.yaml`
    - `OpenAISyncFunction`: Python 3.12, 256 MB, 900s timeout
    - `OpenAISyncSchedule`: EventBridge rule `cron(0 2 * * ? *)`
    - `OpenAISyncRole`: IAM role with DynamoDB (Accounts + Cost_Cache_Table), KMS, CloudWatch Logs permissions
    - _Requirements: 13.1, 13.8_

  - [x] 16.2 Add API Gateway routes for OpenAI endpoints
    - `POST /members/accounts/add-openai`
    - `POST /members/accounts/openai-usage`
    - `POST /members/accounts/test-openai-connection`
    - Update Member Handler Lambda environment: add `openai` to `SUPPORTED_PROVIDERS`
    - _Requirements: 1.3, 5.4, 6.3_

- [x] 17. Update provider router for OpenAI credential extraction
  - [x] 17.1 Add `'openai'` to `SUPPORTED_PROVIDERS` and update `_extract_credentials()` in `provider_router.py`
    - Add `'openai'` case to extract `credentials.encryptedApiKey` from account record
    - Ensure provider router dispatches to OpenAI connector for `cloudProvider='openai'`
    - _Requirements: 1.3, 4.1_

- [x] 18. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each major phase
- Property tests validate the 17 universal correctness properties from the design document
- Python is the implementation language for all backend (Lambda) code
- JavaScript (vanilla) is used for frontend (`members/members.js`)
- CloudFormation YAML for infrastructure definitions
- The OpenAI connector reuses existing `ProviderConnector` interface and `kms_helpers.py`
- The nightly sync follows the same pattern as `incremental_fetch_engine.py`
- Tips integration reuses existing `tips_filter.py` and `tip_citation.py` pipeline

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.4", "3.1"] },
    { "id": 3, "tasks": ["2.3", "2.5", "3.2"] },
    { "id": 4, "tasks": ["5.1", "5.2", "6.1"] },
    { "id": 5, "tasks": ["5.3", "5.4", "6.3", "6.5", "6.7", "6.9"] },
    { "id": 6, "tasks": ["6.2", "6.4", "6.6", "6.8", "6.10"] },
    { "id": 7, "tasks": ["8.1", "9.1", "9.2", "9.4", "10.1"] },
    { "id": 8, "tasks": ["8.2", "8.3", "9.3", "9.5", "9.6", "10.2"] },
    { "id": 9, "tasks": ["12.1", "12.3", "17.1"] },
    { "id": 10, "tasks": ["12.2", "16.1", "16.2"] },
    { "id": 11, "tasks": ["13.1", "13.2"] },
    { "id": 12, "tasks": ["14.1", "14.2", "14.3", "14.4", "14.5", "14.6"] }
  ]
}
```
