# Requirements Document

## Introduction

SlashMyBill currently provides cost visibility and optimization insights for Cloud Service Providers (AWS, Azure, GCP). This feature extends the platform to support a new connection category — AI Vendors — starting with OpenAI (ChatGPT). Users will be able to connect their OpenAI account via API key, and the platform will retrieve usage and billing data to present cost analytics, spend trends, and optimization recommendations for AI/LLM spending.

## Glossary

- **Connection_Wizard**: The multi-step UI flow in the Configure tab that guides users through adding a new provider connection (API key input, validation, and storage)
- **OpenAI_Connector**: The backend connector module that implements the ProviderConnector interface for OpenAI, handling authentication, connection testing, and usage data retrieval
- **AI_Vendor**: A new provider category distinct from Cloud Service Providers, representing AI/LLM service providers such as OpenAI, Anthropic, and Cohere
- **API_Key**: An OpenAI Organization-level or Project-level secret key used to authenticate requests to the OpenAI Usage API
- **Usage_Dashboard**: The Observe tab view that displays token usage, cost breakdowns, spend trends, and optimization insights for a connected OpenAI account
- **KMS_Encryption**: AWS Key Management Service envelope encryption used to securely store sensitive credentials at rest in DynamoDB
- **OpenAI_Usage_API**: The OpenAI platform API endpoint that provides billing, token consumption, and cost data for an organization or project
- **Provider_Registry**: The connector registration system (`member-handler/connectors/`) that maps provider names to their connector implementations

## Requirements

### Requirement 1: AI Vendor Category in Provider Registry

**User Story:** As a platform developer, I want the provider registry to support an AI Vendor category alongside Cloud Service Providers, so that OpenAI and future AI vendors can be connected using the same extensible pattern.

#### Acceptance Criteria

1. THE Provider_Registry SHALL associate each registered connector with a `vendor_type` attribute whose value is one of `cloud_provider` or `ai_vendor`, stored as a metadata entry alongside the connector class in the `_CONNECTORS` registry dictionary
2. WHEN a new OpenAI connection is created, THE MemberPortal-Accounts DynamoDB table SHALL store a `vendorType` field with value `ai_vendor` and a `cloudProvider` field with value `openai`
3. THE OpenAI_Connector SHALL implement the ProviderConnector interface methods: `authenticate`, `test_connection`, and `get_cost_data`, and SHALL be registered under the provider name `openai` with `vendor_type` set to `ai_vendor`
4. WHEN the Provider_Registry loads connectors, THE Provider_Registry SHALL include the OpenAI_Connector in the list of available providers and SHALL classify existing connectors (aws, azure, gcp) with `vendor_type` set to `cloud_provider`
5. WHEN a caller requests the list of available providers filtered by `vendor_type`, THE Provider_Registry SHALL return only connectors matching the specified `vendor_type` value
6. IF a connector is registered without a `vendor_type` attribute, THEN THE Provider_Registry SHALL default its `vendor_type` to `cloud_provider`

### Requirement 2: OpenAI Connection Wizard

**User Story:** As a SlashMyBill user, I want to add my OpenAI account through a connection wizard in the Configure tab, so that the platform can access my AI usage and cost data.

#### Acceptance Criteria

1. WHEN the user selects "Add AI Vendor" in the Configure tab, THE Connection_Wizard SHALL present OpenAI as an available vendor option
2. WHEN the user selects OpenAI, THE Connection_Wizard SHALL display an input form requesting the API Key and an optional connection name limited to 64 characters
3. THE Connection_Wizard SHALL accept API keys with prefix `sk-org-` (Organization-level) or prefix `sk-proj-` (Project-level) that are between 40 and 200 characters in total length as valid key formats
4. WHEN the user submits the API key, THE Connection_Wizard SHALL display a loading indicator while the validation request is in progress, up to a maximum of 15 seconds
5. IF the API key field is empty or does not match a valid format (prefix `sk-org-` or `sk-proj-` with total length between 40 and 200 characters), THEN THE Connection_Wizard SHALL display an inline validation error indicating the expected format before submitting to the backend
6. WHEN the backend validation confirms the API key is valid, THE Connection_Wizard SHALL save the connection and display a success confirmation indicating the OpenAI account has been added
7. IF the backend validation returns an authentication failure for the submitted API key, THEN THE Connection_Wizard SHALL display an error message indicating the key was rejected by OpenAI and allow the user to correct and resubmit
8. IF the validation request exceeds 15 seconds or a network error occurs, THEN THE Connection_Wizard SHALL dismiss the loading indicator, display an error message indicating a connectivity issue, and allow the user to retry the submission

