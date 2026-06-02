# Requirements Document

## Introduction

The Multi-Cloud Support feature extends the SlashMyBill FinOps platform from an AWS-only solution to a multi-cloud platform supporting AWS, Microsoft Azure, and Google Cloud Platform (GCP). Members will be able to connect accounts from all three cloud providers within the same user account, view unified cost data, and receive cloud-specific optimization tips. The admin panel will be extended to manage tips for each cloud provider. The existing AWS connection flow (CloudFormation-based IAM role) remains unchanged, while new provider-specific connection flows are added for Azure and GCP.

## Glossary

- **Cloud_Provider**: One of the three supported cloud platforms: AWS, Azure, or GCP
- **Provider_Connector**: The module responsible for establishing and validating connectivity to a specific Cloud_Provider
- **Azure_Connector**: The Provider_Connector implementation for Microsoft Azure, using Service Principal credentials and Azure Cost Management API
- **GCP_Connector**: The Provider_Connector implementation for Google Cloud Platform, using Service Account credentials and GCP Billing API
- **AWS_Connector**: The existing Provider_Connector implementation for AWS, using cross-account IAM roles and AWS Cost Explorer API
- **Service_Principal**: An Azure Active Directory application identity used to grant SlashMyBill read access to Azure Cost Management data
- **GCP_Service_Account**: A Google Cloud IAM service account used to grant SlashMyBill read access to GCP Billing data
- **Accounts_Table**: The existing DynamoDB table `MemberPortal-Accounts` (partition key: memberEmail, sort key: accountId) extended with a `cloudProvider` attribute
- **Tips_Table**: The existing DynamoDB table `ViewMyBill-CostOptimizationTips` extended to store tips for all three cloud providers
- **Member_Portal**: The web application at `/members/` providing registration, login, and cloud account management
- **Admin_Panel**: The admin web application at `/admin/` for managing members and optimization tips
- **Connection_Test**: An API call that validates credentials and verifies read access to cost data for a specific Cloud_Provider
- **Unified_Dashboard**: The member dashboard view that displays cost data from all connected cloud accounts regardless of provider
- **Cost_Normalizer**: The module that transforms provider-specific cost data into a common format for unified display
- **Tips_Sync_Lambda**: A scheduled Lambda function that automatically syncs Azure and GCP optimization tips from curated source files into the Tips_Table on a daily basis

## Requirements

### Requirement 1: Cloud Provider Selection During Account Addition

**User Story:** As a member, I want to select which cloud provider I am connecting, so that the system uses the correct connection flow for AWS, Azure, or GCP.

#### Acceptance Criteria

1. WHEN the member clicks "Add Account", THE Member_Portal SHALL display a provider selection step with three options: AWS, Azure, and GCP
2. WHEN the member selects AWS, THE Member_Portal SHALL display the existing 12-digit Account ID form and follow the current CloudFormation-based connection flow
3. WHEN the member selects Azure, THE Member_Portal SHALL display a form requesting: Subscription ID, Tenant ID, and Client ID for the Service_Principal
4. WHEN the member selects GCP, THE Member_Portal SHALL display a form requesting: Project ID and a file upload field for the GCP_Service_Account JSON key file
5. THE Member_Portal SHALL validate provider-specific input formats before allowing submission: AWS Account ID as exactly 12 digits, Azure Subscription ID as a valid UUID, Azure Tenant ID as a valid UUID, GCP Project ID as 6 to 30 lowercase alphanumeric characters with hyphens
6. WHEN the member submits a valid account form, THE Account_API SHALL store the `cloudProvider` attribute (aws, azure, or gcp) alongside the account record in the Accounts_Table

### Requirement 2: Azure Account Connection

**User Story:** As a member, I want to connect my Azure subscription, so that I can monitor Azure cost data alongside my AWS accounts.

#### Acceptance Criteria

