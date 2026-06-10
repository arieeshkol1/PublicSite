# Implementation Plan: Vendor-Neutral Agent Tooling

## Overview

This plan transforms the SlashMyBill Bedrock Agent from AWS-specific tooling to a vendor-neutral architecture. Implementation proceeds incrementally: core interfaces and routing first, then connectors, then schemas, then deployment — ensuring each step builds on the previous and no code is orphaned.

## Tasks

- [x] 1. Set up project structure and core interfaces
  - [x] 1.1 Create vendor-neutral module structure and base connector interface
    - Create directories: `agent-action/connectors/`, `agent-action/schemas/`
    - Create `agent-action/connectors/__init__.py` with `CloudConnector` base class defining all tool method signatures (get_compute_instances, get_cost_breakdown, get_database_instances, get_storage_volumes, get_object_storage, get_network_resources, get_serverless_functions, get_container_clusters, get_budgets, get_finops_settings, get_commitment_coverage, get_tag_compliance, get_business_metrics, get_cost_forecast, get_cost_anomalies, get_rightsizing_recommendations, get_spot_candidates, get_licensing_analysis, get_ai_vendor_usage, get_optimization_tips, get_pricing_data)
    - Each method raises `NotImplementedError` by default
    - Add a `SUPPORTED_OPERATIONS` class attribute listing operations the connector supports
    - _Requirements: 3.1, 3.2, 3.3, 3.7, 4.1, 4.2, 4.3, 4.4_

  - [x] 1.2 Create response normalizer module
    - Create `agent-action/response_normalizer.py`
    - Implement `normalize_compute_response(raw, provider)` → returns schema with instanceId, instanceType, state, name, region, launchTime, providerMetadata
    - Implement `normalize_cost_response(raw, provider)` → returns schema with totalCost, currency, period, serviceBreakdown, dailyCosts, providerMetadata
    - Implement `normalize_database_response(raw, provider)` → returns schema with instanceId, instanceType, engine, status, storageSizeGB, multiAZ, providerMetadata
    - Implement `normalize_storage_response(raw, provider)` → returns schema with volumeId, volumeType, sizeGB, state, attached, providerMetadata
    - Implement `normalize_object_storage_response(raw, provider)` → returns schema with buckets, count, providerMetadata
    - Null for unsupported fields rather than omitting them
    - providerMetadata captures all unmapped source fields
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 1.3 Create legacy path mapper module
    - Create `agent-action/legacy_mapper.py`
    - Define `LEGACY_TO_NEUTRAL` dict mapping all 11 legacy paths to vendor-neutral handler names
    - Implement `resolve_path(api_path)` that returns the neutral tool name (passthrough for new paths)
    - Mappings: /get-cost-data→getCostBreakdown, /get-monthly-comparison→getMonthlyTrend, /get-ec2-instances→getComputeInstances, /get-rds-instances→getDatabaseInstances, /get-lambda-functions→getServerlessFunctions, /get-s3-buckets→getObjectStorage, /get-ebs-volumes→getStorageVolumes, /get-network-resources→getNetworkResources, /get-budgets→getBudgets, /get-finops-settings→getFinOpsSettings, /get-aws-pricing→getPricingData
    - _Requirements: 7.1, 7.2, 7.3_

- [x] 2. Implement Provider Router
  - [x] 2.1 Create provider router module
    - Create `agent-action/provider_router.py`
    - Implement `resolve_provider(account_id, member_email)` that queries MemberPortal-Accounts DynamoDB table and returns the `cloudProvider` value
    - If account not found, raise a custom `AccountNotFoundError`
    - If cloudProvider is missing or not in {"aws", "azure", "gcp", "openai"}, default to "aws"
    - Implement `route_tool(tool_name, account_id, member_email, params)` that resolves provider, instantiates the correct connector, checks SUPPORTED_OPERATIONS, and dispatches
    - Return structured `notSupported` response if tool not in connector's supported set
    - Return structured `authError` response if authentication fails
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 9.3, 12.1, 12.2, 12.3_

  - [ ]* 2.2 Write property test: Provider routing dispatches to the correct connector
    - **Property 1: Provider routing dispatches to the correct connector**
    - Generate random (accountId, provider) pairs for all valid providers
    - Mock DynamoDB lookup to return the generated provider
    - Verify the correct connector class is instantiated
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

  - [ ]* 2.3 Write property test: Invalid or missing provider defaults to AWS
    - **Property 2: Invalid or missing provider defaults to AWS**
    - Generate random strings NOT in {"aws", "azure", "gcp", "openai"} including empty/None
    - Verify AWS connector is selected in all cases
    - **Validates: Requirements 2.6**

