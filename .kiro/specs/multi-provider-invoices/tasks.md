# Implementation Plan: Multi-Provider Invoices

## Overview

This plan extends the existing AWS synthetic-monthly-invoice model to Azure, GCP, and the OpenAI AI vendor. The work is deliberately additive: a new pure-logic module `member-handler/provider_invoices.py` is built and tested in isolation first, then wired into the existing list and refresh handlers in `member-handler/invoice_drilldown.py` via a provider router branch, and finally the presentation-only refinements are made in `members/members.js`. AWS behavior is never modified, and forecasting stays AWS-only.

Backend uses **Python** with **Hypothesis** for property tests and `pytest` + `unittest.mock`/`moto` for example/integration tests (placed in `member-handler/tests/`). Frontend uses the project's existing JS test runner. Each of the 18 design correctness properties is implemented as exactly one property-based test running a **minimum of 100 iterations**.

## Tasks

- [x] 1. Scaffold the provider_invoices module and shared constants
  - Create `member-handler/provider_invoices.py` with module docstring and imports (`connectors`, `cost_normalizer`, stdlib `datetime`/`calendar`/`logging`)
  - Define `ISSUER_LABELS = {'aws': 'Amazon Web Services', 'azure': 'Microsoft Azure', 'gcp': 'Google Cloud', 'openai': 'OpenAI'}`
  - Declare public function/class stubs (`generate_provider_invoices`, `MonthlyCostAggregator`/`month_total_from_cost_data`, `_build_invoice_record`, `_load_credentials`) so later tasks fill in bodies
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 2. Implement the synthetic invoice record builder and date/format helpers
  - [x] 2.1 Implement `_build_invoice_record(provider_key, period, month_total)`
    - Produce the canonical dict `{invoiceId, issuer, paymentDate, paymentStatus, totalAmount, currency, period}` plus the `source` provenance tag
    - Set `invoiceId = f"{period}-monthly"`, `period = "YYYY-MM"`, `issuer = ISSUER_LABELS[provider_key]`, `paymentStatus = "paid"`, `currency = "USD"`, `totalAmount = round(month_total, 2)`
    - Compute `paymentDate` as the 15th of the month immediately following `period` in `YYYY-MM-DD`, rolling the year forward when the period is December
    - _Requirements: 1.4, 1.5, 2.4, 3.1, 3.2, 3.3, 3.4, 7 (currency 2.5/10.1/10.2/10.4), 11.1, 11.2_

  - [ ]* 2.2 Write property test for invoiceId/period formatting
    - **Property 2: invoiceId and period formatting**
    - **Validates: Requirements 1.4, 1.5**
    - Tag: `# Feature: multi-provider-invoices, Property 2`, min 100 iterations

  - [ ]* 2.3 Write property test for payment date computation
    - **Property 17: Payment date is the 15th of the following month**
    - **Validates: Requirements 11.1**
    - Include December → January year rollover cases; tag with Property 17, min 100 iterations

  - [ ]* 2.4 Write property test for canonical field set and constant status
    - **Property 10: Built record exposes exactly the canonical field set with constant status**
    - **Validates: Requirements 4.2, 11.2**
    - Assert field set is exactly `{invoiceId, issuer, paymentDate, paymentStatus, totalAmount, currency, period}` and `paymentStatus == "paid"`; tag with Property 10, min 100 iterations

  - [ ]* 2.5 Write property test for currency assignment
    - **Property 7: Currency is always USD for the supported providers**
    - **Validates: Requirements 2.5, 10.1, 10.2, 10.4**
    - Generate over `aws`/`azure`/`gcp`/`openai`; tag with Property 7, min 100 iterations

