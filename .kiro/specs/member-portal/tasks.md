# Implementation Plan: Member Portal

## Overview

Implement the Member Portal feature for SlashMyBill — a self-service area where registered members can connect AWS accounts for FinOps obesrvability. The implementation follows the existing admin-handler Lambda pattern (single Lambda, route dispatch), reuses the OTP/SES infrastructure, and adds new DynamoDB tables, API routes, and a vanilla HTML/CSS/JS frontend under `/members/`.

## Tasks

- [ ] 1. Create Member Handler Lambda with core utilities and registration flow
  - [x] 1.1 Create `member-handler/lambda_function.py` with route dispatch, CORS helpers, error response helpers, and `requirements.txt` (boto3, bcrypt, PyJWT, pyyaml)
    - Follow the `admin-handler/lambda_function.py` routing pattern: `routes = { 'POST /members/register': handle_register, ... }`
    - Include `cors_headers()`, `create_response()`, `create_error_response()` matching admin-handler pattern
    - Include `validate_token()` that checks JWT signature, expiry, and `role == "member"`
    - Environment variables: `JWT_SECRET`, `MEMBERS_TABLE_NAME`, `ACCOUNTS_TABLE_NAME`, `OTP_TABLE_NAME`, `SES_SENDER_EMAIL`, `PLATFORM_ACCOUNT_ID`
    - _Requirements: 10.1, 10.8, 2.6_

  - [x] 1.2 Implement `handle_register` with 3-step OTP flow (send-otp, verify-otp, create-account)
    - `action: "send-otp"`: validate email, check for existing member (409 if exists), generate 6-digit OTP, store in OTP table with 5-min TTL, send via SES
    - `action: "verify-otp"`: verify OTP against OTP table, return short-lived `otpToken` JWT (10-min expiry, `purpose: "registration"`)
    - `action: "create-account"`: validate `otpToken`, validate password ≥ 8 chars, confirm passwords match, hash with bcrypt, store member record in Members table
    - Reuse OTP table patterns from `otp-handler/lambda_function.py`
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 1.3 Implement `handle_login` with bcrypt verification and JWT generation
    - Verify email exists in Members table, check password with `bcrypt.checkpw`
    - Generate JWT with `{ sub: email, role: "member", iat, exp }` (24h expiry)
    - Update `lastLoginAt` in Members table on success
    - Return 401 for invalid credentials (same message for wrong email or wrong password)
    - _Requirements: 2.2, 2.3, 2.4_

  - [ ]* 1.4 Write property tests for registration and login (Properties 1-7)
    - **Property 1: OTP generation stores a valid 6-digit code**
    - **Validates: Requirements 1.2**
    - **Property 2: OTP verification round-trip**
    - **Validates: Requirements 1.3, 1.4**
    - **Property 3: Password validation rejects weak passwords**
    - **Validates: Requirements 1.5**
    - **Property 4: Registration round-trip**
    - **Validates: Requirements 1.6**
    - **Property 5: Duplicate member detection**
    - **Validates: Requirements 1.7**
    - **Property 6: Login produces valid JWT with correct expiry**
    - **Validates: Requirements 2.2, 2.4**
    - **Property 7: Invalid credentials are rejected**
    - **Validates: Requirements 2.3**

  - [ ]* 1.5 Write unit tests for registration and login edge cases
    - Test: invalid JSON body, missing fields, invalid email format, OTP rate limiting
    - Test: expired OTP, wrong OTP code, expired otpToken, password mismatch
    - Test: login with non-existent email, wrong password, correct credentials
    - Create `member-handler/tests/__init__.py`, `member-handler/tests/conftest.py`, `member-handler/tests/test_member_api.py`
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.2, 2.3_

