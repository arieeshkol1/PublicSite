# Requirements Document

## Introduction

SlashMyBill answers AI cost and usage questions in the Bedrock-powered chat. Today the chat path is OpenAI-specific: cache keys are prefixed `OPENAI_DAILY#`, and the resolution logic short-circuits on OpenAI. This feature makes AI cost/usage answers vendor-agnostic so that users can ask about cost, units/tokens, and actor/user dimensions for any connected AI vendor (OpenAI, Anthropic, and future vendors) through one tool and one resolution flow.

The feature registers a single `getAIUsage` tool in the existing Knowledge action group, introduces vendor-neutral cache keys (`COST#{date}`, `USAGE#{date}#{actor}#{service}`), and implements a three-tier resolution strategy: cache rollups first, then a per-service drilldown over the Tips Table executed through the customer's own connection, then a bounded/asynchronous live vendor API call as a last resort. Existing `OPENAI_DAILY#` cache data is migrated to the neutral schema. The AI dashboard data paths in the member portal that also read the cache table — the AI cost summary, per-model breakdown, and per-user token consumption graph — are brought into scope so they read the vendor-neutral keys and are covered by the migration without breaking after cutover. All AI cost data is read from the customer connection only — never from platform-owned AI spend — and the system operates against a single account per resolution.

## Glossary

- **AI_Usage_Service**: The backend resolution component (in `member-handler`, primarily `cache_service.py`, `incremental_fetch_engine.py`, and `provider_invoices.py`) that produces a vendor-agnostic AI cost/usage answer for a single account and time window.
- **Provider_Router**: The dispatch module (`agent-action/provider_router.py`) that resolves an account's vendor and routes a tool invocation to the matching connector, including the `TOOL_TO_METHOD` map.
- **AI_Vendor_Connector**: The connector (`agent-action/connectors/ai_vendor_connector.py`) that retrieves cost and usage data from an AI vendor's API using the customer's stored credentials.
- **Knowledge_Action_Group**: The existing Bedrock Agent action group defined by `agent-action/schemas/knowledge.json`.
- **getAIUsage**: The vendor-agnostic Bedrock Agent tool registered in the Knowledge_Action_Group that returns AI cost and usage data for an account.
- **Cost_Cache_Table**: The DynamoDB table that stores cached AI cost and usage rollups for an account.
- **Cost_Rollup_Item**: A Cost_Cache_Table item with sort key `COST#{date}` holding a daily cost rollup for an account.
- **Usage_Detail_Item**: A Cost_Cache_Table item with sort key `USAGE#{date}#{actor}#{service}` holding per-actor, per-service usage for a given day.
- **Tips_Table**: The DynamoDB optimization-tips table (`ViewMyBill-CostOptimizationTips`) that holds per-service AI usage detail used for Tier-2 drilldown.
- **Tier_1_Resolution**: Reading cached Cost_Rollup_Item and Usage_Detail_Item records from the Cost_Cache_Table.
- **Tier_2_Resolution**: Per-service drilldown over the Tips_Table executed via the customer connection when the cache is insufficient.
- **Tier_3_Resolution**: A bounded, asynchronous live AI_Vendor_Connector API call used as a last resort when Tier_1_Resolution and Tier_2_Resolution cannot satisfy the request.
- **Customer_Connection**: The customer-owned AI vendor credentials and account context used to retrieve AI cost/usage data.
- **Actor**: The user, API key, or project dimension to which AI usage is attributed.
- **Requested_Window**: The date range (start date through end date) for which AI cost/usage data is requested.
- **Staleness_Threshold**: The maximum age of a cached rollup beyond which Tier_1_Resolution data is treated as stale.
- **Intent_Gate**: The branch in `handle_ai_query` (`member-handler/lambda_function.py`) that detects an AI cost/usage question and routes it to the vendor-agnostic resolution path.
- **Migration_Job**: The one-time backfill process that converts existing `OPENAI_DAILY#` items into the vendor-neutral Cost_Rollup_Item and Usage_Detail_Item schema.
- **Admin_Key**: A Customer_Connection credential with sufficient permissions to read account-wide AI usage and cost data.
- **AI_Dashboard_Data_Path**: The member-portal data paths that render AI cost and usage dashboard widgets by reading the Cost_Cache_Table — specifically `handle_dashboard_data` and the OpenAI dashboard data path in `member-handler/lambda_function.py`, the cache-refresh routine `_refresh_cost_cache_for_account`, and the per-user token consumption graph endpoint.
- **AI_Dashboard_Widgets**: The member-portal UI widgets rendered by `members/members.js` that display AI cost summary, per-model cost breakdown, and the per-user token consumption graph.

