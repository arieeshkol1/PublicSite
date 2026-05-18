# Implementation Plan: Invoice Explorer

## Overview

Implement the Invoice Explorer feature for the SlashMyBill member portal. This adds a structured tabular interface for browsing, searching, and drilling into AWS invoices across connected accounts. The implementation extends the existing member-handler Lambda with new API routes, adds a DynamoDB table for invoice caching, and builds a frontend tab in the member portal.

## Tasks

- [x] 1. Set up infrastructure and data layer
  - [x] 1.1 Add DynamoDB InvoicesTable to CloudFormation stack
    - Add `MemberPortal-Invoices` table to `infrastructure/viewmybill-stack.yaml`
    - Define partition key (`pk`: String) and sort key (`sk`: String)
    - Add GSI `month-index` with pk as partition key and month as sort key
    - Set billing mode to PAY_PER_REQUEST
    - Enable TTL on the `ttl` attribute
    - Update MemberHandlerRole IAM policy to allow CRUD on the new table
    - _Requirements: 2.4_

  - [x] 1.2 Add API Gateway routes for invoice explorer endpoints
    - Add GET /members/invoices route
    - Add POST /members/invoices/refresh route
    - Add GET /members/invoices/summary route
    - Add GET /members/invoices/services route
    - Wire all routes to the existing Member Handler Lambda integration
    - _Requirements: 9.1_

- [x] 2. Implement input validation and account ownership
  - [x] 2.1 Implement input validation module
    - Create `member-handler/invoice_validation.py`
    - Implement month format validation (YYYY-MM, year 2015–current, month 01–12)
    - Implement accountId validation (exactly 12 digits)
    - Implement pageSize validation (integer 1–200, default 50)
    - Implement page validation (integer ≥ 1, default 1)
    - Implement sortBy validation (cost, service, date only)
    - Implement sortOrder validation (asc, desc only)
    - Return 400 errors with descriptive messages for invalid inputs
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 2.2 Write property test for month format validation
    - **Property 7: Month format validation**
    - **Validates: Requirements 8.1, 8.2**

  - [x] 2.3 Implement account ownership verification for invoice routes
    - Reuse existing `_verify_account_ownership` function from member-handler
    - Ensure all four invoice endpoints call ownership verification before processing
    - Return 403 with descriptive message when ownership check fails
    - Log unauthorized access attempts with member email and attempted accountId
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 2.4 Write property test for account ownership enforcement
    - **Property 1: Account ownership enforcement**
    - **Validates: Requirements 1.1, 1.2, 1.3, 11.2**

