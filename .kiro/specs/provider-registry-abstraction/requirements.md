# Requirements Document

## Introduction

SlashMyBill currently has AWS-specific logic hardcoded throughout its Lambda functions and frontend JavaScript. This feature extracts ALL provider-specific code into a centralized Provider Registry backed by a DynamoDB table. The registry stores configuration across 10 categories (display, auth, validation, cost-api, resource-discovery, connection-setup, scheduler-actions, pricing, ai-prompts, ui-config) keyed by `providerId` and `configCategory`. A centralized registry module loads provider configuration once per Lambda cold start into an in-memory cache, and all existing hardcoded references are replaced with registry lookups. The frontend accesses provider configuration via a new API endpoint (`GET /members/provider-config`). This is Phase 1 — AWS only — meaning the platform must behave identically to today after refactoring. No new providers are introduced, no new features are added. This is a pure architectural refactoring to enable future multi-cloud support.

## Glossary

- **Provider_Registry**: A DynamoDB table (`ProviderRegistry`) that stores all provider-specific configuration, keyed by `providerId` (partition key) and `configCategory` (sort key)
- **Registry_Module**: A centralized Python module (`provider_registry.py`) that loads provider configuration from the Provider_Registry table into an in-memory cache on Lambda cold start and exposes lookup functions
- **Provider_Config_API**: The new API endpoint (`GET /members/provider-config`) that returns provider configuration to the frontend
- **Member_Handler**: The existing Lambda `aws-bill-analyzer-member-api` (~7,800 lines) that handles all member API routes
- **Agent_Action_Lambda**: The existing Lambda (792 lines) that handles Bedrock Agent action group invocations
- **Admin_Handler**: The existing Lambda that handles admin panel API routes
- **Members_Frontend**: The frontend JavaScript (`members/members.js`, ~12,800 lines) that renders the member portal
- **Config_Category**: One of the 10 configuration categories stored in the Provider_Registry: display, auth, validation, cost-api, resource-discovery, connection-setup, scheduler-actions, pricing, ai-prompts, ui-config
- **Cold_Start_Cache**: The in-memory dictionary populated by the Registry_Module during Lambda initialization, persisting for the lifetime of the Lambda execution environment
- **Platform_Account**: The SlashMyBill AWS account (991105135552) where all platform infrastructure runs
- **Customer_Account**: An AWS account connected to SlashMyBill via a cross-account IAM role

## Requirements

### Requirement 1: Provider Registry DynamoDB Table

**User Story:** As a platform developer, I want a dedicated DynamoDB table that stores all provider-specific configuration, so that provider logic is centralized and decoupled from application code.

#### Acceptance Criteria

1. THE Provider_Registry table SHALL use `providerId` (String) as the partition key and `configCategory` (String) as the sort key.
2. THE Provider_Registry table SHALL be provisioned with PAY_PER_REQUEST billing mode in the CloudFormation stack.
3. THE Provider_Registry table SHALL contain exactly one item per Config_Category for the `aws` provider, totaling 10 items: display, auth, validation, cost-api, resource-discovery, connection-setup, scheduler-actions, pricing, ai-prompts, ui-config.
4. WHEN the Provider_Registry table is deployed, THE Provider_Registry SHALL be pre-populated with seed data extracted from the existing hardcoded values in Member_Handler, Agent_Action_Lambda, Admin_Handler, and Members_Frontend.
5. THE Provider_Registry table SHALL store configuration data in a `config` attribute (Map type) whose schema varies per Config_Category.

### Requirement 2: Display Configuration

**User Story:** As a platform developer, I want provider display metadata stored in the registry, so that UI components can render provider branding without hardcoded values.

#### Acceptance Criteria

1. THE Provider_Registry SHALL store a display configuration item for the `aws` provider containing: provider name, icon URL, brand color hex code, and short description text.
2. WHEN the Provider_Config_API returns display configuration, THE Member_Handler SHALL include all display fields in the response without transformation.

### Requirement 3: Authentication Configuration

**User Story:** As a platform developer, I want authentication parameters stored in the registry, so that cross-account credential logic references configuration rather than hardcoded patterns.

#### Acceptance Criteria

1. THE Provider_Registry SHALL store an auth configuration item for the `aws` provider containing: auth type (`sts_assume_role`), role ARN pattern template (`arn:aws:iam::{accountId}:role/SlashMyBill-{accountId}`), external ID derivation method (`sha256_member_email`), session duration seconds, and required IAM policy actions list.
2. WHEN the Member_Handler performs STS AssumeRole, THE Registry_Module SHALL supply the role ARN pattern and external ID derivation method from the auth configuration.
3. WHEN the Agent_Action_Lambda performs STS AssumeRole, THE Registry_Module SHALL supply the same role ARN pattern and external ID derivation method from the auth configuration.