## Requirements

### Requirement 1: Vendor-Agnostic Provider Resolution

**User Story:** As a SlashMyBill user with any AI vendor connected, I want the chat to resolve cost and usage data without vendor-specific branching, so that I receive consistent answers regardless of which AI vendor I use.

#### Acceptance Criteria

1. WHEN the AI_Usage_Service resolves an AI cost or usage request, THE AI_Usage_Service SHALL select the vendor connector using the account's stored `cloudProvider` value through the Provider_Router rather than vendor-specific conditional logic.
2. WHERE an account's `vendorType` is `ai_vendor`, THE AI_Usage_Service SHALL apply the same three-tier resolution flow for every supported AI vendor.
3. THE Provider_Router SHALL register `getAIUsage` in the `TOOL_TO_METHOD` map mapped to a single connector method that retrieves AI cost and usage data.
4. THE Provider_Router test suite SHALL assert that `len(TOOL_TO_METHOD)` equals 22 after `getAIUsage` is registered.
5. IF the resolved vendor connector does not implement AI usage retrieval, THEN THE AI_Usage_Service SHALL return a structured `notSupported` response identifying the unsupported operation.

### Requirement 2: Vendor-Neutral Cache Schema and Connector Field Mapping

**User Story:** As a platform developer, I want cached AI cost and usage data stored under vendor-neutral keys, so that one schema serves all AI vendors.

#### Acceptance Criteria

1. WHEN the AI_Usage_Service writes a daily cost rollup to the Cost_Cache_Table, THE AI_Usage_Service SHALL store it as a Cost_Rollup_Item with sort key `COST#{date}` where `date` is an ISO 8601 calendar date.
2. WHEN the AI_Usage_Service writes per-actor usage to the Cost_Cache_Table, THE AI_Usage_Service SHALL store it as a Usage_Detail_Item with sort key `USAGE#{date}#{actor}#{service}`.
3. THE Cost_Rollup_Item SHALL contain the account partition key `{memberEmail}#{accountId}`, a total cost amount, a currency code, and a `cached_at` ISO 8601 timestamp.
4. THE Usage_Detail_Item SHALL contain a usage quantity, a unit label, a cost amount, the actor identifier, and the service name.
5. WHEN the AI_Vendor_Connector returns raw vendor data, THE AI_Vendor_Connector SHALL map vendor-specific fields onto the neutral fields cost amount, usage quantity, unit label, actor identifier, service name, and period boundaries before the data is cached.
6. WHERE a neutral field has no corresponding source field in the vendor response, THE AI_Vendor_Connector SHALL set that field to null rather than omitting it.

### Requirement 3: getAIUsage Tool Definition

**User Story:** As a SlashMyBill user, I want a single AI usage tool that supports cost, units, and actor dimensions, so that the chat can answer varied AI spend questions.

#### Acceptance Criteria

1. THE Knowledge_Action_Group schema SHALL define `getAIUsage` with operation path `/get-ai-usage`.
2. THE getAIUsage tool SHALL declare required parameters `accountId` and `memberEmail`.
3. THE getAIUsage tool SHALL declare a required `dimension` parameter accepting the values `cost`, `units`, and `actor`.
4. THE getAIUsage tool SHALL declare an optional `service` parameter that scopes results to a single AI service or model.
5. THE getAIUsage tool SHALL declare an optional `period` parameter that specifies the Requested_Window.
6. WHEN getAIUsage is invoked without a `period` parameter, THE AI_Usage_Service SHALL default the Requested_Window to the most recent 30 days.

