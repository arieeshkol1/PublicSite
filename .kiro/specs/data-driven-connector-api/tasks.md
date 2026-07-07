# Implementation Plan: Data-Driven Connector API

## Overview

Extend the Provider Router's `route_tool()` flow to support data-driven drilldown execution. When `tipId` is present in parameters, the router intercepts the call, queries the Tips DynamoDB table for a Drilldown Plan, and delegates execution to the connector via a new `execute_drilldown_plan()` method. This eliminates code deployments for new vendor API integrations.

## Tasks

- [x] 1. Add base class method and helper utilities
  - [x] 1.1 Add `execute_drilldown_plan()` abstract method to `CloudConnector` base class
    - Add the method to `agent-action/connectors/__init__.py`
    - Signature: `execute_drilldown_plan(self, account_id: str, member_email: str, plan: list, params: dict) -> dict`
    - Raise `NotImplementedError` by default with a descriptive message
    - _Requirements: 3.1, 3.2_

  - [x] 1.2 Add `_substitute_placeholders()` and `_extract_iterable()` helper functions to `provider_router.py`
    - `_substitute_placeholders(call_params: dict, previous_result: dict) -> dict` replaces `"<each>"` values with lists extracted from the previous result
    - `_extract_iterable(result: dict) -> list` scans the result dict for the first list-valued key
    - _Requirements: 3.4_

  - [x] 1.3 Add `_resolve_drilldown_plan()` function to `provider_router.py`
    - Query Tips_Table (`ViewMyBill-CostOptimizationTips`) using `service` (PK) and `tipId` (SK)
    - Return `{'plan': [...], 'format': 'structured'|'legacy'}` on success
    - Return `{'error': 'Drilldown plan not found', 'guidance': ...}` when no record exists
    - Return `{'error': ..., 'retryable': True}` on DynamoDB ClientError (no raw exception in response)
    - Detect format by checking if first element of `drilldownApis` is a dict or string
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.4_

- [x] 2. Implement drilldown execution in connectors
  - [x] 2.1 Implement `execute_drilldown_plan()` in `AWSConnector`
    - File: `agent-action/connectors/aws_connector.py`
    - Use `_assume_role()` for credentials, `_make_client()` for dynamic boto3 client creation
    - Iterate plan steps sequentially; for each step use `service` to create client, `operation` to get method via `getattr`, `params` as kwargs
    - Call `_substitute_placeholders()` when previous results exist
    - On unrecognized service or invalid operation: return `{error, healingRequired: True, tipId, service}`
    - On permission errors (AccessDeniedException, etc.): stop, return `{authError: True, partialResults, failedStep, guidance}`
    - Skip malformed entries (missing service or operation)
    - On success: return `{drilldownResults: [...], stepCount: N}`
    - _Requirements: 2.3, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3_

  - [x] 2.2 Implement `execute_drilldown_plan()` in `AIVendorConnector`
    - File: `agent-action/connectors/ai_vendor_connector.py`
    - Use `_get_credentials()` to obtain the API key
    - Map structured objects: `service` = base URL domain, `operation` = HTTP path, `params` = headers/query/body
    - Build URL as `https://{service}{operation}`, inject `Authorization: Bearer {api_key}` header
    - Use `requests.get()` with timeout=10
    - On 401/403 HTTP errors: return `{authError: True, partialResults, failedStep, guidance}`
    - On success: return `{drilldownResults: [...], stepCount: N}`
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2_