### Requirement 3: API Key Validation

**User Story:** As a SlashMyBill user, I want the platform to verify my OpenAI API key works before saving the connection, so that I know my account is properly linked.

#### Acceptance Criteria

1. WHEN an API key is submitted for validation, THE OpenAI_Connector SHALL verify the key matches the expected format (starts with "sk-" prefix and is between 40 and 200 characters) before calling the OpenAI API to confirm the key grants access to usage data
2. WHEN the API key is valid and has usage data access, THE OpenAI_Connector SHALL return a success result with the organization name and the list of model IDs the key is authorized to use
3. IF the API key is invalid or revoked, THEN THE OpenAI_Connector SHALL return a failure result with an error message indicating the key is not recognized or has been revoked, without persisting the key
4. IF the API key lacks required permissions for usage data access, THEN THE OpenAI_Connector SHALL return a failure result identifying that billing or usage read permissions are not granted by the key
5. IF the OpenAI API does not respond within 30 seconds, THEN THE OpenAI_Connector SHALL return a timeout error indicating the service is temporarily unavailable and the user should retry
6. IF the API key fails format validation (missing "sk-" prefix or outside 40–200 character length), THEN THE OpenAI_Connector SHALL return a failure result indicating the key format is invalid, without making an external API call
7. IF the OpenAI API returns a server error or rate-limit response during validation, THEN THE OpenAI_Connector SHALL return a failure result indicating a temporary service issue and the user should retry after 60 seconds

### Requirement 4: Secure API Key Storage

**User Story:** As a SlashMyBill user, I want my OpenAI API key stored securely, so that it cannot be exposed or accessed by unauthorized parties.

#### Acceptance Criteria

1. WHEN a valid API key is confirmed, THE OpenAI_Connector SHALL encrypt the key using KMS_Encryption with an encryption context containing the member's email and accountId before persisting it to DynamoDB
2. THE MemberPortal-Accounts table SHALL store the encrypted API key in a `credentials.encryptedApiKey` field, and SHALL NOT store the plaintext key in any field or log output
3. WHEN the platform needs to use the stored API key, THE OpenAI_Connector SHALL decrypt the key using KMS_Encryption with the same encryption context (member email and accountId) immediately before use and SHALL NOT cache the decrypted value in memory beyond the request scope
4. IF KMS decryption fails, THEN THE OpenAI_Connector SHALL return an error indicating credentials are inaccessible and SHALL NOT expose the ciphertext or error internals to the user
5. IF KMS encryption fails during API key storage, THEN THE OpenAI_Connector SHALL NOT persist the record to DynamoDB, SHALL return an error indicating the key could not be saved, and SHALL NOT store the plaintext key
6. WHEN the user submits a new API key for an existing OpenAI connection, THE OpenAI_Connector SHALL encrypt the new key and overwrite the previous `credentials.encryptedApiKey` value in the same DynamoDB record

### Requirement 5: Connection Status Management

**User Story:** As a SlashMyBill user, I want to see the current status of my OpenAI connection, so that I know whether data collection is working.

#### Acceptance Criteria

1. WHEN a connection test succeeds, THE Connection_Wizard SHALL update the account record `connectionStatus` to `connected` and record `lastTestedAt` as an ISO 8601 timestamp of when the test completed
2. WHEN a connection test fails, THE Connection_Wizard SHALL update the account record `connectionStatus` to `failed`, record `lastTestedAt` as an ISO 8601 timestamp of when the test completed, and display the failure reason (maximum 200 characters) to the user within the Configure tab
3. WHEN the user views the Configure tab, THE Connection_Wizard SHALL display each OpenAI connection with its connection name, current status (`connected`, `failed`, or `pending`), and the `lastTestedAt` timestamp if a test has been performed
4. WHEN the user clicks "Test Connection" on an existing OpenAI account, THE Connection_Wizard SHALL display a loading indicator, re-validate the stored API key, and update the `connectionStatus` to `connected` if validation succeeds or `failed` if validation fails
5. WHILE a connection test is in progress for an account, THE Connection_Wizard SHALL disable the "Test Connection" button for that account to prevent concurrent test requests