### Requirement 4: Three-Tier Resolution and Staleness

**User Story:** As a SlashMyBill user, I want fast cached answers that fall back to deeper sources only when needed, so that I get accurate AI cost data with low latency.

#### Acceptance Criteria

1. WHEN getAIUsage is invoked, THE AI_Usage_Service SHALL attempt Tier_1_Resolution against the Cost_Cache_Table before any other tier.
2. IF Tier_1_Resolution returns cached records that cover the full Requested_Window and are within the Staleness_Threshold, THEN THE AI_Usage_Service SHALL return the cached result without invoking Tier_2_Resolution or Tier_3_Resolution.
3. IF Tier_1_Resolution does not cover the full Requested_Window or the cached records exceed the Staleness_Threshold, THEN THE AI_Usage_Service SHALL perform Tier_2_Resolution.
4. IF Tier_2_Resolution cannot satisfy the request, THEN THE AI_Usage_Service SHALL perform Tier_3_Resolution as the last resort.
5. THE AI_Usage_Service SHALL treat a Cost_Rollup_Item as stale WHEN its `cached_at` timestamp is older than the Staleness_Threshold.
6. WHEN the AI_Usage_Service completes Tier_2_Resolution or Tier_3_Resolution, THE AI_Usage_Service SHALL write the retrieved data to the Cost_Cache_Table using the vendor-neutral schema.

### Requirement 5: Tier-2 Drilldown Trigger Conditions

**User Story:** As a SlashMyBill user, I want the system to drill into per-service detail when the cache is incomplete, so that recent and specific data is not missed.

#### Acceptance Criteria

1. IF the most recent day within the Requested_Window has no Cost_Rollup_Item in the Cost_Cache_Table, THEN THE AI_Usage_Service SHALL trigger Tier_2_Resolution.
2. IF any day within the Requested_Window has no Cost_Rollup_Item, THEN THE AI_Usage_Service SHALL trigger Tier_2_Resolution for the gap.
3. WHERE the getAIUsage `service` parameter scopes the request to a specific AI service, THE AI_Usage_Service SHALL trigger Tier_2_Resolution for that service.
4. IF Tier_1_Resolution returns no items for the Requested_Window, THEN THE AI_Usage_Service SHALL trigger Tier_2_Resolution.
5. IF the cached records covering the Requested_Window exceed the Staleness_Threshold, THEN THE AI_Usage_Service SHALL trigger Tier_2_Resolution.

### Requirement 6: Tips-Table Drilldown via Customer Connection

**User Story:** As a SlashMyBill user, I want per-service AI usage detail retrieved through my own connection, so that the breakdown reflects my account data.

#### Acceptance Criteria

1. WHEN the AI_Usage_Service performs Tier_2_Resolution, THE AI_Usage_Service SHALL query the Tips_Table for per-service usage scoped to the requested account and service.
2. WHEN the AI_Usage_Service performs Tier_2_Resolution, THE AI_Usage_Service SHALL execute data retrieval using the Customer_Connection credentials for the resolved account.
3. THE AI_Usage_Service SHALL normalize Tier_2_Resolution results into Usage_Detail_Item records before returning or caching them.
4. IF the Customer_Connection credentials are unavailable for Tier_2_Resolution, THEN THE AI_Usage_Service SHALL return a structured error indicating the connection must be configured in the Configure tab.

### Requirement 7: IAM Permissions

**User Story:** As a platform operator, I want the execution roles to hold exactly the permissions needed for vendor-agnostic AI usage, so that resolution succeeds without over-provisioning.

#### Acceptance Criteria