- [x] 3. Implement AWS Cloud Connector
  - [x] 3.1 Create AWS connector with full tool implementation
    - Create `agent-action/connectors/aws_connector.py`
    - Extend the base `CloudConnector` class
    - Move existing `_assume_role`, `_make_client` helpers into the connector
    - Implement all tool methods by refactoring existing lambda_function.py logic:
      - `get_compute_instances` (from _get_ec2_instances)
      - `get_cost_breakdown` (from _get_cost_data_direct)
      - `get_monthly_trend` (from _get_monthly_comparison_direct)
      - `get_database_instances` (from _get_rds_instances)
      - `get_serverless_functions` (from _get_lambda_functions)
      - `get_object_storage` (from _get_s3_buckets)
      - `get_storage_volumes` (from _get_ebs_volumes)
      - `get_network_resources` (from _get_network_resources)
      - `get_budgets` (from _get_budgets)
      - `get_finops_settings` (from _get_finops_settings)
      - `get_spot_candidates` (from _get_spot_placement_score)
      - `get_pricing_data` (from _get_aws_pricing)
    - Add stub implementations for new tools: get_cost_forecast, get_cost_anomalies, get_rightsizing_recommendations, get_licensing_analysis, get_commitment_coverage, get_tag_compliance, get_business_metrics, get_container_clusters
    - Return raw dicts (normalizer applied upstream)
    - _Requirements: 3.1, 3.4, 3.7_

  - [ ]* 3.2 Write unit tests for AWS connector
    - Test each tool method with mocked boto3 clients (using moto or unittest.mock)
    - Verify correct AWS API calls are made
    - Verify response structure matches expected raw format
    - _Requirements: 3.1, 3.4_

