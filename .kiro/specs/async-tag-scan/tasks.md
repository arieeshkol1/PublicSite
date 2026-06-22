# Implementation Plan: Async Tag Scan

## Overview

Convert the synchronous `POST /members/tags/scan` endpoint into an asynchronous pattern: the kickoff returns immediately with a `scanId`, the Lambda self-invokes for background processing, results are persisted in DynamoDB under `lastTagScan`, and the frontend polls a new `GET /members/tags/scan-status` endpoint until completion. This mirrors the existing waste scan async pattern.

## Tasks

- [x] 1. Backend: Scan kickoff and status endpoints
  - [x] 1.1 Refactor `handle_tag_scan` into an async kickoff endpoint
    - Modify `handle_tag_scan` in `member-handler/lambda_function.py` to:
      - Validate auth token, load tag policy, check/consume credits, resolve account IDs, verify ownership (existing logic)
      - Generate a `scanId` (UUID)
      - Write initial state to DynamoDB `lastTagScan` attribute: `{scanId, status: "in_progress", startedAt, accountIds}`
      - Invoke the Lambda asynchronously via `lambda_client.invoke(FunctionName=self, InvocationType='Event', Payload={_asyncTagScan: True, scanId, memberEmail, accountIds, requiredTags})`
      - Return `{scanId, status: "in_progress"}` with HTTP 200
    - Remove the inline synchronous scan execution from this handler
    - Handle edge case: no connected accounts returns empty results immediately (preserving current behavior)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 6.1, 6.3_

  - [x] 1.2 Implement `handle_tag_scan_status` endpoint
    - Create new handler function `handle_tag_scan_status` in `member-handler/lambda_function.py`
    - Validate auth token
    - Return 400 if `scanId` query parameter is missing
    - Read `lastTagScan` attribute from the member's DynamoDB record
    - Return 404 if stored `scanId` doesn't match the requested `scanId`
    - Return the scan state: `in_progress` (with startedAt), `complete` (with full results), or `failed` (with error)
    - If `resourcesS3Key` is present in the stored state, retrieve resources from S3 before returning
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 1.3 Register the new route in `lambda_handler`
    - Add `'GET /members/tags/scan-status': handle_tag_scan_status` to the `routes` dict in `lambda_function.py`
    - Add dispatch check for `_asyncTagScan` in the event before route resolution: `if event.get('_asyncTagScan'): return _execute_async_tag_scan(event)`
    - _Requirements: 3.1_

  - [ ]* 1.4 Write unit tests for kickoff and status endpoints
    - Test kickoff returns `{scanId, status: "in_progress"}` with valid auth
    - Test 401 for invalid/expired token
    - Test 403 for insufficient credits
    - Test status endpoint returns 400 for missing scanId
    - Test status endpoint returns 404 for non-matching scanId
    - Test status endpoint returns correct state for in_progress, complete, and failed
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 2. Backend: Async scan executor
  - [x] 2.1 Implement `_execute_async_tag_scan` function
    - Create `_execute_async_tag_scan(event)` in `member-handler/lambda_function.py`
    - Extract `scanId`, `memberEmail`, `accountIds`, `requiredTags` from event payload
    - Wrap full scanning logic in a top-level try/except:
      - STS AssumeRole per account
      - `ec2.describe_regions` to get opted-in regions
      - Loop all regions: `resourcegroupstaggingapi.get_resources` with pagination
      - Service-specific discovery (CloudFront, Cognito, Route53, etc.)
      - Enrichment (EC2, EBS, RDS cost estimates)
      - Classify each resource as fullyTagged, partiallyTagged, or untagged
      - Assemble result: resources array, summary, coverage, discoveredTagKeys, untaggableServices
    - On success: write completed results to DynamoDB `lastTagScan` with `status: "complete"`
    - On failure: write `{status: "failed", error: <message>}` to DynamoDB `lastTagScan`
    - Remove the 26-second `_TAG_SCAN_TIMEOUT` guard
    - Remove the `accounts[:5]` cap — scan all connected accounts
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 5.1, 5.2, 5.3, 5.4, 6.2_

  - [x] 2.2 Implement S3 overflow for large results
    - After assembling the final result, check if serialized size exceeds 350KB
    - If so, store the `resources` array as JSON in S3 at key `tag-scans/{memberEmail}/{scanId}.json`
    - Store `resourcesS3Key` reference in DynamoDB instead of the full resources array
    - Use existing deployment bucket or create lifecycle policy (7-day expiration)
    - _Requirements: 2.5, 6.2_

  - [ ]* 2.3 Write property test for resource classification (Property 1)
    - **Property 1: Resource Classification Correctness**
    - Generate random `existingTags` dicts and `requiredTags` lists using Hypothesis
    - Verify classification: fullyTagged iff all required keys present, partiallyTagged iff some but not all, untagged iff none
    - **Validates: Requirements 2.3, 2.4**

  - [ ]* 2.4 Write property test for summary count invariant (Property 2)
    - **Property 2: Summary Count Invariant**
    - Generate random classified resource lists using Hypothesis
    - Verify `summary.total == summary.fullyTagged + summary.partiallyTagged + summary.untagged` and each count matches actual category membership
    - **Validates: Requirements 5.2**

  - [ ]* 2.5 Write property test for tag policy fallback chain (Property 3)
    - **Property 3: Tag Policy Fallback Chain**
    - Generate random `(tagPolicy, bodyRequiredTags)` combinations (present/absent) using Hypothesis
    - Verify priority: DynamoDB tag policy > request body requiredTags > defaults `["Environment", "Owner", "CostCenter", "Application"]`
    - **Validates: Requirements 5.4**

  - [ ]* 2.6 Write property test for resource schema completeness (Property 4)
    - **Property 4: Resource Schema Completeness**
    - Generate random resource dicts using Hypothesis
    - Verify after processing each resource contains: arn, resourceType, resourceId, name, account, region, existingTags, missingTags
    - **Validates: Requirements 5.1**

  - [ ]* 2.7 Write property test for discovered tag keys completeness (Property 5)
    - **Property 5: Discovered Tag Keys Completeness**
    - Generate random resources with random tag dicts using Hypothesis
    - Verify `discoveredTagKeys` contains every unique non-`aws:` prefixed tag key from all resources' existingTags
    - **Validates: Requirements 5.3**

