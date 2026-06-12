# Implementation Plan: Invoice Forecast and "AI Cost" Rename

## Overview

This plan implements two capabilities in the SlashMyBill member portal. Part 1 is a display-only rename of "OpenAI" to "AI Cost" via presentation-layer label helpers and static text edits in `members/members.js` and `members/index.html`, leaving all internal identifiers, routes, and Provider_Key values byte-for-byte unchanged. Part 2 adds a Forecasted Invoice: a new pure-logic module `member-handler/invoice_forecast.py` (Forecast_Engine), merge/supersede integration in `member-handler/invoice_drilldown.py`, forecast rendering in the existing invoice table, and a new scheduled `monthly-refresh-handler/` Lambda wired to a monthly EventBridge rule.

Backend logic is Python (Hypothesis for property tests); frontend helpers are JavaScript (fast-check for property tests). Each task builds incrementally and ends with wiring into the existing stack.

## Tasks

- [x] 1. Add AI Cost label helpers (frontend foundation)
  - [x] 1.1 Implement `_aiCostProviderLabel` and `_aiCostIssuerLabel` helpers in `members/members.js`
    - Add `AI_COST_LABEL = 'AI Cost'` constant and both helper functions per Component 1
    - `_aiCostProviderLabel`: map Provider_Key `openai` (trimmed, case-insensitive) → "AI Cost"; pass all other keys through unchanged
    - `_aiCostIssuerLabel`: map stored issuer "OpenAI" → "AI Cost"; pass empty/null through for caller default; pass all others unchanged
    - _Requirements: 1.1, 1.5, 3.2, 3.5, 4.1, 4.2, 4.3, 4.5, 5.1, 5.3_

  - [ ]* 1.2 Write property test for label/issuer mapping helpers
    - **Property 1: Issuer and provider display mapping** — returns "AI Cost" for "openai" (any case/whitespace), default issuer for empty/null in issuer context, input unchanged otherwise, never emits "OpenAI"
    - fast-check `members/tests/label_helper.property.test.js`, ≥100 runs
    - **Validates: Requirements 1.1, 1.5, 3.2, 3.5, 4.1, 4.2, 4.3, 4.5, 5.1, 5.3**

  - [ ]* 1.3 Write property test for identifier invariance
    - **Property 3: Display transform preserves internal identifiers** — applying the substitution to internal identifiers, route paths, encryption-context strings, stored Provider_Key/issuer leaves them byte-for-byte unchanged
    - fast-check, same file, ≥100 runs
    - **Validates: Requirements 1.4, 2.3, 3.4, 4.4, 5.4**

- [x] 2. Apply AI Cost rename to the enumerated user-facing surfaces
  - [x] 2.1 Rename Observe-tab navigation and dashboard surfaces in `members/index.html` and `members/members.js`
    - Surface 1: Observe-tab AI usage nav button text `🤖 OpenAI` → `🤖 AI Cost` (index.html ~975); nav model array `label` → `'AI Cost'` (members.js ~3621); keep `data-section="observe-openai"`, `id="observe-openai-nav-btn"`, `id: 'observe-openai'`
    - Surface 2: dashboard heading → "AI Cost Usage Dashboard" (members.js ~13591); account-selector option text uses `_aiCostProviderLabel` while preserving member-supplied `accountName`
    - Surface 3: dashboard empty state → "No AI Cost accounts connected" / "Connect an AI Cost account..." (members.js ~13575)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.3, 5.2, 5.3, 5.4_

  - [x] 2.2 Rename Configure-tab wizard and connections list surfaces in `members/members.js` and `members/index.html`
    - Surface 4: wizard provider option, `Connect OpenAI` header (~13369), submit text (~13391), confirmation/notify text → "AI Cost"; keep `ChatGPT, GPT-4, DALL-E, Whisper` byte-for-byte; keep `#ai-vendor-select-openai`, `.openai-test-btn`, routes unchanged
    - Surface 5: AI connections list empty state `#ai-vendors-empty` → "...connect AI Cost." (index.html ~871)
    - Failure path: error message uses "AI Cost" (never "OpenAI") and retains member-entered wizard inputs
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.2, 5.3, 5.4_

  - [x] 2.3 Rename account/provider display and Invoice Explorer issuer surfaces in `members/members.js`
    - Surface 6: default AI account display name fallback `'OpenAI Connection'` → `'AI Cost Connection'` (~13276); preserve member-supplied `accountName`
    - Surface 7: wrap provider display for `openai` accounts in `_aiCostProviderLabel(a.cloudProvider)`
    - Surface 8: Invoice Explorer "Issued By" in `_ddRenderInvoices` (~12562) → `esc(_aiCostIssuerLabel(inv.issuer) || 'Amazon Web Services')`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 5.2, 5.3, 5.4_

  - [ ]* 2.4 Write property test for account display-name handling
    - **Property 2: Account display name handling** — default name for `openai` accounts with no member name contains "AI Cost" and not "OpenAI"; non-empty member-supplied names preserved byte-for-byte (case, whitespace, embedded "OpenAI")
    - fast-check `members/tests/label_helper.property.test.js`, ≥100 runs
    - **Validates: Requirements 3.1, 3.3**

  - [ ]* 2.5 Write unit tests for rename surfaces
    - Assert heading exactly "AI Cost Usage Dashboard" (1.2); empty states contain "AI Cost", no "OpenAI" (1.3, 2.2); wizard option/buttons/confirmation use "AI Cost" (2.1); product text preserved (2.4); failure keeps inputs + uses "AI Cost" (2.5, 5.5); enumerated-surfaces sweep finds no "OpenAI" (5.2); submit POSTs to `/members/accounts/add-openai` with key `openai` (2.3)
    - _Requirements: 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 5.2, 5.5_