- [x] 4. Implement Azure, GCP, and AI Vendor Connectors
  - [x] 4.1 Create Azure cloud connector
    - Create `agent-action/connectors/azure_connector.py`
    - Implement `get_compute_instances` calling Azure Compute Management API
    - Implement `get_cost_breakdown` calling Azure Cost Management API
    - Implement `get_database_instances` calling Azure SQL/CosmosDB management APIs
    - Implement stub methods for remaining tools
    - Set `SUPPORTED_OPERATIONS` to list implemented tools
    - Use OAuth2 client credentials from account's encrypted credentials map
    - _Requirements: 3.2, 3.5_

  - [x] 4.2 Create GCP cloud connector
    - Create `agent-action/connectors/gcp_connector.py`
    - Implement `get_compute_instances` calling GCP Compute Engine instances.list
    - Implement `get_cost_breakdown` calling GCP BigQuery Billing Export
    - Implement `get_database_instances` calling Cloud SQL instances.list
    - Implement stub methods for remaining tools
    - Set `SUPPORTED_OPERATIONS` to list implemented tools
    - Use service account JSON key from account's encrypted credentials map
    - _Requirements: 3.3, 3.6_

  - [x] 4.3 Create AI vendor connector
    - Create `agent-action/connectors/ai_vendor_connector.py`
    - Implement `get_ai_vendor_usage` returning token usage, model-level costs, total spend
    - Implement `get_cost_breakdown` returning normalized cost data for AI vendor
    - Set `SUPPORTED_OPERATIONS` to only ["getCostBreakdown", "getAIVendorUsage", "getMonthlyTrend"]
    - Return `notSupported` for compute/database/storage tools
    - Use API key from account's encrypted credentials map
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ]* 4.4 Write property test: Response normalization produces all required schema fields
    - **Property 3: Response normalization produces all required schema fields**
    - Generate random raw responses with varying field completeness per provider
    - Normalize each and verify all required fields present (null for unsupported)
    - **Validates: Requirements 3.7, 4.1, 4.2, 4.3, 4.4, 4.6**

  - [ ]* 4.5 Write property test: Provider metadata preserves unmapped source data
    - **Property 4: Provider metadata preserves unmapped source data**
    - Generate raw responses with extra arbitrary fields
    - Normalize and verify unmapped fields appear in providerMetadata
    - **Validates: Requirements 4.5**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Integrate Cost Cache and refactor Lambda handler
  - [x] 6.1 Implement cost cache integration in provider router
    - Modify `route_tool` so that getCostBreakdown and getMonthlyTrend check Cost_Cache_Table first
    - Cache key format: `{memberEmail}#{accountId}`, sort key: `DAILY#{date}`
    - If cached data exists within 24-hour staleness threshold, return it directly
    - On cache miss or stale data, invoke connector and write result to cache
    - On cache read failure, fall back to live API with warning log
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [x] 6.2 Refactor lambda_function.py to use new routing architecture
    - Replace the existing if/elif chain with: resolve legacy path → route to tool via provider_router
    - Import legacy_mapper, provider_router
    - Keep the Bedrock Agent response envelope (messageVersion, response, actionGroup, apiPath)
    - Handle Knowledge group tools (getOptimizationTips, getPricingData) directly (no account needed)
    - Handle accountId-less invocations for Knowledge tools per Requirement 10.5
    - _Requirements: 2.1, 7.1, 7.2, 10.5_

  - [ ]* 6.3 Write property test: Legacy and vendor-neutral paths produce equivalent results
    - **Property 5: Legacy and vendor-neutral paths produce equivalent results**
    - For all 11 legacy/neutral path pairs, generate random valid params
    - Invoke both paths and verify they route to the same handler
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 6.4 Write property test: Cost cache behavior correctness
    - **Property 7: Cost cache behavior correctness**
    - Generate random cost requests with varying cache states (hit within 24h, stale, missing, error)
    - Verify cache-hit returns cached data, miss/stale invokes connector and writes cache
    - **Validates: Requirements 11.2, 11.3**

- [x] 7. Implement error handling and unsupported operation responses
  - [x] 7.1 Add structured error handling to provider router and lambda handler
    - Implement AccountNotFoundError with guidance message referencing Configure tab
    - Implement structured notSupported response with message and availableOperations list
    - Implement authError response with guidance field
    - Ensure all errors are wrapped in Bedrock Agent response envelope (HTTP 200)
    - Never expose sensitive provider error details to the user
    - _Requirements: 12.1, 12.2, 12.3_

  - [ ]* 7.2 Write property test: Unsupported operations return structured notSupported response
    - **Property 6: Unsupported operations return structured notSupported response**
    - Generate random (tool, provider) pairs where tool is not in SUPPORTED_OPERATIONS
    - Verify response has notSupported=true, message, and availableOperations
    - **Validates: Requirements 9.3, 12.1**

  - [ ]* 7.3 Write property test: Authentication errors produce structured error response
    - **Property 8: Authentication errors produce structured error response**
    - Simulate random auth exceptions per provider connector
    - Verify response has authError=true and guidance field
    - **Validates: Requirements 12.2**

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Create OpenAPI schema files for all 6 action groups
  - [x] 9.1 Create CostAnalysis action group schema
    - Create `agent-action/schemas/cost-analysis.json`
    - Define 4 tools: getCostBreakdown, getMonthlyTrend, getCostForecast, getCostAnomalies
    - All tools use vendor-neutral operationIds (no provider service names)
    - Include accountId (required, string) and memberEmail (required, string) parameters
    - getCostBreakdown and getMonthlyTrend accept startDate/endDate (ISO 8601)
    - getCostForecast accepts forecastDays parameter
    - _Requirements: 1.1, 1.2, 1.3, 1.9, 10.1, 10.2_

  - [x] 9.2 Create ComputeOptimize action group schema
    - Create `agent-action/schemas/compute-optimize.json`
    - Define 4 tools: getComputeInstances, getRightsizingRecommendations, getSpotCandidates, getLicensingAnalysis
    - Include accountId/memberEmail on all tools
    - getComputeInstances accepts optional filters parameter
    - _Requirements: 1.1, 1.2, 1.4, 1.9, 10.1, 10.3_

  - [x] 9.3 Create DatabaseStorage action group schema
    - Create `agent-action/schemas/database-storage.json`
    - Define 3 tools: getDatabaseInstances, getStorageVolumes, getObjectStorage
    - Include accountId/memberEmail on all tools
    - _Requirements: 1.1, 1.2, 1.5, 1.9, 10.1_

  - [x] 9.4 Create NetworkServerless action group schema
    - Create `agent-action/schemas/network-serverless.json`
    - Define 3 tools: getNetworkResources, getServerlessFunctions, getContainerClusters
    - Include accountId/memberEmail on all tools
    - _Requirements: 1.1, 1.2, 1.6, 1.9, 10.1_

  - [x] 9.5 Create FinOpsPlatform action group schema
    - Create `agent-action/schemas/finops-platform.json`
    - Define 5 tools: getBudgets, getFinOpsSettings, getCommitmentCoverage, getTagCompliance, getBusinessMetrics
    - Include accountId/memberEmail on all tools
    - _Requirements: 1.1, 1.2, 1.7, 1.9, 10.1_

  - [x] 9.6 Create Knowledge action group schema
    - Create `agent-action/schemas/knowledge.json`
    - Define 3 tools: getOptimizationTips, getPricingData, getAIVendorUsage
    - getOptimizationTips and getPricingData accept optional `service` parameter
    - getOptimizationTips and getPricingData do NOT require accountId (platform-wide knowledge)
    - getAIVendorUsage requires accountId/memberEmail
    - _Requirements: 1.1, 1.2, 1.8, 10.4, 10.5_