- [x] 3. Implement the monthly cost aggregator
  - [x] 3.1 Implement `month_total_from_cost_data(provider_key, cost_data)`
    - Handle dict shape (Azure/GCP): sum `cost_usd` over `cost_by_service`, skipping tax-classified entries
    - Handle list shape (OpenAI): normalize via `cost_normalizer.normalize_openai`, sum `cost_amount`, excluding tax-classified records
    - Treat an entry as tax-classified when its case-folded, trimmed service/line-item name equals `"tax"` (consistent with the AWS `RECORD_TYPE == 'Tax'` filter)
    - Return a float rounded to 2 decimals
    - _Requirements: 1.2, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 3.2 Write property test for monthly aggregation
    - **Property 3: Monthly aggregation sums connector cost data to one total per period**
    - **Validates: Requirements 1.2, 2.2**
    - Tag with Property 3, min 100 iterations

  - [ ]* 3.3 Write property test for tax exclusion
    - **Property 4: Tax-classified amounts are excluded from Month_Total**
    - **Validates: Requirements 2.3**
    - Generate base cost data, then inject "Tax"/"tax" entries and assert the total is unchanged; tag with Property 4, min 100 iterations

  - [ ]* 3.4 Write property test for rounding
    - **Property 5: Month_Total is rounded to two decimal places**
    - **Validates: Requirements 2.4**
    - Include raw sums with many fractional digits; tag with Property 5, min 100 iterations

- [x] 4. Implement the reporting window builder
  - [x] 4.1 Implement the reporting-window helper
    - Build the 12 calendar months ending with the current (in-progress) month
    - For each Billing_Period emit `start_date` = first day of the period and `end_date` = first day of the following period, both `YYYY-MM-DD`
    - _Requirements: 2.1_

  - [ ]* 4.2 Write property test for the reporting window
    - **Property 6: Reporting window date ranges are valid and cover the window**
    - **Validates: Requirements 2.1**
    - Parametrize over arbitrary "current dates"; assert valid `YYYY-MM-DD` pairs and that the union covers exactly the 12 reporting months; tag with Property 6, min 100 iterations

- [x] 5. Implement per-account credential loading
  - [x] 5.1 Implement `_load_credentials(member_email, account_id, provider_key)`
    - Read the account record from `MemberPortal-Accounts` and build the provider-specific credentials dict: Azure `{tenant_id, client_id, client_secret}` (decrypt `encryptedClientSecret`), GCP service-account JSON (decrypted), OpenAI `{encrypted_api_key, member_email, account_id, org_name}` (connector decrypts)
    - Supply `{memberEmail, accountId}` as the KMS encryption context wherever decryption occurs
    - Ensure decrypted secrets live only in local variables; never log, return, or store plaintext secrets (log only provider + account id on failure)
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 5.2 Write integration test for credential decryption plumbing
    - With mocked KMS/connectors, assert `authenticate` is invoked and that decryption is called with the `{memberEmail, accountId}` encryption context
    - _Requirements: 6.1, 6.2_

- [x] 6. Implement the non-AWS invoice generator (failure boundary)
  - [x] 6.1 Implement `generate_provider_invoices(member_email, account_id, provider_key) -> (records, unavailable)`
    - Resolve the connector via `connectors.get_connector`; return `([], True)` when `None`
    - Call `_load_credentials` then `connector.authenticate`; convert credential/auth failures into `([], True)` (catch internally, never raise to caller)
    - Iterate the reporting window calling `connector.get_cost_data(auth, account_id, start, end)`, reduce each month via `month_total_from_cost_data`, and on `CostRetrievalError`/empty result abort further fetches while returning already-computed months with `unavailable=True`
    - Build a record per period whose `abs(month_total) >= 0.01`, omitting periods below the threshold
    - Do not write or mutate the account's stored `cloudProvider`/Provider_Key
    - _Requirements: 1.1, 1.2, 1.6, 6.4, 7.1, 7.2, 7.4, 8.2_

  - [ ]* 6.2 Write property test for per-period generation and threshold omission
    - **Property 1: Invoice generated per qualifying period, omitted below the threshold**
    - **Validates: Requirements 1.1, 1.6**
    - Tag with Property 1, min 100 iterations

  - [ ]* 6.3 Write property test for secret safety
    - **Property 12: Decrypted secrets never appear in output**
    - **Validates: Requirements 6.3**
    - Inject random secret strings as decrypted values; assert no occurrence in records, serialized response, or captured logs; tag with Property 12, min 100 iterations

  - [ ]* 6.4 Write property test for no forecast row on non-AWS
    - **Property 15: Non-AWS accounts never produce a forecast row**
    - **Validates: Requirements 8.2**
    - Assert no record with `paymentStatus == "Forecast"` and no `FCST#` record for `azure`/`gcp`/`openai`; tag with Property 15, min 100 iterations

  - [ ]* 6.5 Write property test for stored Provider_Key immutability
    - **Property 9: Stored Provider_Key is never mutated**
    - **Validates: Requirements 3.5**
    - Assert generation leaves the account's stored Provider_Key byte-for-byte unchanged; tag with Property 9, min 100 iterations

  - [ ]* 6.6 Write unit tests for generator failure modes
    - No connector registered → `([], True)`; `authenticate` failure → `([], True)`; `get_cost_data` failure mid-window → partial months + `unavailable=True`; never raises
    - _Requirements: 6.4, 7.1, 7.2, 7.4_

