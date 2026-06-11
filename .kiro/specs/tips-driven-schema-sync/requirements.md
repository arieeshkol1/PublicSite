# Requirements Document

## Introduction

Tips-Driven Schema Sync transforms the `ViewMyBill-CostOptimizationTips` DynamoDB table into the single source of truth for the Bedrock Agent's available tools. Instead of maintaining a hardcoded `openapi-schema.json`, the system dynamically generates the OpenAPI specification from tip records and pushes it to the Bedrock Agent action group via `update_agent_action_group`. A universal Service ID system ensures consistent cross-layer referencing between Tips, Tools, and Cost Cache data across multiple cloud providers.

## Glossary

- **Tips_Table**: The DynamoDB table `ViewMyBill-CostOptimizationTips` storing cost optimization tips with embedded tool definitions
- **Schema_Generator**: The component that reads tip records from the Tips_Table and produces a valid OpenAPI 3.0 specification
- **Sync_Lambda**: The AWS Lambda function triggered by DynamoDB Streams or admin action that orchestrates schema generation and Bedrock Agent update
- **Service_ID**: A unique, canonical identifier for a cloud service in the format `<provider>:<service-slug>` (e.g., `aws:ec2`, `gcp:compute-engine`, `azure:virtual-machines`)
- **Service_Registry**: The authoritative mapping of Service_IDs to display names, provider metadata, and aliases maintained within the Tips_Table
- **Action_Group**: The Bedrock Agent action group (`FinOpsActions`) that defines available tool operations for the agent
- **Tool_Definition**: A structured object embedded in a tip record that specifies the OpenAPI operation (path, operationId, parameters, description) the tip requires
- **Provider**: A cloud platform identifier — one of `aws`, `gcp`, `azure`, or `openai`
- **OpenAPI_Schema**: The generated OpenAPI 3.0 JSON document describing all available agent tool operations
- **Bedrock_Agent_API**: The AWS Bedrock Agent service API, specifically the `update_agent_action_group` operation

## Requirements

### Requirement 1: Universal Service ID System

**User Story:** As a platform developer, I want all layers (Tips, Tools, Cost Cache) to reference cloud services using the same canonical identifier, so that there is no ambiguity between name variants like "Amazon EC2", "EC2", or "ec2".

#### Acceptance Criteria

1. THE Service_ID SHALL use the format `<provider>:<service-slug>` where provider is one of `aws`, `gcp`, `azure`, `openai` and service-slug is a lowercase kebab-case string
2. THE Tips_Table SHALL store a `serviceId` attribute on every tip record containing the canonical Service_ID
3. THE Service_Registry SHALL maintain a mapping from each Service_ID to its display name, provider, and known aliases
4. WHEN a tip record is written without a valid Service_ID, THE Schema_Generator SHALL reject the record and log a validation error
5. THE Cost_Cache_Table SHALL use the Service_ID as part of its key structure for cached cost data
6. WHEN querying tips by service, THE Tips_Table SHALL support lookup by Service_ID as the primary key or index

### Requirement 2: Tool Definition Embedding in Tips

**User Story:** As an admin, I want each tip record to contain its own tool definition, so that the OpenAPI schema can be fully derived from the Tips_Table without external configuration.

#### Acceptance Criteria

1. THE Tips_Table SHALL support an optional `toolDefinition` attribute on each tip record containing operationId, path, httpMethod, summary, description, and parameters array
2. WHEN multiple tips reference the same operationId, THE Schema_Generator SHALL merge them into a single OpenAPI path entry using the most complete parameter set
3. THE Tool_Definition parameters array SHALL specify each parameter's name, location (query/path/body), type, required flag, and description
4. WHEN a tip has no toolDefinition attribute, THE Schema_Generator SHALL skip that tip during schema generation without error
5. THE Tool_Definition SHALL include a `provider` field indicating which cloud provider the tool targets

### Requirement 3: OpenAPI Schema Generation

**User Story:** As a platform developer, I want the OpenAPI schema to be automatically generated from tip records, so that I never need to manually edit a hardcoded schema file.

#### Acceptance Criteria

1. THE Schema_Generator SHALL scan all tip records from the Tips_Table and produce a valid OpenAPI 3.0.0 JSON document
2. THE Schema_Generator SHALL group operations by provider, generating provider-scoped paths (e.g., `/aws/get-ec2-instances`, `/gcp/get-compute-instances`)
3. THE Schema_Generator SHALL include standard metadata fields (openapi version, info title, info version, info description) in the generated schema
4. WHEN two tool definitions specify conflicting parameter schemas for the same operationId, THE Schema_Generator SHALL use the definition with the most parameters and log a warning
5. THE Schema_Generator SHALL produce deterministic output given the same set of tip records regardless of DynamoDB scan order
6. THE Schema_Generator SHALL validate the generated schema against OpenAPI 3.0.0 structure rules before returning it

### Requirement 4: DynamoDB Stream Trigger

**User Story:** As an admin, I want changes to the Tips_Table to automatically trigger schema regeneration, so that adding, updating, or deleting tips immediately updates the agent's available tools.

#### Acceptance Criteria

