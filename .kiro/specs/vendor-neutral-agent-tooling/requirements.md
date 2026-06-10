# Requirements Document

## Introduction

This feature redesigns the SlashMyBill Bedrock Agent's action groups and tools from AWS-specific naming (getEC2Instances, getS3Buckets, etc.) to a completely vendor-neutral architecture. Tool names describe WHAT data is needed, not WHERE it comes from. The Lambda backend uses the account's `cloudProvider` field to route to the appropriate vendor API. Vendor-specific knowledge (pricing models, API endpoints, parameter schemas) lives in the enriched Tips Table — NOT in the agent instructions or tool names. The redesign organizes ~20 tools into 6 action groups, maintains backward compatibility with existing functionality, and enables the platform to serve AWS, Azure, GCP, and AI vendor accounts through the same agent interface.

## Glossary

- **Agent_Action_Lambda**: The `SlashMyBill-AgentAction` Lambda function that executes tool operations invoked by the Bedrock Agent
- **Action_Group**: A Bedrock Agent Action Group — a logical grouping of related tools defined by an OpenAPI schema
- **Provider_Router**: The routing module that determines which cloud connector to invoke based on the account's `cloudProvider` field
- **Cloud_Connector**: A provider-specific module (AWS, Azure, GCP, AI vendor) that translates vendor-neutral tool calls into provider-specific API calls
- **Tips_Table**: The `ViewMyBill-CostOptimizationTips` DynamoDB table containing optimization tips enriched with provider-specific routing metadata
- **Cost_Cache_Table**: The `Cost_Cache_Table` DynamoDB table storing cached cost data per member-account pair
- **OpenAPI_Schema**: The JSON schema defining tool operations, parameters, and response formats for Bedrock Agent action groups
- **Bedrock_Agent**: The Amazon Bedrock Agent (ID: G5VJGUOZ5W) that orchestrates tool calls based on user questions
- **Agent_Instructions**: The natural-language instructions provided to the Bedrock Agent that guide its behavior and tool selection
- **Account_Context**: The resolved metadata for a connected account including provider type, credentials, and supported services

## Requirements

### Requirement 1: Vendor-Neutral OpenAPI Schema Structure

**User Story:** As a platform engineer, I want the Bedrock Agent's OpenAPI schema to use vendor-neutral tool names organized into 6 action groups, so that the same agent interface works across all supported cloud providers without modification.

#### Acceptance Criteria

1. THE OpenAPI_Schema SHALL define exactly 6 Action_Groups: CostAnalysis, ComputeOptimize, DatabaseStorage, NetworkServerless, FinOpsPlatform, and Knowledge
2. WHEN a tool is defined in the OpenAPI_Schema, THE OpenAPI_Schema SHALL use a vendor-neutral operationId that describes the data category without referencing any specific cloud provider service name (no "EC2", "S3", "RDS", "Lambda", "Azure", "GCP" in operationId values)
3. THE CostAnalysis Action_Group SHALL contain exactly 4 tools: getCostBreakdown, getMonthlyTrend, getCostForecast, and getCostAnomalies
4. THE ComputeOptimize Action_Group SHALL contain exactly 4 tools: getComputeInstances, getRightsizingRecommendations, getSpotCandidates, and getLicensingAnalysis
5. THE DatabaseStorage Action_Group SHALL contain exactly 3 tools: getDatabaseInstances, getStorageVolumes, and getObjectStorage
6. THE NetworkServerless Action_Group SHALL contain exactly 3 tools: getNetworkResources, getServerlessFunctions, and getContainerClusters
7. THE FinOpsPlatform Action_Group SHALL contain exactly 5 tools: getBudgets, getFinOpsSettings, getCommitmentCoverage, getTagCompliance, and getBusinessMetrics
8. THE Knowledge Action_Group SHALL contain exactly 3 tools: getOptimizationTips, getPricingData, and getAIVendorUsage
9. WHEN a tool requires account identification, THE OpenAPI_Schema SHALL include an `accountId` parameter described as "The connected account identifier" without referencing a specific provider format

