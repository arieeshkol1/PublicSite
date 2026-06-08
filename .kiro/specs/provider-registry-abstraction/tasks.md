# Implementation Plan: Provider Registry Abstraction

## Overview

Data-layer-first refactoring that extracts all AWS-specific hardcoded logic from SlashMyBill's Lambda functions and frontend into a centralized Provider Registry backed by DynamoDB. Implementation proceeds: infrastructure → shared module → seed data → API endpoint → consumer refactoring → frontend → tests → CI/CD.

## Tasks

- [x] 1. Create ProviderRegistry DynamoDB table and registry module
  - [x] 1.1 Add ProviderRegistry DynamoDB table to CloudFormation stack
    - Add `ProviderRegistryTable` resource to `infrastructure/viewmybill-stack.yaml`
    - Table name: `ProviderRegistry`, PAY_PER_REQUEST billing mode
    - Partition key: `providerId` (S), Sort key: `configCategory` (S)
    - Add `dynamodb:Query` permission for ProviderRegistry table to all Lambda IAM roles
    - _Requirements: 1.1, 1.2, 1.5_

  - [x] 1.2 Create `provider_registry.py` shared module
    - Create `provider_registry.py` with `_cache` dict, `_load_provider()`, `get_config()`, `get_all_categories()`, `invalidate_cache()`
    - `_load_provider()` queries DynamoDB with partition key and populates cache
    - `get_config()` lazy-loads if provider not in cache, returns config map or empty dict
    - Place in `member-handler/provider_registry.py` as the source copy
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [x] 1.3 Create `sts_assume_role.py` auth plugin
    - Create `member-handler/sts_assume_role.py` with `assume_role(account_id, member_email, session_name)` function
    - Reads auth config from registry via `get_config('aws', 'auth')`
    - Computes role ARN from pattern, external ID via sha256 of email
    - Returns STS credentials dict
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]* 1.4 Write property tests for registry module (Properties 1, 2, 3)
    - **Property 1: Registry cache lookup correctness** — For any valid (provider_id, category) pair in DynamoDB, `get_config()` returns the exact config map stored
    - **Property 2: Cache serves from memory without DynamoDB calls** — After initial load, zero additional DynamoDB calls for any sequence of lookups
    - **Property 3: Cache lazy-initialization** — When cache is empty, `get_config()` triggers DynamoDB query and returns correct result
    - **Validates: Requirements 12.1, 12.2, 12.3, 12.4**

  - [ ]* 1.5 Write property test for auth plugin (Property 4)
    - **Property 4: Auth config produces correct role ARN and external ID** — For any valid 12-digit account_id and any member_email, `assume_role()` computes role_arn = `arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}` and external_id = sha256(email)
    - **Validates: Requirements 3.2, 3.3, 14.1, 15.1**

- [x] 2. Create seed script and populate registry
  - [x] 2.1 Create `infrastructure/seed-provider-registry.py` with all 10 config categories
    - Extract hardcoded values from `member-handler/lambda_function.py`, `agent-action/lambda_function.py`, `admin-handler/lambda_function.py`, and `members/members.js`
    - Define SEED_DATA list with all 10 items: display, auth, validation, cost-api, resource-discovery, connection-setup, scheduler-actions, pricing, ai-prompts, ui-config
    - Use `batch_writer()` to write all items with `version: 1`
    - Include all config schemas as defined in the design document
    - _Requirements: 1.3, 1.4, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1, 8.1, 9.1, 10.1, 11.1_

  - [ ]* 2.2 Write property test for seed data completeness (Property 12)
    - **Property 12: Seed data byte-for-byte equivalence** — For any configuration value in seed data, the value is byte-for-byte equivalent to the corresponding hardcoded value in the original source
    - **Validates: Requirements 18.5**