- [x] 3. Checkpoint - Verify backend logic
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Backend: Status and credit gate property tests
  - [ ]* 4.1 Write property test for status endpoint behavior (Property 6)
    - **Property 6: Status Endpoint Returns Stored State**
    - Generate random scan states (in_progress/complete/failed) and mock DynamoDB reads using Hypothesis
    - Verify: matching scanId returns stored state, non-matching returns 404, missing param returns 400
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

  - [ ]* 4.2 Write property test for credit gate correctness (Property 7)
    - **Property 7: Credit Gate Correctness**
    - Generate random `(creditBalance, tier, cost)` tuples using Hypothesis
    - Verify: sufficient credits → proceed and consume, insufficient → 403 and no consumption
    - **Validates: Requirements 1.3, 1.5**

- [x] 5. Frontend: Polling and progress display
  - [x] 5.1 Refactor `_runTagScan` to async polling pattern
    - Modify `_runTagScan` in `members/members.js` to:
      - Call `POST /members/tags/scan` and receive `{scanId, status: "in_progress"}`
      - Display progress indicator with "Scanning for untagged resources..." message
      - Poll `GET /members/tags/scan-status?scanId=X` every 3–5 seconds using `setInterval`
      - On `status: "complete"` → clear interval, render results using existing `_renderTagStats` / `_renderTagList`
      - On `status: "failed"` → clear interval, display error message
      - On 120-second timeout → clear interval, show timeout message
    - Handle kickoff errors (non-200 response) by showing error immediately without polling
    - Handle transient poll errors (non-200 during polling) by retrying on next interval
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 5.2 Write property test for frontend polling termination (Property 8)
    - **Property 8: Frontend Stops Polling on Terminal Status**
    - Generate random poll response sequences ending in `"complete"` or `"failed"` using fast-check
    - Verify zero additional poll requests after terminal status received
    - **Validates: Requirements 4.3, 4.4**

- [x] 6. Infrastructure: API Gateway route
  - [x] 6.1 Add API Gateway route for scan-status endpoint
    - Add `GET /members/tags/scan-status` route to the HTTP API configuration (CloudFormation/SAM template or manual CLI)
    - Configure Lambda integration pointing to the member-handler Lambda
    - Ensure the route uses the same authorizer configuration as existing member routes
    - _Requirements: 3.1_

- [x] 7. Final checkpoint - End-to-end validation
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis (Python) and fast-check (JavaScript)
- Unit tests validate specific examples and edge cases
- Backend language: Python (matching existing `member-handler/lambda_function.py`)
- Frontend language: JavaScript (matching existing `members/members.js`)
- The async pattern mirrors the existing waste scan (`_asyncScan` / `POST /members/actions/scan`) for consistency

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1"] },
    { "id": 2, "tasks": ["1.4", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7"] },
    { "id": 3, "tasks": ["4.1", "4.2", "5.1"] },
    { "id": 4, "tasks": ["5.2", "6.1"] }
  ]
}
```