### Requirement 2: Provider Routing via accountId

**User Story:** As a platform engineer, I want the Agent_Action_Lambda to route tool invocations to the correct cloud provider API based on the account's registered provider type, so that a single tool definition serves all supported providers.

#### Acceptance Criteria

1. WHEN the Agent_Action_Lambda receives a tool invocation with an accountId parameter, THE Provider_Router SHALL resolve the account's `cloudProvider` field from the MemberPortal-Accounts DynamoDB table
2. WHEN the Provider_Router resolves a cloudProvider value of "aws", THE Agent_Action_Lambda SHALL invoke the AWS Cloud_Connector for that tool operation
3. WHEN the Provider_Router resolves a cloudProvider value of "azure", THE Agent_Action_Lambda SHALL invoke the Azure Cloud_Connector for that tool operation
4. WHEN the Provider_Router resolves a cloudProvider value of "gcp", THE Agent_Action_Lambda SHALL invoke the GCP Cloud_Connector for that tool operation
5. WHEN the Provider_Router resolves a cloudProvider value of "openai", THE Agent_Action_Lambda SHALL invoke the AI Vendor Cloud_Connector for that tool operation
6. IF the Provider_Router cannot resolve a cloudProvider value or the value is not in the supported set, THEN THE Agent_Action_Lambda SHALL default to the AWS Cloud_Connector for backward compatibility

### Requirement 3: Tool-to-Connector Mapping

**User Story:** As a platform engineer, I want each vendor-neutral tool to map to provider-specific API calls through the Cloud_Connector layer, so that the same tool returns equivalent data regardless of the underlying provider.

#### Acceptance Criteria

1. WHEN the getComputeInstances tool is invoked for an AWS account, THE AWS Cloud_Connector SHALL call the EC2 DescribeInstances API and return results in the vendor-neutral response schema
2. WHEN the getComputeInstances tool is invoked for an Azure account, THE Azure Cloud_Connector SHALL call the Azure Compute Management API and return results in the vendor-neutral response schema
3. WHEN the getComputeInstances tool is invoked for a GCP account, THE GCP Cloud_Connector SHALL call the GCP Compute Engine instances.list API and return results in the vendor-neutral response schema
4. WHEN the getCostBreakdown tool is invoked for an AWS account, THE AWS Cloud_Connector SHALL call the AWS Cost Explorer GetCostAndUsage API
5. WHEN the getCostBreakdown tool is invoked for an Azure account, THE Azure Cloud_Connector SHALL call the Azure Cost Management API
6. WHEN the getCostBreakdown tool is invoked for a GCP account, THE GCP Cloud_Connector SHALL call the GCP BigQuery Billing Export
7. THE Cloud_Connector response schema for each tool SHALL use provider-neutral field names (e.g., "instanceId", "instanceType", "state") regardless of which provider API was called

### Requirement 4: Vendor-Neutral Response Normalization

**User Story:** As a platform engineer, I want all tool responses to use a normalized schema with provider-neutral field names, so that the Bedrock Agent can reason about data consistently regardless of the source provider.

#### Acceptance Criteria

1. WHEN a Cloud_Connector returns compute instance data, THE response SHALL contain fields: instanceId, instanceType, state, name, region, and providerMetadata
2. WHEN a Cloud_Connector returns cost breakdown data, THE response SHALL contain fields: totalCost, currency, period, serviceBreakdown (array of {serviceName, cost}), and providerMetadata
3. WHEN a Cloud_Connector returns database instance data, THE response SHALL contain fields: instanceId, instanceType, engine, status, storageSizeGB, and providerMetadata
4. WHEN a Cloud_Connector returns storage volume data, THE response SHALL contain fields: volumeId, volumeType, sizeGB, state, attached, and providerMetadata
5. THE providerMetadata field SHALL contain provider-specific identifiers and attributes that do not fit the normalized schema, preserving full fidelity of the source data
6. IF a provider does not support a field in the normalized schema, THEN THE Cloud_Connector SHALL return null for that field rather than omitting it

### Requirement 5: Tips Table Provider Routing Metadata

