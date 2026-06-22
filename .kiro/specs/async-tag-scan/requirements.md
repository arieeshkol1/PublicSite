# Requirements Document

## Introduction

The tag resource scan (`POST /members/tags/scan`) currently runs synchronously and hits the API Gateway 29-second timeout for large AWS accounts with hundreds of resources across multiple regions. This results in partial scan results and a degraded user experience. This feature converts the tag scan to an asynchronous pattern — mirroring the existing waste scan (`POST /members/actions/scan`) — so the scan runs without timeout constraints and returns complete results for all regions and resources.

## Glossary

- **Tag_Scan_Service**: The backend system responsible for initiating, executing, and storing tag compliance scan results
- **Frontend**: The member portal JavaScript application (members.js) that initiates scans and displays results
- **Scan_Status_Endpoint**: The GET endpoint that returns the current state of an asynchronous tag scan
- **Scan_Kickoff_Endpoint**: The POST endpoint that initiates an asynchronous tag scan and returns immediately
- **DynamoDB_Store**: The MemberPortal-Members DynamoDB table where scan status and results are persisted
- **Lambda_Self_Invocation**: The pattern of a Lambda function invoking itself with InvocationType='Event' for background processing
- **Tag_Policy**: The set of required tag keys configured per member that resources are evaluated against
- **Resource_Groups_Tagging_API**: The AWS API used to discover resources and their tags across regions
- **Scan_ID**: A UUID that uniquely identifies each tag scan execution

## Requirements

### Requirement 1: Asynchronous Scan Initiation

**User Story:** As a member, I want the tag scan to return immediately when I start it, so that the request does not time out for large accounts.

#### Acceptance Criteria

1. WHEN a tag scan request is received at `POST /members/tags/scan`, THE Scan_Kickoff_Endpoint SHALL return an HTTP 200 response within 3 seconds containing a Scan_ID and status "in_progress"
2. WHEN a tag scan request is received, THE Scan_Kickoff_Endpoint SHALL validate the authentication token and verify account ownership before initiating the scan
3. WHEN a tag scan request is received, THE Scan_Kickoff_Endpoint SHALL check and consume credit tokens based on the member tier before initiating the scan
4. IF the authentication token is invalid or expired, THEN THE Scan_Kickoff_Endpoint SHALL return an appropriate HTTP error response without initiating a scan
5. IF the credit check fails due to insufficient credits, THEN THE Scan_Kickoff_Endpoint SHALL return an HTTP 403 response without initiating a scan

### Requirement 2: Background Scan Execution

**User Story:** As a member with a large AWS account, I want the tag scan to run without timeout limits, so that all regions and resources are scanned completely.

#### Acceptance Criteria

1. WHEN a tag scan is initiated, THE Tag_Scan_Service SHALL invoke itself asynchronously via Lambda_Self_Invocation to perform the full scan
2. WHILE the background scan is executing, THE Tag_Scan_Service SHALL scan ALL opted-in regions for the member's connected accounts using Resource_Groups_Tagging_API
3. WHILE the background scan is executing, THE Tag_Scan_Service SHALL evaluate every discovered resource against the member's Tag_Policy without any resource count cap
4. WHEN the background scan discovers resources, THE Tag_Scan_Service SHALL classify each resource as fully tagged, partially tagged, or untagged based on the Tag_Policy
5. WHEN the background scan completes, THE Tag_Scan_Service SHALL store the full results in DynamoDB_Store including the resource list, tag compliance summary, and discovered tag keys
6. WHEN the background scan completes, THE Tag_Scan_Service SHALL update the scan status to "complete" in DynamoDB_Store
7. IF the background scan encounters an unrecoverable error, THEN THE Tag_Scan_Service SHALL update the scan status to "failed" in DynamoDB_Store with an error message

### Requirement 3: Scan Status Polling

**User Story:** As a member, I want to check the progress of my tag scan, so that I know when results are ready.

#### Acceptance Criteria

1. WHEN a GET request is received at `/members/tags/scan-status` with a valid Scan_ID parameter, THE Scan_Status_Endpoint SHALL return the current scan status and results if complete
2. WHEN the scan status is "in_progress", THE Scan_Status_Endpoint SHALL return an HTTP 200 response with status "in_progress" and the scan start time
3. WHEN the scan status is "complete", THE Scan_Status_Endpoint SHALL return an HTTP 200 response with status "complete", the full resource list, summary statistics, and discovered tag keys
4. WHEN the scan status is "failed", THE Scan_Status_Endpoint SHALL return an HTTP 200 response with status "failed" and an error description
5. IF the Scan_ID does not match any scan for the authenticated member, THEN THE Scan_Status_Endpoint SHALL return an HTTP 404 response
6. IF the Scan_ID query parameter is missing, THEN THE Scan_Status_Endpoint SHALL return an HTTP 400 response

### Requirement 4: Frontend Polling and Progress Display

**User Story:** As a member, I want to see a progress indicator while the tag scan runs, so that I know the system is working.

#### Acceptance Criteria

1. WHEN a tag scan is initiated from the Frontend, THE Frontend SHALL display a progress indicator with a scanning message
2. WHILE the scan status is "in_progress", THE Frontend SHALL poll the Scan_Status_Endpoint every 3 to 5 seconds
3. WHEN the scan status transitions to "complete", THE Frontend SHALL stop polling and render the full resource list with tag compliance data
4. WHEN the scan status transitions to "failed", THE Frontend SHALL stop polling and display an error message to the member
5. IF polling does not receive a "complete" or "failed" status within 120 seconds, THEN THE Frontend SHALL stop polling and display a timeout message

### Requirement 5: Result Data Format Preservation

**User Story:** As a member, I want the tag scan results to contain the same data as before, so that the existing UI renders correctly with the async results.

#### Acceptance Criteria

1. WHEN a completed tag scan result is returned, THE Tag_Scan_Service SHALL include a resources array where each resource contains: ARN, resourceType, resourceId, name, account, region, existingTags, and missingTags
2. WHEN a completed tag scan result is returned, THE Tag_Scan_Service SHALL include a summary object with total, fullyTagged, partiallyTagged, and untagged counts
3. WHEN a completed tag scan result is returned, THE Tag_Scan_Service SHALL include the list of all discovered tag keys across scanned resources
4. THE Tag_Scan_Service SHALL load required tags from the member's Tag_Policy in DynamoDB_Store, falling back to the request body's requiredTags, and then to defaults (Environment, Owner, CostCenter, Application)

### Requirement 6: Scan State Persistence

**User Story:** As a member, I want my last tag scan results to be stored, so that I can view them without re-scanning.

#### Acceptance Criteria

1. WHEN a tag scan is initiated, THE Tag_Scan_Service SHALL store the initial scan state in DynamoDB_Store with Scan_ID, status "in_progress", start timestamp, and account IDs
2. WHEN the background scan completes, THE Tag_Scan_Service SHALL overwrite the scan state in DynamoDB_Store with the final results under a dedicated attribute (lastTagScan)
3. WHEN a member initiates a new tag scan while a previous scan exists, THE Tag_Scan_Service SHALL replace the previous scan state with the new scan state