- [x] 3. Checkpoint - Verify infrastructure and data layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Add Provider Config API endpoint
  - [x] 4.1 Implement `GET /members/provider-config` route in member-handler
    - Add route handler `handle_get_provider_config(event)` to `member-handler/lambda_function.py`
    - Require JWT authentication (same as other member routes)
    - Return combined config from 5 non-sensitive categories: display, validation, connection-setup, ui-config, ai-prompts
    - Exclude sensitive categories: auth, cost-api, resource-discovery, scheduler-actions, pricing
    - Set `Cache-Control: public, max-age=3600` header on success
    - Return 503 with `Retry-After: 30` header if registry unavailable
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [ ]* 4.2 Write property tests for Provider Config API (Properties 10, 11)
    - **Property 10: API category filtering** — Response contains only keys from {display, validation, connection-setup, ui-config, ai-prompts} and never contains {auth, cost-api, resource-discovery, scheduler-actions, pricing}
    - **Property 11: Display config pass-through** — Display category in response is byte-for-byte identical to stored config, no transformation
    - **Validates: Requirements 13.1, 13.2, 2.2**

- [ ] 5. Refactor member-handler to use registry
  - [ ] 5.1 Copy `provider_registry.py` and `sts_assume_role.py` into member-handler deployment package
    - Ensure both modules are importable from `lambda_function.py`
    - Add import statements at module level to trigger cold-start cache load
    - _Requirements: 12.5_

  - [ ] 5.2 Refactor member-handler auth logic to use registry
    - Replace hardcoded role ARN pattern and external ID computation with `assume_role()` calls
    - Remove inline STS AssumeRole code, delegate to `sts_assume_role.assume_role()`
    - _Requirements: 14.1, 3.2_

  - [ ] 5.3 Refactor member-handler validation logic to use registry
    - Replace hardcoded `^\d{12}$` regex with `get_config('aws', 'validation')['account_id_regex']`
    - Replace hardcoded error messages with registry-supplied messages
    - _Requirements: 14.2, 4.2_

  - [ ] 5.4 Refactor member-handler CloudFormation template generation to use registry
    - Replace hardcoded template structure with `get_config('aws', 'connection-setup')` values
    - Use registry-supplied role name pattern, trust policy, IAM actions
    - _Requirements: 14.3, 7.2_

  - [ ] 5.5 Refactor member-handler resource discovery to use registry
    - Replace hardcoded per-service API calls with config-driven discovery loop
    - Use `get_config('aws', 'resource-discovery')['resource_types']` for service/method/path
    - _Requirements: 14.4, 6.2_

  - [ ] 5.6 Refactor member-handler scheduler actions to use registry
    - Replace hardcoded start/stop API calls with config-driven action execution
    - Use `get_config('aws', 'scheduler-actions')['actions']` for service/method/params
    - _Requirements: 14.5, 8.2_

  - [ ] 5.7 Refactor member-handler AI prompts to use registry
    - Replace hardcoded prompt strings with `get_config('aws', 'ai-prompts')` values
    - Use registry-supplied system prompt fragments, pricing rules, response templates
    - _Requirements: 14.6, 10.2_

  - [ ] 5.8 Refactor member-handler pricing logic to use registry
    - Replace hardcoded pricing tables with `get_config('aws', 'pricing')` values
    - Use registry-supplied instance pricing, platform multipliers, Pricing API config
    - _Requirements: 14.7, 9.2_

  - [ ]* 5.9 Write property tests for member-handler refactoring (Properties 5, 6, 7, 8, 9)
    - **Property 5: Validation regex equivalence** — Registry regex produces same match/no-match as hardcoded `^\d{12}$` for any input
    - **Property 6: Resource discovery config completeness** — Each resource type has all required fields (service, method, pagination_token, response_list_path, attributes)
    - **Property 7: CloudFormation template generation equivalence** — Registry-driven template is structurally identical to hardcoded template for any valid account_id and email
    - **Property 8: Scheduler actions config completeness** — Each action has service, method, params (non-empty list), description
    - **Property 9: Pricing lookup equivalence** — Registry pricing rates equal hardcoded rates for all instance types
    - **Validates: Requirements 4.2, 6.2, 6.4, 7.2, 8.2, 8.3, 9.2, 14.2, 14.3, 14.4, 14.5, 14.7**

- [ ] 6. Checkpoint - Verify member-handler refactoring
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Refactor agent-action to use registry
  - [ ] 7.1 Copy `provider_registry.py` and `sts_assume_role.py` into agent-action deployment package
    - Copy modules to `agent-action/` directory
    - Add import statements to trigger cold-start cache load
    - _Requirements: 12.5_

  - [ ] 7.2 Refactor agent-action auth and API calls to use registry
    - Replace hardcoded STS AssumeRole with `assume_role()` calls
    - Replace hardcoded resource discovery API calls with registry-driven config
    - Replace hardcoded pricing API parameters with registry config
    - Replace hardcoded region mappings with registry ui-config/display values
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

