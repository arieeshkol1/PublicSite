# Requirements Document

## Introduction

The Admin Connector Configuration feature moves all hardcoded connector attributes (icons, auth types, sync fields, tips locations, invoice fields, cache schemas, supported operations, display names, staleness thresholds, and cost estimation rates) into a configurable admin panel section. Administrators configure connectors once through the admin UI, the configuration is persisted to DynamoDB, and all runtime code reads from this centralized store (with caching) rather than from static JSON files or hardcoded constants. Adding a new provider becomes a zero-code operation.

## Glossary

- **Admin_Panel**: The existing administration interface served at `/admin` (admin.js, admin/index.html) with authentication gating
- **Connector_Config_Store**: A DynamoDB table (or partition within an existing table) that persists connector configuration records keyed by provider identifier
- **Provider_Key**: The lowercase string identifier for a cloud or AI vendor (e.g., "aws", "azure", "gcp", "openai", "anthropic", "groundcover")
- **Connector_Config**: A complete configuration record for one provider containing all attributes previously hardcoded
- **Config_Cache**: An in-memory or short-lived cache layer within each Lambda function that avoids repeated DynamoDB reads on every request
- **Admin_Handler**: The existing Lambda at `admin-handler/lambda_function.py` that serves admin API routes
- **Member_Handler**: The member-facing Lambda at `member-handler/lambda_function.py` that serves member portal API routes
- **Agent_Action**: The Bedrock agent Lambda at `agent-action/lambda_function.py` that resolves provider routing and tool execution
- **Vendor_Registry**: The current static JSON file (`agent-action/connectors/vendor_registry.json`) that defines provider metadata
- **Staleness_Threshold**: The maximum age (in hours) of cached cost data before a refresh is required
- **Cache_Schema**: The DynamoDB key structure (PK prefix, SK format, attribute names) used for cost cache entries per provider
- **Sync_Fields**: The list of data fields that a connector retrieves and normalizes from the external provider API
- **Auth_Type**: The authentication mechanism a provider uses (e.g., iam_role, service_principal, service_account, api_key)

## Requirements

### Requirement 1: Admin Connector Configuration CRUD API

**User Story:** As an administrator, I want to create, read, update, and delete connector configurations through the admin API, so that I can manage provider attributes without code changes.

#### Acceptance Criteria

1. WHEN an authenticated admin sends a GET request to `/admin/connectors`, THE Admin_Handler SHALL return a list of all Connector_Config records from the Connector_Config_Store
2. WHEN an authenticated admin sends a GET request to `/admin/connectors/{provider_key}`, THE Admin_Handler SHALL return the complete Connector_Config for the specified Provider_Key
3. WHEN an authenticated admin sends a POST request to `/admin/connectors` with a valid Connector_Config body, THE Admin_Handler SHALL create a new record in the Connector_Config_Store and return the created configuration
4. WHEN an authenticated admin sends a PUT request to `/admin/connectors/{provider_key}` with a valid Connector_Config body, THE Admin_Handler SHALL update the existing record in the Connector_Config_Store and return the updated configuration
5. WHEN an authenticated admin sends a DELETE request to `/admin/connectors/{provider_key}`, THE Admin_Handler SHALL remove the Connector_Config record from the Connector_Config_Store
6. IF an unauthenticated request is received on any `/admin/connectors` route, THEN THE Admin_Handler SHALL return a 401 status with an error message
7. IF a POST or PUT request contains an invalid or incomplete Connector_Config body, THEN THE Admin_Handler SHALL return a 400 status with a descriptive validation error

### Requirement 2: Connector Configuration Data Model

**User Story:** As an administrator, I want each connector configuration to contain all provider-specific attributes in a single record, so that runtime code has a complete specification for each provider.

#### Acceptance Criteria

