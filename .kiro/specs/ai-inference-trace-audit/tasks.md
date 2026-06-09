# Implementation Plan: AI Inference Trace Audit

## Overview

Add inference trace capture to the Bedrock Agent invocation path in the member-handler Lambda. Trace events are structured into tools_selected, tool_invocations, and reasoning_steps, stored in the Audit_Transaction_Log, and scored by the audit evaluator for agent reasoning quality.

## Tasks

- [x] 1. Create TraceCollector module
  - [x] 1.1 Create `member-handler/trace_collector.py` with TraceCollector class
    - Implement `__init__` with empty lists for events, tools_selected, tool_invocations, reasoning_steps
    - Implement `capture_event(event)` to extract trace data from EventStream events
    - Implement `_detect_event_type(trace_data)` returning orchestration/preProcessing/postProcessing/guardrail/failure/unknown
    - Implement `_process_orchestration_trace(orch_trace)` to extract rationale text, model invocation input text, action group invocation inputs, and observation outputs
    - Implement `_process_preprocessing_trace(pre_trace)` to extract rationale from parsed response
    - Implement `_process_postprocessing_trace(post_trace)` to extract text from parsed response
    - Implement `build_structured_trace()` returning dict with tools_selected, tool_invocations, reasoning_steps
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4_

  - [x] 1.2 Implement `serialize_trace()` function with 50KB truncation logic
    - Serialize structured trace to JSON using `json.dumps(default=str)`
    - If serialized size ≤ 50KB, return as-is
    - If exceeds 50KB, truncate `response_data` from oldest tool_invocations first
    - Add `_truncated: true` and `_original_size_bytes` fields when truncation applied
    - If still too large after all response_data truncated, truncate reasoning_steps
    - _Requirements: 3.2, 3.3, 3.4_

  - [ ]* 1.3 Write property tests for TraceCollector (Properties 1-5)
    - **Property 1: Trace event capture completeness** — For any N trace events, TraceCollector captures all N with non-empty event_type, numeric timestamp, and full payload
    - **Property 2: Structured output invariant** — build_structured_trace() always returns exactly three keys: tools_selected, tool_invocations, reasoning_steps (all lists)
    - **Property 3: Tool invocation record completeness** — Each tool_invocations entry has tool_name (non-empty string), request_params (dict), response_data (string or None), duration_ms (non-negative int)
    - **Property 4: Reasoning step extraction** — Any orchestration trace with rationale.text or modelInvocationInput.text appears in reasoning_steps
    - **Property 5: Tool name deduplication** — tools_selected contains each tool name exactly once regardless of invocation count
    - **Validates: Requirements 1.1, 1.2, 2.1, 2.2, 2.3, 2.4**

  - [ ]* 1.4 Write property tests for serialize_trace (Properties 6-7)
    - **Property 6: Trace serialization round-trip** — Serializing and deserializing preserves tools_selected, reasoning_steps, and tool_name/request_params in invocations
    - **Property 7: Trace truncation correctness** — Output ≤ 50KB, _truncated=true present, _original_size_bytes matches, oldest response_data truncated first
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

- [x] 2. Modify member-handler to capture trace events
  - [x] 2.1 Update `_invoke_bedrock_agent` in `member-handler/lambda_function.py`
    - Import TraceCollector and serialize_trace from trace_collector module
    - Add `enableTrace=True` parameter to `invoke_agent()` API call
    - Instantiate TraceCollector before streaming response
    - In the event stream loop, detect `'trace'` events and call `collector.capture_event(event_stream)`
    - Wrap trace capture in try/except to log warnings but not break streaming
    - After stream completes, call `build_structured_trace()` and `serialize_trace()`
    - Attach serialized trace as `result['_inference_trace']` for transaction logger
    - Wrap trace build/serialize in try/except — log error, set inference_trace to None on failure
    - _Requirements: 1.1, 1.3, 6.1, 6.3_

  - [ ]* 2.2 Write property test for trace error resilience (Property 12)
    - **Property 12: Trace error resilience** — For any error during trace capture or serialization, _invoke_bedrock_agent still returns valid response with statusCode 200 and the agent's answer
    - **Validates: Requirements 6.3**