- [ ] 8. Refactor admin-handler to use registry
  - [ ] 8.1 Copy `provider_registry.py` into admin-handler deployment package
    - Copy module to `admin-handler/` directory
    - Add import statement to trigger cold-start cache load
    - _Requirements: 12.5_

  - [ ] 8.2 Refactor admin-handler to use registry lookups
    - Replace hardcoded S3 bucket names and knowledge base paths with registry config
    - Replace any hardcoded provider-specific identifiers with registry lookups
    - _Requirements: 17.1, 17.2_

- [ ] 9. Refactor frontend to use Provider Config API
  - [ ] 9.1 Add `getProviderConfig()` client-side cache function to members.js
    - Implement `getProviderConfig()` that calls `GET /members/provider-config` once per session
    - Cache response in module-level variable for session duration
    - Handle error cases (network failure, 503 responses)
    - _Requirements: 16.5_

  - [ ] 9.2 Refactor frontend account validation to use Provider Config API
    - Replace hardcoded regex and error messages with `config.validation` values
    - Use `config.validation.account_id_regex`, `config.validation.placeholder`, `config.validation.error_messages`
    - _Requirements: 16.1, 4.3_

  - [ ] 9.3 Refactor frontend connection setup UI to use Provider Config API
    - Replace hardcoded CloudFormation console URLs with `config['connection-setup'].console_urls`
    - Replace hardcoded template instructions with registry-supplied values
    - _Requirements: 16.2, 7.3_

  - [ ] 9.4 Refactor frontend service name display to use Provider Config API
    - Replace hardcoded service name mapping object with `config['ui-config'].service_display_names`
    - _Requirements: 16.3, 11.2_

  - [ ] 9.5 Refactor frontend AI chat follow-up questions to use Provider Config API
    - Replace hardcoded follow-up question arrays with `config['ui-config'].follow_up_questions`
    - _Requirements: 16.4, 11.3_

- [ ] 10. Checkpoint - Verify all consumer refactoring
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Write behavioral equivalence tests
  - [ ]* 11.1 Write property test for behavioral equivalence (Property 13)
    - **Property 13: Behavioral equivalence of refactored handlers** — For any valid API request, refactored implementation produces identical response bodies and status codes as pre-refactoring implementation given same input and mocked AWS responses
    - **Validates: Requirements 18.1, 18.2, 18.4**

  - [ ]* 11.2 Write integration tests for end-to-end registry flow
    - Test: Deploy table → seed data → call Provider Config API → verify response shape
    - Test: Verify all 5 non-sensitive categories present in API response
    - Test: Verify sensitive categories excluded from API response
    - Test: Verify Cache-Control header present with max-age=3600
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 13.1, 13.2, 13.3_

- [ ] 12. Update CI/CD pipeline to include seed step
  - [ ] 12.1 Add seed step to deployment workflow
    - Add step to `.github/workflows/deploy.yml` that runs `infrastructure/seed-provider-registry.py` after CloudFormation stack deployment
    - Ensure seed runs after table creation but before Lambda deployments
    - Add copy step for `provider_registry.py` and `sts_assume_role.py` to each Lambda build
    - _Requirements: 1.4, 12.5_

- [ ] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each major phase
- Property tests validate universal correctness properties from the design document
- The refactoring is data-layer-first: infrastructure → module → seed → API → consumers
- `provider_registry.py` is copied (not shared via Layer) to avoid versioning complexity
- All 13 correctness properties from the design are covered by property test sub-tasks
- This is Phase 1 (AWS only) — behavioral equivalence is the primary success criterion

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "1.5", "2.1"] },
    { "id": 3, "tasks": ["2.2", "4.1"] },
    { "id": 4, "tasks": ["4.2", "5.1", "7.1", "8.1"] },
    { "id": 5, "tasks": ["5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "5.8"] },
    { "id": 6, "tasks": ["5.9", "7.2", "8.2"] },
    { "id": 7, "tasks": ["9.1"] },
    { "id": 8, "tasks": ["9.2", "9.3", "9.4", "9.5"] },
    { "id": 9, "tasks": ["11.1", "11.2"] },
    { "id": 10, "tasks": ["12.1"] }
  ]
}
```