- [x] 10. Create vendor-neutral agent instructions and Tips Table schema update
  - [x] 10.1 Write vendor-neutral Bedrock Agent instructions
    - Create `agent-action/agent-instructions.txt` with updated instructions
    - Reference only vendor-neutral tool names (getCostBreakdown, getComputeInstances, etc.)
    - Reference SlashMyBill tabs (Chat, Configure, Observe, Act) not vendor consoles
    - Direct agent to use Knowledge tools for pricing/optimization data
    - Instruct agent to always pass accountId parameter
    - Remove all hardcoded pricing tables and provider-specific formulas
    - No provider-specific service names (EC2, S3, RDS, Lambda, Azure VM, GCE)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 10.2 Define Tips Table providerRouting schema extension
    - Document the `providerRouting` map attribute format in a migration script or schema file
    - Each provider entry contains: apiEndpoint, parameterSchema, responseFormat, costThresholds
    - Create a sample DynamoDB update script for enriching existing tips with providerRouting metadata
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 11. Create deployment script for Bedrock Agent action groups
  - [x] 11.1 Implement deployment script
    - Create `infrastructure/deploy-agent-action-groups.py`
    - Use boto3 Bedrock Agent client
    - For each of the 6 schema files: create or update action group on agent G5VJGUOZ5W
    - Associate each action group with existing Agent_Action_Lambda ARN
    - If action group exists (by name), update it rather than creating a duplicate
    - After all groups created, update agent instructions from agent-instructions.txt
    - Call PrepareAgent to create new prepared version
    - On failure: log specific error, report which groups succeeded, exit non-zero
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 11.2 Write unit tests for deployment script
    - Mock boto3 bedrock-agent client
    - Test create new action group flow
    - Test update existing action group flow
    - Test failure handling and partial success reporting
    - _Requirements: 8.5, 8.6_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The AWS connector refactors existing proven code — minimal risk of regression
- Azure, GCP, and AI vendor connectors start as partial implementations (core tools only) with stubs for remaining tools
- The deployment script is idempotent (safe to re-run)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.2", "4.1", "4.2", "4.3"] },
    { "id": 3, "tasks": ["4.4", "4.5", "6.1", "6.2"] },
    { "id": 4, "tasks": ["6.3", "6.4", "7.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "9.1", "9.2", "9.3", "9.4", "9.5", "9.6"] },
    { "id": 6, "tasks": ["10.1", "10.2"] },
    { "id": 7, "tasks": ["11.1"] },
    { "id": 8, "tasks": ["11.2"] }
  ]
}
```