### Requirement 6: Token Usage Dashboard

**User Story:** As a SlashMyBill user, I want to see my OpenAI token usage over time, so that I can understand my AI consumption patterns.

#### Acceptance Criteria

1. WHEN the user navigates to the Observe tab for a connected OpenAI account, THE Usage_Dashboard SHALL display a time-series chart of daily token consumption split into input tokens and output tokens, defaulting to the 30-day date range
2. THE Usage_Dashboard SHALL allow the user to select a date range of 7 days, 30 days, or 90 days for the token usage chart, and SHALL visually indicate the currently selected range
3. WHEN usage data is retrieved, THE OpenAI_Connector SHALL call the OpenAI_Usage_API with the selected date range and return per-day token counts within 10 seconds
4. IF the OpenAI_Usage_API returns no data for the selected period, THEN THE Usage_Dashboard SHALL display a message indicating no usage was recorded in that timeframe
5. IF the OpenAI_Usage_API returns an error or does not respond within 10 seconds, THEN THE Usage_Dashboard SHALL display an error message indicating the data could not be loaded and offer a retry action
6. WHILE the OpenAI_Connector is retrieving usage data, THE Usage_Dashboard SHALL display a loading indicator in place of the chart

### Requirement 7: Cost by Model Breakdown

**User Story:** As a SlashMyBill user, I want to see my costs broken down by OpenAI model, so that I can identify which models drive the most spend.

#### Acceptance Criteria

1. THE Usage_Dashboard SHALL display a breakdown of cost grouped by model name (e.g., gpt-4, gpt-4o, gpt-4o-mini, gpt-3.5-turbo) for the currently selected billing period, showing up to 20 models
2. WHEN cost data is retrieved, THE OpenAI_Connector SHALL aggregate costs per model from the OpenAI_Usage_API response and return a list of model entries each containing the model name, total cost, and percentage of total spend
3. THE Usage_Dashboard SHALL display the cost-by-model breakdown as a bar chart sorted by cost descending
4. THE Usage_Dashboard SHALL show the dollar amount formatted to 2 decimal places and the percentage of total spend formatted to 1 decimal place for each model
5. IF the OpenAI_Usage_API returns an error or is unreachable, THEN THE Usage_Dashboard SHALL display an error message indicating the cost-by-model data is temporarily unavailable while preserving any other dashboard content
6. IF no cost data exists for any model in the selected billing period, THEN THE Usage_Dashboard SHALL display an empty state message indicating no model usage was recorded for the period

### Requirement 8: Spend Trends

**User Story:** As a SlashMyBill user, I want to see daily, weekly, and monthly spend trends for my OpenAI usage, so that I can track cost trajectory and detect anomalies.

#### Acceptance Criteria

1. THE Usage_Dashboard SHALL display a line chart showing daily spend for the selected date range, defaulting to the last 30 days, with a maximum selectable range of 90 days
2. THE Usage_Dashboard SHALL provide toggle options to view spend aggregated at daily, weekly, or monthly granularity
3. WHEN the user switches granularity, IF the underlying data for the selected date range is already loaded, THEN THE Usage_Dashboard SHALL re-render the chart within 1 second using the corresponding time buckets (daily = 1-day intervals, weekly = 7-day intervals starting Monday, monthly = calendar month intervals)
4. THE Usage_Dashboard SHALL display the total spend amount formatted to two decimal places with currency symbol, and the percentage change compared to the equivalent immediately preceding period (e.g., selected 30 days compared to the prior 30 days)
5. IF no spend data exists for the selected date range, THEN THE Usage_Dashboard SHALL display an empty state message indicating no usage data is available for the selected period
6. IF spend data fails to load, THEN THE Usage_Dashboard SHALL display an error message indicating data is temporarily unavailable and provide a retry option

### Requirement 9: Cost per API Key and Project

**User Story:** As a SlashMyBill user, I want to see cost breakdowns by API key or project, so that I can attribute AI spending to specific teams or applications.

#### Acceptance Criteria

