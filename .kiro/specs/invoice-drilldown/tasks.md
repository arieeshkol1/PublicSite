# Implementation Plan: Invoice Drilldown

## Overview

This plan implements a hierarchical three-level drill-down interface (Invoice → Service → Resource) for the existing Invoice Explorer. It extends the member-handler Lambda with 4 new API routes, adds a new `invoice_drilldown.py` module for data fetching at all levels, integrates resource metadata enrichment and AI-powered cost explanations via Bedrock, extends the DynamoDB schema with new sort key patterns, and builds the frontend hierarchical expandable UI.

## Tasks

- [ ] 1. Backend infrastructure and core interfaces
  - [ ] 1.1 Add new API Gateway routes to viewmybill-stack.yaml
    - Add GET /members/invoices/list, GET /members/invoices/services-breakdown, GET /members/invoices/resources, POST /members/invoices/refresh routes to the API Gateway HTTP API v2 resource
    - Add Lambda integration for each new route pointing to the existing MemberHandlerFunction
    - Update IAM permissions for the Lambda to invoke Bedrock (if not already present)
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ] 1.2 Register new routes in member-handler/lambda_function.py route dispatch
    - Add route entries to the `routes` dict: `GET /members/invoices/list`, `GET /members/invoices/services-breakdown`, `GET /members/invoices/resources`, `POST /members/invoices/refresh`
    - Import the new `invoice_drilldown` module
    - Add handler stub functions that delegate to invoice_drilldown module
    - Add INVOICES_TABLE_NAME environment variable reference
    - _Requirements: 10.1, 10.2, 10.3, 10.6_

  - [ ] 1.3 Create member-handler/invoice_drilldown.py module skeleton
    - Define module structure with function signatures for: `handle_invoice_list`, `handle_service_breakdown`, `handle_resource_breakdown`, `handle_refresh`
    - Define internal helper signatures: `fetch_invoice_list`, `fetch_service_breakdown`, `fetch_resource_breakdown`, `enrich_resource_metadata`, `generate_ai_explanations`, `generate_cost_explanation`
    - Import shared utilities from lambda_function.py (auth verification, account ownership, response helpers, _assume_role, _decimal_to_native)
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [ ] 2. Input validation and account ownership
  - [ ] 2.1 Implement input validation utilities in invoice_drilldown.py
    - Validate accountId: exactly 12 digits regex `^\d{12}$`
    - Validate period: YYYY-MM format with valid month (01-12)
    - Validate service: non-empty string
    - Validate pagination params: page >= 1, pageSize 1-100 (default 25)
    - Validate sortBy: one of [paymentDate, amount, status]
    - Validate sortOrder: one of [asc, desc]
    - Return 400 with descriptive error messages for invalid inputs
    - _Requirements: 10.4, 9.4_

  - [ ]* 2.2 Write property test for input validation (Property 9)
    - **Property 9: Input validation rejects invalid parameters**
    - Generate random strings with Hypothesis `st.text()` and `st.from_regex()`, verify accept/reject behavior for accountId, period, and service parameters
    - **Validates: Requirements 10.4**

  - [ ] 2.3 Implement account ownership verification for drill-down endpoints
    - Reuse existing `_verify_account_ownership` pattern from lambda_function.py
    - Query MemberPortal-Accounts table to confirm accountId belongs to authenticated member
    - Return 403 AccessDenied if account not owned
    - Wire into all four new route handlers as the first check after auth
    - _Requirements: 9.4, 10.6_

  - [ ]* 2.4 Write property test for account ownership enforcement (Property 1)
    - **Property 1: Account ownership enforcement**
    - Generate random email/accountId pairs, verify 403 returned for non-owned accounts and no external API calls made
    - **Validates: Requirements 9.4, 10.6**

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Invoice-level data fetching (Level 1)
  - [ ] 4.1 Implement DynamoDB cache read for invoice-level records
    - Query MemberPortal-Invoices table with `pk = {email}#{accountId}` and `sk begins_with "INV#"`
    - Check TTL validity (records within 90-day window)
    - Return cached records if available, sorted by paymentDate descending (default)
    - Support pagination: slice results by page/pageSize, return totalItems/totalPages metadata
    - _Requirements: 1.3, 8.1, 10.1, 10.5_

  - [ ] 4.2 Implement AWS Invoicing API fetch with Cost Explorer fallback
    - Call `invoicing:ListInvoiceSummaries` via cross-account role
    - Normalize response into invoice records: invoiceId, issuer, paymentDate, paymentStatus, totalAmount, currency, period
    - On AccessDenied or API unavailable: fall back to Cost Explorer monthly aggregation to generate synthetic invoice records
    - Set `source` field to "billing_api" or "cost_explorer_fallback"
    - _Requirements: 1.1, 1.4, 1.6_

  - [ ] 4.3 Implement DynamoDB cache write for invoice-level records
    - Write normalized invoice records with `sk = INV#{invoiceId}`
    - Set `recordType = "invoice"`, `lastSyncedAt` = current ISO timestamp
    - Calculate and set `ttl` = current epoch + 7,776,000 (90 days)
    - Use BatchWriteItem for efficiency
    - Do NOT write partial data on API failure (atomic: all or nothing)
    - _Requirements: 1.2, 1.5, 8.1, 8.3_

  - [ ] 4.4 Wire handle_invoice_list endpoint (cache-first with lazy fetch)
    - Check DynamoDB cache first → return if valid
    - On cache miss: fetch from AWS APIs → store → return
    - Apply sorting (sortBy, sortOrder params)
    - Apply pagination (page, pageSize params)
    - Return response matching the API contract from design
    - _Requirements: 1.1, 1.2, 1.3, 10.1, 10.5_

  - [ ]* 4.5 Write property test for TTL correctness (Property 3)
    - **Property 3: TTL correctness for all record types**
    - Generate random sync timestamps, verify ttl = timestamp_epoch + 7,776,000
    - **Validates: Requirements 1.2, 3.9, 8.3, 13.3**

  - [ ]* 4.6 Write property test for pagination completeness (Property 8)
    - **Property 8: Pagination completeness and consistency**
    - Generate lists of N items with random pageSize, verify traversing all pages yields exactly N items with no duplicates
    - **Validates: Requirements 10.5**