1. THE Connector_Config SHALL contain a providerKey field (string, unique identifier, lowercase)
2. THE Connector_Config SHALL contain a displayName field (string, human-readable provider name)
3. THE Connector_Config SHALL contain an iconUrl field (string, URL or path to the connector logo)
4. THE Connector_Config SHALL contain an authType field (string, one of: iam_role, service_principal, service_account, api_key, oauth2)
5. THE Connector_Config SHALL contain a syncFields field (list of strings, naming the data fields to retrieve from the provider)
6. THE Connector_Config SHALL contain a tipsRepository field (string, the S3 path or DynamoDB location where optimization tips for this provider are stored)
7. THE Connector_Config SHALL contain an invoiceFields field (object, defining issuerLabel, accountIdPattern, and currencyDefault for invoice generation)
8. THE Connector_Config SHALL contain a cacheSchema field (object, defining pkPrefix, skFormat, and fieldNames for the Cost_Cache_Table)
9. THE Connector_Config SHALL contain a supportedOperations field (list of strings, enumerating available agent tools for this provider)
10. THE Connector_Config SHALL contain a stalenessThresholdHours field (integer, maximum cache age before refresh)
11. THE Connector_Config SHALL contain a costEstimationRates field (object, mapping model or service identifiers to per-unit pricing for cost distribution)
12. THE Connector_Config SHALL contain a cloud field (string, logical cloud grouping such as "aws", "azure", "gcp", or "ai_vendor")
13. THE Connector_Config SHALL contain a connectorClass field (string, the Python module.Class path to the connector implementation)
14. THE Connector_Config SHALL contain a createdAt and updatedAt timestamp field (ISO 8601 strings, set automatically on create and update)

### Requirement 3: Admin UI Connector Configuration Panel

**User Story:** As an administrator, I want a visual panel within the admin UI to manage connector configurations, so that I can add, edit, and remove providers without using direct API calls.

#### Acceptance Criteria

1. WHEN the admin navigates to the Connectors tab in the Admin_Panel, THE Admin_Panel SHALL display a table listing all configured connectors with their Provider_Key, displayName, authType, and stalenessThresholdHours
2. WHEN the admin clicks "Add Connector", THE Admin_Panel SHALL display a form with input fields for all Connector_Config attributes defined in Requirement 2
3. WHEN the admin submits the Add Connector form with valid data, THE Admin_Panel SHALL send a POST request to `/admin/connectors` and display a success notification
4. WHEN the admin clicks the edit button for an existing connector, THE Admin_Panel SHALL display a pre-populated form with the current Connector_Config values
5. WHEN the admin submits the Edit Connector form with valid changes, THE Admin_Panel SHALL send a PUT request to `/admin/connectors/{provider_key}` and display a success notification
6. WHEN the admin clicks the delete button for a connector, THE Admin_Panel SHALL display a confirmation dialog before sending a DELETE request
7. IF the API returns a validation error on form submission, THEN THE Admin_Panel SHALL display the error message adjacent to the relevant form field
8. THE Admin_Panel SHALL validate that providerKey contains only lowercase letters, numbers, and underscores before submission
9. THE Admin_Panel SHALL validate that supportedOperations contains at least one operation before submission

### Requirement 4: Runtime Configuration Reader with Caching

**User Story:** As a system operator, I want runtime Lambdas to read connector configuration from DynamoDB with a short-lived cache, so that configuration changes take effect within minutes without redeployment.

#### Acceptance Criteria

1. THE Member_Handler SHALL read Connector_Config from the Connector_Config_Store instead of the static Vendor_Registry file
2. THE Agent_Action SHALL read Connector_Config from the Connector_Config_Store instead of the static Vendor_Registry file
3. THE Config_Cache SHALL store loaded configurations in memory with a time-to-live of 300 seconds (5 minutes)
4. WHEN the Config_Cache time-to-live expires, THE Config_Cache SHALL reload all Connector_Config records from the Connector_Config_Store on the next request
5. IF the Connector_Config_Store is unreachable, THEN THE Config_Cache SHALL continue serving the last successfully loaded configuration until the store becomes available
6. THE Config_Cache SHALL expose a function to retrieve a single Connector_Config by Provider_Key
7. THE Config_Cache SHALL expose a function to retrieve all Connector_Config records as a dictionary keyed by Provider_Key

### Requirement 5: Migration of Existing Hardcoded Values

