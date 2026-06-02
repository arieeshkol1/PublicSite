# Implementation Plan: Multi-Cloud Support

## Overview

This plan extends the SlashMyBill FinOps platform from AWS-only to multi-cloud (AWS, Azure, GCP) using a provider-connector pattern. Azure is first priority — full end-to-end Azure support is implemented before GCP. The implementation follows five phases: Infrastructure, Azure Backend, Azure Frontend, GCP (same pattern), and Tips & Polish.

## Tasks

- [ ] 1. Infrastructure Setup (KMS, Schema, Connectors Package)
  - [ ] 1.1 Create KMS encryption key in CloudFormation stack
    - Add an `AWS::KMS::Key` resource to `infrastructure/viewmybill-stack.yaml` with alias `alias/slashmybill-credentials`
    - Add key policy restricting Encrypt/Decrypt to the Member Handler Lambda execution role
    - Add KMS key ARN as environment variable on the Member Handler Lambda
    - _Requirements: 10.1, 10.5_

  - [ ] 1.2 Create connectors package with base interface
    - Create `member-handler/connectors/__init__.py` with connector registry
    - Create `member-handler/connectors/base_connector.py` with abstract `ProviderConnector` class defining `authenticate`, `test_connection`, `get_cost_data` methods
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ] 1.3 Extract existing AWS logic into AWS connector
    - Create `member-handler/connectors/aws_connector.py` implementing `ProviderConnector`
    - Move existing STS AssumeRole and Cost Explorer logic from `member-handler/lambda_function.py` into the connector
    - Ensure existing AWS flow calls the new connector (no behavior change)
    - _Requirements: 6.1, 13.1, 13.4, 13.5_

  - [ ] 1.4 Create Cost Normalizer module
    - Create `member-handler/cost_normalizer.py` with `normalize_aws`, `normalize_azure`, `normalize_gcp` functions
    - Each function transforms provider-specific responses into common schema: `{date, service_name, cost_amount, currency, cloud_provider, account_id}`
    - Implement `aggregate_costs` function that collects results from multiple accounts, skipping failures
    - _Requirements: 5.3, 6.4, 6.5_

  - [ ] 1.5 Extend Accounts table schema handling in Lambda
    - Modify account read paths in `member-handler/lambda_function.py` to backfill `cloudProvider: "aws"` for legacy records missing the attribute
    - Add `cloudProvider` validation (must be "aws", "azure", or "gcp") on all write operations
    - Add duplicate `accountId` check per member (409 Conflict if exists regardless of provider)
    - _Requirements: 9.1, 9.3, 9.4, 9.5, 9.6, 13.2_

