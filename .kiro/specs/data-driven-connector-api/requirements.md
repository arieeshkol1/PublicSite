# Requirements Document

## Introduction

Replace hardcoded API endpoint logic in agent-action connectors with a data-driven lookup from the ViewMyBill-CostOptimizationTips DynamoDB table. When a connector encounters a cache miss for drilldown data, it reads the `drilldownApis` field from the Tips table to determine which provider APIs to call. The `drilldownApis` field migrates from a flat string array to structured objects containing `{service, operation, params}`. This enables new vendor API integrations to be added by updating the Tips table without code deployment.

## Glossary

- **Tips_Table**: The DynamoDB table `ViewMyBill-CostOptimizationTips` with partition key `service` and sort key `tipId`, containing optimization tip records with drilldown metadata.
- **Drilldown_Plan**: The structured `drilldownApis` field on a Tips_Table record, describing which provider APIs to invoke for a specific tip's drilldown.
- **Connector**: A provider-specific implementation of the CloudConnector base class in `agent-action/connectors/` that executes API calls against a cloud provider account.
- **Provider_Router**: The module `agent-action/provider_router.py` that resolves the cloud provider for an account and dispatches tool invocations to the appropriate Connector.
- **Structured_Object**: A JSON object in the Drilldown_Plan with fields `service` (AWS service name or provider API namespace), `operation` (the API action to invoke), and `params` (a dict of parameters for the call).
- **Healing_Flow**: An automated recovery process triggered when a Drilldown_Plan contains an unrecognized schema or malformed Structured_Object, which logs the error and returns a structured error response requesting plan correction.
- **Cache_Miss**: The condition where the Provider_Router or Connector does not have locally cached drilldown results and must read the Tips_Table to obtain a Drilldown_Plan.

## Requirements

### Requirement 1: Drilldown Plan Lookup on Cache Miss

**User Story:** As a platform operator, I want connectors to read API endpoint definitions from the Tips table on every cache miss, so that I can add new vendor APIs by updating the database without redeploying code.

#### Acceptance Criteria

1. WHEN a Connector encounters a Cache_Miss for drilldown data, THE Provider_Router SHALL query the Tips_Table using the tip's `service` (partition key) and `tipId` (sort key) to retrieve the Drilldown_Plan.
2. THE Provider_Router SHALL read the Tips_Table fresh on each Cache_Miss without maintaining an in-memory cache of Drilldown_Plan records.
3. WHEN the Tips_Table query returns no matching record, THE Provider_Router SHALL return a structured error response containing the key `"error"` with value `"Drilldown plan not found"` and a `"guidance"` field.
4. IF the Tips_Table query fails due to a DynamoDB ClientError, THEN THE Provider_Router SHALL log the error details server-side and return a structured error response with `"retryable": true`.

### Requirement 2: Structured Object Format for drilldownApis

**User Story:** As a platform operator, I want the drilldownApis field to use structured objects instead of flat string arrays, so that connectors can programmatically parse and execute API calls without string-parsing heuristics.

#### Acceptance Criteria

1. THE Provider_Router SHALL accept a Drilldown_Plan in the Structured_Object format where each entry contains `service` (string), `operation` (string), and `params` (dict).
2. THE Provider_Router SHALL accept a Drilldown_Plan in the legacy string-array format for backward compatibility with existing Tips_Table records.
3. WHEN a Drilldown_Plan contains Structured_Objects, THE Connector SHALL use the `service` field to identify the provider API client, the `operation` field to identify the method to call, and the `params` field as the call parameters.
4. THE Provider_Router SHALL detect the format (structured vs legacy) by inspecting whether the first element of the parsed Drilldown_Plan is a dict or a string.

### Requirement 3: Connector Execution of Drilldown Plans

**User Story:** As a platform operator, I want connectors to dynamically execute the API calls specified in a Drilldown Plan, so that tip drilldowns work for any provider API defined in the Tips table.

