# Requirements Document

## Introduction

SlashMyBill maintains a curated set of AWS cost optimization tips stored in a DynamoDB table (`ViewMyBill-CostOptimizationTips`). These tips power the Observe tab recommendations and are used by the member-handler Lambda during waste scans to match findings to actionable recommendations. Currently, tips are manually maintained in a JSON file (`knowledge-base/aws-cost-optimization-tips.json`) and loaded into DynamoDB through manual processes. This feature introduces an automated daily sync that fetches new and updated cost optimization tips from AWS FinOps sources (Cost Optimization Hub as primary, Trusted Advisor cost_optimizing category as secondary) and applies only the delta (new or changed tips) to the Tips_Table — keeping recommendations current without full table replacement.

## Glossary

- **Tips_Table**: The DynamoDB table `ViewMyBill-CostOptimizationTips` in the Platform_Account that stores all cost optimization tips
- **Platform_Account**: The SlashMyBill AWS account (991105135552, region us-east-1) where all platform infrastructure runs
- **Tips_Sync_Lambda**: A new Lambda function in the Platform_Account responsible for fetching tips from AWS sources and syncing deltas to the Tips_Table
- **Tips_Source_File**: The JSON file `knowledge-base/aws-cost-optimization-tips.json` that serves as the baseline tip definitions
- **Sync_Schedule**: An EventBridge Scheduler rule that triggers the Tips_Sync_Lambda daily
- **Tip_Record**: A single tip item in the Tips_Table, identified by its `id` field (e.g., `ec2-001`)
- **Delta_Sync**: The process of comparing fetched tips against existing Tips_Table records and applying only inserts and updates, without deleting existing tips
- **AWS_Sources**: The set of AWS services queried for FinOps tip data — Cost Optimization Hub (primary, aggregates all cost recommendations) and Trusted Advisor cost_optimizing category (secondary)
- **Sync_Metadata**: A record in the Tips_Table that tracks the last successful sync timestamp, source, and number of tips processed
- **Content_Hash**: A SHA-256 hash of a tip's content fields used to detect whether a tip has changed since the last sync

## Requirements

### Requirement 1: Daily Scheduled Trigger

**User Story:** As a platform operator, I want the tips sync to run automatically every day, so that the Tips_Table stays current without manual intervention.

#### Acceptance Criteria

1. THE Sync_Schedule SHALL trigger the Tips_Sync_Lambda once per day at a configured time (default: 02:00 UTC).
2. WHEN the Sync_Schedule triggers the Tips_Sync_Lambda, THE Tips_Sync_Lambda SHALL begin the sync process by querying all configured AWS_Sources.
3. IF the Tips_Sync_Lambda is already running when the Sync_Schedule fires (concurrent execution), THEN THE Tips_Sync_Lambda SHALL detect the concurrent run and exit gracefully without processing.

### Requirement 2: AWS Source Data Fetching

**User Story:** As a platform operator, I want the sync to pull cost optimization data from multiple AWS sources, so that tips reflect the latest AWS pricing and recommendations.

#### Acceptance Criteria

1. WHEN the Tips_Sync_Lambda executes, THE Tips_Sync_Lambda SHALL query AWS Cost Optimization Hub as the primary datasource for FinOps recommendations using the `cost-optimization-hub:ListRecommendations` API, which aggregates cost optimization recommendations from multiple AWS services into a single feed filtered exclusively to cost management actions.
2. WHEN the Tips_Sync_Lambda executes, THE Tips_Sync_Lambda SHALL query AWS Trusted Advisor as the secondary datasource, filtering only checks in the `cost_optimizing` category using the `support:DescribeTrustedAdvisorChecks` API with category filter and `support:DescribeTrustedAdvisorCheckResult` for check details.
3. IF a specific AWS_Source (Cost Optimization Hub or Trusted Advisor cost_optimizing) is unavailable or returns an error, THEN THE Tips_Sync_Lambda SHALL log the error, skip that source, and continue processing the remaining source.
4. THE Tips_Sync_Lambda SHALL NOT query AWS Compute Optimizer or AWS Pricing API directly — cost-relevant recommendations from these services are already aggregated by Cost Optimization Hub.

