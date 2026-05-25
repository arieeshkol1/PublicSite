# Requirements Document

## Introduction

The SlashMyBill Admin Panel currently provides tabs for managing Leads, Tips, Feedback, Subscribers, and Schedules. This feature adds a new "Tips Sync" tab that gives the platform operator visibility into the automated tips sync process — showing the latest sync status, a daily log of sync activity (additions, edits, and a zero-value deleted column since the sync never deletes), and the ability to manually trigger a sync run directly from the admin panel. The admin-handler Lambda is extended with new API actions to read sync metadata, retrieve sync history logs, and invoke the tips-sync Lambda on demand.

## Glossary

- **Admin_Panel**: The existing admin web application at `admin/index.html` that uses a tab-based UI for platform management
- **Admin_Handler**: The Lambda function (`admin-handler/lambda_function.py`) that serves API requests from the Admin_Panel via API Gateway
- **Tips_Sync_Lambda**: The Lambda function named `slashmybill-tips-sync` responsible for syncing cost optimization tips from AWS sources to the Tips_Table
- **Tips_Table**: The DynamoDB table `ViewMyBill-CostOptimizationTips` in us-east-1 (account 991105135552) that stores tips and sync metadata
- **Sync_Metadata_Record**: A record in the Tips_Table with keys `service="SYSTEM"`, `tipId="SYNC_METADATA"` containing sync execution results
- **Sync_Log_Record**: A record in the Tips_Table with keys `service="SYSTEM"`, `tipId="SYNC_LOG#{iso_date}"` containing per-run sync history grouped by day
- **Tips_Sync_Tab**: The new tab added to the Admin_Panel that displays sync status, daily logs, and a manual trigger button
- **Sync_Status_Card**: A UI component within the Tips_Sync_Tab that displays the latest sync execution summary
- **Sync_History_Table**: A UI component within the Tips_Sync_Tab that displays daily sync log entries

## Requirements

### Requirement 1: Tips Sync Tab Navigation

**User Story:** As a platform operator, I want a dedicated "Tips Sync" tab in the Admin Panel, so that I can access sync monitoring without leaving the admin interface.

#### Acceptance Criteria

1. THE Admin_Panel SHALL display a "Tips Sync" tab button in the tab navigation bar alongside the existing Leads, Tips, Feedback, Subscribers, and Schedules tabs.
2. WHEN the platform operator clicks the "Tips Sync" tab button, THE Admin_Panel SHALL show the Tips_Sync_Tab content and hide all other tab content panels.
3. WHEN the Tips_Sync_Tab becomes visible, THE Admin_Panel SHALL fetch the latest sync status and sync history from the Admin_Handler.

### Requirement 2: Current Sync Status Display

**User Story:** As a platform operator, I want to see the current sync status at a glance, so that I can verify the sync is running correctly without checking CloudWatch.

#### Acceptance Criteria

1. THE Tips_Sync_Tab SHALL display a Sync_Status_Card containing the following fields from the Sync_Metadata_Record: last sync timestamp, trigger type (scheduled or manual), sources queried count, sources succeeded count, sources failed count, tips inserted count, tips updated count, and tips unchanged count.
2. WHEN the last sync completed successfully (sources failed count equals zero), THE Sync_Status_Card SHALL display a green success indicator next to the last sync timestamp.
3. WHEN the last sync had one or more source failures (sources failed count greater than zero), THE Sync_Status_Card SHALL display an amber warning indicator next to the last sync timestamp.
4. THE Sync_Status_Card SHALL format the last sync timestamp in a human-readable locale format consistent with other timestamps in the Admin_Panel.
5. IF the Sync_Metadata_Record does not exist in the Tips_Table, THEN THE Sync_Status_Card SHALL display a message indicating that no sync has been executed yet.

### Requirement 3: Daily Sync History Log

**User Story:** As a platform operator, I want to see a daily log of sync activity, so that I can track what was added and edited over time and confirm that nothing was deleted.

#### Acceptance Criteria

1. THE Tips_Sync_Tab SHALL display a Sync_History_Table with columns: Date, Added, Edited, Deleted, Trigger Type, and Duration.
2. THE Sync_History_Table SHALL display one row per day, sorted by date descending (most recent first).
3. THE Sync_History_Table SHALL always display zero in the Deleted column because the tips sync process does not delete records.
4. WHEN the Admin_Handler retrieves sync history, THE Admin_Handler SHALL read Sync_Log_Records from the Tips_Table and return entries grouped by day.
5. THE Sync_History_Table SHALL support pagination with a page size consistent with other tables in the Admin_Panel (15 rows per page).
6. IF no Sync_Log_Records exist in the Tips_Table, THEN THE Sync_History_Table SHALL display an empty state message indicating no sync history is available.

### Requirement 4: Manual Sync Trigger

**User Story:** As a platform operator, I want to trigger a tips sync manually from the admin panel, so that I can force an immediate refresh after adding new tips or when debugging sync issues.

#### Acceptance Criteria

1. THE Tips_Sync_Tab SHALL display a "Trigger Sync" button that allows the platform operator to initiate a manual sync.
2. WHEN the platform operator clicks the "Trigger Sync" button, THE Admin_Panel SHALL send a request to the Admin_Handler to invoke the Tips_Sync_Lambda with the payload `{"manual": true}`.
3. WHILE the manual sync invocation is in progress, THE Admin_Panel SHALL disable the "Trigger Sync" button and display a loading indicator to prevent duplicate invocations.
4. WHEN the Admin_Handler successfully invokes the Tips_Sync_Lambda, THE Admin_Panel SHALL display a success notification indicating the sync was triggered.
5. IF the Admin_Handler fails to invoke the Tips_Sync_Lambda, THEN THE Admin_Panel SHALL display an error notification with the failure reason and re-enable the "Trigger Sync" button.
6. WHEN the manual sync trigger succeeds, THE Admin_Panel SHALL refresh the Sync_Status_Card and Sync_History_Table after a 5-second delay to allow the sync Lambda to complete.

