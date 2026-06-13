# Requirements Document

## Introduction

The Invoice Explorer in the SlashMyBill member portal currently lists monthly invoices for AWS accounts only. When the AWS Invoicing API is unavailable, AWS invoices are synthesized from Cost Explorer monthly aggregation: one record per month with `invoiceId` `"<YYYY-MM>-monthly"`, issuer `"Amazon Web Services"`, status `"paid"`, a payment date on the 15th of the following month, and a 90-day-TTL cache row in `MemberPortal-Invoices` under `INV#{invoiceId}` with `recordType` `"real"`.

This feature extends the same synthetic-monthly-invoice approach to every connected provider — AWS, Azure, GCP, and the OpenAI AI vendor — so that the per-account Invoice Explorer shows monthly invoices for whichever provider the selected account belongs to, using the identical five-column shape (Invoice ID, Issued By, Payment Date, Status, Total Amount) and the identical DynamoDB caching scheme. Non-AWS monthly cost data is retrieved through the existing provider connector abstraction (`member-handler/connectors/`), where each connector exposes `authenticate(credentials)` and `get_cost_data(auth_context, account_id, start_date, end_date)` and credentials are KMS-encrypted per account.

This feature is consistent with the prior `invoice-forecast-and-ai-cost-rename` spec: forecasting remains AWS-only (non-AWS accounts show real invoices but no forecast row), and the OpenAI provider's invoices display the issuer as "AI Cost" while the internal provider key remains `openai`.

This document records the requirements for review.

## Glossary

- **Member_Portal**: The SlashMyBill member-facing single-page application served from `members/` that renders the Invoice Explorer.
- **Invoice_Explorer**: The per-account invoice drill-down list within the Member_Portal. It has an account selector and displays five columns in fixed order: Invoice ID, Issued By, Payment Date, Status, and Total Amount.
- **Invoice_List_Service**: The backend handler for `GET /members/invoices/list` (`handle_invoice_list_request` in `member-handler/invoice_drilldown.py`) that returns the invoice list for the selected account.
- **Provider_Connector**: A concrete implementation of `ProviderConnector` (`member-handler/connectors/`) for one provider, exposing `authenticate(credentials)`, `test_connection(...)`, and `get_cost_data(auth_context, account_id, start_date, end_date)`. Registered connectors exist for `aws`, `azure`, `gcp`, and `openai`.
- **Provider_Key**: The internal, non-user-facing provider identifier stored on an account record, one of `aws`, `azure`, `gcp`, or `openai`.
- **Account_Record**: A row in `MemberPortal-Accounts`, keyed by `memberEmail`, holding `accountId` and `cloudProvider` (the Provider_Key). A missing, empty, or absent `cloudProvider` defaults to `aws`.
- **Selected_Account**: The Account_Record currently chosen in the Invoice_Explorer account selector, identified by its `accountId`.
- **Synthetic_Monthly_Invoice**: A generated invoice record representing one calendar month of cost for one account, modeled after the existing AWS Cost Explorer fallback record.
- **Invoice_Record**: A Synthetic_Monthly_Invoice persisted to or read from the cache, with fields `invoiceId`, `issuer`, `paymentDate`, `paymentStatus`, `totalAmount`, `currency`, and `period`.
- **Invoice_Cache**: The `MemberPortal-Invoices` DynamoDB table, where each Invoice_Record is stored under partition key `{memberEmail}#{accountId}`, sort key `INV#{invoiceId}`, with `recordType` `"real"` and a 90-day TTL.
- **Issuer_Label**: The provider-specific value stored in the `issuer` field of an Invoice_Record and shown in the "Issued By" column.
- **Cost_Data**: The result returned by a Provider_Connector's `get_cost_data` call for a date range, from which monthly totals are derived.
- **Billing_Period**: A calendar month expressed as `YYYY-MM`, used as the `period` field and as the basis for the `invoiceId` `"<YYYY-MM>-monthly"`.
- **Month_Total**: The cost total for one Billing_Period for one account, derived from Cost_Data and excluding tax, consistent with how AWS Month_Total is computed today.
- **Forecast_Engine**: The AWS-only current-month forecast logic from the `invoice-forecast-and-ai-cost-rename` spec that emits a `Forecast-<YYYY-MM>` row.
- **Refresh_Service**: The handler for `POST /members/invoices/refresh` (`handle_drilldown_refresh_request`) that clears cached records for an account and re-fetches invoice data.
- **Provider_Display_Name**: The user-facing issuer string shown in the "Issued By" column for each provider: "Amazon Web Services" for `aws`, "Microsoft Azure" for `azure`, "Google Cloud" for `gcp`, and "AI Cost" for `openai`.