- [ ] 5. Service-level data fetching (Level 2)
  - [ ] 5.1 Implement DynamoDB cache read for service-level records
    - Query with `pk = {email}#{accountId}` and `sk begins_with "{YYYY-MM}#"`
    - Filter by recordType = "service" (to distinguish from legacy records if needed)
    - Return cached records sorted by cost descending
    - _Requirements: 2.2, 8.1_

  - [ ] 5.2 Implement Cost Explorer GetCostAndUsage fetch for service breakdown
    - Call GetCostAndUsage with SERVICE dimension + USAGE_TYPE grouping via cross-account role
    - Normalize into service records: serviceName, amount, usageTypes [{type, cost, unit, quantity}]
    - Filter out services with cost < $0.01
    - Calculate percentage of invoice total for each service
    - _Requirements: 2.1, 2.3, 2.7_

  - [ ] 5.3 Implement cost explanation generator
    - Generate formula string: "{quantity} {unit} × ${rate}/{unit_abbrev}"
    - Annotate with "(full month)" when hours ≈ 730 (±10)
    - Handle multiple usage types as separate lines
    - Fallback: "Monthly charge: ${amount}" for blended/amortized costs
    - Fallback: "See resource breakdown for details" when insufficient data
    - Round rates to 4 significant digits, totals to 2 decimal places
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 2.4, 2.5_

  - [ ]* 5.4 Write property test for cost explanation format (Property 5)
    - **Property 5: Cost explanation format correctness**
    - Generate usage data (quantity, unit, rate) with Hypothesis, verify format matches specification
    - **Validates: Requirements 2.4, 11.1, 11.2, 11.3, 11.5**

  - [ ] 5.5 Implement DynamoDB cache write for service-level records
    - Write service records with `sk = {YYYY-MM}#{serviceName}`
    - Include costExplanation, percentage, recordType="service", usageTypes
    - Set TTL = epoch + 90 days
    - Atomic write (no partial data on failure)
    - _Requirements: 2.3, 8.1, 8.3_

  - [ ] 5.6 Wire handle_service_breakdown endpoint
    - Validate accountId and period params
    - Check cache → return if valid
    - On cache miss: fetch from Cost Explorer → generate explanations → store → return
    - Sort by cost descending
    - Return response matching API contract
    - _Requirements: 2.1, 2.2, 2.6, 10.2_

  - [ ]* 5.7 Write property test for sort order correctness (Property 6)
    - **Property 6: Sort order correctness**
    - Generate random cost/date lists, verify non-increasing order in responses
    - **Validates: Requirements 2.6, 3.8, 5.5, 10.1, 10.2, 10.3**

  - [ ]* 5.8 Write property test for service cost threshold (Property 7)
    - **Property 7: Service cost threshold filtering**
    - Generate services with costs around $0.01, verify filtering behavior
    - **Validates: Requirements 2.7**

  - [ ]* 5.9 Write property test for percentage calculation (Property 12)
    - **Property 12: Percentage calculation accuracy**
    - Generate amounts and totals, verify percentage = round((A/T)*100, 1) and sum ≈ 100%
    - **Validates: Requirements 6.4**

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Resource-level data fetching (Level 3)
  - [ ] 7.1 Implement DynamoDB cache read for resource-level records
    - Query with `pk = {email}#{accountId}` and `sk begins_with "RES#{YYYY-MM}#{serviceName}#"`
    - Return cached records sorted by cost descending
    - _Requirements: 3.2, 8.1_

  - [ ] 7.2 Implement GetCostAndUsageWithResources fetch
    - Call GetCostAndUsageWithResources via cross-account role with service filter
    - Normalize into resource records: resourceId, amount, usageTypes
    - Generate cost explanation for each resource
    - Handle "resource data not available" error gracefully
    - _Requirements: 3.1, 3.3, 3.6, 3.7_

  - [ ] 7.3 Implement resource metadata enrichment service
    - Map service names to appropriate Describe API calls (EC2→DescribeInstances, RDS→DescribeDBInstances, S3→ListBuckets, Lambda→ListFunctions, EBS→DescribeVolumes, ElastiCache→DescribeCacheClusters, DynamoDB→parse ARN)
    - Extract resourceName and resourceType from API responses
    - 10-second timeout per Describe API call
    - On failure/timeout: return raw resource ID as name, "Unknown" as type
    - Return warnings list for partial failures
    - _Requirements: 3.4, 3.5, 12.3_

  - [ ]* 7.4 Write property test for resource enrichment graceful degradation (Property 15)
    - **Property 15: Resource enrichment graceful degradation**
    - Generate failure scenarios (timeout, access denied, resource deleted), verify raw ID returned as name and "Unknown" as type
    - **Validates: Requirements 3.5**

  - [ ] 7.5 Implement AI cost explanation service via Bedrock
    - Build prompt from design template with service name, resource details, costs
    - Call Bedrock Nova Lite (`us.amazon.nova-2-lite-v1:0`) with batched resources
    - Parse response to extract per-resource explanations
    - Only call for resources with cost > $1.00
    - 15-second timeout; on timeout/error fall back to formula explanation (aiExplanation = null)
    - Cache AI explanations with same 90-day TTL
    - _Requirements: 13.1, 13.2, 13.5, 13.6, 13.8, 13.9_

  - [ ]* 7.6 Write property test for AI explanation cost threshold (Property 16)
    - **Property 16: AI explanation cost threshold**
    - Generate costs around $1.00, verify Bedrock only called for costs > $1.00
    - **Validates: Requirements 13.8**

  - [ ]* 7.7 Write property test for AI prompt context completeness (Property 17)
    - **Property 17: AI prompt context completeness**
    - Generate resource data, verify prompt includes service name, resource name, type, cost, quantity, unit, rate
    - **Validates: Requirements 13.5**

  - [ ] 7.8 Implement DynamoDB cache write for resource-level records
    - Write resource records with `sk = RES#{YYYY-MM}#{serviceName}#{resourceId}`
    - Include all fields: resourceName, resourceType, costExplanation, aiExplanation, usageTypes
    - Set TTL = epoch + 90 days
    - Atomic write (no partial data on failure)
    - _Requirements: 3.9, 8.1, 8.3, 13.3_

  - [ ] 7.9 Wire handle_resource_breakdown endpoint
    - Validate accountId, period, and service params
    - Check cache → return if valid
    - On cache miss: fetch resources → enrich metadata → generate AI explanations → store → return
    - Sort by cost descending
    - Return response matching API contract including warnings array
    - _Requirements: 3.1, 3.2, 3.8, 10.3_

  - [ ]* 7.10 Write property test for DynamoDB key pattern correctness (Property 10)
    - **Property 10: DynamoDB key pattern correctness**
    - Generate email/account/period/service/resource combos, verify pk and sk patterns match specification
    - **Validates: Requirements 8.1**

  - [ ]* 7.11 Write property test for cache-hit behavior (Property 2)
    - **Property 2: Cache-hit returns cached data without external calls**
    - Generate valid cached records, verify no external API calls made when cache is valid
    - **Validates: Requirements 1.3, 2.2, 3.2, 13.4**

  - [ ]* 7.12 Write property test for no partial writes on failure (Property 4)
    - **Property 4: No partial data stored on API failure**
    - Generate error scenarios, verify DynamoDB state unchanged after failed API calls
    - **Validates: Requirements 1.5**

