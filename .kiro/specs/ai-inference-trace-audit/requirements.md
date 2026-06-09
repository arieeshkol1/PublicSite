# Requirements Document

## Introduction

This feature adds inference trace capture and audit scoring to the Bedrock Agent invocation path. During `_invoke_bedrock_agent` calls in the member-handler, all agent trace events (orchestration, pre/post-processing, guardrails, action group invocations) are captured and stored as a dedicated `inference_trace` field in the existing Audit_Transaction_Log DynamoDB record. The audit evaluator then uses the trace data to score whether the agent selected appropriate tools and followed correct reasoning sequences.

## Glossary

- **Trace_Collector**: The module within member-handler responsible for capturing and structuring Bedrock Agent trace events during `invoke_agent` calls
- **Audit_Transaction_Log**: The existing DynamoDB table that stores request/response audit records for all handler invocations
- **Audit_Evaluator**: The Lambda function triggered by DynamoDB Streams that evaluates transaction quality using Bedrock
- **Inference_Trace**: A JSON-serialized string stored in the Audit_Transaction_Log containing structured trace data from a Bedrock Agent invocation
- **Tool_Invocation**: A single action group function call made by the Bedrock Agent, including the tool name, request parameters, response data, and execution duration
- **Reasoning_Step**: A text segment from the agent's orchestration trace representing its internal thought process
- **Transaction_Logger**: The shared decorator module (`transaction_logger.py`) that captures request/response data and persists entries to DynamoDB

## Requirements

### Requirement 1: Trace Event Capture

**User Story:** As a platform operator, I want all Bedrock Agent trace events captured during invoke_agent calls, so that I can audit the agent's decision-making process.

#### Acceptance Criteria

1. WHEN the member-handler invokes `invoke_agent` via the `_invoke_bedrock_agent` function, THE Trace_Collector SHALL capture all trace events from the response event stream including orchestration traces, pre-processing traces, post-processing traces, guardrail traces, and action group invocation traces.
2. WHEN a trace event is received from the Bedrock Agent response stream, THE Trace_Collector SHALL extract the event type, timestamp, and full event payload.
3. THE Trace_Collector SHALL enable trace capture by setting the `enableTrace` parameter to `true` in the `invoke_agent` API call.

### Requirement 2: Structured Trace Data Format

**User Story:** As an audit evaluator, I want trace data structured into tools_selected, tool_invocations, and reasoning_steps, so that I can programmatically assess agent behavior.

#### Acceptance Criteria

1. THE Trace_Collector SHALL produce a structured trace object containing three fields: `tools_selected` (list of tool name strings), `tool_invocations` (array of invocation records), and `reasoning_steps` (array of reasoning text strings).
2. WHEN an action group invocation trace is captured, THE Trace_Collector SHALL record a tool_invocation entry with the fields: `tool_name`, `request_params`, `response_data`, and `duration_ms`.
3. WHEN an orchestration trace contains rationale or model invocation input text, THE Trace_Collector SHALL extract the text and append it to the `reasoning_steps` array.
4. WHEN an action group tool is invoked, THE Trace_Collector SHALL add the tool name to the `tools_selected` list without duplicates.

### Requirement 3: Trace Storage in Audit_Transaction_Log

**User Story:** As a platform operator, I want trace data stored alongside existing audit records, so that I can correlate agent behavior with transaction outcomes.

#### Acceptance Criteria

1. WHEN the `_invoke_bedrock_agent` function completes, THE Transaction_Logger SHALL store the structured trace as a JSON-serialized string in the `inference_trace` field of the Audit_Transaction_Log DynamoDB record.
2. THE Transaction_Logger SHALL enforce a maximum size of 50KB for the `inference_trace` field value.
3. IF the serialized inference_trace exceeds 50KB, THEN THE Transaction_Logger SHALL truncate the `tool_invocations` response_data fields starting from the oldest invocation until the payload fits within the 50KB limit.
4. IF truncation is applied, THEN THE Transaction_Logger SHALL include a `_truncated` boolean flag set to `true` and an `_original_size_bytes` integer field in the inference_trace object.

### Requirement 4: Trace-Based Audit Scoring

**User Story:** As a platform operator, I want the audit evaluator to assess whether the agent selected appropriate tools and followed correct reasoning sequences, so that I can identify and fix poor agent behavior.

#### Acceptance Criteria

1. WHEN the Audit_Evaluator processes a transaction record that contains an `inference_trace` field, THE Audit_Evaluator SHALL include trace-based scoring criteria in the evaluation prompt.
2. THE Audit_Evaluator SHALL assess whether the agent selected appropriate tools for the question type as part of the trace-based scoring.
3. WHEN the user question relates to a specific AWS service (detected via service name keywords in the question), THE Audit_Evaluator SHALL check whether the agent invoked `usageTypeBreakdown` in the tool_invocations and penalize the score if the tool was not called.
4. WHEN the user question involves cost calculation or pricing comparison, THE Audit_Evaluator SHALL check whether the agent invoked `getPricingData` before performing calculations and penalize the score if the tool was not called first.
5. THE Audit_Evaluator SHALL include a `trace_assessment` field in the evaluation output containing a text explanation of the trace-based scoring decision.

### Requirement 5: Graceful Handling of Missing Trace Data

**User Story:** As a platform operator, I want non-agent-path queries to be scored normally without trace data, so that the audit system remains functional for all transaction types.

#### Acceptance Criteria

1. WHEN the Audit_Evaluator processes a transaction record that does not contain an `inference_trace` field, THE Audit_Evaluator SHALL proceed with standard evaluation criteria without trace-based scoring.
2. WHEN the Audit_Evaluator processes a transaction record without an `inference_trace` field, THE Audit_Evaluator SHALL include a `trace_assessment` field with the value "No inference trace available - non-agent path or trace capture unavailable".
3. IF the `inference_trace` field is present but contains invalid JSON, THEN THE Audit_Evaluator SHALL log a warning, set the `trace_assessment` to "Trace data malformed - skipping trace evaluation", and proceed with standard scoring.

### Requirement 6: Scope Limitation to Agent Path

**User Story:** As a developer, I want trace capture limited to the Bedrock Agent invocation path, so that non-agent queries are not affected by trace collection overhead.

#### Acceptance Criteria

1. THE Trace_Collector SHALL execute trace capture only within the `_invoke_bedrock_agent` function of the member-handler.
2. WHEN the member-handler routes a query through `_invoke_direct_model` or `_invoke_multi_account`, THE Trace_Collector SHALL not execute and the `inference_trace` field SHALL remain absent from the transaction record.
3. IF an error occurs during trace capture or trace serialization, THEN THE Trace_Collector SHALL log the error and allow the `_invoke_bedrock_agent` function to complete normally without the inference_trace field, preserving the existing agent response behavior.