### Requirement 3: Delta Detection and Sync

**User Story:** As a platform operator, I want only new or changed tips synced to the table, so that existing tip metadata (custom fields, action configurations) is preserved and unnecessary writes are avoided.

#### Acceptance Criteria

1. WHEN the Tips_Sync_Lambda processes fetched data, THE Tips_Sync_Lambda SHALL compute a Content_Hash for each tip based on the `title`, `description`, `estimatedSavings`, and `automatedCheck` fields.
2. WHEN a fetched tip has an `id` that does not exist in the Tips_Table, THE Tips_Sync_Lambda SHALL insert the tip as a new Tip_Record with all standard fields and a `syncSource` attribute indicating the originating AWS_Source.
3. WHEN a fetched tip has an `id` that exists in the Tips_Table and the Content_Hash differs from the stored hash, THE Tips_Sync_Lambda SHALL update only the changed content fields (`title`, `description`, `estimatedSavings`, `automatedCheck`) while preserving existing operational fields (`actionType`, `actionLabel`, `actionTarget`, `implementedInAct`, `implementedInScheduler`, `level`).
4. WHEN a fetched tip has an `id` that exists in the Tips_Table and the Content_Hash matches the stored hash, THE Tips_Sync_Lambda SHALL skip the tip without writing to the Tips_Table.
5. THE Tips_Sync_Lambda SHALL NOT delete any existing Tip_Record from the Tips_Table during the sync process.

### Requirement 4: Tip Record Schema Compliance

**User Story:** As a developer, I want synced tips to conform to the existing tip schema, so that the agent-action Lambda and member-handler Lambda can consume them without modification.

#### Acceptance Criteria

1. THE Tips_Sync_Lambda SHALL produce Tip_Records containing all required fields: `id`, `service`, `category`, `title`, `description`, `estimatedSavings`, `difficulty`, and `automatedCheck`.
2. WHEN inserting a new Tip_Record from an AWS_Source, THE Tips_Sync_Lambda SHALL set default values for operational fields: `checkImplemented` to `false`, `actionType` to `advisory`, `actionLabel` to `View Details`, and `level` to `3`.
3. THE Tips_Sync_Lambda SHALL generate the `id` field for new tips using the pattern `{service_lowercase}-{sequential_number}` (e.g., `ec2-042`) ensuring uniqueness against existing Tips_Table records.

### Requirement 5: Sync Metadata and Observability

**User Story:** As a platform operator, I want visibility into sync execution results, so that I can verify the sync is working and troubleshoot failures.

#### Acceptance Criteria

1. WHEN the Tips_Sync_Lambda completes a sync run, THE Tips_Sync_Lambda SHALL write a Sync_Metadata record to the Tips_Table with partition key `SYNC_METADATA`, containing: `lastSyncTimestamp`, `sourcesQueried`, `sourcesSucceeded`, `sourcesFailed`, `tipsInserted`, `tipsUpdated`, `tipsUnchanged`, and `durationMs`.
2. WHEN the Tips_Sync_Lambda encounters an unrecoverable error that prevents completion, THE Tips_Sync_Lambda SHALL publish a CloudWatch metric `TipsSyncFailure` with value 1 to the `SlashMyBill/TipsSync` namespace.
3. THE Tips_Sync_Lambda SHALL log each sync operation (source query, tip insert, tip update, tip skip) at INFO level with structured JSON log entries including the tip `id` and source name.
4. WHEN the Tips_Sync_Lambda completes successfully, THE Tips_Sync_Lambda SHALL publish a CloudWatch metric `TipsSyncSuccess` with value 1 and a `TipsSyncDuration` metric with the execution duration in milliseconds to the `SlashMyBill/TipsSync` namespace.