- [x] 3. Checkpoint - rename complete
  - Ensure all rename tests pass, ask the user if questions arise.

- [x] 4. Implement Forecast Engine pure-math core (`member-handler/invoice_forecast.py`)
  - [x] 4.1 Create module scaffolding, constants, and predicate functions
    - Create `member-handler/invoice_forecast.py` with constants (`FORECAST_START_DAY=4`, `RECORD_TYPE_FORECAST`, `RECORD_TYPE_REAL`, `FORECAST_SK_PREFIX`), `ForecastError`, `is_in_forecast_window`, `is_aws_provider`, and `forecast_invoice_id` (format `Forecast-<YYYY-MM>`, raise on invalid month)
    - _Requirements: 6.1, 6.2, 7.1, 7.2, 11.1, 11.2, 11.3_

  - [x]* 4.2 Write property tests for window predicate and id format
    - **Property 4: Forecast window predicate** — true iff day-of-month ≥ 4 and ≤ last calendar day (incl. leap years)
    - **Property 5: Forecast identifier format and validation** — matches `^Forecast-\d{4}-(0[1-9]|1[0-2])$` and round-trips; raises on invalid month
    - Hypothesis `member-handler/tests/test_forecast_properties.py`, ≥100 examples each
    - **Validates: Requirements 6.1, 6.2, 7.1, 7.2**

  - [x] 4.3 Implement median and variable-forecast math
    - `median` (middle for odd count, mean of two middle for even, empty → 0.0); `compute_variable_forecast(mtd, median_daily, remaining_days)` = `mtd + median_daily * remaining_days`
    - _Requirements: 8.2, 8.4_

  - [x]* 4.4 Write property tests for median and variable formula
    - **Property 6: Median definition**
    - **Property 7: Variable forecast formula** — equals `mtd + median(daily) * (days_in_month - len(daily))`
    - Hypothesis, same file, ≥100 examples each
    - **Validates: Requirements 8.2, 8.4**

  - [x] 4.5 Implement fixed-cost modeling, total composition, and rounding
    - `compute_fixed_forecast(components, projected_total)` (fixed → amount, percentage → share*total, empty → 0.0); `round_half_up_2dp` (Decimal ROUND_HALF_UP); compose `total = round_half_up_2dp(variable + fixed)`
    - _Requirements: 8.1, 8.6, 8.7, 8.9, 8.10_

  - [x]* 4.6 Write property tests for total composition and fixed-cost detection shape
    - **Property 8: Forecast total composition and rounding** — `round_half_up(variable + Σ fixed, 2)`, ≤2 dp, equals rounded variable when fixed set empty
    - **Property 9: Fixed-cost detection records amount and percentage** — each model records `fixed_amount` = component amount and `pct_of_total` = amount / closed-month total
    - Hypothesis, same file, ≥100 examples each
    - **Validates: Requirements 8.1, 8.5, 8.6, 8.7, 8.9**