- [x] 3. Checkpoint - Verify trace capture
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Update Transaction Logger to persist trace data
  - [x] 4.1 Modify `transaction_logger.py` to detect and store inference_trace
    - After handler function returns, check if response dict contains `_inference_trace` key
    - Pop `_inference_trace` from response (so it's not returned to the caller)
    - Add `inference_trace` field to the transaction log entry dict before calling `_persist_async`
    - Only add field when value is non-None (keep it absent for non-agent paths)
    - _Requirements: 3.1, 6.2_

  - [ ]* 4.2 Write unit tests for transaction logger trace handling
    - Test that `_inference_trace` is removed from response before returning to caller
    - Test that `inference_trace` field appears in persisted entry when present
    - Test that `inference_trace` field is absent from entry when `_inference_trace` is not in response
    - _Requirements: 3.1, 6.2_

- [x] 5. Update Audit Evaluator for trace-based scoring
  - [x] 5.1 Add `_build_trace_scoring_section()` helper to `audit-evaluator/lambda_function.py`
    - Parse inference_trace JSON from entry
    - Extract user question from request_payload
    - Build trace scoring prompt section with tools_selected, invocation count, reasoning step count
    - Implement service keyword detection (ec2, s3, rds, lambda, ebs, cloudfront, dynamodb, ecs, eks, elasticache, redshift, route53)
    - Add penalty instruction when usageTypeBreakdown not in tools for service questions
    - Implement pricing keyword detection (cost, price, pricing, compare, cheaper, expensive, savings, calculate)
    - Add penalty instruction when getPricingData not in tools for pricing questions
    - Return None if inference_trace is absent or malformed JSON
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 5.2 Update `_build_prompt()` to include trace scoring section
    - Call `_build_trace_scoring_section()` with entry data
    - Append trace section to prompt when non-None
    - Add `trace_assessment` field to the expected JSON response format in prompt
    - _Requirements: 4.1, 4.5_

  - [x] 5.3 Update `_parse_bedrock_response()` to extract trace_assessment
    - Extract `trace_assessment` from parsed JSON response
    - Map to `audit_trace_assessment` key in evaluation dict
    - _Requirements: 4.5_

  - [x] 5.4 Update `_update_entry_with_evaluation()` to store trace_assessment in DynamoDB
    - Add `audit_trace_assessment` attribute to UpdateItem expression
    - Set default value "No inference trace available - non-agent path or trace capture unavailable" when trace_assessment is None
    - _Requirements: 4.5, 5.2_

  - [x] 5.5 Implement graceful handling of missing/malformed trace data
    - When `inference_trace` field is absent: proceed with standard evaluation, set trace_assessment to default message
    - When `inference_trace` contains invalid JSON: log warning, set trace_assessment to "Trace data malformed - skipping trace evaluation", proceed with standard scoring
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]* 5.6 Write property tests for audit evaluator trace scoring (Properties 8-10)
    - **Property 8: Conditional trace prompt inclusion** — Prompt includes trace scoring if and only if entry has non-null inference_trace with valid JSON
    - **Property 9: Service question penalizes missing usageTypeBreakdown** — When question mentions AWS service keyword and tools_selected lacks usageTypeBreakdown, prompt includes penalty
    - **Property 10: Pricing question penalizes missing getPricingData** — When question mentions pricing keyword and tools_selected lacks getPricingData, prompt includes penalty
    - **Validates: Requirements 4.1, 4.3, 4.4, 5.1**

  - [ ]* 5.7 Write unit tests for audit evaluator trace handling
    - Test `_parse_bedrock_response` extracts trace_assessment field
    - Test default trace_assessment for entries without inference_trace
    - Test malformed JSON handling and diagnostic message
    - Test that standard evaluation proceeds when trace is absent
    - _Requirements: 4.5, 5.1, 5.2, 5.3_

- [x] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The design uses Python — all implementations target the existing Python Lambda codebase
- Trace capture is non-blocking: all trace errors are caught and logged without affecting the agent response

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "2.1"] },
    { "id": 3, "tasks": ["2.2", "4.1"] },
    { "id": 4, "tasks": ["4.2", "5.1"] },
    { "id": 5, "tasks": ["5.2", "5.3", "5.4", "5.5"] },
    { "id": 6, "tasks": ["5.6", "5.7"] }
  ]
}
```