- [ ] 2. Checkpoint — Infrastructure verification
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Azure Backend (Connector, Encryption, API Extensions)
  - [ ] 3.1 Implement Azure connector
    - Create `member-handler/connectors/azure_connector.py` implementing `ProviderConnector`
    - Implement `authenticate`: OAuth2 client credentials flow to `https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token`
    - Implement `test_connection`: call Azure Cost Management query API to verify read access
    - Implement `get_cost_data`: query Azure Cost Management API with daily granularity grouped by service name
    - Handle Azure-specific errors (invalid credentials, expired secret, insufficient permissions)
    - _Requirements: 2.1, 4.1, 4.2, 4.3, 6.2_

  - [ ] 3.2 Implement KMS credential encryption/decryption helper
    - Create utility functions in `member-handler/connectors/kms_helpers.py` for `encrypt_credential(plaintext)` and `decrypt_credential(ciphertext)`
    - Use boto3 KMS client with the dedicated key alias
    - Discard decrypted values from memory after use
    - Handle KMS failures with 500 status and generic user message
    - _Requirements: 10.1, 10.2, 10.4_

  - [ ] 3.3 Extend POST /members/accounts for Azure
    - Accept `cloudProvider: "azure"` with fields: `subscriptionId` (stored as `accountId`), `tenantId`, `clientId`, optional `clientSecret`
    - Validate Azure-specific formats: Subscription ID and Tenant ID as UUID, Client ID as UUID
    - If `clientSecret` provided, encrypt with KMS before storing
    - Store credentials map: `{tenantId, clientId, encryptedClientSecret}` in Accounts_Table
    - Set `connectionStatus: "pending"` if no secret provided
    - _Requirements: 1.3, 1.5, 1.6, 2.1, 2.4, 2.5_

  - [ ] 3.4 Extend POST /members/accounts/test for Azure
    - Route to Azure connector when `cloudProvider` is "azure"
    - Decrypt Client Secret from KMS, call Azure connector `authenticate` then `test_connection`
    - On success: update `connectionStatus` to "connected", set `lastTestedAt`
    - On failure: update `connectionStatus` to "failed", return descriptive error
    - Never return sensitive credential values in response
    - _Requirements: 4.1, 4.2, 4.3, 10.2, 10.3_

  - [ ] 3.5 Extend GET /members/dashboard-data for multi-provider aggregation
    - Query all connected accounts for the member (filter by `connectionStatus: "connected"`)
    - Dispatch cost retrieval to correct connector based on `cloudProvider`
    - Use Cost Normalizer to transform all responses to common schema
    - Build `costByProvider` breakdown with totals and percentages
    - Cache results with key format `{memberEmail}#{cloudProvider}#{accountId}#{dateRange}`
    - Skip failed accounts without blocking others
    - _Requirements: 5.1, 5.2, 5.4, 5.6, 6.5, 6.6_

  - [ ]* 3.6 Write property tests for input validation (P1, P2, P19)
    - **Property 1: Provider-specific input format validation**
    - **Property 2: Account creation stores correct cloudProvider**
    - **Property 19: Only valid cloudProvider values accepted**
    - **Validates: Requirements 1.5, 1.6, 2.1, 3.1, 9.1, 9.6**

  - [ ]* 3.7 Write property tests for credential encryption (P4, P20)
    - **Property 4: Credential encryption round-trip**
    - **Property 20: No sensitive credentials in API responses**
    - **Validates: Requirements 2.4, 3.4, 10.1, 10.3**

  - [ ]* 3.8 Write property tests for connection testing (P5, P18)
    - **Property 5: Successful connection test updates status**
    - **Property 18: Duplicate accountId rejected regardless of provider**
    - **Validates: Requirements 4.2, 4.5, 9.4, 9.5**

  - [ ]* 3.9 Write property tests for cost normalization (P6, P7, P8, P9, P10)
    - **Property 6: Cost normalization produces complete common schema**
    - **Property 7: Provider breakdown percentages are consistent**
    - **Property 8: Only connected accounts contribute to cost calculations**
    - **Property 9: Failed account retrieval does not block others**
    - **Property 10: Cache key uniquely identifies provider and account**
    - **Validates: Requirements 5.3, 5.4, 5.6, 6.4, 6.5, 6.6**

  - [ ]* 3.10 Write unit tests for Azure connector
    - Create `member-handler/tests/test_azure_connector_unit.py`
    - Test OAuth2 token exchange with mocked Azure API
    - Test cost data retrieval with mocked response
    - Test error handling (invalid credentials, timeout, rate limit)
    - _Requirements: 4.1, 4.3, 6.2_