#### Acceptance Criteria

1. WHEN a Drilldown_Plan contains Structured_Objects, THE Connector SHALL create a boto3 client (for AWS) or appropriate provider client using the `service` field and the account's assumed-role credentials.
2. WHEN a Drilldown_Plan contains Structured_Objects, THE Connector SHALL invoke the operation specified in the `operation` field, passing the `params` dict as keyword arguments.
3. THE Connector SHALL execute each Structured_Object in the Drilldown_Plan sequentially, collecting results from each API call into a combined response list.
4. WHEN a Structured_Object `params` field contains the placeholder `<each>`, THE Connector SHALL substitute the placeholder with the corresponding value from the previous API call's result set.

### Requirement 4: Permission Error Handling

**User Story:** As a member, I want to be alerted when a drilldown fails due to insufficient permissions, so that I know to update my account connection rather than assuming the data is unavailable.

#### Acceptance Criteria

1. IF a Connector encounters an AccessDeniedException or equivalent permission error during Drilldown_Plan execution, THEN THE Provider_Router SHALL return a response with `"authError": true` and a `"guidance"` field directing the member to check their account connection in the Configure tab.
2. IF a permission error occurs on one step of a multi-step Drilldown_Plan, THEN THE Connector SHALL stop execution of remaining steps and return partial results collected up to the failure point along with the permission error.
3. THE Connector SHALL log the full permission error details server-side without exposing provider-specific error messages to the member.

### Requirement 5: Unknown Schema and Healing Flow

**User Story:** As a platform operator, I want the system to gracefully handle malformed or unrecognized drilldown plan schemas, so that a bad Tips table entry does not crash the connector.

#### Acceptance Criteria

1. IF a Drilldown_Plan entry is a Structured_Object missing the required `service` or `operation` field, THEN THE Provider_Router SHALL skip that entry, log a warning with the tipId and the malformed entry, and continue processing remaining entries.
2. IF the `service` field in a Structured_Object refers to an unrecognized provider API client, THEN THE Connector SHALL log a warning and return a structured error response with `"error"` containing the unrecognized service name and `"healingRequired": true`.
3. IF the `operation` field in a Structured_Object refers to a method that does not exist on the resolved provider client, THEN THE Connector SHALL log a warning and return a structured error response with `"error"` containing the invalid operation name and `"healingRequired": true`.
4. WHEN a healing response is returned, THE Provider_Router SHALL include the `tipId` and `service` partition key in the response so that the caller can identify which Tips_Table record requires correction.

### Requirement 6: No In-Memory Caching of Drilldown Plans

**User Story:** As a platform operator, I want drilldown plans to always reflect the latest Tips table state, so that updates take effect immediately without waiting for cache expiry or Lambda cold starts.

#### Acceptance Criteria

1. THE Provider_Router SHALL query the Tips_Table on every Cache_Miss without storing Drilldown_Plan records in module-level variables, class attributes, or any in-process cache.
2. WHEN the same tipId is requested multiple times within a single Lambda invocation, THE Provider_Router SHALL query the Tips_Table each time rather than reusing a previously fetched Drilldown_Plan.

### Requirement 7: Backward Compatibility with Existing Pattern

**User Story:** As a platform operator, I want the new data-driven execution to coexist with the existing member-handler Tier-2 drilldown pattern, so that the migration can proceed incrementally without breaking existing functionality.

#### Acceptance Criteria

1. THE Provider_Router SHALL preserve the existing `route_tool` dispatch path for all currently supported tool operations (getCostBreakdown, getComputeInstances, etc.) without modification.
2. THE Provider_Router SHALL invoke the Drilldown_Plan lookup only for tip-specific drilldown requests, identified by the presence of a `tipId` parameter in the tool invocation parameters.
3. WHEN a tool invocation includes a `tipId` parameter, THE Provider_Router SHALL attempt the data-driven Drilldown_Plan execution path before falling through to any hardcoded connector method.