1. WHEN the OpenAI_Usage_API provides per-project or per-key usage data, THE Usage_Dashboard SHALL display a table of costs grouped by project name or API key identifier for the currently selected date range (7, 30, or 90 days)
2. THE Usage_Dashboard SHALL sort the project/key breakdown by cost descending and display both absolute cost (to 2 decimal places) and percentage of total (to 1 decimal place) for each entry
3. IF the connected API key does not have access to project-level breakdowns, THEN THE Usage_Dashboard SHALL display only the aggregate usage with a note indicating that project-level detail requires an Organization-level key
4. IF the OpenAI_Usage_API request for per-project data fails due to a network or server error, THEN THE Usage_Dashboard SHALL display an error message indicating the breakdown could not be loaded and SHALL offer a retry action
5. THE Usage_Dashboard SHALL display a maximum of 50 project/key entries in the breakdown table, and IF more than 50 entries exist, THEN THE Usage_Dashboard SHALL display the top 50 by cost with an indication that additional entries are not shown

### Requirement 10: Rate Limit Utilization

**User Story:** As a SlashMyBill user, I want to see how close I am to my OpenAI rate limits, so that I can plan capacity and avoid throttling.

#### Acceptance Criteria

1. WHEN rate limit data is available from the OpenAI API, THE Usage_Dashboard SHALL display current rate limit utilization as a percentage of the allowed requests-per-minute (RPM) and tokens-per-minute (TPM), where "current" reflects data no older than the most recent dashboard data load or manual refresh
2. IF the OpenAI API provides rate limit data broken down by model tier, THEN THE Usage_Dashboard SHALL display rate limit utilization separately for each model tier
3. IF rate limit utilization exceeds 80% for any model, THEN THE Usage_Dashboard SHALL display a warning indicator next to that model
4. IF rate limit data is not available from the OpenAI API for the connected account, THEN THE Usage_Dashboard SHALL display a message indicating that rate limit information is unavailable for this account's key type

### Requirement 11: Optimization Recommendations

**User Story:** As a SlashMyBill user, I want to receive actionable cost optimization tips for my OpenAI usage, so that I can reduce spend without losing capability.

#### Acceptance Criteria

1. WHEN the Usage_Dashboard renders, THE Usage_Dashboard SHALL display between 0 and 10 optimization recommendations derived from the retrieved usage patterns, ordered by estimated monthly savings descending
2. IF more than 50% of a user's token spend is on GPT-4 and the average output length for those requests is 500 tokens or fewer, THEN THE Usage_Dashboard SHALL recommend switching to a lower-cost model and display the estimated monthly savings as a dollar amount rounded to two decimal places
3. IF the ratio of input tokens to output tokens exceeds 4:1 across the billing period, THEN THE Usage_Dashboard SHALL recommend prompt optimization techniques and display the estimated potential savings as a dollar amount rounded to two decimal places
4. THE Usage_Dashboard SHALL present each recommendation with a title (maximum 80 characters), description (maximum 300 characters), estimated monthly savings in dollars, and a difficulty rating where easy requires configuration change only, medium requires prompt rewriting or minor code changes, and hard requires architectural changes
5. IF no optimization recommendations apply to the user's usage patterns, THEN THE Usage_Dashboard SHALL display an empty state message indicating that no recommendations are available at this time

### Requirement 12: Initial Upload of OpenAI Optimization Tips

**User Story:** As a platform operator, I want to seed the knowledge base with OpenAI-specific cost optimization tips, so that users receive relevant AI spending recommendations from day one.

#### Acceptance Criteria

1. THE platform SHALL include an initial set of at least 10 OpenAI optimization tips in the ViewMyBill-CostOptimizationTips DynamoDB table with `provider` field set to `openai`, each containing at minimum the fields: service, tipId, category, title, description, estimatedSavings, and difficulty
2. THE initial tips dataset SHALL cover at minimum the following five categories: model selection optimization (choosing cost-effective models for specific tasks), prompt length reduction (minimizing input/output token counts), caching strategies (reusing responses for repeated queries), batch API usage (using asynchronous batch endpoints for non-time-sensitive workloads), and fine-tuning cost tradeoffs (when fine-tuning reduces per-request cost versus training cost)
3. WHEN the AI chat processes a question about an OpenAI account, THE tip_citation module SHALL match and return at least 1 and at most 5 relevant OpenAI tips alongside the response, filtered using an OpenAI-specific keyword-to-service mapping registered in the PROVIDER_MAPPINGS dictionary of the tips_filter module
4. THE initial tips upload SHALL be executable as a one-time seed script that populates the tips table using DynamoDB batch_writer with overwrite-by-primary-keys deduplication, ensuring re-execution does not create duplicate entries
5. IF the tips table is unreachable or the seed script fails to write any items, THEN THE script SHALL exit with a non-zero exit code and log an error message indicating the number of tips that failed to write

