# Requirements Document

## Introduction

The Admin Panel is a protected area of the eshkolai.com website that allows the site administrator to manage the "Slash My Bill" tool. It provides a login-protected dashboard to view leads (users who submitted bills for analysis) and to manage the cost optimization tips/rules that the AI bill analyzer uses when generating reports. The panel is served as static HTML/CSS/JS from the `/admin/` path and communicates with a new Lambda function through the existing API Gateway.

## Glossary

- **Admin_Panel**: The complete admin web application including login page, leads viewer, and tips manager, served from `/admin/` on eshkolai.com
- **Admin_API**: The new Lambda function that handles authentication, leads retrieval, and tips CRUD operations via the existing API Gateway
- **Admin_User**: The single authorized administrator who can access the Admin Panel (credentials stored as environment variables in the Lambda)
- **Auth_Token**: A JWT token issued upon successful login, used to authenticate subsequent API requests
- **Leads_Table**: The existing DynamoDB table `ViewMyBill-Leads` (partition key: email, sort key: timestamp) storing contact information from bill uploads
- **Tips_Table**: The existing DynamoDB table `ViewMyBill-CostOptimizationTips` (partition key: service, sort key: tipId) storing cost optimization rules
- **Tip**: A single cost optimization rule with fields: service, tipId, category, title, description, estimatedSavings, difficulty

## Requirements

### Requirement 1: Admin Authentication

**User Story:** As the admin, I want to log in with my credentials, so that only I can access the admin dashboard.

#### Acceptance Criteria

1. THE Admin_Panel SHALL display a login form with username and password fields at the `/admin/` path
2. WHEN the Admin_User submits valid credentials, THE Admin_API SHALL return an Auth_Token (JWT) with a 24-hour expiration
3. WHEN the Admin_User submits invalid credentials, THE Admin_API SHALL return a 401 status with an error message indicating invalid credentials
4. THE Admin_API SHALL validate the Auth_Token on every protected endpoint by checking the JWT signature and expiration
5. IF an API request contains an expired or invalid Auth_Token, THEN THE Admin_API SHALL return a 401 status and THE Admin_Panel SHALL redirect to the login form
6. THE Admin_API SHALL store the admin username and password hash as Lambda environment variables (single admin user, no user registration)
7. WHEN the Admin_User logs in successfully, THE Admin_Panel SHALL store the Auth_Token in sessionStorage and navigate to the dashboard view
8. WHEN the Admin_User clicks a logout button, THE Admin_Panel SHALL clear the Auth_Token from sessionStorage and redirect to the login form

### Requirement 2: Leads Viewer

**User Story:** As the admin, I want to view all leads who submitted bills, so that I can follow up with potential customers.

#### Acceptance Criteria

1. WHEN the Admin_User navigates to the leads view, THE Admin_Panel SHALL display a table of all leads from the Leads_Table
2. THE Admin_Panel SHALL display the following lead fields: email, name, company, phone, fileName, timestamp
3. THE Admin_API SHALL return leads sorted by timestamp in descending order (most recent first)
4. WHEN the Leads_Table contains no records, THE Admin_Panel SHALL display a message indicating no leads have been recorded
5. THE Admin_API SHALL require a valid Auth_Token to access the leads endpoint
6. WHEN the Admin_User types in a search field, THE Admin_Panel SHALL filter the displayed leads by email, name, or company (client-side filtering)

### Requirement 3: Tips Viewer

**User Story:** As the admin, I want to view all cost optimization tips, so that I can review the rules applied during bill analysis.

#### Acceptance Criteria

1. WHEN the Admin_User navigates to the tips view, THE Admin_Panel SHALL display a table of all tips from the Tips_Table
2. THE Admin_Panel SHALL display the following tip fields: service, tipId, category, title, description, estimatedSavings, difficulty
3. THE Admin_API SHALL return all tips grouped by service
4. WHEN the Tips_Table contains no records, THE Admin_Panel SHALL display a message indicating no tips exist
5. THE Admin_API SHALL require a valid Auth_Token to access the tips endpoint
6. WHEN the Admin_User types in a search field, THE Admin_Panel SHALL filter the displayed tips by service, title, or category (client-side filtering)

### Requirement 4: Add New Tip

