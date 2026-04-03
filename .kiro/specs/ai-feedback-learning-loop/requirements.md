# Requirements Document

## Introduction

The AI Feedback Learning Loop embeds a continuous learning mechanism into the SlashMyBill AI Agent. Members can rate AI responses with thumbs-up/thumbs-down feedback directly in the AI Agent tab. Positive feedback reinforces high-quality tips in the RAG knowledge base, while negative feedback with optional corrections is logged for admin review. The RAG retrieval pipeline and prompt engineering are updated to prioritize historically validated tips, creating a self-improving FinOps assistant.

## Glossary

- **Feedback_Widget**: The UI component rendered below each AI response card containing the thumbs-up and thumbs-down buttons and the optional correction text input.
- **Agent_Feedback_Table**: The DynamoDB table `MemberPortal-AgentFeedback` that stores all user feedback records, partitioned by `memberEmail` with sort key `interactionId`.
- **Cost_Optimization_Tips_Table**: The existing DynamoDB table `ViewMyBill-CostOptimizationTips` that serves as the RAG knowledge base for FinOps tips.
- **Feedback_API**: The backend API route `POST /members/accounts/ai-feedback` on the Member Handler Lambda that processes feedback submissions.
- **Member_Handler_Lambda**: The existing Lambda function (`member-handler/lambda_function.py`) that handles all member portal API routes including AI queries.
- **Interaction_ID**: A unique identifier for each AI query-response pair, composed of a timestamp-based string generated at query time.
- **Confidence_Tag**: A metadata attribute on tips in the Cost_Optimization_Tips_Table indicating feedback-validated quality. Values: `high-confidence` or absent.
- **Related_Service**: The AWS service category (e.g., EC2, S3, RDS) associated with a feedback record, extracted from the AI interaction context.

## Requirements

### Requirement 1: Feedback Widget Rendering

**User Story:** As a member, I want to see a feedback prompt below every AI response, so that I can quickly indicate whether the recommendation was helpful.

#### Acceptance Criteria

1. WHEN the AI Agent renders an answer-type message, THE Feedback_Widget SHALL display a "Did this help you?" prompt with a thumbs-up button and a thumbs-down button below the response content.
2. WHEN the member clicks the thumbs-up button, THE Feedback_Widget SHALL visually highlight the selected button, disable both feedback buttons, and submit positive feedback to the Feedback_API.
3. WHEN the member clicks the thumbs-down button, THE Feedback_Widget SHALL visually highlight the selected button, disable both feedback buttons, display an optional text input with the placeholder "What was missing or incorrect?", and display a submit button for the correction text.
4. WHEN the member submits correction text after clicking thumbs-down, THE Feedback_Widget SHALL send the correction text along with the negative feedback to the Feedback_API.
5. WHEN the member dismisses the correction text input without typing, THE Feedback_Widget SHALL submit negative feedback to the Feedback_API without correction text.
6. THE Feedback_Widget SHALL include the current interactionId, the original user question, the AI response text, and the selected account ID in every feedback submission.

### Requirement 2: Feedback API Endpoint

**User Story:** As a system operator, I want a dedicated API endpoint for feedback submissions, so that feedback data is validated and stored reliably.

#### Acceptance Criteria

1. THE Feedback_API SHALL accept POST requests at the route `POST /members/accounts/ai-feedback` with a JSON body containing `interactionId`, `feedbackScore` ("yes" or "no"), `userQuestion`, `agentResponse`, `accountId`, and optionally `userCorrection`.
2. WHEN a valid feedback request is received, THE Feedback_API SHALL authenticate the member using the existing JWT token validation.
3. WHEN the feedback request is missing `interactionId`, `feedbackScore`, `userQuestion`, `agentResponse`, or `accountId`, THE Feedback_API SHALL return a 400 error with a descriptive error message.
4. WHEN `feedbackScore` is a value other than "yes" or "no", THE Feedback_API SHALL return a 400 error indicating an invalid feedback score.
5. WHEN a valid feedback request is received, THE Feedback_API SHALL derive the `relatedService` by matching the `userQuestion` against known AWS service keywords (EC2, S3, RDS, Lambda, EBS, VPC, CloudFront, DynamoDB, ECS, EKS, Route53, KMS, ElastiCache, Redshift, CloudWatch, IAM, General).

### Requirement 3: Feedback Storage in DynamoDB

**User Story:** As an admin, I want all feedback records stored in a dedicated table, so that I can review interaction quality and user corrections.

#### Acceptance Criteria