### Requirement 6: Baseline Tips File Integration

**User Story:** As a developer, I want the sync to also incorporate updates from the local Tips_Source_File, so that manually curated tips are included in the delta sync alongside AWS-sourced tips.

#### Acceptance Criteria

1. WHEN the Tips_Sync_Lambda executes, THE Tips_Sync_Lambda SHALL read the Tips_Source_File from the Lambda deployment package and include its tips in the delta comparison.
2. WHEN a tip exists in both the Tips_Source_File and an AWS_Source with the same `id`, THE Tips_Sync_Lambda SHALL prefer the Tips_Source_File version because manually curated tips contain richer operational metadata.
3. WHEN the Tips_Source_File cannot be read (file missing or malformed JSON), THE Tips_Sync_Lambda SHALL log a warning and continue processing AWS_Sources without the baseline file.

### Requirement 7: Concurrency and Data Integrity

**User Story:** As a platform operator, I want the sync to handle concurrent access safely, so that simultaneous reads from the agent-action Lambda do not conflict with sync writes.

#### Acceptance Criteria

1. WHEN writing Tip_Records to the Tips_Table, THE Tips_Sync_Lambda SHALL use DynamoDB conditional writes with a version attribute to prevent overwriting concurrent manual edits.
2. WHEN a conditional write fails due to a version conflict, THE Tips_Sync_Lambda SHALL log the conflict, skip that tip, and continue processing remaining tips.
3. THE Tips_Sync_Lambda SHALL process tips in batches of no more than 25 items per DynamoDB BatchWriteItem call to stay within DynamoDB limits.

### Requirement 8: IAM Permissions

**User Story:** As a platform operator, I want the Tips_Sync_Lambda to have least-privilege permissions, so that the sync function can access only the resources it needs.

#### Acceptance Criteria

1. THE Tips_Sync_Lambda execution role SHALL have read and write permissions on the Tips_Table (`dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:UpdateItem`, `dynamodb:Query`, `dynamodb:Scan`, `dynamodb:BatchWriteItem`).
2. THE Tips_Sync_Lambda execution role SHALL have read permissions for AWS_Sources: `support:DescribeTrustedAdvisorChecks`, `support:DescribeTrustedAdvisorCheckResult`, `cost-optimization-hub:ListRecommendations`, `cost-optimization-hub:GetRecommendation`.
3. THE Tips_Sync_Lambda execution role SHALL have permissions to publish CloudWatch metrics (`cloudwatch:PutMetricData`) to the `SlashMyBill/TipsSync` namespace.
4. THE Tips_Sync_Lambda execution role SHALL have permissions to write CloudWatch Logs (`logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`).

### Requirement 9: Deployment and CI/CD Integration

**User Story:** As a platform operator, I want the Tips_Sync_Lambda deployed through the existing CI/CD pipeline, so that changes are deployed automatically on push to main.

#### Acceptance Criteria

1. WHEN code is pushed to the `main` branch with changes in the `tips-sync/` directory, THE deploy pipeline SHALL package the Tips_Sync_Lambda code into a zip file, upload the zip to the S3 storage bucket, and update the Lambda function code.
2. THE deploy pipeline SHALL create the EventBridge Scheduler rule for the Sync_Schedule if it does not already exist.
3. THE deploy pipeline SHALL include the `tips-sync/**` path in the deploy trigger paths.

### Requirement 10: Manual Trigger Support

**User Story:** As a platform operator, I want to trigger the tips sync manually, so that I can force an immediate refresh after adding new tips to the source file or when debugging.

#### Acceptance Criteria

1. WHEN the Tips_Sync_Lambda is invoked with a manual trigger event (event containing `{"manual": true}`), THE Tips_Sync_Lambda SHALL execute the full sync process immediately regardless of the Sync_Schedule.
2. WHEN manually triggered, THE Tips_Sync_Lambda SHALL include `"triggerType": "manual"` in the Sync_Metadata record to distinguish manual runs from scheduled runs.