## Requirements

### Requirement 1: Generate synthetic monthly invoices for every supported provider

**User Story:** As a member, I want monthly invoices for any connected account regardless of its provider, so that AWS, Azure, GCP, and AI vendor spend all appear in the Invoice Explorer.

#### Acceptance Criteria

1. WHEN the Invoice_List_Service builds invoices for a Selected_Account whose Provider_Key is `aws`, `azure`, `gcp`, or `openai`, THE Invoice_List_Service SHALL produce one Synthetic_Monthly_Invoice per Billing_Period for which that account's Month_Total is available.
2. THE Invoice_List_Service SHALL derive the Month_Total for a non-AWS Selected_Account from the Cost_Data returned by that account's Provider_Connector `get_cost_data` call, aggregated to one total per calendar month.
3. WHERE a Selected_Account's Provider_Key is `aws`, THE Invoice_List_Service SHALL produce Synthetic_Monthly_Invoice records using the existing AWS invoice-generation path without change to AWS behavior.
4. THE Invoice_List_Service SHALL set the `invoiceId` of each Synthetic_Monthly_Invoice to `"<YYYY-MM>-monthly"`, where `<YYYY-MM>` is the Billing_Period.
5. THE Invoice_List_Service SHALL set the `period` of each Synthetic_Monthly_Invoice to the Billing_Period in `YYYY-MM` format.
6. WHEN a Billing_Period's Month_Total has an absolute value less than 0.01 in the account's currency, THE Invoice_List_Service SHALL omit the Synthetic_Monthly_Invoice for that Billing_Period.

### Requirement 2: Aggregate provider cost data into monthly totals consistently

**User Story:** As a member, I want each provider's monthly invoice total to be computed the same way AWS totals are, so that amounts are comparable and predictable across providers.

#### Acceptance Criteria

1. WHEN the Invoice_List_Service requests Cost_Data for a non-AWS Selected_Account, THE Invoice_List_Service SHALL call that account's Provider_Connector `get_cost_data` with a `start_date` and `end_date` covering the reporting window of completed and in-progress months in `YYYY-MM-DD` format.
2. THE Invoice_List_Service SHALL group the returned Cost_Data by calendar month and sum each month's costs into a single Month_Total per Billing_Period.
3. THE Invoice_List_Service SHALL exclude tax-classified amounts from each Month_Total, consistent with the AWS Month_Total computation that excludes records of type Tax.
4. THE Invoice_List_Service SHALL round each Month_Total to 2 decimal places before storing it in the `totalAmount` field.
5. WHERE a provider reports cost amounts already denominated in United States dollars, THE Invoice_List_Service SHALL record the Month_Total in United States dollars.

### Requirement 3: Apply provider-specific issuer labels

**User Story:** As a member, I want each invoice to show which provider issued it, so that I can tell AWS, Azure, GCP, and AI vendor invoices apart in one list.

#### Acceptance Criteria

1. WHERE a Synthetic_Monthly_Invoice is generated for a Selected_Account whose Provider_Key is `aws`, THE Invoice_List_Service SHALL set its Issuer_Label to the exact text "Amazon Web Services".
2. WHERE a Synthetic_Monthly_Invoice is generated for a Selected_Account whose Provider_Key is `azure`, THE Invoice_List_Service SHALL set its Issuer_Label to the exact text "Microsoft Azure".
3. WHERE a Synthetic_Monthly_Invoice is generated for a Selected_Account whose Provider_Key is `gcp`, THE Invoice_List_Service SHALL set its Issuer_Label to the exact text "Google Cloud".
4. WHERE a Synthetic_Monthly_Invoice is generated for a Selected_Account whose Provider_Key is `openai`, THE Invoice_Explorer SHALL display the "Issued By" column value as the exact text "AI Cost".
5. THE Invoice_List_Service SHALL leave every stored Provider_Key value byte-for-byte unchanged, such that the "AI Cost" issuer display for `openai` accounts is applied at the presentation layer and does not alter the stored Provider_Key.
6. WHEN the Invoice_Explorer renders the "Issued By" column for a Selected_Account, THE Invoice_Explorer SHALL display the Provider_Display_Name corresponding to that account's Provider_Key.

