# Implementation Plan: Admin Connector Configuration

## Overview

This plan implements the complete Admin Connector Configuration feature — moving all hardcoded connector attributes into a DynamoDB-backed, admin-managed configuration layer with CRUD API, admin UI panel, runtime caching, migration script, validation, backward compatibility fallback, and duplication support. The implementation progresses from infrastructure through backend, frontend, migration, and integration wiring.

## Tasks

- [x] 1. Infrastructure and DynamoDB table setup
  - [x] 1.1 Add ConnectorConfig DynamoDB table to CloudFormation stack
    - Add a new `AWS::DynamoDB::Table` resource named `ConnectorConfig` with partition key `providerKey` (String), PAY_PER_REQUEST billing mode
    - Add IAM policy statements granting `dynamodb:Scan`, `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:UpdateItem`, `dynamodb:DeleteItem` on the ConnectorConfig table to the Admin Handler Lambda role
    - Add IAM policy statements granting `dynamodb:Scan`, `dynamodb:GetItem` on the ConnectorConfig table to the Member Handler and Agent Action Lambda roles
    - Add environment variable `CONNECTOR_CONFIG_TABLE_NAME` with value `ConnectorConfig` to Admin Handler, Member Handler, and Agent Action Lambda configurations
    - _Requirements: 2.1–2.14, 4.1, 4.2_

- [x] 2. Backend validation module
  - [x] 2.1 Create `admin-handler/connector_validator.py`
    - Implement `validate_connector_config(body: dict, is_update: bool = False) -> list[str]` function
    - Validate `providerKey` matches `^[a-z][a-z0-9_]{1,30}$`
    - Validate `authType` is one of: `iam_role`, `service_principal`, `service_account`, `api_key`, `oauth2`
    - Validate `stalenessThresholdHours` is a positive integer between 1 and 720
    - Validate `supportedOperations` is a non-empty list of strings
    - Validate `cacheSchema.pkPrefix` is a non-empty uppercase string matching `^[A-Z][A-Z0-9_]*$`
    - Validate `connectorClass` matches `^[a-z_]+\.[A-Za-z]+$`
    - Collect ALL validation errors and return them as a list (no short-circuiting)
    - Validate required fields: `providerKey`, `displayName`, `iconUrl`, `authType`, `syncFields`, `tipsRepository`, `invoiceFields`, `cacheSchema`, `supportedOperations`, `stalenessThresholdHours`, `costEstimationRates`, `cloud`, `connectorClass`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 1.7_

  - [ ]* 2.2 Write property test for validation (Property 3)
    - **Property 3: Validation Rejects Invalid Configs and Reports All Errors**
    - Use Hypothesis to generate Connector_Config dicts with 1+ rule violations
    - Assert that for each violated rule a corresponding error message appears in the response
    - Assert no short-circuiting (all errors reported in single response)
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 1.7**

- [x] 3. Backend CRUD API routes
  - [x] 3.1 Add connector CRUD route handlers to `admin-handler/lambda_function.py`
    - Add `CONNECTOR_CONFIG_TABLE_NAME` env var reference
    - Register routes: `GET /admin/connectors`, `GET /admin/connectors/{provider_key}`, `POST /admin/connectors`, `PUT /admin/connectors/{provider_key}`, `DELETE /admin/connectors/{provider_key}`
    - Implement `handle_get_connectors(event)` — scans ConnectorConfig table, returns all records
    - Implement `handle_get_connector(event)` — get_item by providerKey, return 404 if not found
    - Implement `handle_create_connector(event)` — validate body, check providerKey not exists (409 if duplicate), set `createdAt` and `updatedAt` to current ISO 8601 timestamp, put_item
    - Implement `handle_update_connector(event)` — validate body, check record exists (404 if not), update all fields, set `updatedAt` to current ISO 8601 timestamp
    - Implement `handle_delete_connector(event)` — check record exists (404 if not), delete_item
    - All handlers call `validate_token(event)` first and return 401 on failure
    - All handlers call `validate_connector_config()` for POST/PUT and return 400 with error list on failure
    - Use `@transaction_log('admin-handler')` decorator on mutating handlers
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.14_

  - [ ]* 3.2 Write property test for CRUD round-trip (Property 1)
    - **Property 1: CRUD Round-Trip Consistency**
    - Use Hypothesis `@st.composite` to generate valid Connector_Config dicts
    - Assert: POST → GET returns same values; PUT with changes → GET reflects updates; DELETE → GET returns 404
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

  - [ ]* 3.3 Write property test for authentication enforcement (Property 2)
    - **Property 2: Authentication Enforcement on Connector Routes**
    - Generate random invalid/missing/expired JWT tokens across all connector routes
    - Assert all return 401 status
    - **Validates: Requirements 1.6**

  - [ ]* 3.4 Write property test for automatic timestamps (Property 8)
    - **Property 8: Automatic Timestamp Management**
    - Create connector, verify `createdAt` set; update connector with time mock, verify `updatedAt` changes while `createdAt` stays stable
    - **Validates: Requirements 2.14**

