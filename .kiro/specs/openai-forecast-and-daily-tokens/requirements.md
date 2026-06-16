# Requirements Document

## Introduction

Two backend capabilities for the SlashMyBill OpenAI integration: (1) a chat forecast function that projects month-end OpenAI costs using historical daily averages, returning a formatted response with MTD spend, daily average, projected total, and a per-model table; (2) a per-user daily token usage enrichment pipeline that fetches granular token consumption from the OpenAI Usage API and persists it as time-limited DynamoDB records for future dashboard and invoice modules.

## Glossary

- **Forecast_Function**: The `_answer_openai_forecast` function in `member-handler/lambda_function.py` that computes and returns a month-end cost projection in response to chat questions.
- **Enrichment_Writer**: The `_enrich_daily_token_usage` function in `member-handler/provider_invoices.py` that fetches per-user daily usage and writes records to DynamoDB.
- **Usage_Fetcher**: The `fetch_per_user_daily_usage` method on `agent-action/connectors/ai_vendor_connector.py` that calls the OpenAI Usage API and returns parsed records.
- **Service_Breakdown**: The existing `generate_openai_service_breakdown` function that produces per-model cost rows for a given period.
- **Invoices_Table**: The existing `MemberPortal-Invoices` DynamoDB table used for invoice and usage record storage.
- **Daily_Record**: A DynamoDB item with sort key pattern `DAILY#{date}#{user_id}#{model}` storing per-user per-model daily token counts.
- **Member**: An authenticated SlashMyBill user with a connected OpenAI account.
- **MTD**: Month-to-date cumulative cost from the first of the current month through today.

## Requirements

### Requirement 1: Forecast Intent Detection

**User Story:** As a Member, I want the chat to recognize when I am asking about future OpenAI costs, so that it provides a projection instead of a generic answer.

#### Acceptance Criteria

1. WHEN a Member's chat question contains forecast intent keywords (e.g., "forecast", "predict", "projection", "estimate", "what will my bill be"), THE Forecast_Function SHALL be invoked instead of the generic OpenAI answer handler.
2. WHEN a Member's chat question does not contain any forecast intent keywords, THE system SHALL route the question to the standard OpenAI chat answer flow.
3. THE system SHALL perform keyword matching in a case-insensitive manner.

### Requirement 2: Forecast Calculation

**User Story:** As a Member, I want an accurate month-end cost projection based on my current spending and historical daily average, so that I can budget for my OpenAI costs.

#### Acceptance Criteria

1. THE Forecast_Function SHALL compute projected end-of-month cost using the formula: `MTD_cost + (remaining_days × last_month_daily_avg)`.
2. THE Forecast_Function SHALL derive `remaining_days` as `days_in_current_month - current_day_of_month`.
3. THE Forecast_Function SHALL derive `last_month_daily_avg` as `previous_month_total / days_in_previous_month`.
4. WHEN no previous month cost data is available, THE Forecast_Function SHALL set `last_month_daily_avg` to zero, resulting in projection equal to MTD cost.
5. THE Forecast_Function SHALL produce a projected value that is always greater than or equal to MTD cost.
6. THE Forecast_Function SHALL round the projected total to two decimal places.

### Requirement 3: Forecast Response Formatting

**User Story:** As a Member, I want the forecast response to clearly show my current spend, daily average, and projected total with a per-model breakdown, so that I can understand which models drive cost.

#### Acceptance Criteria

1. WHEN the Forecast_Function produces a projection, THE system SHALL return a response containing: MTD spend, last month daily average, remaining days count, and projected end-of-month total.
2. WHEN per-model cost data is available for the current period, THE Forecast_Function SHALL include a markdown table of up to 5 models sorted by cost descending.
3. WHEN per-model cost data is not available, THE Forecast_Function SHALL omit the model table and return only headline metrics.
4. THE Forecast_Function SHALL return a response with HTTP status code 200 and include `interactionId` for chat continuity.

### Requirement 4: Forecast Edge Cases

**User Story:** As a Member, I want the forecast to handle unusual timing conditions gracefully, so that I always receive a valid answer regardless of when in the month I ask.

#### Acceptance Criteria

1. WHEN the current date is the first day of the month (day 1), THE Forecast_Function SHALL set remaining_days to `days_in_month - 1` and compute the projection using the previous month average.
2. WHEN the current date is the last day of the month, THE Forecast_Function SHALL set remaining_days to zero and return the MTD total as the projection.
3. IF the Forecast_Function encounters an internal error during computation, THEN THE Forecast_Function SHALL return an error response without raising an exception to the caller.

### Requirement 5: Usage API Data Fetching

**User Story:** As a system operator, I want the platform to fetch per-user daily token consumption from the OpenAI Usage API, so that granular usage data is available for future analytics modules.

#### Acceptance Criteria