**User Story:** As a system operator, I want all currently hardcoded connector attributes migrated to the Connector_Config_Store, so that the system runs entirely from dynamic configuration after deployment.

#### Acceptance Criteria

1. WHEN the migration script runs, THE Migration_Script SHALL read the existing vendor_registry.json and create corresponding Connector_Config records in the Connector_Config_Store for each provider (aws, azure, gcp, openai, anthropic, groundcover)
2. WHEN the migration script runs, THE Migration_Script SHALL populate invoiceFields.issuerLabel from the ISSUER_LABELS dictionary values for each provider
3. WHEN the migration script runs, THE Migration_Script SHALL populate invoiceFields.accountIdPattern from the PROVIDER_ACCOUNT_ID_PATTERNS regex strings for each provider
4. WHEN the migration script runs, THE Migration_Script SHALL populate cacheSchema.pkPrefix from the existing cachePrefix values in vendor_registry.json
5. WHEN the migration script runs, THE Migration_Script SHALL populate supportedOperations from the existing supportedTools arrays in vendor_registry.json
6. WHEN the migration script runs, THE Migration_Script SHALL populate stalenessThresholdHours from the existing staleness_hours values in vendor_registry.json
7. IF a Connector_Config record already exists for a Provider_Key, THEN THE Migration_Script SHALL skip that provider and log a warning rather than overwriting

### Requirement 6: Configuration Validation

**User Story:** As an administrator, I want the system to validate connector configurations before persisting them, so that invalid configurations cannot break runtime behavior.

#### Acceptance Criteria

1. WHEN a Connector_Config is submitted for creation or update, THE Admin_Handler SHALL validate that providerKey matches the pattern `^[a-z][a-z0-9_]{1,30}$`
2. WHEN a Connector_Config is submitted for creation or update, THE Admin_Handler SHALL validate that authType is one of the allowed values (iam_role, service_principal, service_account, api_key, oauth2)
3. WHEN a Connector_Config is submitted for creation or update, THE Admin_Handler SHALL validate that stalenessThresholdHours is a positive integer between 1 and 720
4. WHEN a Connector_Config is submitted for creation or update, THE Admin_Handler SHALL validate that supportedOperations is a non-empty list of strings
5. WHEN a Connector_Config is submitted for creation or update, THE Admin_Handler SHALL validate that cacheSchema.pkPrefix is a non-empty uppercase string
6. WHEN a Connector_Config is submitted for creation or update, THE Admin_Handler SHALL validate that connectorClass matches the pattern `^[a-z_]+\.[A-Za-z]+$`
7. IF any validation rule fails, THEN THE Admin_Handler SHALL return a 400 response listing all failed validation rules in a single response

### Requirement 7: Backward Compatibility

**User Story:** As a system operator, I want a fallback mechanism during the transition period, so that the system continues functioning if the Connector_Config_Store is empty or unavailable.

#### Acceptance Criteria

1. IF the Config_Cache loads zero records from the Connector_Config_Store, THEN THE Member_Handler SHALL fall back to reading the static vendor_registry.json file
2. IF the Config_Cache loads zero records from the Connector_Config_Store, THEN THE Agent_Action SHALL fall back to reading the static vendor_registry.json file
3. WHILE the fallback mode is active, THE Member_Handler SHALL log a warning on each request indicating that dynamic configuration is unavailable
4. WHEN at least one Connector_Config record is loaded successfully from the store, THE Config_Cache SHALL disable the fallback path and use only dynamic configuration

### Requirement 8: Connector Configuration Duplication

**User Story:** As an administrator, I want to duplicate an existing connector configuration as a starting point for a new provider, so that I can onboard similar providers quickly.

#### Acceptance Criteria

1. WHEN the admin clicks the duplicate button for an existing connector, THE Admin_Panel SHALL pre-populate the Add Connector form with all values from the source connector except providerKey
2. THE Admin_Panel SHALL clear the providerKey field and focus it for the administrator to enter a new unique identifier
3. WHEN the duplicated configuration is submitted, THE Admin_Handler SHALL treat the request as a standard POST creation with full validation
