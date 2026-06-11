# Bugfix Requirements Document

## Introduction

The inline audit quality gate in `member-handler/lambda_function.py` (lines ~8235-8305) has a logic gap after a rewrite is triggered. When the initial answer scores below the threshold and a rewrite is attempted, the system either (a) accepts the rewritten answer without re-scoring it — potentially delivering inaccurate information — or (b) blocks the response entirely with a generic message if the rewrite fails to produce output. The correct behavior is to re-score the rewritten answer and, if it still fails, return a clarification response using the audit's guiding questions rather than blocking.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the initial answer scores below the quality gate threshold AND the Bedrock retry produces a rewritten answer longer than 20 characters THEN the system delivers the rewritten answer without re-scoring it against the original question

1.2 WHEN the initial answer scores below the quality gate threshold AND the Bedrock retry produces an empty or short answer (≤20 characters) THEN the system blocks the response with a generic "I could not generate a sufficiently accurate answer" message

1.3 WHEN the initial answer scores below the quality gate threshold AND the Bedrock retry raises an exception THEN the system blocks the response with a generic message instead of offering clarification guidance

### Expected Behavior (Correct)

2.1 WHEN the initial answer scores below the quality gate threshold AND the Bedrock retry produces a rewritten answer THEN the system SHALL re-score the rewritten answer by calling `_inline_audit_score(question, rewritten_answer)` before deciding whether to deliver it

2.2 WHEN the re-scored rewritten answer meets or exceeds the quality gate threshold THEN the system SHALL deliver the rewritten answer to the user with `inline_audit_action` set to `'rewrite_accepted'`

2.3 WHEN the re-scored rewritten answer still scores below the quality gate threshold THEN the system SHALL return a clarification response containing guiding questions derived from the second audit result's `guiding_questions` field or generated from its `improvement` field

2.4 WHEN the Bedrock retry produces an empty/short answer or raises an exception THEN the system SHALL return a clarification response with guiding questions from the original audit result's `guiding_questions` field rather than blocking with a generic message

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the initial answer scores at or above the quality gate threshold THEN the system SHALL CONTINUE TO deliver the answer without modification

3.2 WHEN the quality gate is disabled (`_gate_enabled` is False) or the answer is pre-computed THEN the system SHALL CONTINUE TO pass the answer through without scoring

3.3 WHEN the initial score is below threshold AND `can_improve` is False THEN the system SHALL CONTINUE TO return a clarification response immediately (existing Option 3 path)

3.4 WHEN the inline audit gate raises an unexpected exception THEN the system SHALL CONTINUE TO pass through the original answer with `inline_audit_action` set to `'error'`