1. THE Usage_Fetcher SHALL call `GET /v1/organization/usage/completions` with query parameters `group_by=user_id`, `group_by=model`, and `bucket_width=1d`.
2. THE Usage_Fetcher SHALL convert `start_date` and `end_date` (YYYY-MM-DD strings) to Unix epoch timestamps for the `start_time` and `end_time` query parameters.
3. WHEN the API response contains `has_more=true`, THE Usage_Fetcher SHALL follow pagination by passing the `next_page` token until `has_more=false`.
4. THE Usage_Fetcher SHALL cap pagination at 100 pages maximum and log a warning if the cap is reached.
5. THE Usage_Fetcher SHALL return a list of records each containing: `date`, `user_id`, `model`, `input_tokens`, `output_tokens`, `input_cached_tokens`, and `num_model_requests`.
6. IF the OpenAI API returns an authentication error (401/403), THEN THE Usage_Fetcher SHALL return an empty list without raising an exception.
7. IF the OpenAI API returns a server error (5xx), THEN THE Usage_Fetcher SHALL return any records collected so far without raising an exception.

### Requirement 6: Date and Timestamp Conversion

**User Story:** As a developer, I want date conversions between ISO date strings and Unix timestamps to be correct, so that the Usage API receives accurate time boundaries and returned data maps to the right calendar dates.

#### Acceptance Criteria

1. THE Usage_Fetcher SHALL convert a `YYYY-MM-DD` start_date string to a Unix timestamp representing midnight UTC on that date.
2. THE Usage_Fetcher SHALL convert a `YYYY-MM-DD` end_date string to a Unix timestamp representing midnight UTC on that date.
3. WHEN converting a bucket `start_time` Unix timestamp back to a date string, THE Usage_Fetcher SHALL produce a `YYYY-MM-DD` string representing the UTC date of that timestamp.
4. THE Usage_Fetcher SHALL ensure all returned `date` values fall within the requested `[start_date, end_date)` range.

### Requirement 7: DynamoDB Record Persistence

**User Story:** As a system operator, I want per-user daily token records stored in DynamoDB with a consistent key pattern, so that future modules can query them efficiently.

#### Acceptance Criteria

1. THE Enrichment_Writer SHALL write each usage record to the Invoices_Table with partition key `{member_email}#{account_id}`.
2. THE Enrichment_Writer SHALL write each usage record with sort key matching the pattern `DAILY#{YYYY-MM-DD}#{user_id}#{model}`.
3. WHEN writing a record, THE Enrichment_Writer SHALL include fields: `input_tokens`, `output_tokens`, `input_cached_tokens`, `num_model_requests`, `date`, `user_id`, `model`, and `account_id`.
4. THE Enrichment_Writer SHALL set a `ttl` attribute on each record equal to the current Unix timestamp plus 2,592,000 seconds (30 days).
5. WHEN a record with the same pk and sk already exists, THE Enrichment_Writer SHALL overwrite it with the new values (idempotent upsert).
6. THE Enrichment_Writer SHALL return the count of records successfully written.

### Requirement 8: Token Count Data Integrity

**User Story:** As a data consumer, I want stored token counts to be valid non-negative integers, so that downstream analytics produce correct results.

#### Acceptance Criteria

1. THE Usage_Fetcher SHALL ensure all `input_tokens` values are non-negative integers.
2. THE Usage_Fetcher SHALL ensure all `output_tokens` values are non-negative integers.
3. THE Usage_Fetcher SHALL ensure all `input_cached_tokens` values are non-negative integers.
4. THE Usage_Fetcher SHALL ensure all `num_model_requests` values are non-negative integers.
5. WHEN the API returns a null or missing token field, THE Usage_Fetcher SHALL default that field to zero.

### Requirement 9: Non-Breaking Enrichment Integration

**User Story:** As a system operator, I want the daily token enrichment to never disrupt the existing service breakdown flow, so that invoice data remains reliable regardless of enrichment outcomes.

#### Acceptance Criteria

1. THE Enrichment_Writer SHALL execute after `generate_openai_service_breakdown` completes successfully.
2. IF the Enrichment_Writer encounters any exception during execution, THEN THE Enrichment_Writer SHALL catch the exception, log a warning, and return zero without re-raising.
3. IF the Usage_Fetcher returns an empty list, THEN THE Enrichment_Writer SHALL return zero without attempting any DynamoDB writes.
4. THE Enrichment_Writer SHALL never modify the return value or behavior of the Service_Breakdown function.

### Requirement 10: Connector Pattern Compliance

**User Story:** As a developer, I want the new Usage_Fetcher to follow the same patterns as other connector methods, so that the codebase remains consistent and maintainable.

#### Acceptance Criteria

1. THE Usage_Fetcher SHALL reuse the existing HTTP request utility and retry logic present in the ai_vendor_connector module.
2. THE Usage_Fetcher SHALL include the `Authorization: Bearer {api_key}` and `OpenAI-Organization: {organization_id}` headers on all API requests.
3. THE Usage_Fetcher SHALL log API errors at warning level with the HTTP status code and endpoint path.
4. THE Usage_Fetcher SHALL set a request timeout consistent with other connector API calls.
