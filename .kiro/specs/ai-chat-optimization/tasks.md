# Implementation Plan: AI Chat Optimization

## Overview

This plan implements multi-cloud provider routing, tips caching with provider filtering, and performance optimizations (cache-first cost lookups, parallel API calls, intent-based data routing) for the SlashMyBill AI chat query sequence. All changes are in Python within the `member-handler/` Lambda and `connectors/` package, maintaining backward compatibility with the existing AWS flow.

## Tasks

- [x] 1. Set up intent classifier and provider routing foundations
  - [x] 1.1 Implement the Intent Classifier (`_classify_intent`)
    - Create `member-handler/intent_classifier.py` with keyword-based classification
    - Define category-to-API mapping dictionary (ec2, rds, s3, lambda, cost-general, network, storage, compute, all)
    - Implement pattern matching logic that returns a `set[str]` of categories
    - Handle ambiguous/multi-service questions by returning `{'all'}`
    - Ensure execution completes in under 50ms (no LLM calls)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 1.2 Write property test for Intent Classifier
    - **Property 11: Intent-based data routing**
    - **Validates: Requirements 9.2, 9.3, 9.4**
    - Generate questions with various keyword combinations and verify only mapped APIs are selected
    - Verify "cost-general" classification triggers no resource-level APIs
    - Verify ambiguous questions trigger all APIs

  - [x] 1.3 Implement the Cloud Provider Router (`_route_to_connector`)
    - Create `member-handler/provider_router.py` with `_route_to_connector(account_id, member_email)` function
    - Read `cloudProvider` field from MemberPortal-Accounts DynamoDB table
    - Return tuple of `(provider_name, credentials_dict)`
    - Default to "aws" when `cloudProvider` is missing or empty
    - Extract provider-specific credentials from the account item
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 1.4 Write property test for Cloud Provider Router
    - **Property 1: Provider routing correctness**
    - **Validates: Requirements 1.2, 1.3, 1.4, 1.5**
    - Generate random provider strings ("aws", "azure", "gcp", "", None) and verify correct connector selection
    - Verify default-to-aws behavior for missing/empty values

  - [ ]* 1.5 Write property test for multi-account independent routing
    - **Property 2: Multi-account independent routing**
    - **Validates: Requirements 1.6**
    - Generate lists of accounts with mixed providers and verify each routes independently

- [x] 2. Implement GCP Connector
  - [x] 2.1 Create GCP Connector class (`connectors/gcp_connector.py`)
    - Implement `GCPConnector(ProviderConnector)` class inheriting from base
    - Implement `authenticate(credentials)` method using service account JSON key to obtain OAuth2 token
    - Implement `test_connection(auth_context, account_id)` method
    - Implement `get_cost_data(auth_context, account_id, start_date, end_date)` method querying GCP Cloud Billing API
    - Return normalized structure: `cost_by_service` list and `daily_cost_trend` list
    - Handle authentication failures by raising `AuthenticationError`
    - Limit to cost breakdowns only (no Compute Engine inventory, no Cloud Monitoring metrics)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 2.2 Write property test for GCP cost data normalization
    - **Property 3: Cost data normalization (GCP)**
    - **Validates: Requirements 3.4**
    - Generate random GCP API response structures and verify normalized output contains correct fields

  - [ ]* 2.3 Write unit tests for GCP Connector
    - Test authentication with valid/invalid service account keys (mocked HTTP)
    - Test cost data retrieval and normalization from sample GCP API response
    - Test authentication failure produces correct error message
    - _Requirements: 3.1, 3.2, 3.3, 3.6_

- [x] 3. Implement Azure Connector AI Chat Integration
  - [x] 3.1 Extend Azure Connector with `get_cost_data` for AI chat
    - Add `get_cost_data(auth_context, account_id, start_date, end_date)` method to existing `connectors/azure_connector.py`
    - Query Azure Cost Management API for cost data grouped by ServiceName (last 30 days)
    - Query Azure Cost Management API for daily cost trend (last 7 days)
    - Return normalized structure matching AWS connector output format
    - Handle authentication failures by raising `AuthenticationError`
    - Limit to cost breakdowns only (no Azure VM inventory, no Azure Monitor metrics)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 3.2 Write property test for Azure cost data normalization
    - **Property 3: Cost data normalization (Azure)**
    - **Validates: Requirements 2.4**
    - Generate random Azure API response structures and verify normalized output contains correct fields

  - [ ]* 3.3 Write unit tests for Azure Connector AI chat methods
    - Test cost data retrieval and normalization from sample Azure API response
    - Test authentication failure produces correct error message
    - _Requirements: 2.1, 2.2, 2.3, 2.6_