- [ ] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Config Cache module
  - [x] 5.1 Create shared `connector_config_cache.py` module
    - Implement `get_connector(provider_key: str) -> dict | None` function
    - Implement `get_all_connectors() -> dict[str, dict]` function
    - Implement `is_fallback_active() -> bool` function
    - Implement internal `_refresh_cache()` that scans ConnectorConfig DynamoDB table
    - Cache loaded records in module-level `_cache` dict with `_cache_loaded_at` timestamp
    - If DynamoDB scan returns zero records, fall back to reading `vendor_registry.json` (set `_fallback_active = True`, log warning)
    - If DynamoDB is unreachable (ClientError), continue serving last good cache (log warning)
    - When at least one record loaded from DynamoDB, disable fallback path (`_fallback_active = False`)
    - Use `_CACHE_TTL_SECONDS = 300` — skip DynamoDB scan if cache is fresh
    - _Requirements: 4.3, 4.4, 4.5, 4.6, 4.7, 7.1, 7.2, 7.3, 7.4_

  - [ ]* 5.2 Write property test for cache TTL freshness (Property 4)
    - **Property 4: Cache TTL Freshness**
    - Use `freezegun` or `unittest.mock.patch('time.time')` to manipulate time
    - Assert: within 300s → no DynamoDB call; after 300s → DynamoDB call occurs
    - **Validates: Requirements 4.3, 4.4**

  - [ ]* 5.3 Write property test for cache resilience (Property 5)
    - **Property 5: Cache Resilience Under Store Failure**
    - Mock DynamoDB raising ClientError after a successful load
    - Assert: last good cache is still returned without error
    - **Validates: Requirements 4.5**

  - [ ]* 5.4 Write property test for fallback behavior (Property 6)
    - **Property 6: Fallback to Static File When Store Is Empty**
    - Mock DynamoDB returning zero records, assert vendor_registry.json data returned
    - Then mock DynamoDB returning records, assert fallback disabled
    - **Validates: Requirements 7.1, 7.2, 7.4**

- [x] 6. Integrate Config Cache into runtime Lambdas
  - [x] 6.1 Integrate Config Cache into `member-handler/lambda_function.py`
    - Import `connector_config_cache` module
    - Replace any references to static vendor_registry.json with `get_all_connectors()` / `get_connector()` calls
    - When `is_fallback_active()` is True, log a warning per request indicating dynamic configuration is unavailable
    - Deploy `connector_config_cache.py` alongside member-handler Lambda package
    - _Requirements: 4.1, 7.1, 7.3_

  - [x] 6.2 Integrate Config Cache into `agent-action/lambda_function.py`
    - Import `connector_config_cache` module
    - Replace references to `vendor_registry.json` reads with `get_all_connectors()` / `get_connector()` calls
    - When `is_fallback_active()` is True, log a warning per request indicating dynamic configuration is unavailable
    - Deploy `connector_config_cache.py` alongside agent-action Lambda package
    - _Requirements: 4.2, 7.2, 7.3_

- [ ] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Admin UI - Connectors Tab
  - [x] 8.1 Add Connectors tab markup to `admin/index.html`
    - Add new tab button "Connectors" to the `<nav class="tab-nav">` bar
    - Add `<div id="connectors-tab" class="tab-content" hidden>` section
    - Add connectors table with columns: Provider Key, Display Name, Auth Type, Cloud, Staleness (hrs), Actions
    - Add "Add Connector" button in the tab toolbar
    - Add connector modal form with all 14 Connector_Config fields (providerKey, displayName, iconUrl, authType, syncFields, tipsRepository, invoiceFields.issuerLabel, invoiceFields.accountIdPattern, invoiceFields.currencyDefault, cacheSchema.pkPrefix, cacheSchema.skFormat, cacheSchema.fieldNames, supportedOperations, stalenessThresholdHours, costEstimationRates, cloud, connectorClass)
    - Add delete confirmation dialog for connectors
    - Add duplicate button per row
    - _Requirements: 3.1, 3.2, 3.4, 3.6, 8.1_

  - [x] 8.2 Add Connectors tab JavaScript logic to `admin/admin.js`
    - Implement `loadConnectors()` — GET /admin/connectors, populate table
    - Implement `showConnectorForm(connector)` — pre-fill for edit, empty for add
    - Implement `saveConnector()` — POST for new, PUT for edit, display success/error notifications
    - Implement `deleteConnector(providerKey)` — show confirmation, send DELETE, refresh list
    - Implement `duplicateConnector(connector)` — pre-fill Add form with all values except providerKey, clear and focus providerKey field
    - Implement client-side validation: providerKey matches `^[a-z][a-z0-9_]{1,30}$`, supportedOperations has at least one entry
    - Display API validation errors adjacent to relevant form fields
    - Wire Connectors tab button to `switchTab('connectors')` logic
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 8.1, 8.2, 8.3_

  - [ ]* 8.3 Write property test for duplication (Property 9)
    - **Property 9: Duplication Preserves All Fields Except providerKey**
    - Use fast-check to generate random config objects, verify duplication copies all fields except providerKey
    - **Validates: Requirements 8.1, 8.2**

  - [ ]* 8.4 Write property test for client-side providerKey validation (Property 10)
    - **Property 10: Client-Side providerKey Validation**
    - Use fast-check `fc.string()` to generate random strings
    - Assert validation function accepts iff string matches `^[a-z][a-z0-9_]{1,30}$`
    - **Validates: Requirements 3.8, 6.1**