- [ ] 4. Checkpoint — Azure backend verification
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Azure Frontend (Provider Selection, Forms, Icons)
  - [ ] 5.1 Add provider selection step to Add Account modal
    - Modify `members/members.js` to show a provider selection UI with three cards (AWS, Azure, GCP) with logos when "Add Account" is clicked
    - Only proceed to provider-specific form after selection
    - AWS selection shows existing 12-digit Account ID form
    - _Requirements: 1.1, 1.2_

  - [ ] 5.2 Implement Azure-specific account form
    - Add Azure form fields: Subscription ID, Tenant ID, Client ID, Client Secret (optional)
    - Add client-side UUID validation for Subscription ID and Tenant ID
    - Display instructions for creating Service Principal with "Cost Management Reader" role
    - Submit to POST /members/accounts with `cloudProvider: "azure"`
    - _Requirements: 1.3, 1.5, 2.2, 2.3_

  - [ ] 5.3 Add provider icons and labels to accounts list
    - Display cloud provider icon (AWS orange, Azure blue, GCP red) next to each account
    - Show provider-specific identifier labels: "Account ID" for AWS, "Subscription ID" for Azure, "Project ID" for GCP
    - Add provider filter/sort controls to accounts list
    - Display summary count of accounts per provider in dashboard header
    - _Requirements: 5.2, 11.1, 11.2, 11.4, 11.5_

  - [ ] 5.4 Add provider breakdown to dashboard
    - Display provider breakdown pie/bar chart showing percentage of spend per provider
    - Add provider toggle filter for cost data display
    - Show warning indicator next to pending/failed accounts
    - _Requirements: 5.4, 5.5, 5.6_

  - [ ] 5.5 Extend AI chat context for multi-cloud
    - Include connected cloud providers and account identifiers in AI query context
    - Update system prompt to provide cloud-specific recommendations
    - Scope cost data context to specific provider when member asks about one
    - Inform member if they ask about a provider they haven't connected
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [ ] 6. Checkpoint — Azure end-to-end verification
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. GCP Backend (Connector, API Extensions)
  - [ ] 7.1 Implement GCP connector
    - Create `member-handler/connectors/gcp_connector.py` implementing `ProviderConnector`
    - Implement `authenticate`: Create self-signed JWT with service account email and scope, sign with private key (RS256), exchange for access token at `https://oauth2.googleapis.com/token`
    - Implement `test_connection`: call GCP Cloud Billing API to verify billing access
    - Implement `get_cost_data`: query Cloud Billing API for cost data by project
    - Handle GCP-specific errors (invalid key, billing not enabled, insufficient permissions)
    - _Requirements: 3.1, 4.4, 4.5, 4.6, 6.3_

  - [ ] 7.2 Extend POST /members/accounts for GCP
    - Accept `cloudProvider: "gcp"` with fields: `projectId` (stored as `accountId`), `serviceAccountKey` (JSON object)
    - Validate GCP Project ID format (6-30 lowercase alphanumeric + hyphens, starts with letter)
    - Validate service account key file has required fields: `type`, `project_id`, `private_key_id`, `private_key`, `client_email`
    - Encrypt `private_key` with KMS, store credentials map: `{clientEmail, projectId, privateKeyId, encryptedPrivateKey}`
    - Return 400 with descriptive error if key file is malformed
    - _Requirements: 1.4, 1.5, 1.6, 3.1, 3.3, 3.4, 3.6_

  - [ ] 7.3 Extend POST /members/accounts/test for GCP
    - Route to GCP connector when `cloudProvider` is "gcp"
    - Decrypt private key from KMS, call GCP connector `authenticate` then `test_connection`
    - On success: update `connectionStatus` to "connected", set `lastTestedAt`
    - On failure: update `connectionStatus` to "failed", return descriptive error
    - _Requirements: 4.4, 4.5, 4.6, 10.2, 10.3_

  - [ ] 7.4 Add GCP cost normalization to Cost Normalizer
    - Implement `normalize_gcp` function transforming GCP Billing API response to common schema
    - Ensure GCP accounts included in dashboard aggregation
    - _Requirements: 5.1, 5.3, 6.3, 6.4_

  - [ ]* 7.5 Write property test for GCP key validation (P3)
    - **Property 3: GCP service account key file validation**
    - **Validates: Requirements 3.3, 3.6**

  - [ ]* 7.6 Write unit tests for GCP connector
    - Create `member-handler/tests/test_gcp_connector_unit.py`
    - Test JWT signing and token exchange with mocked GCP API
    - Test billing data retrieval with mocked response
    - Test error handling (invalid key, billing not enabled, timeout)
    - _Requirements: 4.4, 4.6, 6.3_

- [ ] 8. GCP Frontend
  - [ ] 8.1 Implement GCP-specific account form
    - Add GCP form fields: Project ID text input, Service Account Key JSON file upload
    - Add client-side Project ID format validation (6-30 lowercase alphanumeric + hyphens)
    - Display instructions for creating Service Account with "Billing Account Viewer" role
    - Submit to POST /members/accounts with `cloudProvider: "gcp"` and parsed key file
    - _Requirements: 1.4, 1.5, 3.2, 3.5_