**User Story:** As the admin, I want to add new cost optimization tips, so that the bill analyzer can provide more recommendations.

#### Acceptance Criteria

1. WHEN the Admin_User clicks an "Add Tip" button, THE Admin_Panel SHALL display a form with fields: service, tipId, category, title, description, estimatedSavings, difficulty
2. THE Admin_Panel SHALL validate that all fields are non-empty before allowing submission
3. THE Admin_Panel SHALL provide a dropdown for the difficulty field with options: easy, medium, hard
4. WHEN the Admin_User submits a valid tip form, THE Admin_API SHALL write the new tip to the Tips_Table
5. IF a tip with the same service and tipId already exists, THEN THE Admin_API SHALL return a 409 status with a conflict error message
6. WHEN the tip is created successfully, THE Admin_Panel SHALL add the new tip to the displayed table and show a success notification
7. THE Admin_API SHALL require a valid Auth_Token to create a tip

### Requirement 5: Edit Existing Tip

**User Story:** As the admin, I want to edit existing tips, so that I can keep the cost optimization rules accurate and up to date.

#### Acceptance Criteria

1. WHEN the Admin_User clicks an edit button on a tip row, THE Admin_Panel SHALL display a pre-filled form with the tip's current values
2. THE Admin_Panel SHALL validate that all fields are non-empty before allowing submission
3. WHEN the Admin_User submits the edited form, THE Admin_API SHALL update the tip in the Tips_Table
4. THE Admin_Panel SHALL not allow editing the service or tipId fields (these are the primary key)
5. WHEN the tip is updated successfully, THE Admin_Panel SHALL update the displayed table row and show a success notification
6. THE Admin_API SHALL require a valid Auth_Token to update a tip

### Requirement 6: Delete Tip

**User Story:** As the admin, I want to delete tips that are no longer relevant, so that the bill analyzer only uses current recommendations.

#### Acceptance Criteria

1. WHEN the Admin_User clicks a delete button on a tip row, THE Admin_Panel SHALL display a confirmation dialog before proceeding
2. WHEN the Admin_User confirms deletion, THE Admin_API SHALL remove the tip from the Tips_Table using the service and tipId keys
3. WHEN the tip is deleted successfully, THE Admin_Panel SHALL remove the tip from the displayed table and show a success notification
4. IF the tip does not exist in the Tips_Table, THEN THE Admin_API SHALL return a 404 status
5. THE Admin_API SHALL require a valid Auth_Token to delete a tip

### Requirement 7: Admin API Infrastructure

**User Story:** As the admin, I want the admin API to be deployed through the existing CI/CD pipeline, so that changes are deployed automatically.

#### Acceptance Criteria

1. THE Admin_API SHALL be deployed as a new Lambda function named `aws-bill-analyzer-admin-api` with Python 3.12 runtime
2. THE Admin_API SHALL be integrated with the existing API Gateway (`ViewMyBill-API`) using new routes prefixed with `/admin/`
3. THE Admin_API SHALL have IAM permissions to read from the Leads_Table and read/write to the Tips_Table
4. THE Admin_API SHALL be defined in the existing CloudFormation stack (`infrastructure/viewmybill-stack.yaml`)
5. THE Admin_Panel frontend files SHALL be deployed to the S3 bucket (`www.eshkolai.com`) under the `admin/` prefix
6. THE existing GitHub Actions workflow SHALL be updated to package and deploy the Admin_API Lambda and the Admin_Panel frontend files
7. THE API Gateway CORS configuration SHALL allow GET, POST, PUT, and DELETE methods for admin routes

### Requirement 8: Admin Panel Frontend Structure

**User Story:** As the admin, I want the admin panel to match the existing site design, so that the experience is consistent.

#### Acceptance Criteria

1. THE Admin_Panel SHALL use the same color theme as the main eshkolai.com website (primary: #0066ff, secondary: #00d4ff, dark: #0a0e27)
2. THE Admin_Panel SHALL include navigation tabs to switch between the leads view and the tips view
3. THE Admin_Panel SHALL display the admin username and a logout button in the header
4. THE Admin_Panel SHALL be responsive and functional on desktop and tablet devices
5. THE Admin_Panel SHALL display loading indicators while API requests are in progress
6. IF an API request fails, THEN THE Admin_Panel SHALL display an error notification with the error message