- [x] 3. Implement invoice data sync service
  - [x] 3.1 Implement cross-account Cost Explorer data fetching
    - Create `member-handler/invoice_sync.py`
    - Implement `sync_invoice_data(member_email, account_id, months)` function
    - Use STS AssumeRole with existing `SlashMyBill-{AccountID}` role pattern
    - Call GetCostAndUsage with SERVICE granularity for service-level costs
    - Call GetCostAndUsage with DAILY granularity for daily breakdown
    - Respect Cost Explorer rate limits (5 req/s) with sequential calls
    - Handle partial failures (some months succeed, others fail)
    - Return error without storing partial/empty records on failure
    - _Requirements: 2.2, 2.3, 2.5, 7.1, 7.5_

  - [x] 3.2 Implement invoice data normalization and DynamoDB storage
    - Normalize Cost Explorer response into flat DynamoDB records
    - Set pk as `{memberEmail}#{accountId}`, sk as `{YYYY-MM}#{serviceName}`
    - Store cost to 2 decimal places in USD
    - Store usageTypes as list of {type, cost, unit, quantity}
    - Store dailyCosts as map {day: cost}
    - Set TTL to 90 days from sync timestamp
    - Set lastSyncedAt to current ISO 8601 timestamp
    - Use BatchWriteItem for efficient writes
    - _Requirements: 2.3, 2.4_

  - [ ]* 3.3 Write property test for cache freshness guarantee
    - **Property 6: Cache freshness guarantee**
    - **Validates: Requirements 2.4, 7.2**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement invoice list endpoint with filtering, sorting, and pagination
  - [x] 5.1 Implement GET /members/invoices route handler
    - Add route handler in `member-handler/lambda_function.py`
    - Query DynamoDB with cache-first logic (return cached data or trigger sync)
    - Implement server-side filtering: service (case-insensitive exact match), month, minCost/maxCost (inclusive), search (case-insensitive substring on service name and usage type)
    - Combine multiple filters with AND logic
    - Ignore search queries shorter than 1 character
    - Return empty items array with totalItems=0 when no matches
    - _Requirements: 2.1, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 5.2 Implement sorting logic
    - Sort by cost (numeric), service (case-insensitive alphabetical), or date (chronological)
    - Default to cost descending when sortBy not specified
    - Apply secondary sort by cost descending for equal values
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x] 5.3 Implement pagination logic
    - Default to page=1, pageSize=50 when not specified
    - Clamp pageSize to 1–200 range
    - Return empty items for out-of-range page numbers with correct metadata
    - Ensure stable sort order for consistent pagination across pages
    - Return pagination metadata: page, pageSize, totalItems, totalPages
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 5.4 Write property test for pagination consistency
    - **Property 2: Pagination consistency**
    - **Validates: Requirements 3.1, 3.4**

  - [ ]* 5.5 Write property test for sort order correctness
    - **Property 4: Sort order correctness**
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 5.6 Write property test for filter correctness
    - **Property 5: Filter correctness**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

- [x] 6. Implement summary, services, and refresh endpoints
  - [x] 6.1 Implement GET /members/invoices/summary route handler
    - Calculate totalCost as sum of all item costs for current month (±0.01 precision)
    - Calculate month-over-month percentage change (rounded to 1 decimal place)
    - Return 0 for month-over-month when previous month has no data or zero total
    - Identify top 5 services by spend with cost and percentage of total
    - Return zeros and empty lists when no data exists
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 6.2 Write property test for cost aggregation accuracy
    - **Property 3: Cost aggregation accuracy**
    - **Validates: Requirements 6.1**

  - [ ]* 6.3 Write property test for summary statistics correctness
    - **Property 9: Summary statistics correctness**
    - **Validates: Requirements 6.2, 6.3**

  - [x] 6.4 Implement GET /members/invoices/services route handler
    - Query distinct service names from Invoice_Cache for the given account
    - Return sorted list in ascending alphabetical order
    - Return empty list with 200 status when no records exist
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [ ]* 6.5 Write property test for services list completeness
    - **Property 10: Services list completeness**
    - **Validates: Requirements 11.1**

  - [x] 6.6 Implement POST /members/invoices/refresh route handler
    - Accept accountId and months array (max 6 months per request)
    - Implement rate limiting: 1 refresh per account per 5-minute window
    - Return 429 with cooldown seconds remaining when rate limited
    - Delete old records and write fresh data on successful refresh
    - Update lastSyncedAt on all affected records
    - Preserve existing cache on Cost Explorer API failure
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 6.7 Write property test for rate limiting on refresh
    - **Property 8: Rate limiting on refresh**
    - **Validates: Requirements 7.3, 7.4**

- [x] 7. Implement error handling and retries
  - [x] 7.1 Implement backend error handling
    - Handle Cost Explorer not enabled (400 with enablement instructions)
    - Handle STS AssumeRole failure (403 with re-deploy guidance)
    - Handle Cost Explorer throttling with exponential backoff (1s start, double, max 3 retries)
    - Handle DynamoDB write throttling with auto-retry
    - Return 429 after exhausting retries on throttling
    - _Requirements: 10.3, 10.4, 10.6_