1. THE member-handler execution role SHALL grant read and write access to the Cost_Rollup_Item and Usage_Detail_Item keys in the Cost_Cache_Table.
2. THE member-handler execution role SHALL grant read access to the Tips_Table for Tier_2_Resolution.
3. WHERE Tier_3_Resolution decrypts Customer_Connection credentials, THE execution role SHALL grant KMS decrypt permission scoped to the credential encryption key.
4. THE IAM policy changes SHALL be expressed in the infrastructure deployment definitions under `infrastructure/` and `.github/workflows/deploy.yml`.

### Requirement 8: Intent Gate in handle_ai_query

**User Story:** As a SlashMyBill user, I want my AI cost questions routed to the vendor-agnostic path automatically, so that I do not need to phrase questions per vendor.

#### Acceptance Criteria

1. WHEN `handle_ai_query` receives a question classified as an AI cost or usage question, THE Intent_Gate SHALL route the request to the vendor-agnostic resolution path.
2. THE Intent_Gate SHALL replace the OpenAI-specific short-circuit previously handled by `_answer_openai_query` with the vendor-agnostic path.
3. WHERE the question is not an AI cost or usage question, THE Intent_Gate SHALL route the request to `_invoke_bedrock_agent` unchanged.
4. WHEN the resolved account's `vendorType` is `ai_vendor`, THE Intent_Gate SHALL invoke the vendor-agnostic resolution path for a single account.

### Requirement 9: Backfill and Migration of OPENAI_DAILY Data

**User Story:** As a platform operator, I want existing OpenAI cache data migrated to the neutral schema, so that historical answers remain available after cutover.

#### Acceptance Criteria

1. THE Migration_Job SHALL read existing Cost_Cache_Table items with sort key prefix `OPENAI_DAILY#` and write equivalent Cost_Rollup_Item records with sort key `COST#{date}`.
2. WHERE a migrated `OPENAI_DAILY#` item contains per-actor or per-service detail, THE Migration_Job SHALL write corresponding Usage_Detail_Item records with sort key `USAGE#{date}#{actor}#{service}`.
3. THE Migration_Job SHALL preserve the original cost amount, currency, and date for each migrated item.
4. WHEN the Migration_Job re-runs over previously migrated data, THE Migration_Job SHALL overwrite by primary key so that re-execution does not create duplicate records.
5. IF the Migration_Job fails to write one or more items, THEN THE Migration_Job SHALL exit with a non-zero status and log the count of items that failed to write.
6. THE AI_Usage_Service SHALL read AI cost and usage data using only the vendor-neutral keys after the cutover completes.
7. THE AI_Dashboard_Data_Path SHALL read AI cost and usage data using only the vendor-neutral Cost_Rollup_Item and Usage_Detail_Item keys after the cutover completes.
8. WHEN the Migration_Job converts `OPENAI_DAILY#` items, THE Migration_Job SHALL produce Cost_Rollup_Item and Usage_Detail_Item records sufficient to render the AI_Dashboard_Widgets without loss of pre-cutover dashboard data.

### Requirement 10: Deployment and Agent Preparation

**User Story:** As a platform operator, I want the new tool and instructions deployed to the Bedrock Agent, so that the chat can use getAIUsage.

#### Acceptance Criteria

1. WHEN the deployment script runs, THE deployment process SHALL update the Knowledge_Action_Group with the getAIUsage operation from `agent-action/schemas/knowledge.json`.
2. WHEN the Knowledge_Action_Group update completes, THE deployment process SHALL update the agent instructions from `agent-action/agent-instructions.txt`.
3. WHEN the action group and instructions are updated, THE deployment process SHALL call PrepareAgent to create a new prepared agent version.
4. IF a deployment step fails, THEN THE deployment process SHALL log the failing step and exit with a non-zero status.

### Requirement 11: Resolution Guardrails

**User Story:** As a platform operator, I want strict guardrails on AI cost resolution, so that answers are cache-first, customer-scoped, and single-account.

