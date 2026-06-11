# Implementation Plan: Tips-Driven Schema Sync

## Overview

Replace the static `openapi-schema.json` with a dynamic schema generation pipeline driven by the `ViewMyBill-CostOptimizationTips` DynamoDB table. Implementation progresses from the Service ID foundation, through the schema generator pure function, to the Sync Lambda orchestrator, and finally the migration script — each step building on the previous and wiring together at the end.

## Tasks

- [ ] 1. Create Service ID module and registry
  - [ ] 1.1 Create `schema-sync/service_id.py` with SERVICE_REGISTRY dict, `validate_service_id()`, `resolve_alias()`, and `get_provider()` functions
    - Define the SERVICE_REGISTRY containing all known service IDs (aws:ec2, aws:s3, aws:rds, aws:lambda, aws:ebs, aws:vpc, aws:cloudfront, gcp:compute-engine, azure:virtual-machines, openai:api) with displayName, provider, and aliases
    - Implement `validate_service_id(service_id: str) -> bool` using regex `^(aws|gcp|azure|openai):[a-z][a-z0-9]*(-[a-z0-9]+)*$`
    - Implement `resolve_alias(alias: str) -> str | None` to look up canonical serviceId from display names or aliases
    - Implement `get_provider(service_id: str) -> str` to extract provider prefix
    - _Requirements: 1.1, 1.3_

  - [ ]* 1.2 Write property test for Service ID format validation
    - **Property 1: Service ID Format Validation**
    - Use Hypothesis to generate arbitrary strings and verify `validate_service_id` accepts only those matching `<provider>:<service-slug>` pattern with known providers and valid kebab-case slugs
    - **Validates: Requirements 1.1**

  - [ ]* 1.3 Write unit tests for Service ID module
    - Test `validate_service_id` with valid IDs (aws:ec2, gcp:compute-engine) and invalid IDs (missing colon, unknown provider, uppercase, empty slug)
    - Test `resolve_alias` maps "Amazon EC2" → "aws:ec2", "S3" → "aws:s3", unknown alias → None
    - Test `get_provider` extracts correct provider string
    - _Requirements: 1.1, 1.3_

- [ ] 2. Implement Schema Generator pure function
  - [ ] 2.1 Create `schema-sync/schema_generator.py` with `generate_schema()`, `validate_schema()`, and `merge_tool_definitions()` functions
    - Implement `generate_schema(tip_records: list[dict]) -> dict` that scans tip records, extracts toolDefinition objects, merges by operationId, and produces a valid OpenAPI 3.0.0 dict
    - Sort paths and parameters deterministically (alphabetical by path key, then by parameter name) to ensure order-independent output
    - Skip tip records missing `serviceId` or `toolDefinition` with warning logs
    - Generate provider-scoped paths (`/aws/get-ec2-instances`) and legacy alias paths (`/get-ec2-instances`) for backward compatibility
    - Include OpenAPI metadata: openapi version "3.0.0", info.title "SlashMyBill FinOps Actions", info.version (auto-incremented), info.description
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 2.4, 1.4_

  - [ ] 2.2 Implement `merge_tool_definitions()` for handling duplicate operationIds
    - When multiple tool definitions share the same operationId, select the one with the most parameters
    - Log a warning when conflicting definitions are detected
    - Return a merged list of unique operations
    - _Requirements: 2.2, 3.4_

  - [ ] 2.3 Implement `validate_schema()` for OpenAPI 3.0.0 structural validation
    - Check for required top-level fields: openapi, info (with title, version, description), paths
    - Validate each path entry has valid HTTP method, operationId, parameters array, and responses object
    - Return list of validation errors (empty list means valid)
    - _Requirements: 3.6_

  - [ ]* 2.4 Write property test for schema generation produces valid OpenAPI
    - **Property 2: Schema Generation Produces Valid OpenAPI**
    - Use Hypothesis to generate arbitrary lists of tip records (including records with missing serviceIds, missing toolDefinitions, malformed data) and verify the output always passes `validate_schema()`
    - **Validates: Requirements 3.1, 3.3, 3.6, 2.4, 1.4**

  - [ ]* 2.5 Write property test for tool definition merge — most parameters wins
    - **Property 3: Tool Definition Merge — Most Parameters Wins**
    - Generate sets of tool definitions sharing the same operationId with varying parameter counts and verify the merged result has parameter count >= every individual definition
    - **Validates: Requirements 2.2, 3.4**

  - [ ]* 2.6 Write property test for deterministic output regardless of input order
    - **Property 4: Deterministic Output Regardless of Input Order**
    - Generate a set of tip records, shuffle into two different permutations, and verify `generate_schema()` produces byte-identical JSON from both
    - **Validates: Requirements 3.5**

  - [ ]* 2.7 Write property test for multi-provider inclusivity
    - **Property 5: Multi-Provider Inclusivity**
    - Generate tip records with valid tool definitions from N distinct providers and verify the generated schema contains at least one path for each provider
    - **Validates: Requirements 6.1, 6.2, 6.3, 3.2**

