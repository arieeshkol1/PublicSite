# Requirements Document

## Introduction

The Member Portal is a new section of the SlashMyBill platform (eshkolai.com) that allows registered members to gain FinOps and Operations visibility across multiple AWS accounts. Members register via email/OTP/password flow, then log in to a dashboard where they can connect AWS accounts by providing an Account ID, deploying a CloudFormation-generated IAM role (`SlashMyBill-{AccountID}`), and testing the cross-account connection. The portal reuses the existing API Gateway (`ViewMyBill-API`), SES OTP infrastructure, and DynamoDB patterns, adding new Lambda functions, DynamoDB tables, and frontend pages.

## Glossary

- **Member_Portal**: The web application served from `/members/` on eshkolai.com providing registration, login, and AWS account management
- **Member**: A registered user of the Member Portal, identified by email address
- **Registration_API**: The Lambda function handling member registration (OTP verification, password creation)
- **Auth_API**: The Lambda function handling member login and JWT token management
- **Account_API**: The Lambda function handling AWS account CRUD and connection testing
- **Members_Table**: A new DynamoDB table storing member profiles (partition key: email) with fields: email, passwordHash, displayName, createdAt, lastLoginAt
- **Accounts_Table**: A new DynamoDB table storing connected AWS accounts (partition key: memberEmail, sort key: accountId) with fields: memberEmail, accountId, roleName, connectionStatus, addedAt, lastTestedAt
- **Member_Token**: A JWT token issued upon successful login, used to authenticate Member Portal API requests
- **CrossAccount_Role**: An IAM role named `SlashMyBill-{AccountID}` created in the member's AWS account via CloudFormation, granting read access to Cost Explorer and Billing APIs
- **CF_Template**: A downloadable CloudFormation YAML template that creates the CrossAccount_Role in the member's AWS account
- **Connection_Test**: An API call that assumes the CrossAccount_Role via STS and verifies access to Cost Explorer APIs
- **OTP_Table**: The existing DynamoDB table `ViewMyBill-OTP` used for email verification codes

## Requirements

### Requirement 1: Member Registration

**User Story:** As a visitor on the SlashMyBill page, I want to register for the Member Portal with my email and a password, so that I can access FinOps visibility features.

#### Acceptance Criteria

1. THE Member_Portal SHALL display a registration form with fields: email address, OTP code input, password, and confirm password
2. WHEN the visitor enters a valid email and clicks "Get OTP", THE Registration_API SHALL send a 6-digit OTP code to the email address using the existing SES sender (noreply@eshkolai.com) and store the code in the OTP_Table with a 5-minute TTL
3. WHEN the visitor submits a valid OTP code, THE Registration_API SHALL verify the code against the OTP_Table and enable the password fields
4. IF the OTP code is invalid or expired, THEN THE Registration_API SHALL return a 400 status with a descriptive error message
5. THE Member_Portal SHALL validate that the password is at least 8 characters and that the password and confirm password fields match before allowing submission
6. WHEN the visitor submits a valid registration form, THE Registration_API SHALL hash the password using bcrypt and store the member record in the Members_Table with email, passwordHash, displayName (derived from email), and createdAt timestamp
7. IF a member with the same email already exists in the Members_Table, THEN THE Registration_API SHALL return a 409 status with a message indicating the email is already registered
8. WHEN registration completes successfully, THE Member_Portal SHALL redirect the member to the login page with a success message

### Requirement 2: Member Login

**User Story:** As a registered member, I want to log in with my email and password, so that I can access my connected AWS accounts.

#### Acceptance Criteria

1. THE Member_Portal SHALL display a login form with email and password fields at the `/members/` path
2. WHEN the member submits valid credentials, THE Auth_API SHALL verify the password against the bcrypt hash in the Members_Table and return a Member_Token (JWT) with a 24-hour expiration
3. WHEN the member submits invalid credentials, THE Auth_API SHALL return a 401 status with an error message indicating invalid email or password
4. THE Auth_API SHALL update the lastLoginAt field in the Members_Table upon successful login
5. WHEN the member logs in successfully, THE Member_Portal SHALL store the Member_Token in sessionStorage and navigate to the dashboard view
6. THE Auth_API SHALL validate the Member_Token on every protected endpoint by checking the JWT signature and expiration
7. IF an API request contains an expired or invalid Member_Token, THEN THE Auth_API SHALL return a 401 status and THE Member_Portal SHALL redirect to the login form
8. WHEN the member clicks a logout button, THE Member_Portal SHALL clear the Member_Token from sessionStorage and redirect to the login form