- [ ] 2. Checkpoint - Ensure registration and login tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Implement Account CRUD operations
  - [x] 3.1 Implement `handle_add_account` — validate 12-digit Account ID, check for duplicates, create record with `connectionStatus: "pending"`
    - Validate Account ID is exactly 12 decimal digits
    - Set `roleName` to `SlashMyBill-{accountId}`, `connectionStatus` to `"pending"`, `addedAt` to current ISO timestamp
    - Return 409 if account already exists for this member
    - _Requirements: 3.2, 3.3, 3.4, 3.6_

  - [x] 3.2 Implement `handle_get_accounts` — query Accounts table by `memberEmail` partition key
    - Return list of accounts sorted by `addedAt`
    - _Requirements: 8.1_

  - [x] 3.3 Implement `handle_edit_account` — delete old record, create new with updated Account ID, preserve `addedAt`, reset status to "pending"
    - Accept `oldAccountId` and `newAccountId` in request body
    - Validate new Account ID is 12 digits, check for duplicates
    - Delete old record, create new record preserving original `addedAt`
    - _Requirements: 6.2, 6.3, 6.4, 6.6_

  - [x] 3.4 Implement `handle_delete_account` — remove record by composite key, return 404 if not found
    - Use `ConditionExpression='attribute_exists(memberEmail)'` to detect non-existent records
    - _Requirements: 7.2, 7.4, 7.5_

  - [ ]* 3.5 Write property tests for Account CRUD (Properties 8-13)
    - **Property 8: JWT validation on protected endpoints**
    - **Validates: Requirements 2.6, 2.7, 3.6, 4.6, 5.7, 6.6, 7.5**
    - **Property 9: Account ID validation**
    - **Validates: Requirements 3.2, 6.2**
    - **Property 10: Add account creates correct record**
    - **Validates: Requirements 3.3**
    - **Property 11: Duplicate account detection**
    - **Validates: Requirements 3.4, 6.4**
    - **Property 12: Edit account preserves addedAt and resets status**
    - **Validates: Requirements 6.3**
    - **Property 13: Delete account removes record**
    - **Validates: Requirements 7.2, 7.4**

  - [ ]* 3.6 Write unit tests for Account CRUD edge cases
    - Test: add with invalid Account ID formats (letters, too short, too long)
    - Test: edit to duplicate Account ID, delete non-existent account
    - Test: all endpoints reject requests without valid JWT
    - _Requirements: 3.2, 3.4, 6.2, 6.4, 7.4_

- [ ] 4. Implement CloudFormation template generation and connection testing
  - [x] 4.1 Implement `handle_generate_template` — generate YAML CF template with IAM role, trust policy, ExternalId, read-only permissions, and Outputs
    - Role name: `SlashMyBill-{AccountID}`
    - Trust policy: allow `arn:aws:iam::991105135552:root` with ExternalId = SHA-256 hash of member email
    - Policy: `ce:GetCostAndUsage`, `ce:GetCostForecast`, `ce:GetReservationUtilization`, `ce:GetSavingsPlansUtilization`, `budgets:ViewBudget`, `cur:DescribeReportDefinitions` on `*`
    - Include `AWSTemplateFormatVersion`, `Description`, `Outputs` with role ARN
    - Return YAML string and suggested filename `SlashMyBill-{AccountID}.yaml`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 4.2 Implement `handle_test_connection` — STS AssumeRole + Cost Explorer test call, update connectionStatus
    - Build role ARN: `arn:aws:iam::{accountId}:role/SlashMyBill-{accountId}`
    - Compute ExternalId: SHA-256 hash of member email
    - Call `sts:AssumeRole`, on failure set status to `"failed"` with descriptive error
    - On STS success, use temporary credentials to call `ce:GetCostAndUsage` for last 7 days
    - On CE failure, set status to `"partial"` with descriptive error
    - On full success, set status to `"connected"`
    - Always update `lastTestedAt` in Accounts table
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 4.3 Write property tests for CF template and connection testing (Properties 14-15)
    - **Property 14: CloudFormation template round-trip**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 11.1, 11.2, 11.3, 11.4, 11.5**
    - **Property 15: Connection test status mapping**
    - **Validates: Requirements 5.3, 5.4, 5.5**

  - [ ]* 4.4 Write unit tests for CF template and connection testing
    - Test: template generation with specific Account ID, verify YAML structure
    - Test: connection test with mocked STS success, STS failure, CE failure
    - Test: lastTestedAt is updated in all cases
    - _Requirements: 4.1, 5.3, 5.4, 5.5_

- [ ] 5. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Update CloudFormation stack with Member Portal resources
  - [x] 6.1 Add MemberPortal-Members and MemberPortal-Accounts DynamoDB tables to `infrastructure/viewmybill-stack.yaml`
    - Members table: PK = `email` (String), PAY_PER_REQUEST, SSE enabled
    - Accounts table: PK = `memberEmail` (String), SK = `accountId` (String), PAY_PER_REQUEST, SSE enabled
    - Tag both with `Project: ViewMyBill`
    - _Requirements: 10.4_

  - [x] 6.2 Add Member Handler Lambda IAM role and function to `infrastructure/viewmybill-stack.yaml`
    - IAM role: `aws-bill-analyzer-member-handler-role` with policies for Members table CRUD, Accounts table CRUD, OTP table read/write/delete, SES SendEmail, STS AssumeRole
    - Lambda function: `aws-bill-analyzer-member-api`, Python 3.12, 256MB, 30s timeout
    - Environment variables: `JWT_SECRET` (from parameter), `MEMBERS_TABLE_NAME`, `ACCOUNTS_TABLE_NAME`, `OTP_TABLE_NAME`, `SES_SENDER_EMAIL`, `PLATFORM_ACCOUNT_ID`
    - Add `MemberHandlerCodeKey` parameter with default `lambda-packages/member-handler.zip`
    - _Requirements: 10.1, 10.3, 10.8_

  - [x] 6.3 Add API Gateway integration and routes for Member Portal to `infrastructure/viewmybill-stack.yaml`
    - Create `MemberIntegration` (AWS_PROXY to Member Lambda)
    - Add routes: `POST /members/register`, `POST /members/login`, `GET /members/accounts`, `POST /members/accounts`, `PUT /members/accounts`, `DELETE /members/accounts`, `POST /members/accounts/template`, `POST /members/accounts/test`
    - Add `MemberHandlerInvokePermission` for API Gateway
    - _Requirements: 10.2, 10.7_

  - [x] 6.4 Add stack outputs for Member Portal resources
    - Output: `MembersTableName`, `MembersTableArn`, `AccountsTableName`, `AccountsTableArn`, `MemberHandlerFunctionArn`
    - _Requirements: 10.4_