- [ ] 3. Checkpoint - Ensure Service ID and Schema Generator tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement backward compatibility checking
  - [ ] 4.1 Create backward compatibility checker in `schema-sync/schema_generator.py`
    - Define `REQUIRED_OPERATION_IDS` list containing the 11 existing operationIds (getCostData, getMonthlyComparison, getEC2Instances, getRDSInstances, getLambdaFunctions, getS3Buckets, getEBSVolumes, getNetworkResources, getBudgets, getFinOpsSettings, getAWSPricing)
    - Implement `check_backward_compatibility(schema: dict, required_ops: list[str]) -> list[str]` that returns missing operationIds
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 4.2 Write property test for backward compatibility gate
    - **Property 6: Backward Compatibility Gate**
    - Generate schemas with varying sets of operationIds and verify the checker returns a non-empty list if and only if required ops are missing
    - **Validates: Requirements 9.2, 9.3**

  - [ ]* 4.3 Write unit tests for backward compatibility
    - Test with a schema containing all 11 operations → empty list
    - Test with a schema missing 2 operations → returns those 2
    - Test with an empty schema → returns all 11
    - _Requirements: 9.1, 9.4_

- [ ] 5. Implement Sync Lambda orchestrator
  - [ ] 5.1 Create `schema-sync/sync_lambda.py` with `lambda_handler()` supporting DynamoDB Stream events and direct invocations
    - Parse event to determine trigger type (stream event vs direct invocation with `{"action": "sync/rollback", "dryRun": bool}`)
    - For stream events, implement `_is_tool_relevant_event()` to filter records involving toolDefinition changes
    - Scan Tips_Table to get all tip records, call `generate_schema()`, then `validate_schema()`, then `check_backward_compatibility()`
    - If any validation fails, abort and publish SNS alert to `SlashMyBill-SchemaSync-Alerts`
    - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.6_

  - [ ] 5.2 Implement S3 backup and version tracking in Sync Lambda
    - Implement `_backup_current_schema(schema: dict, version: int) -> str` to write schema to `s3://slashmybill-schema-versions/v{N}/{timestamp}.json`
    - Maintain a metadata record in DynamoDB with pk="SCHEMA_META", sk="CURRENT" tracking currentVersion, lastSyncTimestamp, syncStatus, operationCount, providersIncluded, s3Key
    - Increment version counter on each successful push
    - _Requirements: 5.5, 8.1, 8.2, 8.4_

  - [ ] 5.3 Implement Bedrock Agent update push in Sync Lambda
    - Implement `_push_to_bedrock(schema: dict) -> dict` calling `update_agent_action_group` with the agent ID and action group name "FinOpsActions"
    - On success, log the updated action group version
    - On failure, log error details and publish SNS alert
    - Implement retry logic: up to 3 attempts with exponential backoff
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 4.5_

  - [ ] 5.4 Implement dryRun mode and rollback in Sync Lambda
    - In dryRun mode: generate schema, compute diff summary (added/removed operations), return result without pushing to Bedrock
    - For rollback action: retrieve specified version from S3, push to Bedrock, update metadata
    - Return response with operationCount, providers covered, and validation warnings
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.3_

  - [ ]* 5.5 Write unit tests for Sync Lambda
    - Test dryRun returns schema without Bedrock push
    - Test diff summary correctly reports added/removed operations
    - Test version counter increments on successful push
    - Test rollback retrieves correct S3 version
    - Test retry logic fires 3 times with backoff on failure
    - Test SNS alert published on Bedrock API failure
    - Test validation failure aborts push
    - Mock DynamoDB, S3, Bedrock, and SNS clients
    - _Requirements: 7.2, 7.3, 7.4, 8.1, 8.3, 4.5, 5.4, 5.6_