- [x] 5. Implement Forecast Engine I/O wrappers and orchestration
  - [x] 5.1 Implement Cost Explorer fetch wrappers and fixed-cost detection
    - `fetch_daily_cost_series` (GetCostAndUsage DAILY, UnblendedCost, exclude Tax, elapsed days); `detect_fixed_components` (SERVICE grouping over single prior closed month, record amount + share + model); reuse `_assume_role` SHA-256 ExternalId pattern
    - _Requirements: 8.3, 8.5_

  - [x] 5.2 Implement `build_forecast_record` and `compute_forecast` orchestration
    - `build_forecast_record` assembles the Forecast_Invoice dict (`invoiceId=Forecast-<YYYY-MM>`, `paymentStatus='Forecast'`, `paymentDate=''`, `recordType='forecast'`, `period`, `forecastMonth`, `currency='USD'`, audit fields)
    - `compute_forecast` runs the 12-step sequence: provider/window gates, month validation, fetch, omission conditions (mtd null/≤0, elapsed_days==0, CE error), issuer derivation (latest real else default), return record or `None`
    - _Requirements: 6.3, 6.4, 7.1, 7.2, 7.3, 8.8, 8.11, 9.3, 9.4, 11.1, 11.2, 11.3, 11.4_

  - [x]* 5.3 Write property tests for omission conditions and provider scope
    - **Property 10: Forecast omission conditions** — mtd null/error/≤0, or zero elapsed days, or CE failure → omitted result with reason code, no mutation of prior record
    - **Property 16: Provider scope of forecasting** — forecast produced exactly for `aws` (trimmed, case-insensitive); zero for others; null/empty/absent treated non-AWS with skip reason
    - Hypothesis `member-handler/tests/test_forecast_properties.py`, ≥100 examples each
    - **Validates: Requirements 6.4, 8.8, 8.11, 11.1, 11.2, 11.3, 11.4**

  - [ ]* 5.4 Write integration test for Cost Explorer call shape
    - Assert `GetCostAndUsage` uses `UnblendedCost`, `Not RECORD_TYPE = Tax` filter, DAILY for current month and SERVICE for closed month, against a mocked CE client
    - _Requirements: 8.3_

- [x] 6. Checkpoint - forecast engine complete
  - Ensure all forecast engine tests pass, ask the user if questions arise.

- [x] 7. Integrate forecast into the invoice list (`member-handler/invoice_drilldown.py`)
  - [x] 7.1 Add forecast cache helpers and stamp real records
    - Implement `_read_forecast_record`, `_write_forecast_record` (sk `FCST#{forecastMonth}`, recordType forecast, ttl epoch+90d), `_delete_forecast_record`; update `_write_invoice_cache` to stamp `recordType='real'` on `INV#` records
    - _Requirements: 12.1_

  - [x] 7.2 Implement merge/supersede/staleness in `handle_invoice_list_request`
    - Extend ownership-verification projection to include `cloudProvider`; add `_get_or_refresh_forecast` (read `FCST#{currentMonth}`, drop+delete if real invoice for same period exists, return cached when month matches, recompute when stale/missing, delete on `None`, surface `forecastUnavailable` on failure); prepend forecast to items at ordinal 0; set forecast `paymentDate=''`, `paymentStatus='Forecast'`, issuer from latest real else default
    - _Requirements: 6.3, 9.1, 9.2, 9.3, 9.4, 9.6, 10.2, 10.3, 10.4, 12.2, 12.3, 12.4_

  - [x]* 7.3 Write property tests for merge precedence, issuer derivation, and staleness
    - **Property 11: At most one record per account per month with real precedence**
    - **Property 12: Forecast issuer derivation** — most recent real invoice issuer, else default
    - **Property 17: Record-type discriminator and staleness handling** — recordType forecast; return cached when month matches; never return stale, replace/remove when month differs
    - Hypothesis `member-handler/tests/test_invoice_merge_properties.py`, ≥100 examples each
    - **Validates: Requirements 6.3, 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4, 12.1, 12.2, 12.3**

  - [ ]* 7.4 Write unit tests for supersession edge cases
    - Closed-month actuals unavailable → forecast retained + actuals-pending indication (10.5); stale recompute failure → remove stale + forecast-unavailable (12.4); status exactly "Forecast" (7.3); total recorded in USD (8.10)
    - _Requirements: 7.3, 8.10, 10.5, 12.4_

