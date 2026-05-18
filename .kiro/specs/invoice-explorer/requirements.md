# Requirements Document

## Introduction

Invoice Explorer is a feature within the SlashMyBill member portal that provides members with a structured, tabular interface to browse, search, and drill into their AWS invoices across all connected accounts. The feature caches normalized invoice data in DynamoDB for fast retrieval and supports filtering, pagination, sorting, and CSV export. It integrates with the existing cross-account IAM role assumption model and is served through the existing member-handler Lambda.

## Glossary

- **Invoice_Explorer**: The tabular interface feature within the member portal for browsing AWS invoice data
- **Member_Handler_Lambda**: The existing AWS Lambda function that serves member portal API requests
- **Invoice_Cache**: The DynamoDB table (MemberPortal-Invoices) storing normalized invoice records
- **Cost_Explorer_API**: AWS Cost Explorer GetCostAndUsage API used as the invoice data source
- **Invoice_Sync_Service**: The component within Member Handler Lambda that fetches and normalizes invoice data from customer AWS accounts
- **Member_Portal_Frontend**: The browser-based SPA served from S3 via CloudFront at the /members/ path
- **Cross_Account_Role**: The IAM role (SlashMyBill-{AccountID}) assumed via STS to access customer AWS accounts

## Requirements

### Requirement 1: Account Ownership Verification

**User Story:** As a member, I want the system to enforce that I can only access invoices for my own connected accounts, so that my billing data remains private and secure.

#### Acceptance Criteria

1. WHEN an API request that includes an accountId parameter is received, THE Member_Handler_Lambda SHALL query the Accounts_Table to verify that every requested accountId is associated with the authenticated member's email before returning any data
2. IF one or more requested accountIds do not belong to the authenticated member, THEN THE Member_Handler_Lambda SHALL return a 403 error indicating which accountId failed the ownership check, and log the unauthorized access attempt including the member's email and the attempted accountId
3. IF an API request requires an accountId but none is provided, THEN THE Member_Handler_Lambda SHALL return a 400 error indicating the missing parameter
4. THE Member_Handler_Lambda SHALL never return invoice or cost data belonging to a different member regardless of the request parameters provided, including cases where multiple accountIds are submitted in a single request

### Requirement 2: Invoice Data Retrieval with Caching

**User Story:** As a member, I want to browse my invoice data quickly without waiting for live AWS API calls, so that I can explore my spending history efficiently.

#### Acceptance Criteria

1. WHEN a member requests invoice data for an account and month that exists in the Invoice_Cache, THE Member_Handler_Lambda SHALL return the cached data without calling the Cost_Explorer_API
2. WHEN a member requests invoice data for an account and month not present in the Invoice_Cache, THE Invoice_Sync_Service SHALL fetch the data from the Cost_Explorer_API via cross-account role assumption and store it in the Invoice_Cache before returning it, with a timeout of 30 seconds for the API call
3. WHEN invoice data is fetched from the Cost_Explorer_API, THE Invoice_Sync_Service SHALL normalize it into flat DynamoDB records containing service name, cost (stored to 2 decimal places in USD), usage types, daily costs, and region
4. THE Invoice_Cache SHALL apply a TTL of 90 days to all invoice records for automatic cleanup
5. IF the Cost_Explorer_API call fails or times out during a cache-miss fetch, THEN THE Invoice_Sync_Service SHALL return an error response indicating the data could not be retrieved and SHALL NOT store partial or empty records in the Invoice_Cache

### Requirement 3: Server-Side Pagination

**User Story:** As a member, I want to page through large sets of invoice data without the browser becoming slow, so that I can explore accounts with extensive billing history.

#### Acceptance Criteria

1. WHEN a paginated invoice query is made with valid page and pageSize parameters, THE Member_Handler_Lambda SHALL return only the items for the requested page along with pagination metadata (page, pageSize, totalItems, totalPages)
2. IF pagination parameters are not specified in the request, THEN THE Member_Handler_Lambda SHALL default to page 1 with a pageSize of 50
3. IF the requested pageSize exceeds 200 or is less than 1, THEN THE Member_Handler_Lambda SHALL clamp the value to the nearest bound (minimum 1, maximum 200) and return results using the clamped pageSize
4. IF the requested page number is less than 1 or exceeds totalPages, THEN THE Member_Handler_Lambda SHALL return an empty items array with the correct pagination metadata (totalItems, totalPages) and the requested page number
5. WHEN iterating through all pages of a result set, THE Member_Handler_Lambda SHALL return results in a stable sort order (by invoice date descending, then by item identifier ascending) such that exactly totalItems records are returned with no duplicates and no missing items across all pages
6. THE Member_Handler_Lambda SHALL require a valid Member_Token to access paginated invoice queries

### Requirement 4: Filtering and Search

**User Story:** As a member, I want to filter invoices by service, date, cost range, and free-text search, so that I can quickly find specific spending items.

#### Acceptance Criteria