### Requirement 5: Admin Handler - Get Sync Status Action

**User Story:** As a developer, I want the Admin_Handler to expose an endpoint for retrieving sync metadata, so that the Tips_Sync_Tab can display the current sync status.

#### Acceptance Criteria

1. WHEN the Admin_Handler receives a GET request to `/admin/tips-sync/status`, THE Admin_Handler SHALL read the Sync_Metadata_Record from the Tips_Table using partition key `SYSTEM` and sort key `SYNC_METADATA`.
2. WHEN the Sync_Metadata_Record exists, THE Admin_Handler SHALL return a JSON response containing: lastSyncTimestamp, triggerType, sourcesQueried, sourcesSucceeded, sourcesFailed, tipsInserted, tipsUpdated, tipsUnchanged, and durationMs.
3. IF the Sync_Metadata_Record does not exist, THEN THE Admin_Handler SHALL return a JSON response with an empty object and HTTP status 200.
4. IF a DynamoDB read error occurs, THEN THE Admin_Handler SHALL return HTTP status 500 with an error message.

### Requirement 6: Admin Handler - Get Sync History Action

**User Story:** As a developer, I want the Admin_Handler to expose an endpoint for retrieving sync history logs, so that the Tips_Sync_Tab can display the daily activity table.

#### Acceptance Criteria

1. WHEN the Admin_Handler receives a GET request to `/admin/tips-sync/history`, THE Admin_Handler SHALL query the Tips_Table for all items with partition key `SYSTEM` and sort key beginning with `SYNC_LOG#`.
2. THE Admin_Handler SHALL return the sync log entries sorted by date descending.
3. WHEN sync log entries exist, THE Admin_Handler SHALL return a JSON response containing an array of log objects, each with: date, tipsInserted, tipsUpdated, tipsDeleted (always 0), triggerType, and durationMs.
4. IF no sync log entries exist, THEN THE Admin_Handler SHALL return a JSON response with an empty array and HTTP status 200.
5. IF a DynamoDB query error occurs, THEN THE Admin_Handler SHALL return HTTP status 500 with an error message.

### Requirement 7: Admin Handler - Trigger Manual Sync Action

**User Story:** As a developer, I want the Admin_Handler to expose an endpoint for triggering a manual sync, so that the platform operator can initiate syncs from the admin panel.

#### Acceptance Criteria

1. WHEN the Admin_Handler receives a POST request to `/admin/tips-sync/trigger`, THE Admin_Handler SHALL invoke the Tips_Sync_Lambda asynchronously using the AWS Lambda invoke API with invocation type `Event` and payload `{"manual": true}`.
2. WHEN the Lambda invocation succeeds (HTTP status 202 from AWS), THE Admin_Handler SHALL return HTTP status 200 with a success message indicating the sync was triggered.
3. IF the Lambda invocation fails, THEN THE Admin_Handler SHALL return HTTP status 500 with an error message describing the failure.
4. THE Admin_Handler SHALL use the Lambda function name `slashmybill-tips-sync` when invoking the Tips_Sync_Lambda.

### Requirement 8: Sync Log Record Creation in Tips Sync Lambda

**User Story:** As a developer, I want the Tips_Sync_Lambda to write a daily sync log record after each run, so that the admin panel can display historical sync activity.

#### Acceptance Criteria

1. WHEN the Tips_Sync_Lambda completes a sync run, THE Tips_Sync_Lambda SHALL write a Sync_Log_Record to the Tips_Table with partition key `SYSTEM` and sort key `SYNC_LOG#{iso_date}` where iso_date is the current date in `YYYY-MM-DD` format.
2. THE Sync_Log_Record SHALL contain: date, tipsInserted, tipsUpdated, tipsDeleted (always 0), triggerType, durationMs, and timestamp (full ISO 8601 with time).
3. WHEN multiple sync runs occur on the same day, THE Tips_Sync_Lambda SHALL update the existing Sync_Log_Record for that day by accumulating the tipsInserted and tipsUpdated counts and using the latest run timestamp and duration.

### Requirement 9: Admin Handler IAM Permissions for Sync Features

**User Story:** As a platform operator, I want the Admin_Handler to have the minimum permissions needed for sync features, so that the new endpoints work without over-privileging the Lambda.

#### Acceptance Criteria

1. THE Admin_Handler execution role SHALL have read permissions on the Tips_Table for the sync metadata and log records (`dynamodb:GetItem`, `dynamodb:Query` with condition on partition key `SYSTEM`).
2. THE Admin_Handler execution role SHALL have permissions to invoke the Tips_Sync_Lambda (`lambda:InvokeFunction` on the `slashmybill-tips-sync` function ARN).

### Requirement 10: UI Consistency with Existing Admin Panel

**User Story:** As a platform operator, I want the Tips Sync tab to look and feel consistent with the existing admin panel tabs, so that the experience is cohesive.

#### Acceptance Criteria

1. THE Tips_Sync_Tab SHALL use the same CSS classes, color scheme, and component patterns (stat cards, data tables, buttons, notifications) as the existing Admin_Panel tabs.
2. THE Sync_Status_Card SHALL use the same dark-background stat card layout used in the Feedback and Subscribers tabs for displaying summary metrics.
3. THE Sync_History_Table SHALL use the same `data-table` class and styling as other tables in the Admin_Panel, including sortable column headers and pagination controls.
4. THE "Trigger Sync" button SHALL use the `btn btn-primary` class consistent with other action buttons in the Admin_Panel.
