# Implementation Plan: Cost Data Cache

## Overview

This plan implements a DynamoDB-based caching layer for AWS Cost Explorer data within the existing `member-handler` Lambda. The implementation follows an incremental approach: first establishing data types and infrastructure, then building the core cache service, followed by the incremental fetch engine, background refresh, cache invalidation, and finally wiring everything into the existing dashboard endpoint.

## Tasks

- [x] 1. Set up data types and DynamoDB table infrastructure
  - [x] 1.1 Create data type definitions in `member-handler/cache_types.py`
    - Define `DateRange`, `CostDataItem`, and `CacheResult` dataclasses
    - Include type hints and docstrings for all fields
    - _Requirements: 1.3, 4.5_

  - [x] 1.2 Add Cost_Cache_Table to CloudFormation stack
    - Add `CostCacheTable` DynamoDB resource to `infrastructure/viewmybill-stack.yaml`
    - Configure PAY_PER_REQUEST billing mode, pk/sk key schema, TTL on `ttl` attribute, SSE encryption at rest
    - Add IAM policy for MemberHandlerRole with Query, GetItem, PutItem, DeleteItem, BatchWriteItem permissions scoped to the table ARN
    - Add `COST_CACHE_TABLE_NAME` environment variable to MemberHandlerFunction
    - Add `POST /members/cache/invalidate` API Gateway route
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 8.2, 8.3_

- [ ] 2. Implement Cache Service core module
  - [x] 2.1 Create `member-handler/cache_service.py` with key construction and initialization
    - Implement `CacheService.__init__` accepting table_name and optional dynamodb_resource
    - Implement `_build_partition_key(member_id, account_id)` returning `{member_id}#{account_id}`
    - Implement `_build_sort_key(date)` returning `DAILY#{date}`
    - Implement `_calculate_ttl(fetched_at)` returning Unix epoch 90 days from fetched_at
    - Only DAILY granularity is supported — no MONTHLY or HOURLY
    - _Requirements: 1.1, 1.2, 1.5, 2.1, 2.5, 5.4_

  - [ ]* 2.2 Write property tests for key construction and TTL calculation
    - **Property 1: Key Construction Correctness**
    - **Property 4: TTL Calculation**
    - **Validates: Requirements 1.1, 1.2, 1.5, 2.1, 2.5, 5.4**

  - [ ] 2.3 Implement cache read path in `cache_service.py`
    - Implement `get_cost_data` method that queries DynamoDB using pk and sk range conditions
    - Use `between` condition on sort key for date range queries
    - Return `CacheResult` with appropriate `cache_status` field
    - _Requirements: 3.1, 3.2, 4.1, 4.5_

  - [ ]* 2.4 Write property tests for cache status field correctness
    - **Property 8: Cache Status Field Correctness**
    - **Validates: Requirements 4.5**

  - [ ] 2.5 Implement cache write path in `cache_service.py`
    - Implement `write_cost_data` method using DynamoDB BatchWriteItem
    - Write each day as a separate item with all required fields (pk, sk, cost_amount, currency, service_breakdown, fetched_at, ttl)
    - Handle BatchWriteItem 25-item limit by chunking
    - Set TTL to 90 days from write timestamp
    - Overwrite existing items for the same date (last-write-wins)
    - Log errors on write failure without blocking response
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 2.6 Write property tests for cache item completeness and write idempotency
    - **Property 3: Cache Item Completeness**
    - **Property 11: Write Idempotency (Last Write Wins)**
    - **Validates: Requirements 1.3, 5.5**

- [x] 3. Implement tenant isolation and ownership verification
  - [ ] 3.1 Implement account ownership verification in `cache_service.py`
    - Implement `_verify_account_ownership(member_id, account_ids)` that checks MemberPortal-Accounts table
    - Reject requests where account_id does not belong to authenticated member
    - Integrate ownership check into `get_cost_data` and `write_cost_data`
    - _Requirements: 2.2, 2.3, 2.4_

  - [ ]* 3.2 Write property tests for tenant isolation
    - **Property 2: Tenant Isolation via Ownership Verification**
    - **Validates: Requirements 2.2, 2.3, 7.5**

