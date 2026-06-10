# Requirements: Inline Audit Quality Gate

## Overview
Move the audit/scoring mechanism from post-response (async DynamoDB Streams) to pre-response (inline quality gate) within the member-handler Lambda. Low-quality answers are intercepted before reaching the user.

## Requirements

### REQ-1: Inline Quality Scoring
- **Given** the Bedrock Agent has produced a response to a user question
- **When** the response is generated but before returning to the user
- **Then** invoke an inline scoring model (Amazon Nova Lite) to evaluate the response quality (0-100 score)
- **And** the scoring completes within 3 seconds

### REQ-2: Configurable Quality Threshold
- **Given** the inline scoring has produced a score
- **When** the score is compared against the threshold
- **Then** use the `AUDIT_QUALITY_THRESHOLD` environment variable (default: 70)
- **And** responses scoring at or above the threshold are returned to the user immediately

### REQ-3: Option 1 — Audit Rewrite (Data Available)
- **Given** the inline score is below threshold AND the audit assessment indicates the data exists but was poorly presented
- **When** the audit returns `can_improve: true` with improvement suggestions
- **Then** re-invoke the Bedrock Agent with an enhanced prompt including the audit's improvement instructions
- **And** the rewritten response is returned to the user without a second audit pass (to avoid loops)

### REQ-4: Option 2 — Guiding Questions (Insufficient Data)
- **Given** the inline score is below threshold AND the audit determines the question is ambiguous or lacks sufficient context
- **When** the audit returns `can_improve: false` with clarification needs
- **Then** return 2-3 guiding questions to help the user refine their question
- **And** include `"needsClarification": true` in the response JSON

### REQ-5: Single Retry Cap
- **Given** a response has been rewritten (Option 1 triggered)
- **When** evaluating whether to audit again
- **Then** never perform more than 1 retry — return the rewritten answer regardless of its quality
- **And** log the retry event for monitoring

### REQ-6: Preserve Async Audit
- **Given** the inline quality gate has processed a response (pass or rewrite)
- **When** the transaction is logged to DynamoDB
- **Then** the existing async DynamoDB Stream audit evaluator continues to run for historical tracking
- **And** include `inline_audit_score` and `inline_audit_action` fields in the transaction log

### REQ-7: Graceful Degradation
- **Given** the inline audit scoring call fails (timeout, throttling, model error)
- **When** the scoring cannot complete
- **Then** return the original Bedrock Agent response without blocking the user
- **And** log the failure for monitoring

### REQ-8: Frontend Clarification Support
- **Given** the response includes `"needsClarification": true`
- **When** the frontend receives this response
- **Then** display the guiding questions as clickable suggestions instead of the normal answer format
- **And** allow the user to click a question or type their own refined query
