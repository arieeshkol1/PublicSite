# Requirements Document

## Introduction

Add a "Tips Sync" tab to the existing Admin Panel that displays sync status information, a historical daily sync log showing what was added or edited per run, and a "Trigger Manual Sync" button. This feature requires backend changes to the tips-sync Lambda (to write per-run log records to DynamoDB), a new API route in admin-handler (to trigger manual sync and retrieve sync logs), and a new frontend tab in the admin panel.

## Glossary

- **Admin_Panel**: The web-based administration interface at `/admin/index.html` used to manage leads, tips, feedback, subscribers, and schedules for SlashMyCloudBill.
- **Tips_Sync_Lambda**: The AWS Lambda function (`slashmybill-tips-sync`) that synchronizes cost optimization tips from multiple sources into the DynamoDB table.
- **Admin_Handler**: The AWS Lambda function that serves the admin API routes at `https://l2fd4h481h.execute-api.us-east-1.amazonaws.com/admin/*`.
- **Tips_Table**: The DynamoDB table `ViewMyBill-CostOptimizationTips` with partition key `service` and sort key `tipId`.
- **Sync_Log_Record**: A DynamoDB item in the Tips_Table with `service=SYSTEM` and `tipId=SYNC_LOG#<ISO-timestamp>` that stores per-run sync execution details.
- **SYNC_METADATA**: The existing DynamoDB item (`service=SYSTEM`, `tipId=SYNC_METADATA`) that stores the latest sync run summary and gets overwritten each run.
- **Tips_Sync_Tab**: The new tab in the Admin_Panel that displays sync status, historical sync logs, and a manual trigger button.

## Requirements

### Requirement 1: Sync Log Record Persistence

**User Story:** As an admin, I want each sync run to persist a log record in DynamoDB, so that I can view historical sync activity over time.

#### Acceptance Criteria

1. WHEN a sync run completes successfully, THE Tips_Sync_Lambda SHALL write a Sync_Log_Record to the Tips_Table with `service=SYSTEM` and `tipId=SYNC_LOG#<ISO-8601-timestamp>`.
2. THE Sync_Log_Record SHALL contain the fields: `timestamp`, `triggerType`, `sourcesQueried`, `sourcesSucceeded`, `sourcesFailed`, `tipsInserted`, `tipsUpdated`, `tipsUnchanged`, `durationMs`, and `status`.
3. WHEN a sync run fails with an unrecoverable error, THE Tips_Sync_Lambda SHALL write a Sync_Log_Record with `status` set to `failed` and an `errorMessage` field containing the error description.
4. THE Tips_Sync_Lambda SHALL continue to write the SYNC_METADATA record as it does currently, in addition to the new Sync_Log_Record.

### Requirement 2: Admin API - Retrieve Sync Logs

**User Story:** As an admin, I want an API endpoint to retrieve sync log history, so that the frontend can display historical sync data.

#### Acceptance Criteria

1. WHEN a GET request is received at `/admin/tips-sync/logs`, THE Admin_Handler SHALL query the Tips_Table for all items where `service=SYSTEM` and `tipId` begins with `SYNC_LOG#`.
2. THE Admin_Handler SHALL return the sync log records sorted by timestamp in descending order.
3. THE Admin_Handler SHALL return the current SYNC_METADATA record alongside the log records in the response.
4. IF no sync log records exist, THEN THE Admin_Handler SHALL return an empty array for the logs and the SYNC_METADATA record if available.

### Requirement 3: Admin API - Retrieve Sync Status

**User Story:** As an admin, I want to see the current sync status at a glance, so that I can quickly assess the health of the tips sync process.

#### Acceptance Criteria

1. WHEN a GET request is received at `/admin/tips-sync/status`, THE Admin_Handler SHALL return the SYNC_METADATA record from the Tips_Table.
2. THE response SHALL include: `lastSyncTimestamp`, `triggerType`, `sourcesSucceeded`, `sourcesFailed`, `tipsInserted`, `tipsUpdated`, `tipsUnchanged`, and `durationMs`.
3. IF no SYNC_METADATA record exists, THEN THE Admin_Handler SHALL return a response indicating that no sync has been executed.

### Requirement 4: Admin API - Trigger Manual Sync

**User Story:** As an admin, I want to trigger a manual sync from the admin panel, so that I can force a refresh of tips without waiting for the scheduled run.

#### Acceptance Criteria

1. WHEN a POST request is received at `/admin/tips-sync/trigger`, THE Admin_Handler SHALL invoke the Tips_Sync_Lambda with the payload `{"manual": true}`.
2. THE Admin_Handler SHALL invoke the Lambda asynchronously using the `InvocationType` of `Event`.
3. WHEN the Lambda invocation is accepted, THE Admin_Handler SHALL return a 202 status code with a confirmation message.
4. IF the Lambda invocation fails, THEN THE Admin_Handler SHALL return a 500 status code with an error description.

### Requirement 5: Frontend - Tips Sync Tab Layout

**User Story:** As an admin, I want a dedicated "Tips Sync" tab in the admin panel, so that I can monitor and manage the sync process from one place.

#### Acceptance Criteria

1. THE Admin_Panel SHALL display a "Tips Sync" tab button in the tab navigation bar.
2. WHEN the "Tips Sync" tab is selected, THE Admin_Panel SHALL display three sections: status cards, a sync history table, and a manual trigger button.
3. THE status cards section SHALL display: last sync timestamp, last sync status (success or failed), sync duration, and sources summary (succeeded vs failed).
4. THE sync history table SHALL display columns for: timestamp, trigger type, tips inserted, tips updated, tips unchanged, duration, sources succeeded, and status.

### Requirement 6: Frontend - Sync History Display

**User Story:** As an admin, I want to see a paginated table of past sync runs, so that I can review what changed over time.

#### Acceptance Criteria

1. WHEN the Tips_Sync_Tab loads, THE Admin_Panel SHALL fetch sync log records from the `/admin/tips-sync/logs` endpoint.
2. THE Admin_Panel SHALL display sync log records in a table sorted by timestamp descending.
3. THE Admin_Panel SHALL paginate the sync history table with 15 records per page.
4. THE Admin_Panel SHALL color-code the status column: green for successful runs and red for failed runs.

### Requirement 7: Frontend - Manual Sync Trigger

**User Story:** As an admin, I want a button to trigger a manual sync, so that I can refresh tips on demand.

#### Acceptance Criteria

1. THE Admin_Panel SHALL display a "Trigger Manual Sync" button in the Tips_Sync_Tab.
2. WHEN the admin clicks the "Trigger Manual Sync" button, THE Admin_Panel SHALL send a POST request to `/admin/tips-sync/trigger`.
3. WHEN the trigger request succeeds, THE Admin_Panel SHALL display a success notification indicating the sync has been queued.
4. WHILE a trigger request is in progress, THE Admin_Panel SHALL disable the trigger button and display a loading state.
5. IF the trigger request fails, THEN THE Admin_Panel SHALL display an error notification with the failure reason.

### Requirement 8: Authentication for Sync Endpoints

**User Story:** As an admin, I want the sync endpoints to be protected, so that only authenticated admins can view sync data or trigger syncs.

#### Acceptance Criteria

1. THE Admin_Handler SHALL validate the JWT token for all `/admin/tips-sync/*` routes using the same authentication mechanism as existing admin routes.
2. IF the token is missing or invalid, THEN THE Admin_Handler SHALL return a 401 status code with an authentication error message.