**User Story:** As a platform engineer, I want the Tips Table to store provider-specific API endpoints, parameter schemas, and pricing models per tip, so that the Agent_Action_Lambda can dynamically route and parameterize calls without hardcoded provider logic.

#### Acceptance Criteria

1. THE Tips_Table schema SHALL include a `providerRouting` map attribute containing provider-specific entries keyed by provider name ("aws", "azure", "gcp")
2. WHEN a tip has provider routing metadata, THE providerRouting entry for each provider SHALL contain: apiEndpoint, parameterSchema, responseFormat, and costThresholds
3. WHEN the Agent_Action_Lambda executes an optimization check referenced by a tip, THE Agent_Action_Lambda SHALL load the providerRouting entry matching the resolved cloudProvider to determine the correct API endpoint and parameters
4. IF a tip does not have a providerRouting entry for the resolved cloudProvider, THEN THE Agent_Action_Lambda SHALL skip that tip and log a warning indicating the tip is not supported for that provider

### Requirement 6: Vendor-Neutral Agent Instructions

**User Story:** As a platform engineer, I want the Bedrock Agent instructions to be completely vendor-neutral, so that the agent does not assume any specific cloud provider and works correctly for all connected account types.

#### Acceptance Criteria

1. THE Agent_Instructions SHALL reference tools by their vendor-neutral names (getCostBreakdown, getComputeInstances, etc.) and SHALL NOT contain any provider-specific service names (EC2, S3, RDS, Lambda, Azure VM, GCE)
2. THE Agent_Instructions SHALL reference SlashMyBill platform features (Chat tab, Configure tab, Observe tab, Act tab) rather than vendor-specific consoles (AWS Console, Azure Portal, GCP Console)
3. THE Agent_Instructions SHALL NOT contain hardcoded pricing tables, pricing formulas, or provider-specific cost calculations
4. WHEN the Agent_Instructions describe optimization strategies, THE Agent_Instructions SHALL reference the Knowledge action group tools (getOptimizationTips, getPricingData) as the source of pricing and optimization data
5. THE Agent_Instructions SHALL instruct the Bedrock_Agent to always pass the accountId parameter to tools so the Provider_Router can determine the correct provider

### Requirement 7: Backward Compatibility Mapping

**User Story:** As a platform engineer, I want the existing 11 AWS-specific tool invocations to continue working during migration, so that no service disruption occurs during the transition to vendor-neutral tooling.

#### Acceptance Criteria

1. WHEN the Agent_Action_Lambda receives an invocation with a legacy apiPath (e.g., "/get-ec2-instances"), THE Agent_Action_Lambda SHALL map it to the corresponding vendor-neutral handler (getComputeInstances) and execute normally
2. THE Agent_Action_Lambda SHALL support both legacy apiPath routing and new vendor-neutral apiPath routing simultaneously
3. THE legacy-to-neutral mapping SHALL cover all 11 existing tools: getCostData→getCostBreakdown, getMonthlyComparison→getMonthlyTrend, getEC2Instances→getComputeInstances, getRDSInstances→getDatabaseInstances, getLambdaFunctions→getServerlessFunctions, getS3Buckets→getObjectStorage, getEBSVolumes→getStorageVolumes, getNetworkResources→getNetworkResources, getBudgets→getBudgets, getFinOpsSettings→getFinOpsSettings, getAWSPricing→getPricingData

### Requirement 8: Action Group Deployment

**User Story:** As a platform engineer, I want a deployment script that creates or updates all 6 action groups on the Bedrock Agent, updates the agent instructions, and creates a new prepared agent version, so that the entire configuration can be deployed atomically.

#### Acceptance Criteria

1. WHEN the deployment script executes, THE script SHALL create or update each of the 6 Action_Groups on Bedrock_Agent G5VJGUOZ5W with their respective OpenAPI schemas
2. WHEN the deployment script creates an Action_Group, THE script SHALL associate it with the existing Agent_Action_Lambda ARN
3. WHEN the deployment script completes action group creation, THE script SHALL update the Agent_Instructions to the new vendor-neutral version
4. WHEN the deployment script completes instruction updates, THE script SHALL call PrepareAgent to create a new prepared agent version
5. IF an Action_Group already exists with the same name, THEN THE deployment script SHALL update the existing group rather than creating a duplicate
6. IF any step in the deployment fails, THEN THE deployment script SHALL log the specific failure, report which groups were successfully created, and exit with a non-zero status code