### Requirement 13: Nightly Incremental Usage Data Sync

**User Story:** As a SlashMyBill user, I want my OpenAI usage data to be refreshed automatically every night, so that the dashboard reflects up-to-date spending without manual intervention.

#### Acceptance Criteria

1. THE platform SHALL execute a scheduled job daily at 02:00 UTC (via EventBridge rule or CloudWatch scheduled event) that syncs usage data for all OpenAI connections with `connectionStatus` of `connected`
2. WHEN the nightly sync runs for an account that has a `lastSyncedAt` value, THE OpenAI_Connector SHALL retrieve usage data only for the period from `lastSyncedAt` to the current date (incremental fetch) rather than re-fetching the entire history
3. IF the nightly sync runs for an account that has no `lastSyncedAt` value (first sync), THEN THE OpenAI_Connector SHALL retrieve usage data for the previous 90 days as the initial backfill
4. THE nightly sync SHALL store retrieved usage data in the Cost_Cache_Table with a partition key of `{memberEmail}#{accountId}` and a sort key prefix of `OPENAI_DAILY#` followed by the date
5. IF a connection's API key is found to be invalid during the nightly sync, THEN THE sync job SHALL update the connection status to `failed` and skip that account without affecting other accounts
6. IF the nightly sync fails for a specific account due to a transient error (timeout, rate limit), THEN THE sync job SHALL retry up to 3 times with exponential backoff starting at a 2-second base delay before marking the sync as failed for that account
7. THE nightly sync SHALL record the timestamp of the last successful sync per account in the MemberPortal-Accounts table in a `lastSyncedAt` field as an ISO 8601 string
8. THE nightly sync Lambda SHALL complete processing of all accounts within a maximum execution duration of 900 seconds

### Requirement 14: OpenAI Usage Data Retrieval and Normalization

**User Story:** As a platform developer, I want the OpenAI connector to reliably fetch and normalize usage data from the OpenAI Usage API, so that the dashboard can present accurate cost analytics.

#### Acceptance Criteria

1. THE OpenAI_Connector SHALL retrieve usage data from the OpenAI_Usage_API using the stored (decrypted) API key as the Bearer token, with a request timeout of 30 seconds per attempt
2. THE OpenAI_Connector SHALL normalize the raw API response into the standard cost data structure used by the platform (matching the field set and format returned by AWS and Azure connectors), including at minimum: provider identifier, service name, usage quantity, unit cost, total cost, and usage period start/end timestamps
3. IF the OpenAI_Usage_API returns an HTTP 429 (rate limited) response and the response includes a `Retry-After` header, THEN THE OpenAI_Connector SHALL retry the request after the duration specified in the `Retry-After` header, up to 3 attempts
4. IF the OpenAI_Usage_API returns an HTTP 429 (rate limited) response and the response does not include a `Retry-After` header, THEN THE OpenAI_Connector SHALL retry the request using exponential backoff starting at 1 second, up to 3 attempts
5. IF the OpenAI_Connector exhausts all 3 retry attempts without a successful response, THEN THE OpenAI_Connector SHALL update the connection status to `failed` and return an error indicating that the usage API is temporarily unavailable
6. IF the OpenAI_Usage_API returns an HTTP 401 (unauthorized) response, THEN THE OpenAI_Connector SHALL update the connection status to `failed` and return an error indicating the API key may have been revoked
7. IF the OpenAI_Usage_API returns an HTTP error response other than 401 or 429, THEN THE OpenAI_Connector SHALL return an error indicating the failure status code and preserve the connection status as unchanged
8. THE OpenAI_Connector SHALL parse the OpenAI_Usage_API response and THE OpenAI_Connector SHALL format it back into a normalized structure such that re-parsing the formatted output yields an equivalent result (round-trip integrity)