- [x] 7. Checkpoint - provider_invoices module complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Wire the provider router into the invoice list path
  - [x] 8.1 Add the provider branch to `handle_invoice_list_request` in `invoice_drilldown.py`
    - On cache miss, branch on `_get_account_provider`: `aws` → existing `fetch_invoice_list` (unchanged); else → `generate_provider_invoices`
    - Surface the unavailable flag as an `invoiceDataUnavailable` field in the response alongside existing `forecastUnavailable`/`forecastDiag`
    - Route both branches through the existing `_write_invoice_cache`, sort, paginate, and response-shaping code; gate forecast merge on `aws` only
    - Preserve the existing `_verify_account_ownership` access-denied behavior
    - _Requirements: 4.1, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 6.4, 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.4_

  - [ ]* 8.2 Write property test for provider-failure preservation
    - **Property 13: Provider failure preserves cache and stays successful with an unavailable indication**
    - **Validates: Requirements 6.4, 7.1, 7.2, 7.4**
    - Include the empty-cache case; tag with Property 13, min 100 iterations

  - [ ]* 8.3 Write property test for cache non-mutation on failure
    - **Property 14: Failing cost retrieval does not mutate the cache**
    - **Validates: Requirements 7.3**
    - Assert no delete/overwrite of cached items when `get_cost_data` fails; tag with Property 14, min 100 iterations

  - [ ]* 8.4 Write property test for provider-independent sorting/pagination
    - **Property 11: Sorting and pagination are independent of provider/issuer**
    - **Validates: Requirements 4.5**
    - Generate item lists with arbitrary issuers and valid `page`/`pageSize`/`sortBy`/`sortOrder`; tag with Property 11, min 100 iterations

  - [ ]* 8.5 Write integration test for cache write scheme
    - With mocked DynamoDB (`moto`), assert each record is written under PK `{memberEmail}#{accountId}`, SK `INV#{invoiceId}`, `recordType="real"`, and 90-day TTL
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]* 8.6 Write unit tests for list control flow and AWS non-regression
    - Cache hit returns cached items without calling the connector; cache miss generates/stores/returns (5.4, 5.5); AWS branch unchanged (1.3, 8.4, 10.4 AWS); access-denied gate (4.4); per-provider handler smoke (4.1)
    - _Requirements: 1.3, 4.1, 4.4, 5.4, 5.5, 8.4, 10.4_