- [x] 8. Render the forecast row in the Invoice Explorer (`members/members.js`, `members/members.css`)
  - [x] 8.1 Add the Forecast status badge and confirm em-dash payment date
    - Add `s === 'forecast'` branch in `_ddStatusBadge` returning class `dd-status-forecast` with label exactly "Forecast"; add distinct `.dd-status-forecast` style to `members/members.css`; confirm `_ddFormatDate` renders U+2014 em-dash for empty `paymentDate`; `_ddRenderInvoices` renders the five columns in order (backend supplies forecast first)
    - _Requirements: 7.4, 7.5, 7.6, 9.5_

  - [ ]* 8.2 Write property tests for forecast rendering
    - **Property 13: Forecast payment-date rendering** — em-dash is sole content of Payment Date for forecast items
    - **Property 14: Forecast sorts to the top** — forecast occupies index 0 after default sort
    - **Property 15: Status badge distinctness** — (label, color) pairs pairwise distinct across {paid,pending,overdue,forecast}; forecast label exactly "Forecast"
    - fast-check `members/tests/invoice_render.property.test.js`, ≥100 runs each
    - **Validates: Requirements 7.5, 9.5, 9.6**

- [x] 9. Checkpoint - forecast end-to-end in invoice list
  - Ensure all integration and render tests pass, ask the user if questions arise.

- [x] 10. Implement the Monthly Refresh Job (`monthly-refresh-handler/lambda_function.py`)
  - [x] 10.1 Implement the refresh handler modeled on `daily-refresh-handler`
    - `lambda_handler` scans `MemberPortal-Accounts`; `_refresh_account_monthly` rebuilds Real_Invoices incl. just-closed month, invalidates+rewrites `INV#` (recordType real), recomputes/replaces `FCST#{currentMonth}` for AWS (delete on `None`); per-account try/except isolation; `_build_run_summary` returns `{processed, succeeded, failed, failures[]}`
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

  - [x]* 10.2 Write property tests for refresh resilience and idempotence
    - **Property 18: Monthly refresh resilience and count invariant** — attempts all N accounts, records each failure, `accountsProcessed + accountsFailed == N`
    - **Property 19: Monthly refresh idempotence** — running twice yields the same invoice records as once
    - Hypothesis `monthly-refresh-handler/tests/test_refresh_properties.py`, ≥100 examples each
    - **Validates: Requirements 13.4, 13.5**

  - [ ]* 10.3 Write integration test for monthly rebuild + cache invalidation
    - Rebuild real invoices incl. just-closed month and recompute forecast for an AWS account (13.2); invalidate `INV#` before rewrite (13.3) — mocked CE + local DynamoDB
    - _Requirements: 13.2, 13.3_

- [x] 11. Wire the monthly schedule into infrastructure (`infrastructure/viewmybill-stack.yaml`)
  - [x] 11.1 Add the Monthly Refresh Lambda, IAM role, and EventBridge rule
    - Define `slashmybill-monthly-refresh` Lambda + role mirroring `DailyRefreshRole` (sts:AssumeRole; DynamoDB Scan/Query/PutItem/BatchWriteItem on `MemberPortal-Accounts` and `MemberPortal-Invoices`; `ce:GetCostAndUsage`); add EventBridge rule `slashmybill-monthly-invoice-refresh` with `ScheduleExpression = cron(0 4 7 * ? *)` targeting the Lambda, mirroring `DailyRefreshSchedule`
    - _Requirements: 13.1_

  - [ ]* 11.2 Write schedule smoke test
    - Assert the EventBridge rule exists with `cron(0 4 7 * ? *)` and targets `slashmybill-monthly-refresh` — single CloudFormation/synth assertion
    - _Requirements: 13.1_

- [x] 12. Final checkpoint - full feature verification
  - Ensure all property, unit, and integration tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP.
- Each task references specific requirements for traceability; property test sub-tasks reference their design property number.
- Property-based tests use Hypothesis (Python) and fast-check (JavaScript), each ≥100 iterations, with AWS access (STS, Cost Explorer, DynamoDB) mocked.
- The rename is presentation-layer only; internal identifiers, routes, encryption contexts, and Provider_Key values stay byte-for-byte unchanged.
- The forecast path is additive and best-effort: any failure leaves the real-invoice list intact.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "4.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "4.2", "4.3", "4.5"] },
    { "id": 2, "tasks": ["2.1", "2.2", "2.3", "4.4", "4.6", "5.1"] },
    { "id": 3, "tasks": ["2.4", "2.5", "5.2"] },
    { "id": 4, "tasks": ["5.3", "5.4", "7.1"] },
    { "id": 5, "tasks": ["7.2"] },
    { "id": 6, "tasks": ["7.3", "7.4", "8.1", "10.1", "11.1"] },
    { "id": 7, "tasks": ["8.2", "10.2", "10.3", "11.2"] }
  ]
}
```
