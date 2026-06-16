# Requirements Document

## Introduction

The Custom Data Source Wizard enables members to manually configure and populate the Cost_Cache_Table with cost data from sources not covered by automated integrations (AWS, Azure, GCP, OpenAI). Members define named custom sources, upload data via CSV or manual entry, and see the data alongside automated data in the Observe tab. The system reuses the existing CacheService and account management patterns.

## Glossary

- **System**: The Custom Data Source Wizard feature (frontend wizard + backend API routes + DynamoDB integration)
- **Member**: An authenticated user of the member portal with a valid JWT
- **Custom_Source**: A named data source record in MemberPortal-Accounts with cloudProvider "custom"
- **Cost_Cache_Table**: DynamoDB table storing daily cost data items for all providers
- **CacheService**: Existing Python class managing reads/writes to Cost_Cache_Table
- **Wizard**: The multi-step modal UI for creating sources and uploading data
- **CSV_Parser**: Client-side JavaScript function that parses and validates CSV input
- **AccountId**: Unique identifier for a custom source in format `custom-{slug}-{12hex}`
- **CostDataItem**: A single day's aggregated cost data for one account
- **Observe_Tab**: The dashboard view showing aggregated cost data across all providers

## Requirements

### Requirement 1: Create Custom Data Source

**User Story:** As a member, I want to define a new custom data source with a descriptive name, so that I can organize my non-automated cost data by provider.

#### Acceptance Criteria

1. WHEN a member submits a valid source name (1-50 characters, alphanumeric/spaces/hyphens/periods), THE System SHALL create a Custom_Source record in MemberPortal-Accounts with cloudProvider set to "custom" and connectionStatus set to "connected"
2. WHEN a Custom_Source is created, THE System SHALL set the displayName to the user-provided name and generate a valid addedAt ISO 8601 timestamp
3. WHEN a Custom_Source is created, THE System SHALL generate an AccountId matching the pattern `custom-{slug}-{12 hex chars}` where slug is derived from the source name
4. IF a member submits a source name that already exists for that member (case-insensitive), THEN THE System SHALL return a 409 status and not create a duplicate record
5. IF a member submits an empty name or a name exceeding 50 characters, THEN THE System SHALL return a 400 status with a descriptive error message
6. IF a member submits a name containing characters other than alphanumeric, spaces, hyphens, or periods, THEN THE System SHALL return a 400 status with a descriptive error message


### Requirement 2: List Custom Data Sources

**User Story:** As a member, I want to see all my custom data sources, so that I can manage them and upload additional data.

#### Acceptance Criteria

1. WHEN a member requests their custom sources list, THE System SHALL return all Custom_Source records belonging to that member with displayName, accountId, connectionStatus, addedAt, and lastUpdatedAt fields
2. WHEN a member has no custom sources, THE System SHALL return an empty sources array with a 200 status

### Requirement 3: CSV Upload and Parsing

**User Story:** As a member, I want to upload cost data via CSV file, so that I can bulk-import data from external systems without manual row-by-row entry.

#### Acceptance Criteria

1. WHEN a valid CSV file is provided with headers (date, service_name, cost_amount, currency) and valid data rows, THE CSV_Parser SHALL parse all rows into valid cost data objects with no errors
2. WHEN a CSV row contains an invalid date (not YYYY-MM-DD or not a real calendar date), invalid cost_amount (not positive, not numeric), empty service_name, or invalid currency (not 3 uppercase letters), THE CSV_Parser SHALL report an error for that row with the line number and a descriptive message
3. WHEN a CSV file is missing required headers, THE CSV_Parser SHALL return an error indicating which headers are missing
4. WHEN a CSV file contains empty lines, THE CSV_Parser SHALL skip them without generating errors
5. THE CSV_Parser SHALL trim whitespace from all field values before validation

### Requirement 4: Data Upload and Storage

**User Story:** As a member, I want my uploaded cost data to be stored in the same format as automated integrations, so that it appears seamlessly in the Observe tab.

#### Acceptance Criteria