### Requirement 4: Account Validation Configuration

**User Story:** As a platform developer, I want account ID validation rules stored in the registry, so that validation logic is driven by configuration rather than hardcoded regex patterns.

#### Acceptance Criteria

1. THE Provider_Registry SHALL store a validation configuration item for the `aws` provider containing: account ID regex pattern (`^\d{12}$`), format description, input placeholder text, and error messages for invalid format.
2. WHEN the Member_Handler validates an account ID during connection setup, THE Registry_Module SHALL supply the regex pattern and error messages from the validation configuration.
3. WHEN the Members_Frontend validates an account ID on input, THE Provider_Config_API SHALL supply the regex pattern, placeholder text, and format description from the validation configuration.

### Requirement 5: Cost API Configuration

**User Story:** As a platform developer, I want Cost Explorer API parameters stored in the registry, so that cost data retrieval logic references configuration rather than hardcoded AWS API details.

#### Acceptance Criteria

1. THE Provider_Registry SHALL store a cost-api configuration item for the `aws` provider containing: service name (`ce`), API method for cost queries, supported granularities (DAILY, MONTHLY), supported group-by dimensions (SERVICE, LINKED_ACCOUNT, USAGE_TYPE), date format, and metric names (UnblendedCost, BlendedCost, AmortizedCost).
2. WHEN the Member_Handler queries cost data, THE Registry_Module SHALL supply the API method name, granularity options, and group-by dimensions from the cost-api configuration.
3. WHEN the Agent_Action_Lambda queries cost data, THE Registry_Module SHALL supply the same cost-api configuration parameters.

### Requirement 6: Resource Discovery Configuration

**User Story:** As a platform developer, I want per-resource-type API configurations stored in the registry, so that resource discovery logic is driven by configuration rather than hardcoded per-service API calls.

#### Acceptance Criteria

1. THE Provider_Registry SHALL store a resource-discovery configuration item for the `aws` provider containing per-resource-type entries for: EC2, RDS, Lambda, S3, EBS, NAT Gateway, VPC Endpoint, EKS, and ECS.
2. WHEN the Member_Handler discovers resources in a Customer_Account, THE Registry_Module SHALL supply the API service name, API method, response path to extract resource list, and relevant attribute mappings for each resource type from the resource-discovery configuration.
3. WHEN the Agent_Action_Lambda discovers resources, THE Registry_Module SHALL supply the same resource-discovery configuration parameters.
4. THE resource-discovery configuration for each resource type SHALL include: service name, API method name, pagination token field name, response list path, and a mapping of resource attributes to display fields.

### Requirement 7: Connection Setup Configuration

**User Story:** As a platform developer, I want CloudFormation template generation parameters stored in the registry, so that connection setup logic references configuration rather than hardcoded template structures.

#### Acceptance Criteria

1. THE Provider_Registry SHALL store a connection-setup configuration item for the `aws` provider containing: template type (`cloudformation`), template generation parameters (role name pattern, trust policy structure, managed policy ARNs), and console URLs (CloudFormation console URL pattern, IAM console URL pattern).
2. WHEN the Member_Handler generates a cross-account CloudFormation template, THE Registry_Module SHALL supply the role name pattern, trust policy structure, and IAM policy actions from the connection-setup configuration.
3. WHEN the Members_Frontend displays connection setup instructions, THE Provider_Config_API SHALL supply the console URL patterns from the connection-setup configuration.

### Requirement 8: Scheduler Actions Configuration

**User Story:** As a platform developer, I want scheduler action definitions stored in the registry, so that the automated scheduler references configuration rather than hardcoded AWS API calls for start/stop operations.

#### Acceptance Criteria

1. THE Provider_Registry SHALL store a scheduler-actions configuration item for the `aws` provider containing supported actions for each resource type: EC2 (stop_instances, start_instances), RDS (stop_db_instance, start_db_instance), EKS (update_nodegroup_config to scale down/up), and ECS (update_service to set desired count).
2. WHEN the Member_Handler executes a scheduled action, THE Registry_Module SHALL supply the API service name, API method, and required parameters template for the target resource type and action from the scheduler-actions configuration.
3. THE scheduler-actions configuration for each action SHALL include: service name, API method name, required parameter names, and a description of the action effect.

### Requirement 9: Pricing Configuration

**User Story:** As a platform developer, I want instance pricing tables and pricing API configuration stored in the registry, so that cost calculations reference configuration rather than hardcoded pricing data.

#### Acceptance Criteria