1. WHEN a service filter is applied, THE Member_Handler_Lambda SHALL return only invoice items whose AWS service name exactly matches the specified filter value using case-insensitive comparison
2. WHEN a month filter is applied, THE Member_Handler_Lambda SHALL return only invoice items for the specified billing month
3. WHEN minCost and/or maxCost filters are applied, THE Member_Handler_Lambda SHALL return only invoice items whose cost is greater than or equal to minCost and less than or equal to maxCost (inclusive boundaries), where cost values are compared with two decimal places of precision
4. WHEN a search query is provided, THE Member_Handler_Lambda SHALL return invoice items where the service name or usage type contains the search text using case-insensitive substring matching
5. WHEN multiple filters are applied simultaneously, THE Member_Handler_Lambda SHALL combine all active filters using AND logic, returning only items that satisfy every specified filter criterion
6. WHEN applied filters match zero invoice items, THE Member_Handler_Lambda SHALL return an empty items array with totalItems set to 0 and totalPages set to 0
7. WHEN a search query of fewer than 1 character is provided, THE Member_Handler_Lambda SHALL ignore the search filter and return results as if no search query was specified

### Requirement 5: Sorting

**User Story:** As a member, I want to sort invoice data by cost, service name, or date, so that I can identify my highest-spend items or organize data chronologically.

#### Acceptance Criteria

1. WHEN sortBy is set to "cost" and sortOrder is "desc", THE Member_Handler_Lambda SHALL return items ordered from highest cost to lowest cost
2. WHEN sortBy is set to "cost" and sortOrder is "asc", THE Member_Handler_Lambda SHALL return items ordered from lowest cost to highest cost
3. WHEN sortBy is set to "service", THE Member_Handler_Lambda SHALL return items ordered alphabetically by service name using case-insensitive comparison, with ascending as the default sortOrder
4. WHEN sortBy is set to "date", THE Member_Handler_Lambda SHALL return items ordered by billing month, with descending (most recent first) as the default sortOrder
5. IF sortBy is not specified, THEN THE Member_Handler_Lambda SHALL default to sorting by cost in descending order
6. IF sortBy contains a value other than "cost", "service", or "date", THEN THE Member_Handler_Lambda SHALL return a 400 error with a message indicating the valid sortBy values
7. WHEN two or more items have equal values for the active sort field, THE Member_Handler_Lambda SHALL apply a secondary sort by cost descending to produce a deterministic order

### Requirement 6: Cost Aggregation and Summary

**User Story:** As a member, I want to see spending summaries including totals, month-over-month changes, and top services, so that I can quickly understand my cost trends.

#### Acceptance Criteria

1. WHEN a summary is requested for an account, THE Member_Handler_Lambda SHALL return the total cost equal to the sum of all individual invoice item costs for the current calendar month (within ±0.01 precision)
2. WHEN a summary is requested and the previous calendar month contains at least one invoice item with cost greater than zero, THE Member_Handler_Lambda SHALL calculate and return the month-over-month percentage change as ((currentMonthTotal − previousMonthTotal) / previousMonthTotal × 100) rounded to one decimal place
3. IF the previous calendar month has no invoice items or a total cost of zero, THEN THE Member_Handler_Lambda SHALL return a month-over-month change value of 0
4. WHEN a summary is requested, THE Member_Handler_Lambda SHALL identify and return the top 5 services ranked by spend in descending order, each including its cost (rounded to 2 decimal places) and percentage of total spend (rounded to 1 decimal place)
5. IF no invoice items exist for the requested account in the current calendar month, THEN THE Member_Handler_Lambda SHALL return a total cost of 0, a month-over-month change of 0, and an empty top services list

### Requirement 7: Invoice Data Refresh

**User Story:** As a member, I want to manually refresh my invoice data to get the latest figures from AWS, so that I can see up-to-date spending when needed.

#### Acceptance Criteria

1. WHEN a refresh request is submitted, THE Invoice_Sync_Service SHALL fetch fresh data from the Cost_Explorer_API for the specified months (maximum 6 months per request) and replace the existing cached records for those months
2. WHEN a refresh completes successfully, THE Invoice_Sync_Service SHALL update the lastSyncedAt timestamp on all affected records to the current time
3. IF a refresh request is made for an account that was refreshed within the last 5 minutes, THEN THE Member_Handler_Lambda SHALL return a 429 response including the number of seconds remaining in the cooldown period
4. THE Member_Handler_Lambda SHALL allow only one successful refresh per account within any 5-minute window
5. IF the Cost_Explorer_API returns an error during a refresh, THEN THE Invoice_Sync_Service SHALL preserve the existing cached records unchanged and return an error response indicating which months failed to refresh

### Requirement 8: Input Validation

**User Story:** As a developer, I want the API to validate all input parameters strictly, so that malformed requests are rejected early with clear error messages.

#### Acceptance Criteria