- [x] 9. Wire the provider router into the refresh path
  - [x] 9.1 Add the provider branch to `handle_drilldown_refresh_request` in `invoice_drilldown.py`
    - After clearing `INV#` rows, regenerate via the AWS path for `aws` and via `generate_provider_invoices` for non-AWS
    - Keep the existing 5-minute per-account cooldown and success-result shape
    - On regeneration failure, return an error indication and retain the prior cached `INV#` rows
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 9.2 Write property test for refresh-failure cache retention
    - **Property 16: Refresh failure retains prior cache and signals an error**
    - **Validates: Requirements 9.3**
    - Tag with Property 16, min 100 iterations

  - [ ]* 9.3 Write integration/unit tests for refresh behavior
    - Clear-and-regenerate for a non-AWS account (9.1); cooldown enforced identically (9.2); success result equivalent to AWS (9.4)
    - _Requirements: 9.1, 9.2, 9.4_

- [x] 10. Checkpoint - backend wiring complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement frontend presentation refinements
  - [x] 11.1 Add provider display mapping and issuer fallback in `members/members.js`
    - Add `_providerDisplayName(key)` mapping `aws`→"Amazon Web Services", `azure`→"Microsoft Azure", `gcp`→"Google Cloud", `openai`→"AI Cost"
    - Resolve the empty-issuer fallback to the selected account's `cloudProvider` display name instead of always "Amazon Web Services"
    - Keep `_aiCostIssuerLabel` mapping stored `"OpenAI"` → `"AI Cost"`; no change to column order, sorting/pagination controls, or the request shape
    - _Requirements: 3.4, 3.5, 3.6, 4.3, 10.3, 11.3, 11.4_

  - [ ]* 11.2 Write property test for issuer/display-name mapping
    - **Property 8: Provider-key to issuer/display-name mapping**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6**
    - Tag with Property 8, min 100 iterations (use JS property library if available, else table-driven generated inputs)

  - [ ]* 11.3 Write property test for empty-issuer fallback
    - **Property 18: Empty issuer falls back to a non-empty Provider_Display_Name**
    - **Validates: Requirements 11.4**
    - Assert rendered "Issued By" equals the Provider_Display_Name and is never empty for missing/empty issuers; tag with Property 18, min 100 iterations

  - [ ]* 11.4 Write frontend example/snapshot tests for rendering
    - Five-column order per provider (4.3), currency rendering with the item's `currency` (10.3), status rendering (11.3), and no Forecast row for non-AWS accounts (8.3)
    - _Requirements: 4.3, 8.3, 10.3, 11.3_

- [x] 12. Final checkpoint - full feature verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP; core implementation sub-tasks are never optional.
- Each task references specific requirements (and, for test tasks, a specific design property) for traceability.
- All 18 design correctness properties are covered exactly once by a property-based test: P1→6.2, P2→2.2, P3→3.2, P4→3.3, P5→3.4, P6→4.2, P7→2.5, P8→11.2, P9→6.5, P10→2.4, P11→8.4, P12→6.3, P13→8.2, P14→8.3, P15→6.4, P16→9.2, P17→2.3, P18→11.3.
- Property tests use Hypothesis (backend) with a minimum of 100 iterations each; DynamoDB/KMS/connector/handler wiring and frontend rendering are covered by example/integration tests.
- AWS behavior is never modified; non-AWS failures degrade to a successful list plus an `invoiceDataUnavailable` indication.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "11.1"] },
    { "id": 1, "tasks": ["2.1", "11.2"] },
    { "id": 2, "tasks": ["3.1", "2.2", "11.3"] },
    { "id": 3, "tasks": ["4.1", "2.3", "11.4"] },
    { "id": 4, "tasks": ["5.1", "2.4", "3.2"] },
    { "id": 5, "tasks": ["6.1", "2.5", "3.3", "4.2"] },
    { "id": 6, "tasks": ["8.1", "5.2", "3.4", "6.2"] },
    { "id": 7, "tasks": ["9.1", "6.3", "6.6"] },
    { "id": 8, "tasks": ["6.4", "8.2", "8.5"] },
    { "id": 9, "tasks": ["6.5", "8.3", "8.6", "9.2"] },
    { "id": 10, "tasks": ["8.4", "9.3"] }
  ]
}
```