1. THE Provider_Registry SHALL store a pricing configuration item for the `aws` provider containing: instance family pricing tables (On-Demand hourly rates per instance type), platform multipliers (Windows, RHEL, SUSE cost multipliers), and Pricing API configuration (service code, filter parameters).
2. WHEN the Member_Handler calculates savings estimates, THE Registry_Module SHALL supply the instance pricing tables and platform multipliers from the pricing configuration.
3. WHEN the Agent_Action_Lambda retrieves pricing data, THE Registry_Module SHALL supply the Pricing API service code and filter parameters from the pricing configuration.

### Requirement 10: AI Prompts Configuration

**User Story:** As a platform developer, I want AI system prompt fragments and service explanations stored in the registry, so that Bedrock Agent responses reference configuration rather than hardcoded prompt text.

#### Acceptance Criteria

1. THE Provider_Registry SHALL store an ai-prompts configuration item for the `aws` provider containing: system prompt fragments (cost optimization context, service-specific explanations), pricing rule descriptions, and response formatting templates.
2. WHEN the Member_Handler constructs AI prompts for cost analysis, THE Registry_Module SHALL supply the system prompt fragments and pricing rules from the ai-prompts configuration.
3. WHEN the Agent_Action_Lambda constructs responses, THE Registry_Module SHALL supply the service explanation text and formatting templates from the ai-prompts configuration.

### Requirement 11: UI Configuration

**User Story:** As a platform developer, I want UI display mappings and interaction templates stored in the registry, so that the frontend renders provider-specific content from configuration rather than hardcoded JavaScript objects.

#### Acceptance Criteria

1. THE Provider_Registry SHALL store a ui-config configuration item for the `aws` provider containing: service name to display name mapping (e.g., `AmazonEC2` → `EC2 Instances`), follow-up question templates for the AI chat, and topic-to-service mapping for navigation.
2. WHEN the Members_Frontend renders service names, THE Provider_Config_API SHALL supply the service name to display name mapping from the ui-config configuration.
3. WHEN the Members_Frontend displays follow-up questions in the AI chat, THE Provider_Config_API SHALL supply the follow-up question templates from the ui-config configuration.

### Requirement 12: Registry Module with Cold Start Cache

**User Story:** As a platform developer, I want a centralized registry module that caches provider configuration in memory, so that Lambda functions load configuration once per cold start without repeated DynamoDB reads on every request.

#### Acceptance Criteria

1. WHEN a Lambda function cold-starts, THE Registry_Module SHALL query the Provider_Registry table for all items matching the `aws` provider (using a partition key query) and store the results in the Cold_Start_Cache.
2. WHILE the Lambda execution environment is warm, THE Registry_Module SHALL serve all configuration lookups from the Cold_Start_Cache without additional DynamoDB calls.
3. THE Registry_Module SHALL expose a `get_config(provider_id, category)` function that returns the configuration map for the specified provider and category from the Cold_Start_Cache.
4. IF the Cold_Start_Cache is empty when a lookup is requested, THEN THE Registry_Module SHALL perform a DynamoDB query to populate the cache before returning the result.
5. THE Registry_Module SHALL be importable by Member_Handler, Agent_Action_Lambda, and Admin_Handler without code duplication (shared module pattern via Lambda Layer or bundled copy).

### Requirement 13: Provider Config API Endpoint

**User Story:** As a frontend developer, I want an API endpoint that returns provider configuration, so that the Members_Frontend can render provider-specific UI elements from configuration rather than hardcoded values.

#### Acceptance Criteria

1. WHEN the Members_Frontend sends a GET request to `/members/provider-config`, THE Member_Handler SHALL return the combined configuration from the display, validation, connection-setup, ui-config, and ai-prompts categories for the `aws` provider.
2. WHEN the Provider_Config_API returns configuration, THE Member_Handler SHALL exclude sensitive categories (auth, cost-api, resource-discovery, scheduler-actions, pricing) from the response.
3. WHEN the Provider_Config_API is called by an authenticated member, THE Member_Handler SHALL return the configuration with a Cache-Control header allowing client-side caching for 1 hour.
4. IF the Provider_Registry table is unavailable, THEN THE Member_Handler SHALL return a 503 Service Unavailable error with a retry-after header.

### Requirement 14: Data Layer Refactoring — Member Handler

**User Story:** As a platform developer, I want all hardcoded AWS-specific values in the Member_Handler replaced with Registry_Module lookups, so that the handler is provider-agnostic.

#### Acceptance Criteria

