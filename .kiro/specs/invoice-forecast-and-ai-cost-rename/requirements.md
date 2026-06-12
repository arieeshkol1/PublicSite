# Requirements Document

## Introduction

This feature adds two capabilities to the SlashMyBill member portal.

**Part 1 — "AI Cost" rename.** The user-facing label "OpenAI" is replaced with "AI Cost" across the member portal UI (Observe-tab navigation, the usage dashboard, the Configure-tab AI connection wizard, account/provider display names, empty states, and any invoice issuer label that currently reads "OpenAI"). This is a display-only rename. Internal provider keys and identifiers (for example `cloudProvider === 'openai'`, `vendorType === 'ai_vendor'`, KMS contexts, and API routes such as `/members/accounts/add-openai`) remain unchanged.

**Part 2 — Forecasted Invoice.** The Invoice Explorer drill-down list gains a forecast invoice for the current, in-progress month. From the 4th day of the month through the last day of the month, the system projects a full-month total from month-to-date actuals and presents it in the same invoice list as real monthly invoices, clearly identified as a forecast. Once the month closes, the forecast is superseded by the real actual invoice for that month.

This document records the requirements. The open decisions from the brief have been confirmed with the requester and are reflected directly in the acceptance criteria below: the forecast uses a two-part projection (fixed-cost pattern detection from historical months plus median-based daily provisioning), forecasting applies to AWS accounts only, the forecast row shows an em-dash placeholder in the Payment Date column, and the forecast is omitted entirely when there is no usable month-to-date cost.

## Glossary

- **Member_Portal**: The SlashMyBill member-facing single-page application served from `members/` (HTML in `members/index.html`, logic in `members/members.js`).
- **Invoice_Explorer**: The invoice drill-down list within the Member_Portal, served by `GET /members/invoices/list` (`handle_invoice_list_request` in `member-handler/invoice_drilldown.py`) and rendered by `_ddRenderInvoices` / `_loadInvoiceData` in `members/members.js`. Columns are Invoice ID, Issued By, Payment Date, Status, and Total Amount.
- **Forecast_Engine**: The backend logic that determines whether a forecast invoice should be produced for the current month, computes its projected total, and emits a forecast invoice record.
- **Forecast_Invoice**: A synthetic invoice record representing the projected full-month total for the current, in-progress month. Its invoice identifier follows the pattern `Forecast-<YYYY-MM>` and its status is `Forecast`.
- **Real_Invoice**: A non-forecast invoice record for a completed or already-invoiced month (the existing behavior, including Cost Explorer synthetic monthly records with `invoiceId = "<YYYY-MM>-monthly"`).
- **Current_Month**: The calendar month containing the current date (UTC).
- **Closed_Month**: Any calendar month strictly earlier than the Current_Month.
- **Month_To_Date_Cost**: The sum of actual unblended cost (excluding Tax) for the Current_Month from the first day of the month through the most recent fully elapsed day, retrieved from Cost Explorer `GetCostAndUsage`.
- **Elapsed_Days**: The count of fully elapsed days in the Current_Month for which actual daily cost data is available.
- **Remaining_Days**: `Days_In_Month` minus `Elapsed_Days`.
- **Days_In_Month**: The total number of calendar days in the Current_Month.
- **Daily_Cost_Series**: The per-day actual cost values for the elapsed days of the Current_Month, retrieved from Cost Explorer `GetCostAndUsage` at DAILY granularity (excluding Tax).
- **Median_Daily_Cost**: The median value of the Daily_Cost_Series across the elapsed days.
- **Variable_Cost_Forecast**: The projected variable/daily portion of the month, defined as `Month_To_Date_Cost + (Median_Daily_Cost * Remaining_Days)`.
- **Fixed_Cost_Component**: A recurring monthly charge identified from historical Closed_Months that is not proportional to daily usage (for example a flat monthly fee posted at month end, or a charge that recurs as a stable percentage of the monthly total).
- **Fixed_Cost_Model**: The detected model describing how a Fixed_Cost_Component recurs — either a fixed monetary amount per month or a percentage of the monthly total.
- **Fixed_Cost_Forecast**: The projected fixed-cost portion of the Current_Month, derived by applying each detected Fixed_Cost_Model to the Current_Month.
- **Forecast_Total**: The Forecast_Invoice total, defined as `Variable_Cost_Forecast + Fixed_Cost_Forecast`.
- **AI_Cost_Label**: The user-facing display string "AI Cost" that replaces the user-facing string "OpenAI".
- **Provider_Key**: An internal, non-user-facing identifier such as `openai`, `aws`, `azure`, or `gcp`, used in data records, encryption contexts, and API routes.
- **Monthly_Refresh_Job**: A scheduled backend job that runs on the 7th calendar day of each month (UTC) and performs a full invoice refresh across all members and all of their accounts.