- [ ] 7. Update CI/CD pipeline for Member Portal deployment
  - [x] 7.1 Update `.github/workflows/deploy.yml` to package and deploy Member Handler Lambda
    - Add `member-handler/**` to the `paths` trigger list
    - Add `members/**` to the `paths` trigger list (frontend)
    - Add "Package Member Handler Lambda" step: install PyJWT, bcrypt, pyyaml, copy lambda_function.py, zip, upload to S3
    - Add `aws lambda update-function-code` call for `aws-bill-analyzer-member-api`
    - _Requirements: 10.6_

  - [x] 7.2 Add Member Portal frontend deployment step to `.github/workflows/deploy.yml`
    - Deploy `members/index.html`, `members/members.css`, `members/members.js` to S3 under `members/` prefix
    - Inject API URL into `members.js` (same pattern as SlashMyBill frontend)
    - Add to deploy summary output
    - _Requirements: 10.5, 10.6_

- [ ] 8. Checkpoint - Verify CloudFormation template and CI/CD changes are valid
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Build Member Portal frontend
  - [x] 9.1 Create `members/index.html` with login, registration, and dashboard views
    - Single-page layout with three views toggled via `hidden` attribute (same pattern as admin panel)
    - Login view: email + password fields, "Login" button, link to registration
    - Registration view: multi-step form (email + "Get OTP" → OTP input → password + confirm password), link to login
    - Dashboard view: header with member email + logout button, accounts table, "Add Account" button
    - Add Account / Edit Account modal with 12-digit Account ID input
    - Confirmation dialog for delete actions
    - Loading indicators and error notification banner
    - _Requirements: 1.1, 2.1, 2.5, 2.8, 3.1, 6.1, 7.1, 8.1, 8.4, 8.5, 8.6, 8.7, 8.8, 9.2, 9.3_

  - [x] 9.2 Create `members/members.css` with styles matching the admin panel design
    - Reuse CSS variables and component patterns from `admin/admin.css`
    - Color-coded status indicators: green (connected), yellow (pending), red (failed), orange (partial)
    - Responsive layout, modal styles, notification banner styles
    - _Requirements: 8.3_

  - [x] 9.3 Create `members/members.js` with API integration and view management
    - API base URL configuration (injected during deployment)
    - `fetch()` wrapper with JWT Authorization header from sessionStorage
    - Registration flow: send-otp → verify-otp → create-account API calls
    - Login: call API, store token in sessionStorage, navigate to dashboard
    - Logout: clear sessionStorage, show login view
    - Dashboard: load accounts on view, render accounts table with action buttons
    - Add/Edit Account: validate 12-digit input, call API, refresh list
    - Download CF Template: call API, trigger browser file download from response YAML
    - Test Connection: call API, update status indicator in table
    - Auto-redirect to login on 401 responses
    - _Requirements: 1.8, 2.5, 2.7, 2.8, 3.2, 3.5, 5.6, 6.2, 6.5, 7.1, 7.3, 8.1, 8.2, 8.7, 8.8_

  - [ ]* 9.4 Write property test for dashboard rendering (Property 16)
    - **Property 16: Dashboard renders account information correctly**
    - **Validates: Requirements 8.2, 8.3**

- [ ] 10. Add navigation link from SlashMyBill to Member Portal
  - Update `slashMyBill/index.html` to include a "Member Portal" link/button in the navigation bar pointing to `/members/`
  - _Requirements: 9.1_

- [ ] 11. Final checkpoint - Ensure all tests pass and integration is complete
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use `hypothesis` library with `@settings(max_examples=100)` and `moto` for AWS mocking
- Unit tests use `pytest` with `moto` for AWS service mocking
- The implementation language is Python for the backend Lambda and vanilla HTML/CSS/JS for the frontend
- Checkpoints ensure incremental validation at key milestones