#### Acceptance Criteria

1. THE AI_Usage_Service SHALL attempt Tier_1_Resolution before invoking any live vendor API call.
2. THE AI_Usage_Service SHALL retrieve AI cost and usage data exclusively from the Customer_Connection and SHALL NOT read platform-owned AI spend.
3. THE AI_Usage_Service SHALL resolve getAIUsage for exactly one account per invocation.
4. THE AI_Dashboard_Data_Path SHALL retrieve AI cost and usage data exclusively from the Customer_Connection and SHALL NOT read platform-owned AI spend.
5. THE AI_Dashboard_Data_Path SHALL resolve AI cost and usage data for exactly one account per request.

### Requirement 12: Graceful Degradation

**User Story:** As a SlashMyBill user, I want clear handling when data is bounded or unavailable, so that the chat stays responsive and honest about limits.

#### Acceptance Criteria

1. IF Tier_3_Resolution requires an Admin_Key that the account does not have, THEN THE AI_Usage_Service SHALL return a structured message indicating that account-wide usage requires an admin-level key.
2. WHEN the AI_Usage_Service builds a response, THE AI_Usage_Service SHALL cap the response payload at the configured maximum size by truncating to the highest-cost entries and indicating that additional entries are not shown.
3. IF Tier_3_Resolution does not complete within the configured latency bound, THEN THE AI_Usage_Service SHALL return the best available Tier_1_Resolution or Tier_2_Resolution result and indicate that live data was not fully retrieved.
4. WHERE Tier_3_Resolution is dispatched asynchronously, THE AI_Usage_Service SHALL return a bounded response without blocking on the live vendor API beyond the configured latency bound.

### Requirement 13: AI Dashboard Cache Consumers

**User Story:** As a SlashMyBill member viewing the AI dashboard, I want the AI cost summary, per-model breakdown, and per-user token consumption graph to read from the vendor-neutral cache, so that the dashboard keeps working after the cache cuts over from `OPENAI_DAILY#` to the neutral schema.

#### Acceptance Criteria

1. WHEN the AI_Dashboard_Data_Path reads AI cost data from the Cost_Cache_Table, THE AI_Dashboard_Data_Path SHALL read Cost_Rollup_Item records with sort key prefix `COST#` rather than `OPENAI_DAILY#` records.
2. WHEN the AI_Dashboard_Data_Path reads per-actor or per-service AI usage data from the Cost_Cache_Table, THE AI_Dashboard_Data_Path SHALL read Usage_Detail_Item records with sort key prefix `USAGE#` rather than `OPENAI_DAILY#` records.
3. WHEN `_refresh_cost_cache_for_account` writes AI cost or usage data to the Cost_Cache_Table, THE AI_Dashboard_Data_Path SHALL write Cost_Rollup_Item and Usage_Detail_Item records using the vendor-neutral schema rather than `OPENAI_DAILY#` records.
4. WHEN the AI_Dashboard_Data_Path resolves the vendor connector for an account, THE AI_Dashboard_Data_Path SHALL select the connector using the account's stored `cloudProvider` value through the Provider_Router rather than vendor-specific conditional logic.
5. WHEN the per-user token consumption graph endpoint reads AI usage data, THE AI_Dashboard_Data_Path SHALL read Usage_Detail_Item records keyed by actor and service from the Cost_Cache_Table.
6. WHERE the AI_Dashboard_Data_Path requires AI cost or usage data that is missing or stale in the Cost_Cache_Table, THE AI_Dashboard_Data_Path SHALL obtain fresh data using the same three-tier resolution flow applied by the AI_Usage_Service and SHALL write the retrieved data back to the Cost_Cache_Table using the vendor-neutral schema.
7. THE AI_Dashboard_Widgets rendered by `members/members.js` SHALL display AI cost summary, per-model cost breakdown, and per-user token consumption sourced from the vendor-neutral Cost_Rollup_Item and Usage_Detail_Item records.