1. WHEN the member submits Azure connection details, THE Account_API SHALL store the Subscription ID as the `accountId`, Tenant ID, and Client ID in the Accounts_Table with `cloudProvider` set to "azure" and `connectionStatus` set to "pending"
2. THE Member_Portal SHALL display instructions for creating a Service_Principal in Azure Active Directory with "Cost Management Reader" role assignment on the target subscription
3. THE Member_Portal SHALL provide a downloadable Azure CLI script or step-by-step guide for creating the Service_Principal with the correct permissions
4. WHEN the member provides the Client Secret for the Service_Principal, THE Account_API SHALL encrypt the secret using AWS KMS before storing it
5. IF the member does not provide a Client Secret, THEN THE Account_API SHALL store the account in "pending" status and prompt the member to complete setup
6. THE Account_API SHALL require a valid Member_Token to add an Azure account

### Requirement 3: GCP Account Connection

**User Story:** As a member, I want to connect my GCP project, so that I can monitor GCP cost data alongside my other cloud accounts.

#### Acceptance Criteria

1. WHEN the member submits GCP connection details, THE Account_API SHALL store the Project ID as the `accountId` in the Accounts_Table with `cloudProvider` set to "gcp" and `connectionStatus` set to "pending"
2. THE Member_Portal SHALL display instructions for creating a GCP_Service_Account with "Billing Account Viewer" and "BigQuery User" roles
3. WHEN the member uploads a GCP_Service_Account JSON key file, THE Account_API SHALL validate that the file contains required fields (type, project_id, private_key_id, private_key, client_email)
4. THE Account_API SHALL encrypt the GCP_Service_Account private key using AWS KMS before storing it
5. THE Member_Portal SHALL provide a downloadable gcloud CLI script or step-by-step guide for creating the GCP_Service_Account with the correct permissions
6. IF the uploaded key file is malformed or missing required fields, THEN THE Account_API SHALL return a 400 status with a descriptive error message
7. THE Account_API SHALL require a valid Member_Token to add a GCP account

### Requirement 4: Multi-Cloud Connection Testing

**User Story:** As a member, I want to test the connection to my Azure and GCP accounts, so that I can verify the credentials are configured correctly.

#### Acceptance Criteria

1. WHEN the member clicks "Test Connection" on an Azure account, THE Azure_Connector SHALL authenticate using the stored Service_Principal credentials (Tenant ID, Client ID, Client Secret) and attempt to read cost data from the Azure Cost Management API
2. WHEN the Azure authentication and cost data read succeed, THE Account_API SHALL update the connectionStatus to "connected" and lastTestedAt in the Accounts_Table
3. IF the Azure authentication fails, THEN THE Account_API SHALL return a descriptive error indicating the Service_Principal credentials are invalid or the role assignment is missing, and set connectionStatus to "failed"
4. WHEN the member clicks "Test Connection" on a GCP account, THE GCP_Connector SHALL authenticate using the stored GCP_Service_Account credentials and attempt to read billing data from the GCP Cloud Billing API
5. WHEN the GCP authentication and billing data read succeed, THE Account_API SHALL update the connectionStatus to "connected" and lastTestedAt in the Accounts_Table
6. IF the GCP authentication fails, THEN THE Account_API SHALL return a descriptive error indicating the service account key is invalid or permissions are insufficient, and set connectionStatus to "failed"
7. THE existing AWS connection test flow SHALL remain unchanged

### Requirement 5: Unified Cost Data Display

**User Story:** As a member, I want to see cost data from all my connected cloud accounts in a single dashboard, so that I can understand my total cloud spend.

#### Acceptance Criteria

1. WHEN the member opens the dashboard, THE Unified_Dashboard SHALL display a combined cost summary showing total spend across all connected cloud providers
2. THE Unified_Dashboard SHALL display cost data grouped by Cloud_Provider with provider-specific icons and color coding: AWS (orange), Azure (blue), GCP (red)
3. THE Cost_Normalizer SHALL convert all cost data to a common currency (USD) using the currency reported by each provider
4. WHEN the member has accounts from multiple providers, THE Unified_Dashboard SHALL display a provider breakdown chart showing the percentage of spend per Cloud_Provider
5. THE Unified_Dashboard SHALL allow the member to filter cost data by Cloud_Provider using a provider toggle
6. WHILE a cloud account has connectionStatus of "pending" or "failed", THE Unified_Dashboard SHALL exclude that account from cost calculations and display a warning indicator next to the account

### Requirement 6: Provider-Specific Cost Data Retrieval

**User Story:** As a member, I want the system to fetch cost data from each cloud provider using the appropriate API, so that I get accurate cost information.