1. THE Agent_Feedback_Table SHALL be provisioned as a DynamoDB table with partition key `memberEmail` (String) and sort key `interactionId` (String), using PAY_PER_REQUEST billing mode and server-side encryption enabled.
2. WHEN a feedback submission is processed, THE Feedback_API SHALL write a record to the Agent_Feedback_Table containing `memberEmail`, `interactionId`, `userQuestion`, `agentResponse`, `feedbackScore`, `userCorrection` (if provided), `relatedService`, `accountId`, and `createdAt` (ISO 8601 timestamp).
3. THE Agent_Feedback_Table SHALL be defined in the CloudFormation stack (`infrastructure/viewmybill-stack.yaml`) alongside the existing DynamoDB tables.
4. THE Member_Handler_Lambda SHALL have IAM permissions to perform `PutItem` on the Agent_Feedback_Table.

### Requirement 4: Positive Feedback Reinforcement

**User Story:** As a system operator, I want positive feedback to automatically reinforce the RAG knowledge base, so that validated tips are prioritized in future responses.

#### Acceptance Criteria

1. WHEN `feedbackScore` is "yes", THE Feedback_API SHALL extract a tip from the `agentResponse` and save it to the Cost_Optimization_Tips_Table with the `service` set to the derived `relatedService`, a generated `tipId`, and a `confidenceTag` attribute set to `high-confidence`.
2. WHEN `feedbackScore` is "yes" AND the Cost_Optimization_Tips_Table already contains a tip with the same generated `tipId`, THE Feedback_API SHALL skip the duplicate insertion without error.
3. WHEN `feedbackScore` is "no", THE Feedback_API SHALL log the feedback record to the Agent_Feedback_Table and SHALL NOT save any tip to the Cost_Optimization_Tips_Table.

### Requirement 5: RAG Retrieval Prioritization

**User Story:** As a member, I want the AI Agent to prioritize tips that have been validated by other users, so that I receive higher-quality recommendations.

#### Acceptance Criteria

1. WHEN the `_search_tips` function retrieves tips from the Cost_Optimization_Tips_Table, THE Member_Handler_Lambda SHALL sort the retrieved tips so that tips with `confidenceTag` equal to `high-confidence` appear before tips without a confidence tag.
2. THE `_search_tips` function SHALL continue to return tips without a `confidenceTag` when fewer than 5 high-confidence tips are available for the matched services, ensuring the AI Agent always has context to work with.

### Requirement 6: Prompt Engineering Updates

**User Story:** As a system operator, I want the AI system prompt to instruct the model to prioritize validated knowledge and acknowledge user corrections, so that the AI behavior aligns with the feedback loop.

#### Acceptance Criteria

1. THE `_ask_bedrock_analyze` function SHALL include the instruction "Prioritize strategies from Knowledge Base tips that have historically positive user feedback" in the system prompt sent to Bedrock.
2. THE `_ask_bedrock_analyze` function SHALL include the instruction "If a user corrects you in the chat, acknowledge the correction and adjust recommendations accordingly" in the system prompt sent to Bedrock.
3. WHEN tips with `confidenceTag` equal to `high-confidence` are included in the prompt context, THE `_ask_bedrock_analyze` function SHALL annotate those tips with a "[Validated]" label so the model can distinguish them from unvalidated tips.

### Requirement 7: Interaction ID Generation

**User Story:** As a system operator, I want each AI interaction to have a unique identifier, so that feedback can be reliably linked back to the specific query-response pair.

#### Acceptance Criteria

1. WHEN the `handle_ai_query` function processes a query, THE Member_Handler_Lambda SHALL generate a unique `interactionId` composed of the current UTC timestamp in ISO 8601 format concatenated with a random 8-character hex suffix.
2. THE `handle_ai_query` function SHALL include the generated `interactionId` in the API response body so the frontend can reference it in subsequent feedback submissions.

### Requirement 8: Infrastructure and IAM Updates

**User Story:** As a DevOps engineer, I want the CloudFormation stack updated with the new table and permissions, so that the feedback loop infrastructure is deployed consistently.

#### Acceptance Criteria

1. THE CloudFormation stack SHALL define the Agent_Feedback_Table resource with table name `MemberPortal-AgentFeedback`, partition key `memberEmail` (String), sort key `interactionId` (String), PAY_PER_REQUEST billing, SSE enabled, and a `Project: ViewMyBill` tag.
2. THE CloudFormation stack SHALL add an API Gateway route for `POST /members/accounts/ai-feedback` integrated with the Member_Handler_Lambda.
3. THE Member_Handler_Lambda IAM role SHALL include permissions for `dynamodb:PutItem` on the Agent_Feedback_Table ARN.
4. THE Member_Handler_Lambda SHALL receive the Agent_Feedback_Table name as an environment variable `FEEDBACK_TABLE_NAME`.