1. WHEN a month parameter is provided, THE Member_Handler_Lambda SHALL validate it matches the format YYYY-MM where YYYY is between 2015 and the current year and MM is between 01 and 12
2. IF an invalid month format is provided, THEN THE Member_Handler_Lambda SHALL return a 400 error with the message "Month must be in YYYY-MM format"
3. IF an accountId is provided that does not match exactly 12 digits, THEN THE Member_Handler_Lambda SHALL return a 400 error with a message indicating the account ID must be a 12-digit number
4. THE Member_Handler_Lambda SHALL validate that pageSize is an integer between 1 and 200 inclusive, and that page is an integer greater than or equal to 1
5. IF pageSize or page fails validation, THEN THE Member_Handler_Lambda SHALL return a 400 error with a message indicating the invalid parameter and its allowed range
6. IF pageSize is not provided, THEN THE Member_Handler_Lambda SHALL default pageSize to 50; IF page is not provided, THEN THE Member_Handler_Lambda SHALL default page to 1

### Requirement 9: Frontend Invoice Explorer Interface

**User Story:** As a member, I want a dedicated tab in my portal dashboard to explore invoices with an interactive table, filters, and summary cards, so that I have a clear visual overview of my spending.

#### Acceptance Criteria

1. THE Member_Portal_Frontend SHALL render the Invoice Explorer as a new tab in the existing member portal navigation, accessible to authenticated members
2. THE Member_Portal_Frontend SHALL display summary cards showing total spend (formatted as currency), month-over-month change (as a percentage with positive/negative indicator), and top service by cost for the currently applied filters
3. THE Member_Portal_Frontend SHALL provide a filter bar with account selector (populated from the member's connected accounts), month picker (allowing selection within the last 12 months), service dropdown (populated from available services in the data), and a text search input that matches against service name and region
4. WHEN filters are applied, THE Member_Portal_Frontend SHALL update the table and summary cards to reflect only the matching invoice data
5. THE Member_Portal_Frontend SHALL render invoice data in a sortable, paginated table with columns for service, cost, month, and region, displaying 25 rows per page by default and sorted by cost descending
6. WHEN a table row is expanded, THE Member_Portal_Frontend SHALL display the daily cost breakdown for that service and month as a list of date and cost pairs
7. THE Member_Portal_Frontend SHALL provide a CSV export button that downloads the currently filtered result set including all table columns
8. IF the invoice data API request fails, THEN THE Member_Portal_Frontend SHALL display an error notification with the error message and a retry option
9. IF no invoice data matches the applied filters, THEN THE Member_Portal_Frontend SHALL display a message indicating no results were found and suggesting the member adjust filters
10. WHILE invoice data is loading, THE Member_Portal_Frontend SHALL display a loading indicator in the table and summary card areas

### Requirement 10: Error Handling and User Feedback

**User Story:** As a member, I want clear error messages and appropriate UI states when something goes wrong, so that I understand what happened and how to fix it.

#### Acceptance Criteria

1. WHEN no AWS accounts are connected, THE Member_Portal_Frontend SHALL display a message directing the member to connect an account
2. WHEN invoice data is loading, THE Member_Portal_Frontend SHALL display a skeleton loader in place of the content area until the API response is received or a 30-second timeout elapses
3. IF the Cost_Explorer_API is not enabled for the target account, THEN THE Member_Handler_Lambda SHALL return a 400 error with a message indicating that Cost Explorer is not enabled and instructing the member to enable it in the AWS Billing Console
4. IF the cross-account STS AssumeRole fails, THEN THE Member_Handler_Lambda SHALL return a 403 error advising the member to re-deploy the CloudFormation template
5. WHEN a network error occurs during data loading, THE Member_Portal_Frontend SHALL display a retry button and an error message indicating that the request failed due to a network issue
6. IF the Cost_Explorer_API returns a throttling error, THEN THE Member_Handler_Lambda SHALL retry with exponential backoff starting at 1 second, doubling on each attempt, up to a maximum of 3 retries, before returning a 429 error to the client
7. IF the loading timeout of 30 seconds elapses without an API response, THEN THE Member_Portal_Frontend SHALL replace the skeleton loader with an error message indicating the request timed out and display a retry button
8. IF a retry attempt triggered by the retry button also fails, THEN THE Member_Portal_Frontend SHALL continue to display the retry button and update the error message to indicate the number of consecutive failures

### Requirement 11: Services List Endpoint

**User Story:** As a member, I want to see a list of all AWS services that appear in my invoices, so that I can use the service filter dropdown effectively.

#### Acceptance Criteria

1. WHEN the services endpoint is called with a valid accountId, THE Member_Handler_Lambda SHALL verify account ownership and return a distinct list of all AWS service names present in the Invoice_Cache for that account, sorted in ascending alphabetical order
2. IF the requested accountId does not belong to the authenticated member, THEN THE Member_Handler_Lambda SHALL return a 403 error without revealing any invoice data
3. WHEN the Invoice_Cache contains no records for the specified account, THE Member_Handler_Lambda SHALL return an empty list with a 200 status
4. IF the accountId parameter is missing or does not match the 12-digit format, THEN THE Member_Handler_Lambda SHALL return a 400 error indicating the invalid account ID format
