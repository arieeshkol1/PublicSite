# Requirements Document

## Introduction

Add Account ID as a hierarchy level in the invoice explorer view. The current drilldown hierarchy is Month > Service > Sub-service. This feature introduces the Account level between Month and Service, creating: Month > Account > Service > Sub-service. The Account ID is displayed both as a static header/badge above the invoice table when an account is selected and as a field in each invoice row. The Account ID value is sourced from the parsed invoice PDF (bill_parser.py) with a fallback to connected account metadata in DynamoDB.

## Glossary

- **Invoice_Explorer**: The tabular interface within the member portal for browsing, filtering, and drilling into invoices across connected accounts.
- **Account_ID**: A provider account identifier (e.g., 12-digit number for cloud providers) that identifies the billing account associated with an invoice.
- **Drilldown_Hierarchy**: The navigational structure for exploring invoice data at increasing levels of granularity: Month > Account > Service > Sub-service.
- **Account_Header**: A static information badge displayed above the invoice table showing the currently selected Account ID.
- **Invoice_Row**: A single data record displayed in the invoice table representing one invoice or billing line item.
- **Bill_Parser**: The existing module (bill_parser.py) that extracts metadata including account_id from uploaded invoice PDFs.
- **Account_Metadata**: The connected account records stored in the MemberPortal-Accounts DynamoDB table containing account identifiers linked to member profiles.
- **Invoice_Drilldown**: The existing backend module (invoice_drilldown.py) that provides hierarchical invoice data endpoints.
- **Account_Selector**: The existing dropdown component in the invoice explorer that allows members to select which connected account to view.

## Requirements

### Requirement 1: Account ID Field in Invoice Data

**User Story:** As a member, I want to see the Account ID associated with each invoice record, so that I can identify which billing account generated each charge.

#### Acceptance Criteria

1. THE Invoice_Explorer SHALL include an account_id field in each Invoice_Row returned by the invoice list endpoint.
2. WHEN the Bill_Parser has extracted an account_id from the invoice PDF, THE Invoice_Drilldown SHALL use the parsed account_id value for the Invoice_Row.
3. WHEN the Bill_Parser has not extracted an account_id from the invoice PDF, THE Invoice_Drilldown SHALL fall back to the Account_ID from the connected Account_Metadata in DynamoDB.
4. WHEN neither the Bill_Parser nor the Account_Metadata provides an Account_ID, THE Invoice_Drilldown SHALL set the account_id field to the string "N/A".
5. THE Invoice_Explorer SHALL display the account_id field as a visible column in the invoice table.

### Requirement 2: Account Header Display

**User Story:** As a member, I want to see the selected Account ID prominently displayed above the invoice table, so that I always know which account's data I am viewing.

#### Acceptance Criteria

1. WHEN a member selects an account from the Account_Selector, THE Invoice_Explorer SHALL display an Account_Header badge above the invoice table showing the selected Account_ID.
2. WHILE an account is selected, THE Account_Header SHALL remain visible regardless of pagination, sorting, or filtering applied to the invoice table.
3. WHEN no account is selected, THE Invoice_Explorer SHALL hide the Account_Header.
4. WHEN the selected account changes, THE Invoice_Explorer SHALL update the Account_Header to reflect the newly selected Account_ID within 100 milliseconds of the selection event.

### Requirement 3: Hierarchy Level Integration

**User Story:** As a member, I want to drill down from Month to Account to Service to Sub-service, so that I can explore my costs at each level of detail.

#### Acceptance Criteria

1. THE Invoice_Explorer SHALL present the drilldown hierarchy in the order: Month > Account > Service > Sub-service.
2. WHEN a member selects a month, THE Invoice_Explorer SHALL display the list of accounts with invoices for that month.
3. WHEN a member selects an account within a month, THE Invoice_Explorer SHALL display the service-level breakdown for that account and month combination.
4. WHEN a member navigates from the service level back up, THE Invoice_Explorer SHALL return to the account-level view for the same month.
5. THE Invoice_Explorer SHALL include the Account_ID in breadcrumb navigation between hierarchy levels.

### Requirement 4: Account ID Data Source Resolution

**User Story:** As a member, I want the system to reliably determine the Account ID for each invoice, so that the account information is accurate even when one source is unavailable.

#### Acceptance Criteria

1. WHEN syncing invoice data, THE Invoice_Drilldown SHALL first attempt to read the account_id from the parsed invoice PDF via Bill_Parser.
2. WHEN the Bill_Parser returns an account_id value other than "N/A" and the value is non-empty, THE Invoice_Drilldown SHALL treat the parsed value as authoritative.
3. IF the Bill_Parser returns "N/A" or an empty account_id, THEN THE Invoice_Drilldown SHALL retrieve the Account_ID from the Account_Metadata record matching the connected account.
4. THE Invoice_Drilldown SHALL store the resolved Account_ID in the DynamoDB invoice cache alongside each invoice record.
5. THE Invoice_Drilldown SHALL resolve the Account_ID once at sync time and serve the cached value on subsequent reads without re-resolving.

### Requirement 5: Account-Level Aggregation

**User Story:** As a member, I want to see total costs grouped by Account ID within a month, so that I can compare spending across accounts.

#### Acceptance Criteria

1. WHEN displaying the account-level view for a selected month, THE Invoice_Explorer SHALL show each Account_ID with its aggregated total cost for that month.
2. THE Invoice_Explorer SHALL sort accounts by total cost descending within the month-level view.
3. THE Invoice_Explorer SHALL display the number of services with charges alongside each account in the aggregation view.
4. WHEN a member has a single connected account, THE Invoice_Explorer SHALL still display the account-level view with that single account's total.

### Requirement 6: Account ID in CSV Export

**User Story:** As a member, I want the Account ID included when I export invoice data to CSV, so that the exported file identifies which account generated each charge.

#### Acceptance Criteria

1. WHEN a member exports invoice data to CSV, THE Invoice_Explorer SHALL include the account_id as a column in the exported file.
2. THE Invoice_Explorer SHALL position the account_id column immediately after the month column and before the service column in the CSV output.
3. WHEN the account_id value is "N/A", THE Invoice_Explorer SHALL write the literal string "N/A" in the CSV cell for that row.

### Requirement 7: Backend API Account Field

**User Story:** As a developer, I want the invoice API responses to include the Account ID field, so that the frontend can render account information without additional API calls.

#### Acceptance Criteria

1. THE Invoice_Drilldown SHALL include an "accountId" key in each item object returned by the GET /members/invoices/list endpoint response.
2. THE Invoice_Drilldown SHALL include an "accountId" key in the response of GET /members/invoices/services-breakdown endpoint.
3. WHEN the invoice data was synced from Cost Explorer, THE Invoice_Drilldown SHALL populate the accountId field with the account identifier used in the STS AssumeRole call.
4. THE Invoice_Drilldown SHALL accept an optional "groupByAccount" query parameter on the invoice list endpoint that, when set to "true", returns results grouped by Account_ID with per-account totals.

### Requirement 8: Account ID Validation

**User Story:** As a developer, I want the Account ID to be validated before storage and display, so that only properly formatted identifiers are shown to members.

#### Acceptance Criteria

1. WHEN resolving an Account_ID from the Bill_Parser, THE Invoice_Drilldown SHALL validate that the value matches the expected format for the account's provider before accepting the value.
2. IF the parsed Account_ID fails format validation, THEN THE Invoice_Drilldown SHALL discard the parsed value and fall back to the Account_Metadata source.
3. THE Invoice_Drilldown SHALL log a warning when a parsed Account_ID fails format validation, including the invalid value and the expected format.