#### Acceptance Criteria

1. WHEN retrieving cost data for an AWS account, THE AWS_Connector SHALL use STS AssumeRole with the CrossAccount_Role and call the AWS Cost Explorer API (ce:GetCostAndUsage)
2. WHEN retrieving cost data for an Azure account, THE Azure_Connector SHALL authenticate with the Service_Principal and call the Azure Cost Management API (Microsoft.CostManagement/query)
3. WHEN retrieving cost data for a GCP account, THE GCP_Connector SHALL authenticate with the GCP_Service_Account and query the GCP BigQuery billing export or Cloud Billing API
4. THE Cost_Normalizer SHALL transform provider-specific cost responses into a common schema containing: date, service_name, cost_amount, currency, cloud_provider, and account_id
5. IF a provider API call fails for a specific account, THEN THE Cost_Normalizer SHALL log the error, skip that account, and continue processing remaining accounts
6. THE Account_API SHALL cache normalized cost data in the Cost_Cache_Table with a cache key that includes the cloudProvider and accountId

### Requirement 7: Multi-Cloud Optimization Tips

**User Story:** As an admin, I want to manage cost optimization tips for Azure and GCP in addition to AWS, so that members receive relevant recommendations for all their cloud providers.

#### Acceptance Criteria

1. THE Tips_Table SHALL support tips for all three cloud providers by using a `cloudProvider` attribute (aws, azure, gcp) on each tip record
2. WHEN the admin adds a new tip, THE Admin_Panel SHALL include a "Cloud Provider" dropdown with options: AWS, Azure, GCP
3. THE Admin_Panel SHALL display tips grouped by Cloud_Provider with provider-specific tabs or filter controls
4. WHEN the admin views tips, THE Admin_API SHALL support filtering tips by cloudProvider query parameter
5. THE knowledge base JSON file structure SHALL be extended to include an `azure-cost-optimization-tips.json` and a `gcp-cost-optimization-tips.json` alongside the existing `aws-cost-optimization-tips.json`
6. WHEN a member views optimization tips in the dashboard, THE Member_Portal SHALL display only tips relevant to the cloud providers the member has connected

### Requirement 8: Automatic Daily Tips Sync for Azure and GCP

**User Story:** As an admin, I want Azure and GCP optimization tips to be automatically synced daily from curated sources, so that the tips knowledge base stays current without manual intervention.

#### Acceptance Criteria

1. THE Tips_Sync_Lambda SHALL execute once daily via an EventBridge scheduled rule at a configurable time (default: 02:00 UTC)
2. WHEN the daily sync executes, THE Tips_Sync_Lambda SHALL fetch the latest Azure cost optimization tips from the curated `azure-cost-optimization-tips.json` source file and upsert them into the Tips_Table with `cloudProvider` set to "azure"
3. WHEN the daily sync executes, THE Tips_Sync_Lambda SHALL fetch the latest GCP cost optimization tips from the curated `gcp-cost-optimization-tips.json` source file and upsert them into the Tips_Table with `cloudProvider` set to "gcp"
4. THE Tips_Sync_Lambda SHALL compare each tip by its unique identifier (service + tipId) and update only tips that have changed, preserving any admin-modified fields
5. IF a tip exists in the source file but not in the Tips_Table, THEN THE Tips_Sync_Lambda SHALL insert the new tip
6. IF a tip exists in the Tips_Table but has been removed from the source file, THEN THE Tips_Sync_Lambda SHALL mark the tip as `deprecated: true` rather than deleting it
7. WHEN the sync completes, THE Tips_Sync_Lambda SHALL log a summary including: total tips processed, tips added, tips updated, tips deprecated, and any errors encountered
8. IF the sync fails for one provider, THEN THE Tips_Sync_Lambda SHALL continue processing the remaining provider and log the failure
9. THE Admin_Panel SHALL display the last successful sync timestamp and sync status for each Cloud_Provider on the tips management page

### Requirement 9: Accounts Table Schema Extension

**User Story:** As a developer, I want the accounts data model to support multiple cloud providers, so that the system can store provider-specific connection details.

#### Acceptance Criteria