- [x] 4. Checkpoint - Core connectors and routing
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement tips caching and provider filtering
  - [x] 5.1 Implement Tips Cache with TTL
    - Add module-level globals `_tips_cache` and `TIPS_CACHE_TTL = 300` to `member-handler/lambda_function.py` (or a dedicated `tips_cache.py` module)
    - Implement `_get_cached_tips(provider)` that returns cached tips if `time.time() - timestamp < 300`, else None
    - Implement `_set_cached_tips(provider, tips)` that stores tips list with current timestamp
    - Key cache by cloud provider ("aws", "azure", "gcp")
    - No external dependencies (no Redis, no ElastiCache)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 5.2 Write property test for Tips Cache TTL
    - **Property 5: Tips cache TTL correctness**
    - **Validates: Requirements 4.2, 4.3**
    - Generate timestamps at varying distances from "now" and verify serve/discard behavior at 300-second boundary

  - [x] 5.3 Implement provider-specific tips mappings and filtering
    - Add `AZURE_SERVICE_MAPPING` dictionary to map keywords to Azure service names
    - Add `GCP_SERVICE_MAPPING` dictionary to map keywords to GCP service names
    - Modify `_search_tips` to accept a `provider` parameter and use the corresponding mapping
    - Always include tips tagged with service "General" regardless of provider
    - Implement deduplication by `tipId` when merging tips from multiple providers in multi-account queries
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 5.4 Write property test for provider-specific tips mapping
    - **Property 6: Provider-specific tips mapping**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
    - Generate random questions with service keywords and verify only correct provider's mappings are used plus "General"

  - [ ]* 5.5 Write property test for tips deduplication
    - **Property 7: Tips deduplication invariant**
    - **Validates: Requirements 5.5**
    - Generate tip lists with overlapping tipIds and verify merged result has no duplicates

  - [x] 5.6 Implement tip citation prompt enhancement
    - Modify prompt building to include tip citation instruction when tips are non-empty
    - Format: "💡 Tip:" prefix followed by tip title and explanation
    - Include tip titles, descriptions, and confidence levels in prompt context
    - Omit citation instruction when no tips match
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 5.7 Write property test for tip citation conditional inclusion
    - **Property 8: Tip citation prompt conditional inclusion**
    - **Validates: Requirements 6.1, 6.3, 6.4**
    - Generate empty and non-empty tip lists and verify citation instruction presence/absence

- [x] 6. Implement performance optimizations
  - [x] 6.1 Implement cache-first cost data retrieval
    - Create `_get_cost_data_cached(member_email, account_id, credentials, start_date, end_date)` function
    - Query `Cost_Cache_Table` for cached daily cost items for requested date range
    - If cache has full coverage, skip live Cost Explorer API call
    - If cache miss or incomplete, fall back to live Cost Explorer API
    - If both fail, return partial response with error indicator
    - Apply only to AWS accounts (Azure/GCP manage own caching)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 6.2 Write property test for cache-first cost retrieval
    - **Property 9: Cache-first cost retrieval**
    - **Validates: Requirements 7.2, 7.3**
    - Generate cache states (full, partial, empty) and verify correct API call behavior

  - [x] 6.3 Implement parallel API calls within account
    - Create `_gather_aws_data_parallel(credentials, question, intent)` using `ThreadPoolExecutor(max_workers=5)`
    - Execute EC2, CloudWatch, RDS, S3, EBS API calls concurrently based on intent classification
    - Enforce 10-second per-call timeout via `future.result(timeout=10)`
    - Log and skip failed individual calls, continue with successful results
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 6.4 Implement parallel multi-account processing
    - Create `_gather_multi_account_parallel(account_configs, question)` using `ThreadPoolExecutor(max_workers=3)`
    - Process accounts concurrently with each routing to its respective connector
    - Log each account failure with account ID, provider, and error details
    - Collect partial results from successful accounts
    - _Requirements: 8.5, 12.1, 12.2, 12.3, 12.4_

  - [ ]* 6.5 Write property test for parallel execution partial failure
    - **Property 10: Parallel execution partial failure resilience**
    - **Validates: Requirements 8.3**
    - Generate random success/failure combinations for N concurrent calls and verify all K successful results are present

  - [ ]* 6.6 Write property test for partial failure isolation in multi-account
    - **Property 4: Partial failure isolation**
    - **Validates: Requirements 2.6, 3.6, 12.1, 12.2**
    - Generate multi-account queries with some failing and verify non-failed accounts succeed and failed accounts appear in metadata