### Requirement 3: Add AWS Account

**User Story:** As a member, I want to add an AWS account to my portal, so that I can monitor its FinOps data.

#### Acceptance Criteria

1. WHEN the member clicks "Add Account", THE Member_Portal SHALL display a form with a field for the 12-digit AWS Account ID
2. THE Member_Portal SHALL validate that the Account ID is exactly 12 digits before allowing submission
3. WHEN the member submits a valid Account ID, THE Account_API SHALL create a record in the Accounts_Table with memberEmail, accountId, roleName (`SlashMyBill-{AccountID}`), connectionStatus set to "pending", and addedAt timestamp
4. IF the member already has an account with the same Account ID in the Accounts_Table, THEN THE Account_API SHALL return a 409 status with a message indicating the account is already connected
5. WHEN the account is added successfully, THE Member_Portal SHALL display the new account in the accounts list with a "pending" connection status
6. THE Account_API SHALL require a valid Member_Token to add an account

### Requirement 4: Download CloudFormation Template

**User Story:** As a member, I want to download a CloudFormation template for my AWS account, so that I can create the required IAM role for cross-account access.

#### Acceptance Criteria

1. WHEN the member clicks "Download CloudFormation Template" for a specific account, THE Account_API SHALL generate a CloudFormation YAML template customized with the member's Account ID
2. THE CF_Template SHALL create an IAM role named `SlashMyBill-{AccountID}` in the member's AWS account
3. THE CF_Template SHALL configure the CrossAccount_Role trust policy to allow the SlashMyBill platform account (991105135552) to assume the role via STS
4. THE CF_Template SHALL attach a policy granting read-only access to Cost Explorer APIs (ce:GetCostAndUsage, ce:GetCostForecast, ce:GetReservationUtilization, ce:GetSavingsPlansUtilization) and Billing read APIs (budgets:ViewBudget, cur:DescribeReportDefinitions)
5. THE CF_Template SHALL include an ExternalId condition using the member's email hash for additional security
6. THE Account_API SHALL require a valid Member_Token to generate the template

### Requirement 5: Test Account Connection

**User Story:** As a member, I want to test the connection to my AWS account, so that I can verify the IAM role was set up correctly.

#### Acceptance Criteria

1. WHEN the member clicks "Test Connection" for a specific account, THE Account_API SHALL attempt to assume the CrossAccount_Role (`SlashMyBill-{AccountID}`) in the member's AWS account using STS AssumeRole with the ExternalId
2. WHEN the STS AssumeRole call succeeds, THE Account_API SHALL make a test call to Cost Explorer (ce:GetCostAndUsage) using the assumed role credentials to verify billing API access
3. WHEN both the role assumption and the Cost Explorer test call succeed, THE Account_API SHALL update the connectionStatus to "connected" and lastTestedAt in the Accounts_Table and return a success response
4. IF the STS AssumeRole call fails, THEN THE Account_API SHALL return a descriptive error indicating the role does not exist or the trust policy is misconfigured, and set connectionStatus to "failed"
5. IF the Cost Explorer test call fails after successful role assumption, THEN THE Account_API SHALL return a descriptive error indicating insufficient permissions, and set connectionStatus to "partial"
6. THE Member_Portal SHALL display the connection test result with a clear success or failure indicator and actionable error messages
7. THE Account_API SHALL require a valid Member_Token to test a connection

### Requirement 6: Edit AWS Account

**User Story:** As a member, I want to edit an AWS account entry, so that I can update the Account ID if I made a mistake.

#### Acceptance Criteria

1. WHEN the member clicks "Edit" on an account entry, THE Member_Portal SHALL display a form pre-filled with the current Account ID
2. THE Member_Portal SHALL validate that the new Account ID is exactly 12 digits before allowing submission
3. WHEN the member submits an edited Account ID, THE Account_API SHALL delete the old record and create a new record in the Accounts_Table with the updated accountId, a new roleName (`SlashMyBill-{NewAccountID}`), connectionStatus reset to "pending", and the original addedAt timestamp preserved
4. IF the new Account ID already exists for the member, THEN THE Account_API SHALL return a 409 status with a conflict message
5. WHEN the account is updated successfully, THE Member_Portal SHALL refresh the accounts list and show a success notification
6. THE Account_API SHALL require a valid Member_Token to edit an account

### Requirement 7: Delete AWS Account