1. THE Accounts_Table SHALL include a `cloudProvider` attribute (aws, azure, or gcp) on every account record
2. THE Accounts_Table SHALL store provider-specific credentials in an encrypted `credentials` attribute: for Azure, the Tenant ID, Client ID, and encrypted Client Secret; for GCP, the encrypted service account key JSON
3. FOR ALL existing AWS account records that lack a `cloudProvider` attribute, THE Account_API SHALL treat them as `cloudProvider: "aws"` (backward compatibility)
4. THE Accounts_Table sort key (`accountId`) SHALL remain unique per member regardless of cloud provider
5. IF a member attempts to add an account with an accountId that already exists for that member, THEN THE Account_API SHALL return a 409 status regardless of the cloud provider
6. THE Account_API SHALL validate that the `cloudProvider` value is one of the three allowed values (aws, azure, gcp) on every write operation

### Requirement 10: Credential Security for Multi-Cloud

**User Story:** As a member, I want my Azure and GCP credentials to be stored securely, so that my cloud accounts are protected.

#### Acceptance Criteria

1. THE Account_API SHALL encrypt all sensitive credential fields (Azure Client Secret, GCP private key) using AWS KMS with a dedicated encryption key before storing them in the Accounts_Table
2. THE Account_API SHALL decrypt credentials only at the time of connection testing or cost data retrieval, and discard decrypted values from memory after use
3. THE Account_API SHALL never return sensitive credential values in API responses; only non-sensitive identifiers (Subscription ID, Tenant ID, Client ID, Project ID) are returned
4. IF the KMS decryption call fails, THEN THE Account_API SHALL return a 500 status with a generic error message and log the detailed error for debugging
5. THE KMS encryption key SHALL have a resource policy restricting usage to the Member Portal Lambda execution role

### Requirement 11: Member Portal UI Updates for Multi-Cloud

**User Story:** As a member, I want the account management interface to clearly show which cloud provider each account belongs to, so that I can manage my multi-cloud environment effectively.

#### Acceptance Criteria

1. THE Member_Portal SHALL display a cloud provider icon (AWS, Azure, or GCP logo) next to each account entry in the accounts list
2. THE Member_Portal SHALL display the provider-specific identifier label: "Account ID" for AWS, "Subscription ID" for Azure, "Project ID" for GCP
3. WHEN the member views account details, THE Member_Portal SHALL show provider-specific connection instructions based on the cloudProvider value
4. THE Member_Portal SHALL allow sorting and filtering the accounts list by Cloud_Provider
5. THE Member_Portal SHALL display a summary count of connected accounts per Cloud_Provider in the dashboard header

### Requirement 12: AI Chat Multi-Cloud Context

**User Story:** As a member, I want the AI chat to understand my multi-cloud environment, so that I can ask cost optimization questions about any of my connected cloud providers.

#### Acceptance Criteria

1. WHEN the member sends an AI query, THE Account_API SHALL include the list of connected cloud providers and their account identifiers in the context sent to the Bedrock model
2. THE AI chat system prompt SHALL instruct the model to provide cloud-specific recommendations based on which providers the member has connected
3. WHEN the member asks about a specific cloud provider, THE Account_API SHALL scope the cost data context to that provider's accounts
4. IF the member asks about a cloud provider they have not connected, THEN THE AI chat SHALL inform the member that no accounts are connected for that provider and suggest connecting one

### Requirement 13: Backward Compatibility

**User Story:** As an existing member with AWS accounts, I want my current setup to continue working without changes, so that the multi-cloud feature does not disrupt my existing workflow.

#### Acceptance Criteria

1. THE Account_API SHALL continue to support all existing AWS account API endpoints without breaking changes
2. FOR ALL existing account records without a `cloudProvider` attribute, THE Account_API SHALL default to "aws" in all read operations
3. THE existing CloudFormation template generation endpoint SHALL continue to function identically for AWS accounts
4. THE existing AWS connection test flow SHALL remain unchanged in behavior and response format
5. THE existing cost data retrieval for AWS accounts SHALL continue to use the same STS AssumeRole and Cost Explorer API flow
6. WHEN a member who has only AWS accounts logs in, THE Member_Portal SHALL display the same dashboard experience as before the multi-cloud update, with the addition of provider icons