### Requirement 4: Return provider-appropriate invoices through the existing endpoint and shape

**User Story:** As a member, I want the same invoice list endpoint and the same columns for every account, so that switching the account selector to a non-AWS account works exactly like AWS.

#### Acceptance Criteria

1. WHEN a member requests `GET /members/invoices/list` for a Selected_Account, THE Invoice_List_Service SHALL return invoice items for that account regardless of the account's Provider_Key.
2. THE Invoice_List_Service SHALL return each invoice item with the fields `invoiceId`, `issuer`, `paymentDate`, `paymentStatus`, `totalAmount`, `currency`, and `period`, matching the existing AWS response shape.
3. THE Invoice_Explorer SHALL render every returned invoice item using the same five columns, in the same order, for all providers: Invoice ID, Issued By, Payment Date, Status, and Total Amount.
4. WHEN the Invoice_List_Service requests an account whose ownership cannot be confirmed for the authenticated member, THE Invoice_List_Service SHALL return an access-denied response and SHALL NOT return invoice items for that account.
5. THE Invoice_List_Service SHALL apply the existing pagination and sorting parameters (`page`, `pageSize`, `sortBy`, `sortOrder`) to non-AWS invoice items identically to AWS invoice items.

### Requirement 5: Cache provider invoices using the existing DynamoDB scheme

**User Story:** As a member, I want non-AWS invoices to load quickly on repeat visits, so that the experience matches AWS and avoids repeated provider API calls.

#### Acceptance Criteria

1. WHEN the Invoice_List_Service generates Synthetic_Monthly_Invoice records for any provider, THE Invoice_List_Service SHALL write each record to the Invoice_Cache under partition key `{memberEmail}#{accountId}` and sort key `INV#{invoiceId}`.
2. THE Invoice_List_Service SHALL set `recordType` to the value `"real"` on every cached Synthetic_Monthly_Invoice, identical to the AWS caching scheme.
3. THE Invoice_List_Service SHALL set a time-to-live of 90 days on every cached Synthetic_Monthly_Invoice.
4. WHEN cached Invoice_Record items exist for a Selected_Account at request time, THE Invoice_List_Service SHALL return the cached items without calling the Provider_Connector.
5. WHEN no cached Invoice_Record items exist for a Selected_Account at request time, THE Invoice_List_Service SHALL generate the records, store them in the Invoice_Cache, and then return them.

### Requirement 6: Retrieve and decrypt per-account credentials for cost retrieval

**User Story:** As a member, I want my stored provider credentials used securely to fetch my costs, so that non-AWS invoices are generated without exposing my secrets.

#### Acceptance Criteria

1. WHEN the Invoice_List_Service needs Cost_Data for a non-AWS Selected_Account, THE Invoice_List_Service SHALL retrieve that account's KMS-encrypted credentials and obtain an authenticated context by calling the account's Provider_Connector `authenticate`.
2. WHERE a Provider_Connector requires an encryption context to decrypt credentials, THE Invoice_List_Service SHALL supply the account's `memberEmail` and `accountId` as that encryption context.
3. THE Invoice_List_Service SHALL NOT include any decrypted credential value or plaintext secret in any returned invoice item, response body, or log message.
4. IF decryption or authentication for a Selected_Account fails, THEN THE Invoice_List_Service SHALL omit that account's provider-sourced invoices, SHALL return any previously cached Invoice_Record items unchanged, and SHALL include an indication that invoice data for that account is currently unavailable.

### Requirement 7: Handle provider cost-retrieval failures gracefully

**User Story:** As a member, I want the invoice list to keep working when one provider's cost API is unavailable, so that a single failure does not break the page.

#### Acceptance Criteria

1. IF a Provider_Connector `get_cost_data` call for a Selected_Account fails or returns no usable Cost_Data, THEN THE Invoice_List_Service SHALL return a successful response containing any available cached Invoice_Record items for that account.
2. IF a Provider_Connector `get_cost_data` call for a Selected_Account fails, THEN THE Invoice_List_Service SHALL include in the response an unavailable indication identifying that provider invoice data could not be retrieved.
3. WHEN a Provider_Connector `get_cost_data` call for a Selected_Account fails, THE Invoice_List_Service SHALL retain any existing cached Invoice_Record items for that account without deleting or overwriting them.
4. WHILE a Selected_Account has no cached Invoice_Record items and its Provider_Connector cost retrieval is failing, THE Invoice_Explorer SHALL display an empty invoice list together with the unavailable indication and SHALL NOT display an application error page.