1. WHEN the Member_Handler performs STS AssumeRole, THE Member_Handler SHALL obtain the role ARN pattern and external ID derivation method from the Registry_Module auth configuration instead of hardcoded strings.
2. WHEN the Member_Handler validates an account ID, THE Member_Handler SHALL obtain the regex pattern from the Registry_Module validation configuration instead of a hardcoded pattern.
3. WHEN the Member_Handler generates a CloudFormation template, THE Member_Handler SHALL obtain the template structure and IAM actions from the Registry_Module connection-setup configuration instead of hardcoded template strings.
4. WHEN the Member_Handler discovers resources, THE Member_Handler SHALL obtain the per-resource-type API parameters from the Registry_Module resource-discovery configuration instead of hardcoded API calls.
5. WHEN the Member_Handler executes scheduler actions, THE Member_Handler SHALL obtain the API method and parameters from the Registry_Module scheduler-actions configuration instead of hardcoded action definitions.
6. WHEN the Member_Handler constructs AI prompts, THE Member_Handler SHALL obtain prompt fragments from the Registry_Module ai-prompts configuration instead of hardcoded prompt strings.
7. WHEN the Member_Handler calculates pricing, THE Member_Handler SHALL obtain pricing tables and multipliers from the Registry_Module pricing configuration instead of hardcoded pricing data.

### Requirement 15: Data Layer Refactoring — Agent Action Lambda

**User Story:** As a platform developer, I want all hardcoded AWS-specific values in the Agent_Action_Lambda replaced with Registry_Module lookups, so that the agent action handler is provider-agnostic.

#### Acceptance Criteria

1. WHEN the Agent_Action_Lambda performs STS AssumeRole, THE Agent_Action_Lambda SHALL obtain the role ARN pattern and external ID derivation method from the Registry_Module auth configuration instead of hardcoded strings.
2. WHEN the Agent_Action_Lambda calls AWS APIs for resource data, THE Agent_Action_Lambda SHALL obtain the API service names and method names from the Registry_Module resource-discovery configuration instead of hardcoded API calls.
3. WHEN the Agent_Action_Lambda retrieves pricing data, THE Agent_Action_Lambda SHALL obtain the Pricing API parameters from the Registry_Module pricing configuration instead of hardcoded values.
4. WHEN the Agent_Action_Lambda maps regions to display names, THE Agent_Action_Lambda SHALL obtain the region mapping from the Registry_Module ui-config or display configuration instead of hardcoded mappings.

### Requirement 16: Data Layer Refactoring — Frontend

**User Story:** As a platform developer, I want all hardcoded AWS-specific values in the Members_Frontend replaced with Provider_Config_API lookups, so that the frontend is provider-agnostic.

#### Acceptance Criteria

1. WHEN the Members_Frontend validates an account ID input, THE Members_Frontend SHALL obtain the regex pattern, placeholder, and error messages from the Provider_Config_API response instead of hardcoded values.
2. WHEN the Members_Frontend renders the CloudFormation connection setup UI, THE Members_Frontend SHALL obtain the console URLs and template instructions from the Provider_Config_API response instead of hardcoded URLs.
3. WHEN the Members_Frontend displays service names in cost breakdowns, THE Members_Frontend SHALL obtain the service name to display name mapping from the Provider_Config_API response instead of a hardcoded JavaScript object.
4. WHEN the Members_Frontend renders follow-up questions in the AI chat, THE Members_Frontend SHALL obtain the question templates from the Provider_Config_API response instead of hardcoded arrays.
5. WHEN the Members_Frontend loads, THE Members_Frontend SHALL call the Provider_Config_API once and cache the response for the duration of the browser session.

### Requirement 17: Data Layer Refactoring — Admin Handler

**User Story:** As a platform developer, I want hardcoded AWS-specific values in the Admin_Handler replaced with Registry_Module lookups, so that the admin handler is provider-agnostic.

#### Acceptance Criteria

1. WHEN the Admin_Handler performs tips backfill operations, THE Admin_Handler SHALL obtain the S3 bucket name and knowledge base path from the Registry_Module configuration instead of hardcoded values.
2. WHEN the Admin_Handler references provider-specific identifiers, THE Admin_Handler SHALL obtain those identifiers from the Registry_Module instead of hardcoded strings.

### Requirement 18: Behavioral Equivalence Guarantee

**User Story:** As a platform operator, I want the refactored system to behave identically to the current system, so that existing members experience zero difference after the registry migration.

#### Acceptance Criteria

1. WHEN the refactored Member_Handler processes any existing API request, THE Member_Handler SHALL return identical response bodies and status codes as the pre-refactoring implementation for the same input.
2. WHEN the refactored Agent_Action_Lambda processes any existing action group invocation, THE Agent_Action_Lambda SHALL return identical response content as the pre-refactoring implementation for the same input.
3. WHEN the refactored Members_Frontend renders any existing page, THE Members_Frontend SHALL produce identical DOM output and behavior as the pre-refactoring implementation.
4. WHEN the refactored Admin_Handler processes any existing admin request, THE Admin_Handler SHALL return identical response bodies and status codes as the pre-refactoring implementation for the same input.
5. THE Provider_Registry seed data SHALL contain values that are byte-for-byte equivalent to the hardcoded values being replaced, ensuring no behavioral drift during migration.