## Requirements

### Requirement 1: Rename user-facing "OpenAI" navigation and dashboard labels

**User Story:** As a member, I want AI provider spend to be labeled "AI Cost" in the portal navigation and dashboard, so that the feature reads as a generic cost category rather than a single vendor name.

#### Acceptance Criteria

1. WHERE the Observe-tab navigation renders the AI usage section button, THE Member_Portal SHALL display the visible button label as the exact text "AI Cost" and SHALL NOT display the text "OpenAI" (matched case-insensitively) anywhere in that button's visible label or its accessible name (e.g. tooltip or aria-label).
2. WHEN the AI usage dashboard section is displayed, THE Member_Portal SHALL display the section heading as the exact text "AI Cost Usage Dashboard" and SHALL NOT display the text "OpenAI" (matched case-insensitively) in that heading.
3. WHILE no AI provider account is connected, THE Member_Portal SHALL display an empty-state message whose visible text contains the term "AI Cost" and SHALL NOT contain the text "OpenAI" (matched case-insensitively).
4. THE Member_Portal SHALL leave the internal section identifier `observe-openai` and all related Provider_Key values (e.g. cloudProvider value `openai`) byte-for-byte unchanged, such that no user-facing label change alters any internal identifier.
5. WHERE any user-facing element within the AI usage navigation or dashboard renders a vendor name for this feature, THE Member_Portal SHALL render the term "AI Cost" and SHALL NOT render the text "OpenAI" (matched case-insensitively) in any visible label, heading, tooltip, or accessible name.

### Requirement 2: Rename user-facing "OpenAI" labels in the Configure-tab connection wizard

**User Story:** As a member, I want the AI connection setup flow to refer to "AI Cost", so that the connection experience matches the renamed category.

#### Acceptance Criteria

1. WHEN the Configure-tab AI connection wizard is displayed, THE Member_Portal SHALL render the provider option label, all button labels, and all confirmation messages using the exact term "AI Cost" and SHALL NOT render the term "OpenAI" (in any letter case) in any of those user-visible elements.
2. WHEN the AI connections list contains zero connections, THE Member_Portal SHALL display an empty-state message that contains the term "AI Cost" and SHALL NOT contain the term "OpenAI" (in any letter case).
3. WHEN a member submits an AI connection request from the wizard, THE Member_Portal SHALL send the request to the existing API route paths (including the route containing the literal segment "openai") with those route paths and internal provider key values unchanged from their pre-rename values.
4. WHERE the wizard displays vendor product detail text, THE Member_Portal SHALL display the string "ChatGPT, GPT-4, DALL-E, Whisper" byte-for-byte unchanged.
5. IF the AI connection request fails, THEN THE Member_Portal SHALL display an error message that indicates the connection could not be completed, SHALL use the term "AI Cost" rather than "OpenAI" in that message, and SHALL retain the member-entered wizard input values without clearing them.

### Requirement 3: Rename user-facing "OpenAI" account and provider display names

**User Story:** As a member, I want connected AI accounts to be labeled "AI Cost" wherever their provider name is shown, so that naming is consistent across the portal.

#### Acceptance Criteria