- [ ] 6. Checkpoint - Ensure Sync Lambda tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement migration script
  - [ ] 7.1 Create `schema-sync/migrate_service_ids.py` with `migrate_tips_table()` and `LEGACY_SERVICE_KEY_MAP`
    - Define `LEGACY_SERVICE_KEY_MAP` mapping legacy serviceKey strings to canonical Service_IDs (e.g., "Amazon EC2" → "aws:ec2", "Amazon S3" → "aws:s3", "Amazon RDS" → "aws:rds", "AWS Lambda" → "aws:lambda", "EC2 - Other" → "aws:ebs", "Amazon Virtual Private Cloud" → "aws:vpc", "Amazon CloudFront" → "aws:cloudfront")
    - Implement `migrate_tips_table() -> dict` that scans all records, maps serviceKey to serviceId, writes back with both fields preserved
    - Skip records with unknown serviceKey (log warning), skip records already having serviceId (idempotent)
    - Return summary: `{migrated: int, skipped: int, total: int}`
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ]* 7.2 Write property test for migration idempotence
    - **Property 7: Migration Idempotence**
    - Generate sets of tip records, run migrate twice, and verify the result is identical to running once: `migrate(migrate(records)) == migrate(records)`
    - **Validates: Requirements 10.4**

  - [ ]* 7.3 Write property test for migration preserves legacy fields and maps correctly
    - **Property 8: Migration Preserves Legacy Fields and Maps Correctly**
    - For any tip with a legacy serviceKey in the map, verify after migration the record has both original serviceKey (unchanged) and serviceId equals mapped value. For unknown serviceKey, verify record is unchanged.
    - **Validates: Requirements 10.1, 10.2, 10.3**

  - [ ]* 7.4 Write unit tests for migration script
    - Test migration summary has correct counts (migrated, skipped, total)
    - Test record with known serviceKey gets serviceId populated
    - Test record with unknown serviceKey is skipped
    - Test record already having serviceId is not modified
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ] 8. Seed Tips Table with toolDefinition data for existing operations
  - [ ] 8.1 Create `schema-sync/seed_tool_definitions.py` script that populates toolDefinition on the 11 existing tip records
    - Map each of the 11 current openapi-schema.json operations to their corresponding tip records
    - Write toolDefinition objects matching the existing parameter schemas (preserving names, types, required flags)
    - Include operationId, path (legacy format), httpMethod "POST", summary, description, and parameters array
    - Include provider field "aws" for all current operations
    - _Requirements: 9.1, 9.4, 2.1, 2.3, 2.5_

- [ ] 9. Wire everything together and create deployment infrastructure
  - [ ] 9.1 Create CloudFormation/SAM additions for the Sync Lambda, DynamoDB Stream trigger, S3 bucket, SNS topic, and IAM roles
    - Define Lambda function resource for sync_lambda with Python 3.12 runtime, 60-second timeout, reserved concurrency 1
    - Configure DynamoDB Stream on Tips Table (NEW_AND_OLD_IMAGES) with batch size and 5-second window
    - Create S3 bucket `slashmybill-schema-versions` for schema archive
    - Create SNS topic `SlashMyBill-SchemaSync-Alerts`
    - Define IAM role with permissions for DynamoDB (scan, stream read), S3 (put/get), Bedrock (update_agent_action_group), SNS (publish)
    - Add environment variables: TIPS_TABLE_NAME, SCHEMA_BUCKET, AGENT_ID, ACTION_GROUP_NAME, ALERT_TOPIC_ARN
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.2, 5.5, 8.2, 1.5, 1.6_

  - [ ] 9.2 Create `schema-sync/requirements.txt` with dependencies (boto3, hypothesis for tests) and package structure
    - Include boto3 (Lambda runtime), hypothesis (testing), pytest (testing)
    - Create `schema-sync/__init__.py` for proper module imports
    - Wire schema_generator, service_id, and sync_lambda modules together ensuring imports work correctly
    - _Requirements: All_

- [ ] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis with `@settings(max_examples=100)`
- Unit tests validate specific examples and edge cases
- Implementation language is Python (as specified in the design document)
- The schema generator is a pure function — no side effects — making it trivially testable
- All existing 11 operations must remain in generated schema during and after migration (backward compatibility gate)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3"] },
    { "id": 3, "tasks": ["2.4", "2.5", "2.6", "2.7", "4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "5.1"] },
    { "id": 5, "tasks": ["5.2", "5.3"] },
    { "id": 6, "tasks": ["5.4"] },
    { "id": 7, "tasks": ["5.5", "7.1"] },
    { "id": 8, "tasks": ["7.2", "7.3", "7.4", "8.1"] },
    { "id": 9, "tasks": ["9.1", "9.2"] }
  ]
}
```