1. WHEN valid cost data rows are submitted, THE System SHALL aggregate rows with the same date into a single CostDataItem with a service_breakdown map containing each service_name and its cost_amount
2. WHEN multiple rows share the same date and service_name, THE System SHALL sum their cost_amounts in the service_breakdown
3. WHEN cost data is written to Cost_Cache_Table, THE System SHALL use the exact schema: pk as `{member_email}#{accountId}`, sk as `DAILY#{YYYY-MM-DD}`, cost_amount as string decimal, currency as string, service_breakdown as map, fetched_at as ISO 8601, and ttl as epoch integer 90 days from fetched_at
4. WHEN data is uploaded for a date that already has an entry for the same source, THE System SHALL overwrite the existing entry (upsert behavior)
5. THE System SHALL reject uploads with fewer than 1 or more than 1000 rows, returning a 400 status


### Requirement 5: Security and Tenant Isolation

**User Story:** As a member, I want my custom data sources and cost data to be private to my account, so that no other member can access or modify my data.

#### Acceptance Criteria

1. WHEN a data upload or delete request references an accountId that does not belong to the authenticated member, THE System SHALL return a 403 status and perform no writes
2. WHEN any custom source operation is requested without a valid JWT, THE System SHALL return a 401 status
3. THE System SHALL verify account ownership by querying MemberPortal-Accounts before any read or write to Cost_Cache_Table for custom sources

### Requirement 6: Delete Custom Data Source

**User Story:** As a member, I want to delete a custom data source I no longer need, so that it no longer appears in my Observe tab and its data is cleaned up.

#### Acceptance Criteria

1. WHEN a member deletes a Custom_Source, THE System SHALL remove the MemberPortal-Accounts record for that source
2. WHEN a Custom_Source is deleted, THE System SHALL remove all Cost_Cache_Table items associated with that source's partition key
3. IF a member attempts to delete a source that does not exist or does not belong to them, THEN THE System SHALL return a 404 or 403 status respectively

### Requirement 7: Delete Custom Data Range

**User Story:** As a member, I want to delete specific date ranges of cost data from a custom source, so that I can correct mistakes without deleting the entire source.

#### Acceptance Criteria

1. WHEN a member requests deletion of data for a date range (startDate, endDate), THE System SHALL remove only Cost_Cache_Table items within that range for the specified source
2. WHEN startDate or endDate are invalid formats, THE System SHALL return a 400 status with descriptive error
3. THE System SHALL verify account ownership before performing any data deletion

### Requirement 8: Wizard UI Flow

**User Story:** As a member, I want a guided step-by-step wizard for creating custom sources and uploading data, so that the process is intuitive and prevents errors.

#### Acceptance Criteria

1. WHEN the wizard opens, THE System SHALL display Step 1 (source name input) with a progress indicator showing 4 total steps
2. WHEN the member completes Step 1 with a valid name, THE System SHALL advance to Step 2 (choose input method: CSV or Manual)
3. WHEN the member selects CSV upload in Step 2, THE System SHALL advance to Step 3 showing a file picker and CSV preview table
4. WHEN the member selects Manual entry in Step 2, THE System SHALL advance to Step 3 showing an editable row table with add/remove row controls
5. WHEN Step 3 data is valid and confirmed, THE System SHALL advance to Step 4 showing a summary with source name, row count, date range, and total cost
6. WHEN the member confirms in Step 4, THE System SHALL create the source and upload the data, then close the wizard and show a success notification


### Requirement 9: Observe Tab Integration

**User Story:** As a member, I want my custom data source cost data to appear in the Observe tab alongside AWS/Azure/OpenAI data, so that I have a unified view of all my costs.

#### Acceptance Criteria

1. WHEN the Observe tab queries cost data, THE System SHALL include custom source data from Cost_Cache_Table using the same query pattern as automated integrations
2. WHEN displaying custom source data in the Observe tab, THE System SHALL show the source displayName as the account label
3. WHEN aggregating costs across all sources, THE System SHALL include custom source costs in the totals

### Requirement 10: Input Validation

**User Story:** As a member, I want clear validation feedback when my data has errors, so that I can correct issues before submission.

#### Acceptance Criteria

1. WHEN a cost_amount is zero, negative, or exceeds 999,999,999.99, THE System SHALL reject the row with a descriptive error
2. WHEN a date is in the future (after today), THE System SHALL reject the row with a descriptive error
3. WHEN a service_name exceeds 100 characters, THE System SHALL reject the row with a descriptive error
4. WHEN server-side validation fails, THE System SHALL return all validation errors at once (not fail on first error) with row numbers
5. WHEN client-side CSV parsing finds errors, THE Wizard SHALL display them inline with the affected rows highlighted
