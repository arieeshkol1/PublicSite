# Tasks: Inline Audit Quality Gate

## Task 1: Implement `_inline_audit_score()` function [REQ-1, REQ-7]
- [x] Create `_inline_audit_score(question, answer)` function in `member-handler/lambda_function.py`
- [x] Use `bedrock_runtime.invoke_model` with `us.amazon.nova-lite-v1:0`
- [x] Build compact scoring prompt (question + answer + scoring rules) under 2000 chars
- [x] Parse JSON response: `{"score": int, "can_improve": bool, "improvement": str, "guiding_questions": list}`
- [x] Add try/except: on any failure, return `{"score": 100}` (graceful pass-through)
- [x] Add timeout of 5 seconds for the scoring call
- [x] Log scoring result at INFO level

## Task 2: Integrate quality gate into `handle_ai_query` response flow [REQ-2, REQ-5]
- [x] After Bedrock Agent `invoke_agent` returns the answer, call `_inline_audit_score(question, answer)`
- [x] Read threshold from `AUDIT_QUALITY_THRESHOLD` env var (default 70)
- [x] Add `AUDIT_QUALITY_GATE_ENABLED` env var feature flag (default "true")
- [x] If disabled or pre-computed answer (`_svc_precomputed` or forecast), skip the gate
- [x] If score >= threshold: proceed normally (return answer as-is)
- [x] Track `inline_audit_score` and `inline_audit_action` in the response for logging

## Task 3: Implement Option 1 — Agent re-invocation with improvement instructions [REQ-3, REQ-5]
- [x] When `score < threshold` AND `can_improve == True`: construct enhanced prompt
- [x] Append improvement instructions to the original `enriched_prompt`
- [x] Re-invoke Bedrock Agent with the enhanced prompt (same session config)
- [x] Use the rewritten answer without a second audit pass (single retry cap)
- [x] Set `inline_audit_action = "rewrite"` in response metadata
- [x] Log the rewrite event with original score and improvement suggestions

## Task 4: Implement Option 2 — Guiding questions response [REQ-4]
- [x] When `score < threshold` AND `can_improve == False`: return clarification response
- [x] Build response JSON with `"needsClarification": true`
- [x] Include `"guidingQuestions"` array (2-3 questions from audit response)
- [x] Include a friendly message: "I need a bit more detail to give you an accurate answer."
- [x] Set `inline_audit_action = "clarify"` in response metadata
- [x] Ensure follow-up questions, chart data, and tips are NOT included in clarification responses

## Task 5: Add inline audit metadata to transaction log [REQ-6]
- [x] Add `inline_audit_score`, `inline_audit_action` to the response result dict
- [x] Ensure the transaction logger picks up these fields for DynamoDB
- [x] The async audit evaluator continues to run independently on the stream

## Task 6: Frontend — Handle `needsClarification` responses [REQ-8]
- [x] In `members/members.js`, check for `needsClarification` field in AI response
- [x] When true: display guiding questions as clickable suggestion buttons
- [x] When a guiding question is clicked, submit it as the new question
- [x] Do NOT display the empty/placeholder answer text — show only the questions
- [x] Style clarification state differently (info color, question-mark icon)

## Task 7: Add environment variables to deployment config
- [x] Add `AUDIT_QUALITY_THRESHOLD` (default "70") to member-handler Lambda env vars
- [x] Add `AUDIT_QUALITY_GATE_ENABLED` (default "true") to member-handler Lambda env vars
- [x] Update `infrastructure/complete-stack.yaml` or deployment scripts if applicable