1. WHEN the Member_Portal renders an AI provider account that has no member-supplied account name, THE Member_Portal SHALL display a default account name whose text contains the literal string "AI Cost" in place of "OpenAI".
2. WHERE a connected account's provider is displayed to the member, THE Member_Portal SHALL display the exact text "AI Cost" for accounts whose Provider_Key is `openai` and SHALL NOT display the text "OpenAI" (matched case-insensitively) in any member-facing provider-name field.
3. THE Member_Portal SHALL preserve member-supplied account names byte-for-byte, including character case, leading/trailing whitespace, and any embedded "OpenAI" substring.
4. THE Member_Portal SHALL apply the "AI Cost" substitution only at the presentation layer and SHALL leave the stored Provider_Key value `openai` unchanged.
5. IF an account's Provider_Key is a value other than `openai`, THEN THE Member_Portal SHALL NOT apply the "AI Cost" provider-name substitution to that account.

### Requirement 4: Rename user-facing "OpenAI" issuer label in the Invoice Explorer

**User Story:** As a member, I want AI provider invoices in the Invoice Explorer to show "AI Cost" as the issuer, so that the invoice list matches the renamed category.

#### Acceptance Criteria

1. WHEN the Invoice_Explorer renders the "Issued By" column for an invoice whose stored issuer value equals "OpenAI", THE Invoice_Explorer SHALL display the exact text "AI Cost" in that column.
2. WHEN the Invoice_Explorer renders the "Issued By" column for an AWS invoice, THE Invoice_Explorer SHALL display the exact text "Amazon Web Services".
3. WHERE an invoice's stored issuer value is neither "OpenAI" nor the AWS issuer, THE Invoice_Explorer SHALL display that stored issuer value unchanged.
4. THE Invoice_Explorer SHALL apply the issuer substitution as a display-only transformation and SHALL NOT modify the stored issuer value of any invoice record.
5. IF an invoice record has a missing or empty issuer value, THEN THE Invoice_Explorer SHALL display the existing default issuer text and SHALL NOT display the text "OpenAI".

### Requirement 5: Enumerate user-facing rename surfaces

**User Story:** As a maintainer, I want a defined list of the user-facing surfaces affected by the rename, so that the rename is complete and verifiable.

#### Acceptance Criteria

1. WHEN the Member_Portal renders any one of the enumerated user-facing surfaces listed in this requirement, THE Member_Portal SHALL display the AI_Cost_Label in place of any prior "OpenAI" term on that surface.
2. THE enumerated user-facing surfaces SHALL be exactly the following eight surfaces: (1) the Observe-tab AI usage navigation button; (2) the AI usage dashboard heading and its account-selector labels; (3) the AI usage dashboard "no account connected" empty state; (4) the Configure-tab AI connection wizard, covering provider selection, form headers, submit text, and confirmation text; (5) the AI connections list empty state; (6) the default AI account display name; (7) the provider display for accounts whose Provider_Key equals `openai`; and (8) the Invoice_Explorer "Issued By" label for AI provider invoices.
3. WHEN the Member_Portal renders any enumerated user-facing surface, THE Member_Portal SHALL NOT display the character sequence "OpenAI" in any letter case (including "openai" and "OPENAI") as visible text on that surface.
4. WHERE a string containing "OpenAI" exists only in non-user-facing code (Provider_Key values, API route paths, encryption contexts, internal identifiers, log messages, or code comments), THE Member_Portal SHALL leave that string byte-for-byte unchanged.
5. IF an enumerated user-facing surface fails to render (for example, due to missing data or a load error), THEN THE Member_Portal SHALL display an error indication to the user identifying the unavailable surface and SHALL NOT display the term "OpenAI" as part of that indication.

### Requirement 6: Generate a forecast invoice during the forecast window

**User Story:** As a member, I want to see a projected total for the current month once enough days have elapsed, so that I can anticipate my spend before the month closes.

#### Acceptance Criteria

1. WHILE the current date in UTC is on or after the 4th calendar day of the Current_Month and on or before the last calendar day of the Current_Month, THE Forecast_Engine SHALL produce exactly one Forecast_Invoice per AWS account for the Current_Month.
2. IF the current date in UTC is before the 4th calendar day of the Current_Month, THEN THE Forecast_Engine SHALL NOT produce a Forecast_Invoice for the Current_Month.
3. IF a Forecast_Invoice for the Current_Month already exists for an AWS account, THEN THE Forecast_Engine SHALL NOT produce an additional Forecast_Invoice for that AWS account, so that at most one Forecast_Invoice per AWS account exists for the Current_Month at any time.
4. IF Cost Explorer returns a Month_To_Date_Cost for the Current_Month that is null, an error response, or a value not greater than 0.00, THEN THE Forecast_Engine SHALL omit the Forecast_Invoice for the Current_Month for that AWS account.