- [ ] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Refresh endpoint and rate limiting
  - [ ] 9.1 Implement refresh handler with rate limiting
    - Track last refresh timestamp per account (in DynamoDB or in-memory)
    - Check 5-minute cooldown: if within window, return 429 with secondsRemaining
    - On valid refresh: delete all records for account+period (INV#, SVC#, RES# prefixes)
    - Re-fetch all three levels and store fresh data
    - Return 200 with refreshed: true
    - _Requirements: 8.4, 8.5, 12.4_

  - [ ]* 9.2 Write property test for rate limiting (Property 11)
    - **Property 11: Rate limiting on refresh**
    - Generate timestamp sequences, verify only first request in 5-min window executes, subsequent return 429 with correct secondsRemaining
    - **Validates: Requirements 8.5**

- [ ] 10. Frontend hierarchical UI
  - [ ] 10.1 Add invoice drilldown HTML structure to members/index.html
    - Add a new section/tab for the Invoice Drilldown view
    - Create table container with expandable row structure
    - Add loading spinner templates and error message containers
    - Add refresh button with cooldown indicator
    - _Requirements: 4.1, 4.7, 4.8, 5.1_

  - [ ] 10.2 Implement invoice-level rendering in members/members.js
    - Fetch invoice list from GET /members/invoices/list
    - Render invoice rows with columns: Invoice ID, Issued By, Payment Date (formatted "Mon DD, YYYY"), Payment Status (color badge), Total Amount (formatted $X,XXX.XX)
    - Add expand/collapse click handlers on invoice rows
    - Implement column header sort toggle (paymentDate, amount, status)
    - Implement pagination controls (page navigation, pageSize selector)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 4.1, 4.5_

  - [ ] 10.3 Implement service-level rendering with expand/collapse
    - On invoice row click: fetch service breakdown from GET /members/invoices/services-breakdown
    - Render service rows indented 24px with columns: Service Name, Amount, Percentage bar, Cost Explanation
    - Add expand/collapse click handlers on service rows
    - Show loading spinner inline while fetching
    - Show error message with retry button on failure
    - Allow multiple services expanded simultaneously
    - _Requirements: 4.2, 4.4, 4.6, 4.7, 4.8, 6.1, 6.2, 6.3, 6.4_

  - [ ] 10.4 Implement resource-level rendering with AI explanations
    - On service row click: fetch resources from GET /members/invoices/resources
    - Render resource rows indented 48px with columns: Resource Name/ID, Resource Type (badge), Cost Explanation, Amount
    - Display AI explanation in light-blue info box with 🤖 icon below formula
    - Show resource IDs in monospace when name unavailable
    - Show loading spinner inline while fetching
    - Show error message with retry button on failure
    - _Requirements: 4.3, 4.4, 4.7, 4.8, 7.1, 7.2, 7.3, 7.4, 7.5, 13.7_

  - [ ] 10.5 Implement client-side session cache
    - Cache fetched data in a JavaScript object keyed by accountId+period+service
    - On re-expand: return cached data without API call
    - Clear cache on manual refresh
    - Clear cache on page navigation away
    - _Requirements: 8.2_

  - [ ] 10.6 Implement refresh button with cooldown UI
    - POST /members/invoices/refresh on click
    - On 429 response: disable button, show countdown timer with secondsRemaining
    - On success: clear client cache, re-render current expanded state
    - _Requirements: 8.4, 8.5, 12.4_

- [ ] 11. Frontend styling
  - [ ] 11.1 Add invoice drilldown CSS to members/members.css
    - Style three-level indentation (0px, 24px, 48px)
    - Style expand/collapse chevron icons (▶ collapsed, ▼ expanded)
    - Style payment status badges (green/amber/red)
    - Style resource type badges (monospace, rounded)
    - Style AI explanation info box (light-blue background, 🤖 icon)
    - Style percentage bar for service amounts
    - Style loading spinners and error messages inline
    - Style pagination controls
    - Ensure responsive layout for smaller screens
    - _Requirements: 4.1, 4.2, 4.3, 5.3, 6.4, 7.3, 7.5, 13.7_

- [ ] 12. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Formatting utilities and remaining property tests
  - [ ] 13.1 Implement currency and date formatting utilities
    - Currency formatter: dollar sign, comma thousands separator, 2 decimal places, negative with minus before $
    - Date formatter: ISO date → "Mon DD, YYYY" format
    - Add to both backend (Python response formatting) and frontend (JS display)
    - _Requirements: 5.2, 5.4, 6.2, 7.2_

  - [ ]* 13.2 Write property test for currency formatting (Property 13)
    - **Property 13: Currency formatting correctness**
    - Generate numeric amounts, verify format includes $, comma separator, 2 decimal places
    - **Validates: Requirements 5.4, 6.2, 7.2**

  - [ ]* 13.3 Write property test for date formatting (Property 14)
    - **Property 14: Date formatting correctness**
    - Generate ISO dates, verify output matches "Mon DD, YYYY" pattern
    - **Validates: Requirements 5.2**

- [ ] 14. Integration wiring and deployment
  - [ ] 14.1 Update CloudFormation template with new API routes and permissions
    - Add 4 new route resources to viewmybill-stack.yaml
    - Add Bedrock InvokeModel permission to Lambda execution role (if not present)
    - Add INVOICES_TABLE_NAME environment variable to Lambda function
    - Verify existing DynamoDB table TTL is enabled
    - _Requirements: 10.1, 10.2, 10.3, 9.1_

  - [ ] 14.2 Update cross-account CloudFormation template documentation
    - Document new permissions needed: `invoicing:ListInvoiceSummaries`, `ce:GetCostAndUsageWithResources`
    - Update the template generation handler to include new permissions
    - Add guidance message for users with existing roles
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ]* 14.3 Write integration tests for full drill-down flow
    - Test cache miss → fetch → store → cache hit cycle for all three levels
    - Test refresh flow: delete + re-fetch
    - Test Billing API fallback to Cost Explorer
    - Test error handling for all documented error scenarios
    - Mock AWS APIs (Billing, Cost Explorer, Describe, Bedrock)
    - _Requirements: 1.1-1.6, 2.1-2.7, 3.1-3.9, 8.4, 8.5_