1. WHEN a tip record with a toolDefinition is inserted into the Tips_Table, THE Sync_Lambda SHALL trigger and regenerate the OpenAPI_Schema
2. WHEN a tip record with a toolDefinition is modified in the Tips_Table, THE Sync_Lambda SHALL trigger and regenerate the OpenAPI_Schema
3. WHEN a tip record with a toolDefinition is deleted from the Tips_Table, THE Sync_Lambda SHALL trigger and regenerate the OpenAPI_Schema
4. WHEN multiple stream events arrive within a 5-second window, THE Sync_Lambda SHALL batch them into a single schema regeneration to avoid redundant updates
5. IF the Sync_Lambda fails during execution, THEN THE Sync_Lambda SHALL retry up to 3 times with exponential backoff before sending an alert to the admin

### Requirement 5: Bedrock Agent Action Group Update

**User Story:** As a platform developer, I want the regenerated schema to be pushed to the Bedrock Agent automatically, so that the agent's tools stay current without manual redeployment.

#### Acceptance Criteria

1. WHEN the Schema_Generator produces a new OpenAPI_Schema, THE Sync_Lambda SHALL call the Bedrock_Agent_API `update_agent_action_group` with the new schema payload
2. THE Sync_Lambda SHALL use the existing agent ID and action group name (`FinOpsActions`) to target the correct action group
3. WHEN the `update_agent_action_group` call succeeds, THE Sync_Lambda SHALL log the updated action group version
4. IF the `update_agent_action_group` call fails, THEN THE Sync_Lambda SHALL log the error details and publish a notification to an SNS alert topic
5. THE Sync_Lambda SHALL store the previously successful schema in an S3 backup location before applying the new one
6. IF the new schema fails validation, THEN THE Sync_Lambda SHALL abort the update and retain the existing agent configuration

### Requirement 6: Multi-Cloud Provider Support

**User Story:** As an admin, I want to add tips for GCP, Azure, and OpenAI services, so that the agent can provide cost optimization across multiple cloud providers.

#### Acceptance Criteria

1. THE Tips_Table SHALL accept tip records with Service_IDs from any supported provider (aws, gcp, azure, openai)
2. THE Schema_Generator SHALL generate provider-specific tool operations based on the provider field in each Tool_Definition
3. WHEN tips exist for multiple providers, THE OpenAPI_Schema SHALL include operations for all providers in a single schema document
4. THE Tool_Definition SHALL support provider-specific parameter sets (e.g., AWS operations require `accountId` and `memberEmail`, GCP operations require `projectId`)
5. WHEN a new provider is added to the Service_Registry, THE Schema_Generator SHALL include that provider's tools in the next regeneration without code changes

### Requirement 7: Admin-Triggered Manual Sync

**User Story:** As an admin, I want to manually trigger schema regeneration, so that I can force a sync after bulk edits or verify the system works correctly.

#### Acceptance Criteria

1. WHEN an admin invokes the Sync_Lambda directly (via AWS Console, CLI, or admin API), THE Sync_Lambda SHALL perform a full schema regeneration and update
2. THE manual trigger SHALL accept an optional `dryRun` parameter that generates the schema and returns it without pushing to Bedrock
3. WHEN running in dryRun mode, THE Sync_Lambda SHALL return the generated schema JSON and a diff summary comparing it to the currently active schema
4. THE manual trigger response SHALL include the count of operations generated, providers covered, and any validation warnings

### Requirement 8: Schema Version Tracking

**User Story:** As a platform developer, I want to track schema versions over time, so that I can audit changes and roll back if needed.

#### Acceptance Criteria

1. THE Sync_Lambda SHALL increment a version counter each time a new schema is successfully pushed to the Bedrock Agent
2. THE Sync_Lambda SHALL store each generated schema version in S3 with the version number and timestamp in the object key
3. WHEN an admin requests a rollback, THE Sync_Lambda SHALL retrieve a previous schema version from S3 and push it to the Bedrock Agent
4. THE Sync_Lambda SHALL maintain a metadata record in DynamoDB tracking the current active version, last sync timestamp, and sync status

### Requirement 9: Backward Compatibility with Existing Operations

**User Story:** As a platform developer, I want the generated schema to support all existing hardcoded operations during migration, so that no agent functionality is lost.

#### Acceptance Criteria

1. THE Schema_Generator SHALL produce operations matching all existing paths in the current `openapi-schema.json` (getCostData, getEC2Instances, getRDSInstances, getLambdaFunctions, getS3Buckets, getEBSVolumes, getNetworkResources, getMonthlyComparison, getBudgets, getFinOpsSettings, getAWSPricing)
2. WHEN migrating from the hardcoded schema, THE Sync_Lambda SHALL verify that the generated schema contains all previously existing operationIds before pushing the update
3. IF the generated schema is missing any previously active operationId, THEN THE Sync_Lambda SHALL abort the update and alert the admin
4. THE generated operation parameters SHALL maintain the same names, types, and required flags as the current hardcoded schema for existing operations

### Requirement 10: Service ID Migration

**User Story:** As a platform developer, I want existing tip records to be migrated to the new Service_ID format, so that the system can operate uniformly on the canonical identifiers.

#### Acceptance Criteria

1. THE migration script SHALL map existing `serviceKey` values (e.g., "Amazon EC2", "Amazon S3") to canonical Service_IDs (e.g., `aws:ec2`, `aws:s3`)
2. THE migration script SHALL populate the `serviceId` field on all existing tip records without removing the legacy `serviceKey` field
3. WHEN a legacy `serviceKey` cannot be mapped to a known Service_ID, THE migration script SHALL log a warning and skip that record
4. THE migration script SHALL be idempotent — running it multiple times SHALL produce the same result
5. AFTER migration completes, THE migration script SHALL output a summary of records migrated, skipped, and total processed