**User Story:** As a member, I want to delete an AWS account from my portal, so that I can remove accounts I no longer want to monitor.

#### Acceptance Criteria

1. WHEN the member clicks "Delete" on an account entry, THE Member_Portal SHALL display a confirmation dialog before proceeding
2. WHEN the member confirms deletion, THE Account_API SHALL remove the account record from the Accounts_Table using the memberEmail and accountId keys
3. WHEN the account is deleted successfully, THE Member_Portal SHALL remove the account from the displayed list and show a success notification
4. IF the account does not exist in the Accounts_Table, THEN THE Account_API SHALL return a 404 status
5. THE Account_API SHALL require a valid Member_Token to delete an account

### Requirement 8: Member Dashboard View

**User Story:** As a member, I want to see a dashboard listing all my connected AWS accounts, so that I can manage them in one place.

#### Acceptance Criteria

1. WHEN the member logs in, THE Member_Portal SHALL display a dashboard showing all accounts from the Accounts_Table for the authenticated member
2. THE Member_Portal SHALL display each account with: Account ID, role name, connection status (pending/connected/failed/partial), and last tested timestamp
3. THE Member_Portal SHALL use color-coded status indicators: green for "connected", yellow for "pending", red for "failed", orange for "partial"
4. WHEN the member has no accounts, THE Member_Portal SHALL display a message prompting the member to add their first AWS account
5. THE Member_Portal SHALL provide buttons for "Add Account", "Download CF Template", "Test Connection", "Edit", and "Delete" actions on each account entry
6. THE Member_Portal SHALL display the member's email and a logout button in the header
7. THE Member_Portal SHALL display loading indicators while API requests are in progress
8. IF an API request fails, THEN THE Member_Portal SHALL display an error notification with the error message

### Requirement 9: Navigation Link from SlashMyBill

**User Story:** As a visitor on the SlashMyBill page, I want to see a link to the Member Portal, so that I can register or log in to access advanced features.

#### Acceptance Criteria

1. THE SlashMyBill page (`/slashMyBill/index.html`) SHALL include a visible link or button labeled "Member Portal" in the navigation bar that navigates to `/members/`
2. THE Member_Portal login page SHALL include a link to the registration page for new members
3. THE Member_Portal registration page SHALL include a link back to the login page for existing members

### Requirement 10: Member Portal Infrastructure

**User Story:** As a developer, I want the Member Portal backend to be deployed through the existing CI/CD pipeline, so that changes are deployed automatically.

#### Acceptance Criteria

1. THE Member Portal backend SHALL be deployed as a new Lambda function named `aws-bill-analyzer-member-api` with Python 3.12 runtime
2. THE Member Portal Lambda SHALL be integrated with the existing API Gateway (`ViewMyBill-API`) using new routes prefixed with `/members/`
3. THE Member Portal Lambda SHALL have IAM permissions to read/write the Members_Table, read/write the Accounts_Table, read/write the OTP_Table, send emails via SES, and call STS AssumeRole
4. THE Members_Table and Accounts_Table SHALL be defined in the existing CloudFormation stack (`infrastructure/viewmybill-stack.yaml`) with PAY_PER_REQUEST billing and SSE encryption enabled
5. THE Member_Portal frontend files SHALL be deployed to the S3 bucket (`www.eshkolai.com`) under the `members/` prefix
6. THE existing GitHub Actions workflow SHALL be updated to package and deploy the Member Portal Lambda and frontend files
7. THE API Gateway CORS configuration SHALL allow the Member Portal routes from `https://www.eshkolai.com` and `https://eshkolai.com` origins
8. THE Member Portal Lambda SHALL use the same JWT_SECRET environment variable as the Admin_API for token signing consistency

### Requirement 11: CloudFormation Template Generation

**User Story:** As a developer, I want the CF template generation to be correct and secure, so that members can safely grant cross-account access.

#### Acceptance Criteria

1. THE Account_API SHALL generate a valid CloudFormation YAML template that can be deployed in any AWS account
2. FOR ALL valid Account IDs, generating the CF_Template then parsing the generated YAML SHALL produce a valid CloudFormation template (round-trip property)
3. THE CF_Template SHALL restrict the trust policy to only the SlashMyBill platform account (991105135552) with an ExternalId condition
4. THE CF_Template SHALL grant only read-only permissions to Cost Explorer and Billing APIs with no write or administrative permissions
5. THE CF_Template SHALL include a description and output section with the role ARN for easy reference