### Requirement 7: Identify the forecast invoice

**User Story:** As a member, I want the forecast clearly identified in the invoice list, so that I do not mistake a projection for a billed invoice.

#### Acceptance Criteria

1. THE Forecast_Engine SHALL set the Forecast_Invoice identifier to the pattern `Forecast-<YYYY-MM>`, where `<YYYY-MM>` is the Current_Month formatted as a four-digit year and a two-digit, zero-padded month separated by a single hyphen (for example `Forecast-2026-06`).
2. IF the Current_Month cannot be determined or does not match the `YYYY-MM` format, THEN THE Forecast_Engine SHALL NOT create a Forecast_Invoice and SHALL produce an error indication reporting the invalid month value.
3. THE Forecast_Engine SHALL set the Forecast_Invoice status to the exact value `Forecast`.
4. WHEN the Invoice_Explorer renders a Forecast_Invoice, THE Invoice_Explorer SHALL display a status indicator whose label text is exactly "Forecast".
5. WHEN the Invoice_Explorer renders a Forecast_Invoice, THE Invoice_Explorer SHALL render the "Forecast" status indicator with styling that is not identical to the styling of the `paid`, `pending`, or `overdue` status indicators, such that no two of these four indicators share the same combination of label text and color.
6. WHEN the Invoice_Explorer renders a Forecast_Invoice, THE Invoice_Explorer SHALL display it using the same five columns, in the same order, as a Real_Invoice: Invoice ID, Issued By, Payment Date, Status, and Total Amount.

### Requirement 8: Compute the forecast total from fixed-cost detection and median daily provisioning

**User Story:** As a member, I want the forecast to combine my recurring fixed charges with a projection of my variable daily spend, so that the number reflects both how my account is billed and how I am consuming this month.

#### Acceptance Criteria

1. THE Forecast_Engine SHALL compute the Forecast_Total as `Variable_Cost_Forecast + Fixed_Cost_Forecast`.
2. THE Forecast_Engine SHALL compute the Variable_Cost_Forecast as `Month_To_Date_Cost + (Median_Daily_Cost * Remaining_Days)`, where Elapsed_Days is the count of fully elapsed days with available daily cost data and Remaining_Days is `Days_In_Month - Elapsed_Days`.
3. THE Forecast_Engine SHALL derive the Daily_Cost_Series and Month_To_Date_Cost from Cost Explorer `GetCostAndUsage` using UnblendedCost and excluding records of type Tax, consistent with Real_Invoice totals.
4. THE Forecast_Engine SHALL set Median_Daily_Cost to the median of the Daily_Cost_Series, computed as the middle value when Elapsed_Days is odd and the mean of the two middle values when Elapsed_Days is even.
5. THE Forecast_Engine SHALL analyze the most recent Closed_Month available from Cost Explorer (the single month immediately preceding the Current_Month) to detect each Fixed_Cost_Component and assign its Fixed_Cost_Model, recording for each detected component both its absolute monetary amount and its share of that month's total so that the component can be applied as either a fixed monetary amount per month or a percentage of the monthly total.
6. THE Forecast_Engine SHALL compute the Fixed_Cost_Forecast by applying each detected Fixed_Cost_Model to the Current_Month and summing the results.
7. IF no Fixed_Cost_Component is detected from the available Closed_Months, THEN THE Forecast_Engine SHALL set the Fixed_Cost_Forecast to zero.
8. IF Elapsed_Days is zero, THEN THE Forecast_Engine SHALL omit the Forecast_Invoice for the Current_Month.
9. THE Forecast_Engine SHALL round the Forecast_Total to 2 decimal places using round-half-up.
10. THE Forecast_Engine SHALL record the Forecast_Total in USD using the same currency convention as Real_Invoice records.
11. IF Cost Explorer retrieval of the Daily_Cost_Series or Month_To_Date_Cost fails, THEN THE Forecast_Engine SHALL omit the Forecast_Invoice for the Current_Month, SHALL retain any prior invoice record unchanged, and SHALL return an indication that the forecast is unavailable.

