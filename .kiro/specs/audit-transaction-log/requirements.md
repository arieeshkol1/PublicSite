# Requirements Document

## Introduction

The Audit Transaction Log feature adds comprehensive observability to the SlashMyCloudBill platform by logging every user interaction and function call, evaluating transaction quality via a Bedrock-based audit agent, and exposing the results through a dedicated section in the Admin panel. This enables the platform operator to monitor system performance, identify quality issues, and continuously improve the AI and user experience.

## Glossary

- **Transaction_Logger**: The component responsible for capturing and persisting interaction data to the transaction log table.
- **Transaction_Log_Table**: A DynamoDB table that stores all logged transaction entries.
- **Audit_Agent**: A Bedrock agent (Claude Opus) that evaluates each logged transaction for quality, accuracy, and timing.
- **Admin_Transaction_UI**: The new section in the Admin panel that displays transaction log entries and their audit evaluations.
- **Transaction_Entry**: A single record representing one user interaction or function call, including request, response, function name, timing, and metadata.
- **Audit_Evaluation**: The output produced by the Audit_Agent for a given Transaction_Entry, containing a score, accuracy assessment, timing analysis, and improvement suggestions.
- **Admin_User**: An authenticated administrator who accesses the Admin panel.

## Requirements

### Requirement 1: Transaction Logging on User Interactions

**User Story:** As a platform operator, I want every user interaction and function call logged automatically, so that I have a complete audit trail of system activity.

#### Acceptance Criteria

1. WHEN a user invokes any function in the member-handler or admin-handler, THE Transaction_Logger SHALL create a Transaction_Entry in the Transaction_Log_Table within 2 seconds of the function completing.
2. THE Transaction_Entry SHALL contain the following fields: transaction_id (unique identifier), user_email, function_name, request_payload, response_payload, start_timestamp, end_timestamp, duration_ms, source_handler (member-handler or admin-handler), and status (success or error).
3. WHEN a function call results in an error, THE Transaction_Logger SHALL log the Transaction_Entry with status set to "error" and include the error message in the response_payload field.
4. THE Transaction_Logger SHALL generate a unique transaction_id using UUID v4 for each Transaction_Entry.
5. WHEN the Transaction_Log_Table write fails, THE Transaction_Logger SHALL log the failure to CloudWatch and continue processing the original request without interruption.

### Requirement 2: Transaction Log Data Schema

**User Story:** As a platform operator, I want transaction entries to be consistently structured, so that I can reliably query and analyze them.

#### Acceptance Criteria

1. THE Transaction_Log_Table SHALL use transaction_id as the partition key and start_timestamp as the sort key.
2. THE Transaction_Log_Table SHALL include a Global Secondary Index (GSI) on user_email with start_timestamp as the sort key.
3. THE Transaction_Log_Table SHALL include a Global Secondary Index (GSI) on function_name with start_timestamp as the sort key.
4. THE Transaction_Log_Table SHALL retain entries for a minimum of 90 days using DynamoDB Time-To-Live (TTL) on an expiry_ttl attribute.

### Requirement 3: Audit Agent Evaluation

**User Story:** As a platform operator, I want each transaction automatically evaluated for quality, so that I can identify poor interactions and improve the system.

#### Acceptance Criteria

1. WHEN a new Transaction_Entry is persisted to the Transaction_Log_Table, THE Audit_Agent SHALL evaluate the transaction within 30 seconds.
2. THE Audit_Agent SHALL produce an Audit_Evaluation containing: score (integer 0-100 where 0 is very bad and 100 is very good), accuracy_assessment (text describing whether the user request was properly addressed), timing_assessment (text describing whether the duration was acceptable), and improvement_suggestions (text describing what could be changed in the response).
3. THE Audit_Agent SHALL use the request_payload, response_payload, function_name, and duration_ms from the Transaction_Entry as input context for evaluation.
4. IF the Audit_Agent fails to evaluate a transaction, THEN THE Transaction_Logger SHALL mark the Audit_Evaluation status as "pending" and retry evaluation up to 3 times with exponential backoff.
5. THE Audit_Agent SHALL persist the Audit_Evaluation to the Transaction_Log_Table as additional attributes on the existing Transaction_Entry.

### Requirement 4: Admin UI - Transaction Log Viewer

**User Story:** As an admin user, I want to view all transaction log entries in the Admin panel, so that I can monitor platform activity.

#### Acceptance Criteria

1. WHEN an Admin_User navigates to the Transaction Log tab, THE Admin_Transaction_UI SHALL display a paginated table of Transaction_Entries sorted by start_timestamp in descending order.
2. THE Admin_Transaction_UI SHALL display the following columns: row number, user_email, function_name, duration_ms, score, status, and start_timestamp.
3. WHEN an Admin_User clicks on a Transaction_Entry row, THE Admin_Transaction_UI SHALL display a detail modal showing the full request_payload, response_payload, and Audit_Evaluation fields.
4. THE Admin_Transaction_UI SHALL load the initial page of 50 Transaction_Entries within 3 seconds.

### Requirement 5: Admin UI - Search and Filtering

**User Story:** As an admin user, I want to search and filter transaction logs, so that I can quickly find specific interactions.

#### Acceptance Criteria

1. THE Admin_Transaction_UI SHALL provide a text search input that filters Transaction_Entries by user_email, function_name, or request_payload content.
2. THE Admin_Transaction_UI SHALL provide filter controls for: date range (start and end date), score range (minimum and maximum), status (success or error), and source_handler.
3. WHEN an Admin_User applies filters, THE Admin_Transaction_UI SHALL update the displayed results within 2 seconds.
4. WHEN an Admin_User clears all filters, THE Admin_Transaction_UI SHALL return to showing all Transaction_Entries in descending chronological order.

### Requirement 6: Admin UI - Audit Evaluation Display

**User Story:** As an admin user, I want to see the audit evaluation for each transaction, so that I can assess quality and identify improvement areas.

#### Acceptance Criteria

1. THE Admin_Transaction_UI SHALL display the audit score as a color-coded badge in the table (green for 70-100, yellow for 40-69, red for 0-39).
2. WHEN an Admin_User opens the Transaction_Entry detail modal, THE Admin_Transaction_UI SHALL display the full Audit_Evaluation including score, accuracy_assessment, timing_assessment, and improvement_suggestions.
3. WHILE a Transaction_Entry has an Audit_Evaluation status of "pending", THE Admin_Transaction_UI SHALL display a "Pending" indicator instead of the score badge.

### Requirement 7: Transaction Logging Independence

**User Story:** As a platform operator, I want the transaction logging to be generic and not coupled to specific features, so that any new function is automatically logged.

#### Acceptance Criteria

1. THE Transaction_Logger SHALL operate as a decorator or middleware pattern that wraps function handlers without requiring modification to individual function implementations.
2. WHEN a new route is added to member-handler or admin-handler, THE Transaction_Logger SHALL automatically log calls to the new route without additional code changes beyond applying the decorator or middleware.
3. THE Transaction_Logger SHALL exclude sensitive fields (passwords, tokens, JWT secrets) from the request_payload and response_payload before persisting to the Transaction_Log_Table.

### Requirement 8: Admin Authentication for Transaction Log

**User Story:** As a platform operator, I want the transaction log to be accessible only to authenticated admins, so that sensitive interaction data is protected.

#### Acceptance Criteria

1. WHEN an unauthenticated request is made to the transaction log API endpoints, THE admin-handler SHALL return HTTP 401 status with an "Unauthorized" message.
2. THE admin-handler SHALL require a valid JWT token for all transaction log read operations.