- [ ] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Incremental Fetch Engine
  - [ ] 5.1 Create `member-handler/incremental_fetch_engine.py` with gap detection
    - Implement `IncrementalFetchEngine.compute_gaps` that identifies missing date ranges from cached dates
    - Return minimal list of contiguous `DateRange` objects covering uncached dates
    - Always include today's date in gaps if within requested range
    - _Requirements: 3.1, 3.3, 3.5, 7.3_

  - [ ]* 5.2 Write property tests for gap detection
    - **Property 5: Gap Detection Produces Minimal Contiguous Ranges**
    - **Property 7: Today Always Re-fetched**
    - **Validates: Requirements 3.1, 3.3, 3.5, 7.3**

  - [ ] 5.3 Implement CE API fetch logic in `incremental_fetch_engine.py`
    - Implement `fetch_cost_data` that calls Cost Explorer GetCostAndUsage for given date ranges
    - Batch contiguous ranges into minimum number of API calls
    - Implement exponential backoff with max 3 retries for transient errors
    - Parse CE API response into `CostDataItem` objects
    - _Requirements: 3.3, 7.3, 9.5_

  - [ ]* 5.4 Write property tests for retry logic and full cache hit behavior
    - **Property 6: Full Cache Hit Requires Zero API Calls**
    - **Property 13: Exponential Backoff Retry Logic**
    - **Validates: Requirements 3.2, 7.2, 9.5**

  - [ ] 5.5 Implement `merge_results` in `incremental_fetch_engine.py`
    - Merge cached and freshly fetched items, preferring fresh data for overlapping dates
    - Return combined sorted list of `CostDataItem` objects
    - _Requirements: 3.4, 5.5_

- [x] 6. Implement background refresh and rate limiting
  - [ ] 6.1 Implement staleness detection in `cache_service.py`
    - Implement `should_background_refresh` that checks if recent 3 days' data is older than 6 hours
    - Check META#last_refresh item to enforce max one refresh per account per hour
    - _Requirements: 6.1, 6.4_

  - [ ]* 6.2 Write property tests for staleness detection and rate limiting
    - **Property 9: Staleness Detection**
    - **Property 10: Refresh Rate Limiting**
    - **Validates: Requirements 6.1, 6.4**

  - [ ] 6.3 Implement `trigger_background_refresh` in `cache_service.py`
    - Non-blocking refresh of recent 3 days using threading or async invocation
    - Update META#last_refresh item on trigger
    - Log failures without blocking the member's current request
    - _Requirements: 6.2, 6.3_

- [ ] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement cache invalidation and account disconnect
  - [ ] 8.1 Implement `invalidate` method in `cache_service.py`
    - Delete cached items for specified date range using Query + BatchWriteItem (delete)
    - If no date range specified, delete all items for the account
    - Return count of deleted items
    - _Requirements: 10.1, 10.4_

  - [ ] 8.2 Implement `delete_account_cache` method in `cache_service.py`
    - Delete ALL cached data for an account (including META items)
    - Used when member disconnects an AWS account
    - _Requirements: 10.3_

  - [ ] 8.3 Add `handle_cache_invalidate` route to `member-handler/lambda_function.py`
    - Add POST /members/cache/invalidate route handler
    - Validate JWT authentication token
    - Verify account ownership before invalidation
    - Call `cache_service.invalidate` for each requested account
    - Return count of deleted items
    - _Requirements: 8.1, 10.1_