- [x] 3. Integrate drilldown path into route_tool()
  - [x] 3.1 Add tipId routing branch to `route_tool()` in `provider_router.py`
    - After `resolve_provider()` succeeds: check if `params` contains `tipId`
    - If `tipId` present: call `_resolve_drilldown_plan(service, tip_id)`
    - On error response from plan lookup: return it directly
    - For structured format: filter malformed entries, return error if all are malformed, otherwise dispatch to `connector.execute_drilldown_plan()`
    - For legacy format: call `connector.execute_legacy_drilldown()` (pass-through to existing behavior)
    - If `tipId` absent: proceed with existing flow unchanged
    - _Requirements: 7.1, 7.2, 7.3, 1.1, 2.1, 2.2, 5.4_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Property-based tests for correctness properties
  - [ ]* 5.1 Write property test for no-cache freshness guarantee
    - **Property 1: No-cache freshness guarantee**
    - For any tipId requested N times, verify exactly N DynamoDB GetItem calls are issued (never reusing prior results)
    - **Validates: Requirements 1.2, 6.1, 6.2**

  - [ ]* 5.2 Write property test for missing plan produces structured error
    - **Property 2: Missing plan produces structured error**
    - For any (service, tipId) that doesn't match a record, verify response contains `"error": "Drilldown plan not found"` and a non-empty `"guidance"` string
    - **Validates: Requirements 1.3**

  - [ ]* 5.3 Write property test for DynamoDB failure returns retryable error
    - **Property 3: DynamoDB failure returns retryable error**
    - For any DynamoDB ClientError during lookup, verify response contains `"retryable": true` and does NOT contain the raw exception message
    - **Validates: Requirements 1.4**

  - [ ]* 5.4 Write property test for format detection correctness
    - **Property 4: Format detection correctness**
    - For any drilldownApis list, if first element is a dict → format is "structured"; if first element is a string → format is "legacy"
    - **Validates: Requirements 2.4**

  - [ ]* 5.5 Write property test for structured object execution maps fields correctly
    - **Property 5: Structured object execution maps fields correctly**
    - For any valid `{service, operation, params}` object, verify the connector creates a client for `service`, invokes `operation`, and passes `params` as kwargs
    - **Validates: Requirements 2.3, 3.1, 3.2**

  - [ ]* 5.6 Write property test for sequential execution preserves order
    - **Property 6: Sequential execution preserves order and collects all results**
    - For any plan with N valid steps (no errors), verify execution order 0..N-1 and results list length equals N
    - **Validates: Requirements 3.3**

  - [ ]* 5.7 Write property test for placeholder substitution
    - **Property 7: Placeholder substitution from previous results**
    - For any params dict with `"<each>"` value and a non-empty previous result, verify the placeholder is replaced with a list extracted from the previous result
    - **Validates: Requirements 3.4**

  - [ ]* 5.8 Write property test for permission error stops execution
    - **Property 8: Permission error stops execution and returns partial results**
    - For any N-step plan where step K raises a permission error, verify `authError: true`, `partialResults` of length K, `guidance` string, and steps K+1..N-1 are NOT executed
    - **Validates: Requirements 4.1, 4.2, 4.3**

  - [ ]* 5.9 Write property test for malformed entries are skipped
    - **Property 9: Malformed entries are skipped, valid entries execute**
    - For any plan with a mix of valid and invalid entries, verify only valid entries execute and results only include valid entry outputs
    - **Validates: Requirements 5.1**

  - [ ]* 5.10 Write property test for healing response
    - **Property 10: Healing response for unrecognized service or operation**
    - For any structured object with unrecognized service or invalid operation, verify response includes `healingRequired: true`, `tipId`, and `service`
    - **Validates: Requirements 5.2, 5.3, 5.4**

  - [ ]* 5.11 Write property test for tipId presence bifurcates routing
    - **Property 11: tipId presence bifurcates routing**
    - For any params dict: if `tipId` is present → drilldown path is taken; if absent → existing route_tool flow is followed
    - **Validates: Requirements 7.1, 7.2, 7.3**

- [x] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The design uses Python (existing codebase language) — no language selection needed
- All property tests go in `agent-action/tests/` alongside existing test files
- Property tests should use `pytest` with `hypothesis` for generation (matching existing test patterns)
- Checkpoints ensure incremental validation
- The existing `route_tool` flow is preserved unchanged for non-tipId calls (Requirement 7.1)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3"] },
    { "id": 2, "tasks": ["2.1", "2.2"] },
    { "id": 3, "tasks": ["3.1"] },
    { "id": 4, "tasks": ["5.1", "5.2", "5.3", "5.4", "5.7"] },
    { "id": 5, "tasks": ["5.5", "5.6", "5.8", "5.9", "5.10", "5.11"] }
  ]
}
```