- [x] 8. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement frontend invoice explorer tab
  - [x] 9.1 Add Invoice Explorer tab to member portal navigation
    - Add tab button to existing navigation in `members/index.html`
    - Create tab content container with summary cards area, filter bar, and table area
    - Wire tab switching logic in `members/members.js`
    - _Requirements: 9.1_

  - [x] 9.2 Implement summary cards section
    - Display total spend formatted as currency
    - Display month-over-month change as percentage with positive/negative indicator
    - Display top service by cost
    - Update cards when filters change
    - Show skeleton loader while data loads
    - _Requirements: 9.2, 10.2_

  - [x] 9.3 Implement filter bar
    - Add account selector dropdown (populated from member's connected accounts)
    - Add month picker (last 12 months)
    - Add service dropdown (populated from /members/invoices/services endpoint)
    - Add text search input for service name and region matching
    - Trigger API calls with updated parameters on filter change
    - _Requirements: 9.3, 9.4_

  - [x] 9.4 Implement sortable paginated invoice table
    - Render table with columns: service, cost, month, region
    - Display 25 rows per page by default, sorted by cost descending
    - Add clickable column headers for sorting
    - Add pagination controls (previous/next, page indicator)
    - Implement expandable rows showing daily cost breakdown on click
    - _Requirements: 9.5, 9.6_

  - [x] 9.5 Implement CSV export functionality
    - Add export button above the table
    - Export currently filtered result set with all table columns
    - Generate CSV with service, cost, month, region fields
    - Trigger browser download of the CSV file
    - _Requirements: 9.7_

  - [ ]* 9.6 Write property test for CSV export fidelity
    - **Property 11: CSV export fidelity**
    - **Validates: Requirements 9.6**

  - [x] 9.7 Implement error states and loading UI
    - Show "Connect an AWS account" message when no accounts connected
    - Show skeleton loader during data loading (30-second timeout)
    - Show error notification with retry button on API failure
    - Show "No results found" message with filter adjustment suggestion
    - Show timeout message with retry button after 30 seconds
    - Track consecutive failures and update error message accordingly
    - Disable refresh button with countdown when rate limited
    - _Requirements: 10.1, 10.2, 10.5, 10.7, 10.8, 9.8, 9.9, 9.10_

- [x] 10. Integration and wiring
  - [x] 10.1 Wire all components together and add route dispatch
    - Add invoice route dispatch to main Lambda handler (lambda_function.py)
    - Map GET /members/invoices → invoice list handler
    - Map POST /members/invoices/refresh → refresh handler
    - Map GET /members/invoices/summary → summary handler
    - Map GET /members/invoices/services → services handler
    - Ensure JWT validation runs before all invoice routes
    - _Requirements: 1.1, 3.6_

  - [ ]* 10.2 Write integration tests for end-to-end invoice flows
    - Test cache hit path (data in DynamoDB → response)
    - Test cache miss path (fetch from Cost Explorer → store → response)
    - Test refresh flow with rate limiting
    - Test pagination across multiple pages
    - Test filter combinations
    - _Requirements: 2.1, 2.2, 3.1, 4.5, 7.3_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The design uses Python — all implementation uses Python for Lambda code and vanilla JS for frontend
- Existing patterns in member-handler (JWT validation, account ownership, STS role assumption) should be reused
- Hypothesis library is used for property-based testing as specified in the design

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "2.3"] },
    { "id": 2, "tasks": ["2.2", "2.4", "3.1"] },
    { "id": 3, "tasks": ["3.2"] },
    { "id": 4, "tasks": ["3.3", "5.1"] },
    { "id": 5, "tasks": ["5.2", "5.3"] },
    { "id": 6, "tasks": ["5.4", "5.5", "5.6", "6.1", "6.4", "6.6"] },
    { "id": 7, "tasks": ["6.2", "6.3", "6.5", "6.7", "7.1"] },
    { "id": 8, "tasks": ["9.1"] },
    { "id": 9, "tasks": ["9.2", "9.3"] },
    { "id": 10, "tasks": ["9.4", "9.5"] },
    { "id": 11, "tasks": ["9.6", "9.7", "10.1"] },
    { "id": 12, "tasks": ["10.2"] }
  ]
}
```
