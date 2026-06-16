# Requirements Document

## Introduction

Add an "Anthropic (via GroundCover)" connection option to the AI vendor wizard in the SlashMyBill member portal. This extends the existing OpenAI vendor integration pattern — vendor selection, token validation, API connectivity test, KMS encryption, and DynamoDB storage — for GroundCover tokens. Scope is limited to the connection wizard and credential storage; no data fetching or dashboard integration.

## Glossary

- **Member_Portal**: The authenticated member-facing web application (members.js frontend + member-handler Lambda backend)
- **AI_Vendor_Wizard**: The modal UI flow for adding a new AI vendor connection (vendor selection → token input → test → store)
- **GroundCover_Token**: An API token issued by GroundCover with the prefix `gcsa_`
- **Member_Handler**: The backend Lambda function routing member API requests
- **Connection_Record**: A DynamoDB item in MemberPortal-Accounts representing a stored vendor connection
- **KMS**: AWS Key Management Service used for encrypting stored credentials

## Requirements

### Requirement 1: Vendor Selection

**User Story:** As a member, I want to see GroundCover as an option in the AI vendor wizard, so that I can connect my GroundCover account alongside OpenAI.

#### Acceptance Criteria

1. WHEN the user opens the AI vendor wizard, THE AI_Vendor_Wizard SHALL display both "AI Cost" (OpenAI) and "Anthropic (via GroundCover)" as selectable vendor options
2. WHEN the user selects "Anthropic (via GroundCover)", THE AI_Vendor_Wizard SHALL display a token input form with placeholder text indicating the `gcsa_` prefix format
3. WHEN the user selects a vendor, THE AI_Vendor_Wizard SHALL hide the selection step and show the token input form for that specific vendor

### Requirement 2: Token Format Validation

**User Story:** As a member, I want immediate feedback on invalid token formats, so that I don't submit obviously incorrect tokens to the backend.

#### Acceptance Criteria

1. WHEN a token is submitted on the frontend, THE AI_Vendor_Wizard SHALL validate that the token starts with the prefix `gcsa_` and has a total length between 20 and 200 characters inclusive
2. WHEN frontend validation fails, THE AI_Vendor_Wizard SHALL display an inline error message describing the validation failure
3. WHEN the backend receives a token, THE Member_Handler SHALL re-validate the `gcsa_` prefix and 20-200 character length before proceeding
4. WHEN backend validation fails, THE Member_Handler SHALL return a 400 response with error code `InvalidKeyFormat` and a descriptive message

### Requirement 3: Connection Test

**User Story:** As a member, I want the system to verify my GroundCover token works before saving it, so that I don't store invalid credentials.

#### Acceptance Criteria

1. WHEN testing a GroundCover connection, THE Member_Handler SHALL POST to the GroundCover API with the token in a `Bearer` Authorization header and `X-Backend-Id: groundcover` header
2. WHEN the GroundCover API returns HTTP 200, THE Member_Handler SHALL report connection success
3. WHEN the GroundCover API returns a non-200 status, THE Member_Handler SHALL report connection failure including the HTTP status code in the error message
4. WHEN the GroundCover API request times out after 10 seconds, THE Member_Handler SHALL report a timeout failure
5. WHEN a network error occurs during the GroundCover API call, THE Member_Handler SHALL report a connection error with a truncated message (max 100 characters)

### Requirement 4: Credential Storage

**User Story:** As a member, I want my GroundCover token stored securely, so that my credentials are protected at rest.

#### Acceptance Criteria

1. WHEN the connection test succeeds, THE Member_Handler SHALL encrypt the token using KMS with member email and accountId as encryption context
2. WHEN storing the connection, THE Member_Handler SHALL write a Connection_Record with `cloudProvider` set to `groundcover` and `vendorType` set to `ai_vendor`
3. WHEN the connection test fails, THE Member_Handler SHALL NOT write any record to DynamoDB
4. IF KMS encryption fails, THEN THE Member_Handler SHALL return a 500 error and NOT persist the record

### Requirement 5: Success and Failure States

**User Story:** As a member, I want consistent success/failure feedback matching the OpenAI flow, so that the experience feels unified across vendors.

#### Acceptance Criteria

1. WHEN a GroundCover connection is added successfully, THE Member_Handler SHALL return HTTP 201 with `success: true` and the connection record (excluding encrypted credentials)
2. WHEN a GroundCover connection fails, THE Member_Handler SHALL return HTTP 400 with `success: false` and an error message
3. WHEN the frontend receives a success response, THE AI_Vendor_Wizard SHALL display a success confirmation state
4. WHEN the frontend receives a failure response, THE AI_Vendor_Wizard SHALL display an error state with the failure message and a retry option

### Requirement 6: Test Existing Connection

**User Story:** As a member, I want to re-test an existing GroundCover connection, so that I can verify my token is still valid.

#### Acceptance Criteria

1. WHEN a user calls the test-groundcover-connection endpoint with a valid accountId, THE Member_Handler SHALL decrypt the stored token and re-test it against the GroundCover API
2. WHEN the re-test succeeds, THE Member_Handler SHALL update `connectionStatus` to `connected` and `lastTestedAt` to the current timestamp
3. WHEN the re-test fails, THE Member_Handler SHALL update `connectionStatus` to `failed`, store the failure reason (max 200 characters), and update `lastTestedAt`
4. WHEN the accountId does not belong to the authenticated member, THE Member_Handler SHALL return a 403 error

### Requirement 7: Connection List Display

**User Story:** As a member, I want GroundCover connections to appear in my AI vendor connections list, so that I can see and manage them.

#### Acceptance Criteria

1. WHEN displaying the AI vendor connections list, THE Member_Portal SHALL include GroundCover connections with their name, status, and last-tested timestamp
2. WHEN a GroundCover connection is displayed, THE Member_Portal SHALL show a "Test Connection" button that triggers the test-groundcover-connection endpoint
3. WHEN a GroundCover connection has status `failed`, THE Member_Portal SHALL display the failure reason