### Requirement 9: Present the forecast invoice in the Invoice Explorer list

**User Story:** As a member, I want the forecast invoice to appear in the same list as my real invoices, so that I see all monthly costs in one place.

#### Acceptance Criteria

1. WHEN the Invoice_Explorer list is requested for an account during the forecast window (from the 4th calendar day of the Current_Month through the day the Real_Invoice for the Current_Month is issued), THE Invoice_Explorer SHALL include exactly one Forecast_Invoice for the Current_Month in the returned items.
2. IF the Real_Invoice for the Current_Month has already been issued at the time the list is requested, THEN THE Invoice_Explorer SHALL NOT include a Forecast_Invoice for the Current_Month in the returned items.
3. WHEN the Invoice_Explorer includes a Forecast_Invoice for an account, THE Invoice_Explorer SHALL set the Forecast_Invoice "Issued By" value to the identical issuer value used on the most recent Real_Invoice for that same account.
4. IF the account has no prior Real_Invoice from which to derive the issuer value, THEN THE Invoice_Explorer SHALL set the Forecast_Invoice "Issued By" value to the account's configured default issuer value.
5. WHEN the Invoice_Explorer renders a Forecast_Invoice, THE Invoice_Explorer SHALL display the em-dash placeholder character ("—", U+2014) as the sole content of the "Payment Date" column.
6. WHEN the Invoice_Explorer list is sorted by the default sort, THE Invoice_Explorer SHALL position the Forecast_Invoice for the Current_Month at the first (top) ordinal position, ahead of all Real_Invoices, regardless of the empty Payment Date value.

### Requirement 10: Supersede the forecast with actuals once the month closes

**User Story:** As a member, I want the forecast to be replaced by the real invoice after the month ends, so that historical months always show actual costs.

#### Acceptance Criteria

1. WHEN the Current_Month transitions to a Closed_Month (at 00:00 UTC on the first day of the following calendar month), THE Forecast_Engine SHALL produce exactly one Real_Invoice for that Closed_Month for the account, based on actual cost data for that account and month.
2. WHILE a Real_Invoice exists for a given account and month, THE Invoice_Explorer SHALL NOT display a Forecast_Invoice for that same account and month.
3. WHEN the Invoice_Explorer data for an account is refreshed after the Current_Month has changed, THE Forecast_Engine SHALL replace the prior `Forecast-<YYYY-MM>` record for the now-Closed_Month with the Real_Invoice record for that account and month.
4. THE Invoice_Explorer SHALL display at most one invoice record per account per month, giving precedence to the Real_Invoice over any Forecast_Invoice for the same account and month.
5. IF actual cost data for a Closed_Month is unavailable when the Forecast_Engine attempts to produce the Real_Invoice, THEN THE Forecast_Engine SHALL retain the existing `Forecast-<YYYY-MM>` record unchanged and display an indication to the member that actual costs for that month are pending.

### Requirement 11: Forecast provider scope

**User Story:** As a member, I want forecasting to apply only to AWS accounts, so that projections are produced only where the run-rate and fixed-cost model are accurate.

#### Acceptance Criteria

1. WHERE an account's Provider_Key is exactly equal to `aws` (case-insensitive, trimmed of surrounding whitespace), WHEN the Forecast_Engine runs during the forecast window, THE Forecast_Engine SHALL produce exactly one Forecast_Invoice for that account for the Current_Month.
2. WHERE an account's Provider_Key is any value other than `aws` (including provider keys such as `openai`, `azure`, `gcp`, or any unrecognized value), WHEN the Forecast_Engine runs during the forecast window, THE Forecast_Engine SHALL produce zero Forecast_Invoice records for that account.
3. IF an account's Provider_Key is null, empty, or absent, THEN THE Forecast_Engine SHALL treat the account as non-AWS, SHALL produce zero Forecast_Invoice records for that account, and SHALL record a skip indication identifying the account and the reason (missing Provider_Key).
4. WHEN the Forecast_Engine processes a set of accounts containing a mix of AWS and non-AWS Provider_Key values, THE Forecast_Engine SHALL produce Forecast_Invoice records only for the accounts whose Provider_Key is `aws` and SHALL leave all other accounts unchanged with no Forecast_Invoice produced.