- [x] 9. Implement error handling and fallback paths
  - [ ] 9.1 Add fallback logic to cache read path
    - If DynamoDB read fails, fall back to direct CE API call
    - If CE API times out, return available cached data with `partial_data=true`
    - If both unavailable, return HTTP 503 with clear error message
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ] 9.2 Add partial failure handling for multi-account processing
    - Continue processing remaining accounts when one account's CE API call fails
    - Log failures per account and include partial results in response
    - _Requirements: 9.4_

  - [ ]* 9.3 Write property tests for partial failure resilience
    - **Property 12: Partial Failure Resilience**
    - **Validates: Requirements 9.4**

- [x] 10. Integrate cache service into dashboard endpoint
  - [ ] 10.1 Modify `handle_dashboard_data` in `member-handler/lambda_function.py`
    - Initialize `CacheService` with table name from environment variable
    - Replace direct CE API calls with `cache_service.get_cost_data`
    - Add background refresh trigger after cache read
    - Implement fallback to existing `_gather_account_data` on cache failure
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 6.1_

  - [ ] 10.2 Add account disconnect cache cleanup to `handle_delete_account`
    - Call `cache_service.delete_account_cache` when member disconnects an account
    - _Requirements: 10.3_

  - [ ] 10.3 Add audit logging for cache operations
    - Log all cache read and write operations with member_id
    - Use parameterized key conditions in all DynamoDB queries
    - _Requirements: 8.4, 8.5_

  - [ ]* 10.4 Write unit tests for integration and error scenarios
    - Test end-to-end cache read/write with moto (local DynamoDB mock)
    - Test fallback path when DynamoDB is unavailable
    - Test authentication is checked before cache access
    - Test response format matches existing dashboard-data contract
    - _Requirements: 4.2, 8.1, 9.1_

- [ ] 11. Integrate cache into Bedrock Agent action Lambda
  - [ ] 11.1 Modify `_get_cost_data` in `agent-action/lambda_function.py` to read from cache
    - Query `Cost_Cache_Table` using `member_email#account_id` partition key and `DAILY#` sort key prefix
    - Aggregate daily items into service breakdown and total cost
    - Fall back to direct CE API call on cache miss or DynamoDB error
    - Add `COST_CACHE_TABLE_NAME` environment variable to AgentAction Lambda
    - _Requirements: 4.1, 7.2_

  - [ ] 11.2 Modify `_get_monthly_comparison` in `agent-action/lambda_function.py` to read from cache
    - Query cache for the requested month range, aggregate daily items per month per service
    - Fall back to direct CE API call on cache miss
    - _Requirements: 7.2_

  - [ ] 11.3 Add DynamoDB read permissions for AgentAction Lambda in CloudFormation
    - Add IAM policy granting `dynamodb:Query` and `dynamodb:GetItem` on `Cost_Cache_Table` ARN to the AgentAction Lambda role
    - Add `COST_CACHE_TABLE_NAME` environment variable to AgentAction Lambda function resource
    - _Requirements: 8.2_

- [ ] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis (Python PBT library)
- Unit tests validate specific examples and edge cases using moto for DynamoDB mocking
- The implementation uses Python, matching the existing member-handler Lambda codebase
- All new modules are created within the `member-handler/` directory to maintain single-Lambda architecture

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.2"] },
    { "id": 3, "tasks": ["2.4", "2.5"] },
    { "id": 4, "tasks": ["2.6", "5.1"] },
    { "id": 5, "tasks": ["5.2", "5.3", "5.5"] },
    { "id": 6, "tasks": ["5.4", "6.1"] },
    { "id": 7, "tasks": ["6.2", "6.3"] },
    { "id": 8, "tasks": ["8.1", "8.2"] },
    { "id": 9, "tasks": ["8.3", "9.1", "9.2"] },
    { "id": 10, "tasks": ["9.3", "10.1"] },
    { "id": 11, "tasks": ["10.2", "10.3"] },
    { "id": 12, "tasks": ["10.4", "11.1", "11.2", "11.3"] }
  ]
}
```