- [ ] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document using Hypothesis (Python)
- Unit tests validate specific examples and edge cases
- The existing routes (GET /members/invoices, GET /members/invoices/summary, GET /members/invoices/services) remain unchanged for backward compatibility
- The frontend is a vanilla JS SPA — no framework, just DOM manipulation in members.js
- All backend code is Python 3.x in the member-handler Lambda
- DynamoDB table MemberPortal-Invoices already exists; only new sort key patterns are added (no schema migration needed)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "2.3"] },
    { "id": 2, "tasks": ["2.2", "2.4"] },
    { "id": 3, "tasks": ["4.1", "4.2", "5.3"] },
    { "id": 4, "tasks": ["4.3", "4.4", "5.1", "5.2"] },
    { "id": 5, "tasks": ["4.5", "4.6", "5.5", "5.6"] },
    { "id": 6, "tasks": ["5.4", "5.7", "5.8", "5.9"] },
    { "id": 7, "tasks": ["7.1", "7.2", "7.3"] },
    { "id": 8, "tasks": ["7.5", "7.8", "7.9"] },
    { "id": 9, "tasks": ["7.4", "7.6", "7.7", "7.10", "7.11", "7.12"] },
    { "id": 10, "tasks": ["9.1"] },
    { "id": 11, "tasks": ["9.2", "10.1", "11.1"] },
    { "id": 12, "tasks": ["10.2", "13.1"] },
    { "id": 13, "tasks": ["10.3", "10.5", "10.6", "13.2", "13.3"] },
    { "id": 14, "tasks": ["10.4"] },
    { "id": 15, "tasks": ["14.1", "14.2"] },
    { "id": 16, "tasks": ["14.3"] }
  ]
}
```