### Requirement 12: Forecast caching consistency

**User Story:** As a member, I want the forecast to reflect recent usage without stale data lingering, so that the projection stays meaningful as the month progresses.

#### Acceptance Criteria

1. WHEN a Forecast_Invoice is stored, THE Forecast_Engine SHALL persist a record type attribute set to the value "forecast" on the stored record so that it is distinguishable from cached Real_Invoice records, which carry a record type attribute set to "real".
2. WHEN the Invoice_Explorer requests a cached Forecast_Invoice whose stored Current_Month value matches the current calendar month and year in UTC, THE Forecast_Engine SHALL return the cached Forecast_Invoice without recomputation.
3. WHEN the Invoice_Explorer requests a cached Forecast_Invoice whose stored Current_Month value does not match the current calendar month and year in UTC, THE Forecast_Engine SHALL recompute the Forecast_Invoice for the current calendar month and replace the stale cached record before returning a result, and SHALL NOT return the stale Forecast_Invoice.
4. IF recomputation of a stale Forecast_Invoice fails, THEN THE Forecast_Engine SHALL remove the stale Forecast_Invoice from the cache and return a result containing no forecast projection together with an error indication that the forecast is unavailable.

### Requirement 13: Scheduled monthly full refresh

**User Story:** As the platform operator, I want a scheduled job to refresh every customer's invoice data on the 7th of each month, so that the prior month is finalized as actuals and the new month's forecast is established without each member having to click Refresh.

#### Acceptance Criteria

1. WHEN the current date in UTC reaches the 7th calendar day of the month, THE Monthly_Refresh_Job SHALL run exactly once and perform a full invoice refresh for every member and every account owned by each member.
2. WHEN the Monthly_Refresh_Job processes an account, THE Monthly_Refresh_Job SHALL rebuild that account's Real_Invoice records (including the now-Closed_Month that just ended) and SHALL recompute the Current_Month Forecast_Invoice for AWS accounts.
3. WHEN the Monthly_Refresh_Job rebuilds invoice data for an account, THE Monthly_Refresh_Job SHALL invalidate that account's cached `INV#` invoice-list records so the rebuilt data replaces the prior cache.
4. IF the refresh for an individual account fails, THEN THE Monthly_Refresh_Job SHALL record the failure for that account and SHALL continue processing the remaining accounts without aborting the entire run.
5. THE Monthly_Refresh_Job SHALL be idempotent, such that running it more than once on the 7th produces the same resulting invoice records as a single run.

## Confirmed Decisions

1. **Projection method (Requirement 8):** Two-part projection. Variable/daily portion = `Month_To_Date_Cost + (Median_Daily_Cost × Remaining_Days)`, where the median is taken over the elapsed days of the current month. Fixed/recurring charges are detected from historical closed months (each classified as a fixed monthly amount or a percentage of the monthly total) and added on top.
2. **Forecast Payment Date and Status (Requirements 7, 9):** The Payment Date column shows an em-dash placeholder ("—") for forecast rows. The status is `Forecast`, displayed as a visually distinct status indicator.
3. **Provider scope (Requirement 11):** Forecasting applies to AWS accounts only.
4. **Rename surfaces (Requirements 4, 5):** All enumerated user-facing surfaces are renamed to "AI Cost"; internal Provider_Key values, API routes, encryption contexts, and identifiers remain unchanged. The Configure-wizard product detail text ("ChatGPT, GPT-4, DALL-E, Whisper") is retained unchanged.
5. **Empty/zero forecast handling (Requirements 6, 8):** The forecast is omitted entirely when there is no usable month-to-date cost or zero elapsed days.
6. **Scheduled persistence (Requirement 13):** A scheduled job runs on the 7th of each month (UTC) and performs a full invoice refresh for all members and all their accounts — finalizing the prior month as actuals and recomputing the current-month forecast. The on-demand Refresh button remains available between scheduled runs.
7. **Fixed-cost detection window (Requirement 8.5):** Fixed-cost components and their model (fixed amount vs percentage of monthly total) are seeded from the single most recent closed month, then applied to the current-month forecast calculation.