- [x] 9. Migration script
  - [x] 9.1 Create `scripts/migrate_connector_config.py`
    - Read `agent-action/connectors/vendor_registry.json` — extract all vendor entries
    - For each vendor, compose a full Connector_Config record:
      - Map `displayName`, `cloud`, `authType`, `connector` → `connectorClass`
      - Map `cachePrefix` → `cacheSchema.pkPrefix`, set `cacheSchema.skFormat` and `cacheSchema.fieldNames` from known patterns
      - Map `staleness_hours` → `stalenessThresholdHours`
      - Map `supportedTools` → `supportedOperations`
      - Populate `invoiceFields.issuerLabel` from known ISSUER_LABELS dictionary
      - Populate `invoiceFields.accountIdPattern` from known PROVIDER_ACCOUNT_ID_PATTERNS regex strings
      - Set `invoiceFields.currencyDefault` to "USD" (default)
      - Set `iconUrl`, `syncFields`, `tipsRepository`, `costEstimationRates` with sensible defaults
      - Set `createdAt` and `updatedAt` to current ISO 8601 timestamp
    - For each provider, check if record already exists in DynamoDB — if yes, skip and log warning
    - Write new records using `put_item` with condition expression `attribute_not_exists(providerKey)`
    - Handle errors: missing vendor_registry.json → exit with error; DynamoDB unreachable → exit with error; partial failures → log which providers failed, exit non-zero
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [ ]* 9.2 Write property test for migration idempotency (Property 7)
    - **Property 7: Migration Idempotency**
    - Pre-seed DynamoDB mock with existing records, run migration, verify records unchanged
    - **Validates: Requirements 5.7**

- [ ] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Integration wiring and final validation
  - [ ] 11.1 Wire all components together and verify end-to-end flow
    - Verify Admin Handler routes are registered and dispatch correctly
    - Verify Config Cache module is importable from both member-handler and agent-action directories (copy or shared layer)
    - Verify environment variable `CONNECTOR_CONFIG_TABLE_NAME` is read correctly by all Lambdas
    - Verify the Connectors tab appears in admin UI and loads data from the API
    - Verify backward compatibility: if ConnectorConfig table is empty, runtime Lambdas still function using vendor_registry.json fallback
    - _Requirements: 1.1–1.7, 3.1–3.9, 4.1–4.7, 7.1–7.4_

  - [ ]* 11.2 Write integration tests for end-to-end CRUD flow
    - Test full lifecycle: create connector via POST, list via GET, update via PUT, verify change, delete via DELETE
    - Test Member Handler reads config from cache (not static file) after migration
    - Test Agent Action loads connector metadata from cache
    - _Requirements: 1.1–1.5, 4.1, 4.2_

- [ ] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The Config Cache module (`connector_config_cache.py`) must be deployed with both `member-handler` and `agent-action` Lambda packages (copy into each directory or use a Lambda Layer)
- The migration script is a one-time operation run after the DynamoDB table is created
- The `vendor_registry.json` file is retained as fallback during the transition period

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "5.1"] },
    { "id": 2, "tasks": ["2.2", "3.1", "5.2", "5.3", "5.4"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "6.1", "6.2"] },
    { "id": 4, "tasks": ["8.1", "9.1"] },
    { "id": 5, "tasks": ["8.2", "8.3", "8.4", "9.2"] },
    { "id": 6, "tasks": ["11.1"] },
    { "id": 7, "tasks": ["11.2"] }
  ]
}
```