- [x] 7. Checkpoint - Performance and caching
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Wire components and integrate into AI chat handler
  - [x] 8.1 Integrate provider routing into `_invoke_direct_model`
    - Modify `_invoke_direct_model` to call `_route_to_connector` for account provider detection
    - Route to `_gather_provider_data` based on detected provider
    - Pass intent classification result to data gatherer
    - Maintain existing behavior for AWS accounts
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 11.2, 11.3_

  - [x] 8.2 Integrate provider routing into `_invoke_multi_account`
    - Modify `_invoke_multi_account` to detect provider for each account
    - Use `_gather_multi_account_parallel` for concurrent processing
    - Handle mixed-provider queries by routing each account independently
    - Include `failedAccounts` metadata in response for partial failures
    - _Requirements: 1.6, 12.1, 12.2, 12.3, 12.4_

  - [x] 8.3 Integrate tips cache and provider filtering into search flow
    - Modify `_search_tips` to check cache before DynamoDB query
    - Apply provider-specific service mappings based on account's cloud provider
    - Store fresh query results in cache after DynamoDB read
    - Merge and deduplicate tips in multi-provider queries
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 8.4 Integrate intent classifier into query flow
    - Call `_classify_intent(question)` early in both `_invoke_direct_model` and `_invoke_multi_account`
    - Pass intent set to data gatherers to control which APIs are called
    - Verify no behavioral change for ambiguous questions (fetch all)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 8.5 Integrate cache-first cost lookup into AWS data gathering
    - Wire `_get_cost_data_cached` into the existing AWS cost retrieval path
    - Ensure fallback to live API on cache miss
    - Add error handling for both cache and live API failures
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 8.6 Verify Lambda Guard timeout protection
    - Ensure all new code paths operate within the existing 27-second soft timeout
    - Verify ThreadPoolExecutor calls use appropriate timeout values
    - Confirm graceful partial response when timeout is reached during data gathering or Bedrock invocation
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 8.7 Write property test for response structure invariance
    - **Property 12: Response structure invariance**
    - **Validates: Requirements 11.1**
    - Generate responses from different providers and verify all required fields present (answer, interactionId, commands, results, tipFound, agentUsed, chartData, topServices)

  - [ ]* 8.8 Write property test for account ID validation
    - **Property 13: Account ID validation**
    - **Validates: Requirements 11.4**
    - Generate valid AWS (12-digit), Azure (UUID), and GCP (6-30 lowercase alphanum with hyphens) IDs and verify acceptance
    - Generate invalid strings and verify rejection

- [x] 9. Final checkpoint - Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document using the `hypothesis` library
- Unit tests validate specific examples and edge cases
- The implementation language is Python, consistent with the existing `member-handler/lambda_function.py` and `connectors/` package
- All parallel execution uses `concurrent.futures.ThreadPoolExecutor` (not asyncio) to match existing synchronous boto3 patterns
- Azure and GCP connectors return normalized data matching the existing AWS connector structure

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3"] },
    { "id": 1, "tasks": ["1.2", "1.4", "1.5", "2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.2", "3.3", "5.1", "5.3"] },
    { "id": 3, "tasks": ["5.2", "5.4", "5.5", "5.6", "6.1", "6.3"] },
    { "id": 4, "tasks": ["5.7", "6.2", "6.4"] },
    { "id": 5, "tasks": ["6.5", "6.6", "8.1", "8.3", "8.4", "8.5"] },
    { "id": 6, "tasks": ["8.2", "8.6"] },
    { "id": 7, "tasks": ["8.7", "8.8"] }
  ]
}
```
