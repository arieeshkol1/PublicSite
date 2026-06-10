# Tasks: Inline Audit Quality Gate

## Task 1: Implement `_inline_audit_score()` function [REQ-1, REQ-7]
- [ ] Create `_inline_audit_score(question, answer)` function in `member-handler/lambda_function.py`
- [ ] Use `bedrock_runtime.invoke_model` with `us.amazon.nova-lite-v1:0`
- [ ] Build compact scoring prompt (question + answer + scoring rules) under 2000 chars
- [ ] Parse JSON response: `{"score": int, "can_improve": bool, "improvement": str, "guiding_questions": list}`
- [ ] Add try/except: on any failure, return `{"score": 100}` (graceful pass-through)
- [ ] Add timeout of 5 seconds for the scoring call
- [ ] Log scoring result at INFO level

## Task 2: Integrate quality gate into `handle_ai_query` response flow [REQ-2, REQ-5]
- [ ] After Bedrock Agent `invoke_agent` returns the answer, call `_inline_audit_score(question, answer)`
- [ ] Read threshold from `AUDIT_QUALITY_THRESHOLD` env var (default 70)
- [ ] Add `AUDIT_QUALITY_GATE_ENABLED` env var feature flag (default "true")
- [ ] If disabled or pre-computed answer (`_svc_precomputed` or forecast), skip the gate
- [ ] If score >= threshold: proceed normally (return answer as-is)
- [ ] Track `inline_audit_score` and `inline_audit_action` in the response for logging

## Task 3: Implement Option 1 — Agent re-invocation with improvement instructions [REQ-3, REQ-5]
- [ ] When `score < threshold` AND `can_improve == True`: construct enhanced prompt
- [ ] Append improvement instructions to the original `enriched_prompt`
- [ ] Re-invoke Bedrock Agent with the enhanced prompt (same session config)
- [ ] Use the rewritten answer without a second audit pass (single retry cap)
- [ ] Set `inline_audit_action = "rewrite"` in response metadata
- [ ] Log the rewrite event with original score and improvement suggestions

## Task 4: Implement Option 2 — Guiding questions response [REQ-4]
- [ ] When `score < threshold` AND `can_improve == False`: return clarification response
- [ ] Build response JSON with `"needsClarification": true`
- [ ] Include `"guidingQuestions"` array (2-3 questions from audit response)
- [ ] Include a friendly message: "I need a bit more detail to give you an accurate answer."
- [ ] Set `inline_audit_action = "clarify"` in response metadata
- [ ] Ensure follow-up questions, chart data, and tips are NOT included in clarification responses

## Task 5: Add inline audit metadata to transaction log [REQ-6]
- [ ] Add `inline_audit_score`, `inline_audit_action` to the response result dict
- [ ] Ensure the transaction logger picks up these fields for DynamoDB
- [ ] The async audit evaluator continues to run independently on the stream

## Task 6: Frontend — Handle `needsClarification` responses [REQ-8]
- [ ] In `members/members.js`, check for `needsClarification` field in AI response
- [ ] When true: display guiding questions as clickable suggestion buttons
- [ ] When a guiding question is clicked, submit it as the new question
- [ ] Do NOT display the empty/placeholder answer text — show only the questions
- [ ] Style clarification state differently (info color, question-mark icon)

## Task 7: Add environment variables to deployment config
- [ ] Add `AUDIT_QUALITY_THRESHOLD` (default "70") to member-handler Lambda env vars
- [ ] Add `AUDIT_QUALITY_GATE_ENABLED` (default "true") to member-handler Lambda env vars
- [ ] Update `infrastructure/complete-stack.yaml` or deployment scripts if applicable