- [ ] 9. Checkpoint — GCP end-to-end verification
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Tips Sync & Admin Panel Extensions
  - [ ] 10.1 Create Azure and GCP tips knowledge base files
    - Create `knowledge-base/azure-cost-optimization-tips.json` following existing AWS tips structure with `cloudProvider: "azure"`
    - Create `knowledge-base/gcp-cost-optimization-tips.json` following existing AWS tips structure with `cloudProvider: "gcp"`
    - Include initial set of tips covering common optimization categories (right-sizing, reserved instances, idle resources)
    - _Requirements: 7.1, 7.5_

  - [ ] 10.2 Extend Tips Sync Lambda for Azure and GCP
    - Modify `tips-sync/lambda_function.py` to read `azure-cost-optimization-tips.json` and `gcp-cost-optimization-tips.json` from S3
    - Upsert tips with `cloudProvider` attribute
    - Compare by composite key `(service, tipId)` — update only changed tips
    - Mark removed tips as `deprecated: true` instead of deleting
    - Log per-provider sync summary (added, updated, deprecated, errors)
    - Continue processing remaining providers if one fails
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

  - [ ] 10.3 Extend Admin Panel for multi-cloud tips
    - Add "Cloud Provider" dropdown (AWS, Azure, GCP) to tip creation/edit form in `admin/admin.js`
    - Add provider tabs/filter on tips list page
    - Display per-provider sync status with last sync timestamp
    - _Requirements: 7.2, 7.3, 8.9_

  - [ ] 10.4 Extend GET /admin/tips for provider filtering
    - Modify admin handler to accept `?cloudProvider=` query parameter
    - Backfill `cloudProvider: "aws"` for legacy tips without the attribute
    - Require `cloudProvider` field on new tip creation
    - _Requirements: 7.4_

  - [ ] 10.5 Filter member tips by connected providers
    - Modify member tips endpoint to query member's connected providers
    - Return only tips whose `cloudProvider` matches a connected provider
    - _Requirements: 7.6_

  - [ ]* 10.6 Write property tests for tips (P11, P12, P13, P14, P15, P16)
    - **Property 11: Admin tips filtering returns only matching provider**
    - **Property 12: Member sees only tips for connected providers**
    - **Property 13: Tips sync updates only changed tips and preserves admin modifications**
    - **Property 14: Removed tips are deprecated, not deleted**
    - **Property 15: Sync summary counts match actual operations**
    - **Property 16: Sync continues processing after single-provider failure**
    - **Validates: Requirements 7.4, 7.6, 8.4, 8.5, 8.6, 8.7, 8.8**

- [ ] 11. Backward Compatibility & Legacy Handling
  - [ ] 11.1 Implement legacy record backfill for all read paths
    - Ensure all GET endpoints (accounts, dashboard, tips) backfill `cloudProvider: "aws"` for records missing the attribute
    - Verify existing CloudFormation template generation endpoint unchanged
    - Verify AWS connection test flow unchanged
    - _Requirements: 9.3, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_

  - [ ]* 11.2 Write property test for backward compatibility (P17)
    - **Property 17: Legacy records default to AWS**
    - **Validates: Requirements 9.3, 13.2**

  - [ ]* 11.3 Write unit tests for AWS connector regression
    - Create `member-handler/tests/test_aws_connector_unit.py`
    - Verify STS AssumeRole flow unchanged
    - Verify Cost Explorer call format unchanged
    - Verify CloudFormation template generation unchanged
    - _Requirements: 13.1, 13.4, 13.5_

- [ ] 12. Final Checkpoint — Full integration verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Azure is implemented end-to-end (backend + frontend) before GCP starts
- The existing AWS flow is preserved via connector extraction (no behavior change)
- All sensitive credentials are encrypted with KMS before storage
- Python is used for all Lambda backend code; JavaScript for frontend

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5"] },
    { "id": 2, "tasks": ["3.1", "3.2"] },
    { "id": 3, "tasks": ["3.3", "3.4", "3.5"] },
    { "id": 4, "tasks": ["3.6", "3.7", "3.8", "3.9", "3.10"] },
    { "id": 5, "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5"] },
    { "id": 6, "tasks": ["7.1", "7.2"] },
    { "id": 7, "tasks": ["7.3", "7.4", "7.5", "7.6"] },
    { "id": 8, "tasks": ["8.1"] },
    { "id": 9, "tasks": ["10.1", "10.2", "10.4"] },
    { "id": 10, "tasks": ["10.3", "10.5", "10.6"] },
    { "id": 11, "tasks": ["11.1", "11.2", "11.3"] }
  ]
}
```