### Requirement 9: AI Vendor Account Support

**User Story:** As a platform user with connected AI vendor accounts (OpenAI, Anthropic, etc.), I want the agent to provide cost and usage data for my AI vendor accounts using the same tool interface, so that I can manage all vendor costs in one place.

#### Acceptance Criteria

1. WHEN the getAIVendorUsage tool is invoked with an AI vendor accountId, THE AI Vendor Cloud_Connector SHALL return usage data including total spend, token usage breakdown, and model-level cost attribution
2. WHEN the getCostBreakdown tool is invoked for an AI vendor account, THE AI Vendor Cloud_Connector SHALL return cost data normalized to the same response schema as cloud provider accounts (totalCost, currency, period, serviceBreakdown)
3. IF an AI vendor account does not support a tool operation (e.g., getComputeInstances), THEN THE Agent_Action_Lambda SHALL return a response indicating the operation is not applicable for that account type with a descriptive message

### Requirement 10: OpenAPI Schema Parameter Consistency

**User Story:** As a platform engineer, I want all tools across all action groups to follow a consistent parameter convention, so that the Bedrock Agent can reliably invoke tools without per-tool parameter knowledge.

#### Acceptance Criteria

1. WHEN a tool operates on a specific account, THE tool SHALL accept an `accountId` parameter (required, string) and a `memberEmail` parameter (required, string)
2. WHEN a tool accepts time-range parameters, THE tool SHALL use `startDate` (string, ISO 8601 date) and `endDate` (string, ISO 8601 date) as parameter names
3. WHEN a tool accepts a filtering parameter, THE tool SHALL use `filters` (string, comma-separated key=value pairs) as the parameter name
4. THE Knowledge Action_Group tools (getOptimizationTips, getPricingData) SHALL accept a `service` parameter (optional, string) to scope results to a specific service category
5. THE Knowledge Action_Group tools SHALL NOT require accountId when querying platform-wide knowledge that is not account-specific

### Requirement 11: Cost Cache Integration

**User Story:** As a platform engineer, I want vendor-neutral tools to read from the Cost_Cache_Table first and fall back to live provider APIs on cache miss, so that response latency is minimized and API rate limits are respected.

#### Acceptance Criteria

1. WHEN the getCostBreakdown or getMonthlyTrend tool is invoked, THE Agent_Action_Lambda SHALL query the Cost_Cache_Table for cached data matching the accountId and requested time period
2. WHEN cached data exists and is within the staleness threshold (24 hours), THE Agent_Action_Lambda SHALL return the cached data without invoking provider APIs
3. WHEN cached data does not exist or exceeds the staleness threshold, THE Agent_Action_Lambda SHALL invoke the appropriate Cloud_Connector and write the result back to the Cost_Cache_Table
4. IF the Cost_Cache_Table read fails, THEN THE Agent_Action_Lambda SHALL fall back to direct provider API invocation and log a warning

### Requirement 12: Error Handling for Unsupported Operations

**User Story:** As a platform user, I want clear feedback when I ask about operations that my account type does not support, so that I understand what data is available for my specific account.

#### Acceptance Criteria

1. WHEN a tool is invoked for an account type that does not support that operation, THE Agent_Action_Lambda SHALL return a structured response with a `notSupported` flag set to true and a `message` field explaining which operations are available for that account type
2. WHEN a Cloud_Connector encounters an authentication or permissions error, THE Agent_Action_Lambda SHALL return a structured error response with an `authError` flag and guidance to check the account connection in the Configure tab
3. IF the Provider_Router cannot find the account in the MemberPortal-Accounts table, THEN THE Agent_Action_Lambda SHALL return an error response indicating the account is not connected with guidance to add it via the Configure tab
