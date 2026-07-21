# Tasks

## Task 1: Infrastructure — AgentFeedback DynamoDB Table and IAM
- [x] 1.1 Add `AgentFeedbackTable` DynamoDB resource to `infrastructure/viewmybill-stack.yaml` with table name `MemberPortal-AgentFeedback`, partition key `memberEmail` (S), sort key `interactionId` (S), PAY_PER_REQUEST billing, SSE enabled, `Project: ViewMyBill` tag
- [x] 1.2 Add `DynamoDBFeedbackAccess` IAM policy to `MemberHandlerRole` granting `dynamodb:PutItem` on `!GetAtt AgentFeedbackTable.Arn`
- [x] 1.3 Add `FEEDBACK_TABLE_NAME: !Ref AgentFeedbackTable` environment variable to `MemberHandlerFunction`
- [x] 1.4 Add `MemberAIFeedbackRoute` API Gateway route for `POST /members/accounts/ai-feedback` targeting `MemberIntegration`
- [x] 1.5 Add `AgentFeedbackTableName` and `AgentFeedbackTableArn` to Outputs section

## Task 2: Backend — InteractionId Generation in handle_ai_query()
- [x] 2.1 Add `FEEDBACK_TABLE_NAME` to environment variable declarations at top of `member-handler/lambda_function.py`
- [x] 2.2 In `handle_ai_query()`, generate `interactionId` using `datetime.now(timezone.utc).isoformat() + '-' + secrets.token_hex(4)` before calling the agent/model
- [x] 2.3 Pass `interactionId` through to `_invoke_bedrock_agent()` and `_invoke_direct_model()` return values
- [x] 2.4 Include `interactionId` in the response JSON body of both `_invoke_bedrock_agent()` and `_invoke_direct_model()`

## Task 3: Backend — handle_ai_feedback() Endpoint
- [x] 3.1 Add `'POST /members/accounts/ai-feedback': handle_ai_feedback` to the `routes` dict in `lambda_handler()`
- [x] 3.2 Implement `_derive_related_service(question)` helper that matches question text against AWS service keyword map and returns the service name (or "General")
- [x] 3.3 Implement `handle_ai_feedback(event)` function: authenticate via `validate_token()`, parse and validate body fields (`interactionId`, `feedbackScore`, `userQuestion`, `agentResponse`, `accountId`), reject invalid `feedbackScore`, derive `relatedService`, write record to `FEEDBACK_TABLE_NAME`
- [x] 3.4 In `handle_ai_feedback()`, when `feedbackScore == "yes"`: generate `tipId` as `ai-fb-{md5(userQuestion)[:8]}`, save tip to `TIPS_TABLE_NAME` with `confidenceTag: high-confidence`, `service: relatedService`, using `ConditionExpression='attribute_not_exists(tipId)'` for idempotency
- [x] 3.5 Return `{ success: true }` on success, appropriate error responses on validation failure

## Task 4: Backend — _search_tips() Prioritization Update
- [x] 4.1 In `_search_tips()`, after collecting tips, sort the list so items with `confidenceTag == 'high-confidence'` appear first (stable sort preserving order within each group)
- [x] 4.2 Ensure the function still returns up to 10 tips, including non-tagged tips when fewer than 5 high-confidence tips are available

## Task 5: Backend — Prompt Engineering Updates
- [x] 5.1 In `_ask_bedrock_analyze()`, update the tips formatting block to prefix tips that have `confidenceTag == 'high-confidence'` with `[Validated]` label
- [x] 5.2 Add "Prioritize strategies from Knowledge Base tips that have historically positive user feedback." to the system prompt
- [x] 5.3 Add "If a user corrects you in the chat, acknowledge the correction and adjust recommendations accordingly." to the system prompt

## Task 6: Frontend — Feedback Widget in addAIMessage()
- [x] 6.1 In `members/members.js` `addAIMessage()`, update the `askAI()` function to store `data.interactionId` as a `data-interaction-id` attribute on the answer message div
- [x] 6.2 In `addAIMessage()` for `type === 'answer'`, append feedback widget HTML after the follow-up buttons: "Did this help you?" prompt with 👍 and 👎 buttons, each with `data-interaction-id` attribute
- [x] 6.3 Add click handler for thumbs-up: highlight button, disable both buttons, call `api('POST', '/members/accounts/ai-feedback', { interactionId, feedbackScore: 'yes', userQuestion, agentResponse, accountId })`
- [x] 6.4 Add click handler for thumbs-down: highlight button, disable both buttons, show correction text input with placeholder "What was missing or incorrect?" and a Submit button
- [x] 6.5 Add correction submit handler: send feedback with `feedbackScore: 'no'` and `userCorrection` text; if dismissed without text, send without `userCorrection`
- [x] 6.6 Add CSS styles for feedback widget (inline or in `members/members.css`): button hover states, selected state highlighting, correction input styling

## Task 8: Frontend — Sticky Question Input Pane
- [x] 8.1 In `members/members.css`, update `.lab-input-area` to use `position: sticky; bottom: 0; z-index: 10; background: #0d1117; border-top: 1px solid #30363d; padding: 12px 20px;` so the question input always floats at the bottom of the AI Agent tab
- [x] 8.2 Ensure `.lab-chat` has appropriate `overflow-y: auto` and `flex: 1` so the chat area scrolls independently while the input stays pinned at the bottom
- [x] 8.3 Ensure `.lab-container` uses `display: flex; flex-direction: column; height: 100%;` to create the flex layout that allows the chat to fill available space above the sticky input

## Task 7: Testing
- [x] 7.1 Write property-based tests with `hypothesis` for `_derive_related_service()` — Property 5: for any question with known keywords, correct service is returned; for any question without keywords, "General" is returned
- [x] 7.2 Write property-based tests for `handle_ai_feedback()` validation — Property 4: for any payload missing required fields or with invalid feedbackScore, API returns 400
- [x] 7.3 Write property-based tests for positive feedback tip creation — Property 6: for any positive feedback, tip is saved with `confidenceTag: high-confidence`
- [x] 7.4 Write property-based tests for negative feedback — Property 8: for any negative feedback, no tip is written to tips table
- [x] 7.5 Write property-based tests for `_search_tips()` sorting — Property 9: for any tip list, high-confidence tips appear first
- [x] 7.6 Write property-based tests for validated tip annotation — Property 10: for any high-confidence tip in context, prompt contains `[Validated]` label
- [x] 7.7 Write property-based tests for interactionId format — Property 11: for any generated interactionId, it matches ISO-timestamp + 8-hex-char pattern
- [x] 7.8 Write unit tests for edge cases: empty correction text, duplicate feedback submission, very long agentResponse truncation, prompt string verification (Requirements 6.1, 6.2)