### Requirement 8: Coexist with the AWS-only forecast

**User Story:** As a member, I want a forecast row only where forecasting is supported, so that non-AWS accounts correctly show real invoices without a misleading projection.

#### Acceptance Criteria

1. WHERE a Selected_Account's Provider_Key is exactly `aws`, THE Invoice_List_Service SHALL allow the Forecast_Engine to add at most one `Forecast-<YYYY-MM>` row for the current month, consistent with the existing forecast behavior.
2. WHERE a Selected_Account's Provider_Key is any value other than `aws`, THE Invoice_List_Service SHALL return only Synthetic_Monthly_Invoice records and SHALL NOT include any forecast row.
3. WHEN the Invoice_Explorer renders invoices for a non-AWS Selected_Account, THE Invoice_Explorer SHALL display only real monthly invoices and SHALL NOT display a row whose status is "Forecast".
4. THE addition of multi-provider invoices SHALL NOT change the existing AWS forecast behavior for accounts whose Provider_Key is `aws`.

### Requirement 9: Mirror refresh behavior for non-AWS accounts

**User Story:** As a member, I want the Refresh action to work for any provider, so that I can force up-to-date invoices for Azure, GCP, and AI vendor accounts just like AWS.

#### Acceptance Criteria

1. WHEN a member triggers `POST /members/invoices/refresh` for a non-AWS Selected_Account, THE Refresh_Service SHALL clear that account's cached `INV#` Invoice_Record items and regenerate them from the account's Provider_Connector Cost_Data.
2. THE Refresh_Service SHALL apply the same 5-minute per-account cooldown to non-AWS accounts that it applies to AWS accounts.
3. IF regeneration during refresh fails for a non-AWS Selected_Account, THEN THE Refresh_Service SHALL return an error indication that the refresh could not be completed and SHALL retain the prior cached Invoice_Record items for that account.
4. WHEN a refresh for a non-AWS Selected_Account completes successfully, THE Refresh_Service SHALL return a success result equivalent to the AWS refresh success result.

### Requirement 10: Record currency per provider

**User Story:** As a member, I want each invoice to carry the correct currency, so that amounts are not misrepresented across providers.

#### Acceptance Criteria

1. THE Invoice_List_Service SHALL set the `currency` field of each Synthetic_Monthly_Invoice to the currency in which that account's Month_Total is denominated.
2. WHERE a Selected_Account's Provider_Connector reports cost amounts in United States dollars, THE Invoice_List_Service SHALL set the `currency` field of that account's Synthetic_Monthly_Invoice records to `"USD"`.
3. WHEN the Invoice_Explorer renders the "Total Amount" column for an invoice item, THE Invoice_Explorer SHALL display the amount together with the `currency` value carried by that invoice item.
4. THE Invoice_List_Service SHALL set the `currency` field for AWS Synthetic_Monthly_Invoice records to `"USD"`, unchanged from existing behavior.

### Requirement 11: Assign payment date and status consistent with the AWS synthetic model

**User Story:** As a member, I want non-AWS monthly invoices to show a sensible payment date and status, so that the list reads consistently with AWS synthetic invoices.

#### Acceptance Criteria

1. THE Invoice_List_Service SHALL set the `paymentDate` of each Synthetic_Monthly_Invoice to the 15th day of the calendar month immediately following its Billing_Period, in `YYYY-MM-DD` format, consistent with the AWS synthetic invoice model.
2. THE Invoice_List_Service SHALL set the `paymentStatus` of each Synthetic_Monthly_Invoice to the value `"paid"`, consistent with the AWS synthetic invoice model.
3. WHEN the Invoice_Explorer renders the "Status" column for a Synthetic_Monthly_Invoice, THE Invoice_Explorer SHALL display the value of that invoice item's `paymentStatus`.
4. WHERE an invoice item has a missing or empty `issuer` value, THE Invoice_Explorer SHALL display the Provider_Display_Name for the Selected_Account's Provider_Key and SHALL NOT display an empty "Issued By" column.
