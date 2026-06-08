# Requirements Document

## Introduction

The AI Chat Optimization feature addresses three critical gaps in the SlashMyBill AI chat query sequence (POST /members/ai-query). Currently, the AI chat only gathers data from AWS APIs regardless of the connected account's cloud provider, queries tips from DynamoDB on every request without caching or provider filtering, and executes sequential API calls resulting in 8–18 second response times. This feature introduces multi-cloud provider routing for Azure and GCP accounts, tips table integration improvements with session-level caching and provider filtering, and performance optimizations including cache-first cost lookups, parallel API calls, and intent-based data routing to achieve under 5 seconds perceived latency.

## Glossary

- **AI_Chat_Handler**: The `_invoke_direct_model` and `_invoke_multi_account` functions in `member-handler/lambda_function.py` that orchestrate the AI query flow (tips lookup, data gathering, Bedrock invocation)
- **Cloud_Provider_Router**: The routing logic that determines which data-gathering connector to invoke based on an account's `cloudProvider` field stored in the MemberPortal-Accounts DynamoDB table
- **AWS_Connector**: The existing data-gathering path using STS AssumeRole and direct boto3 calls to Cost Explorer, EC2, CloudWatch, RDS, and S3 APIs
- **Azure_Connector**: The existing `AzureConnector` class in `member-handler/connectors/azure_connector.py` that authenticates via OAuth2 Service Principal and queries Azure Cost Management API
- **GCP_Connector**: The connector for Google Cloud Platform that authenticates via service account and queries GCP Cloud Billing API for cost data
- **Tips_Cache**: An in-memory cache using Lambda execution context global variables that stores tips query results per cloud provider with a 5-minute TTL
- **Tips_Table**: The `ViewMyBill-CostOptimizationTips` DynamoDB table containing cost optimization tips indexed by service name
- **Intent_Classifier**: A lightweight function that classifies the user's question into a target category (EC2, RDS, S3, cost-general, etc.) before data gathering to skip irrelevant API calls
- **Cost_Cache_Table**: The existing `Cost_Cache_Table` DynamoDB table used by the dashboard-data endpoint to store daily cost data with 90-day TTL
- **Data_Gatherer**: The `_gather_account_data` function that collects cost, resource, and metric data from a single account
- **Thread_Pool**: A `concurrent.futures.ThreadPoolExecutor` used to run multiple API calls concurrently within and across accounts
- **Bedrock_Model**: The Amazon Bedrock foundation model (Claude) used to generate AI analysis responses
- **API_Gateway_Timeout**: The 29-second hard timeout imposed by AWS API Gateway on synchronous Lambda invocations
- **Lambda_Guard**: A 27-second soft timeout enforced in the Lambda function to return a graceful response before the API_Gateway_Timeout fires
- **Service_Tip_Mapping**: The `keyword_to_service` dictionary in `_search_tips` that maps question keywords to DynamoDB service partition keys for tips lookup

## Requirements

### Requirement 1: Multi-Cloud Provider Detection and Routing

**User Story:** As a member with Azure or GCP accounts connected, I want the AI chat to gather cost data from the correct cloud provider APIs, so that I receive accurate cost analysis regardless of which cloud account I select.

#### Acceptance Criteria

1. WHEN the AI_Chat_Handler receives a query for an account, THE Cloud_Provider_Router SHALL read the `cloudProvider` field from the MemberPortal-Accounts table for each requested account ID
2. WHEN the `cloudProvider` field value is "aws", THE Cloud_Provider_Router SHALL route data gathering to the AWS_Connector using STS AssumeRole
3. WHEN the `cloudProvider` field value is "azure", THE Cloud_Provider_Router SHALL route data gathering to the Azure_Connector using the stored Service Principal credentials
4. WHEN the `cloudProvider` field value is "gcp", THE Cloud_Provider_Router SHALL route data gathering to the GCP_Connector using the stored service account credentials
5. IF the `cloudProvider` field is missing or empty, THEN THE Cloud_Provider_Router SHALL default to "aws" routing to maintain backward compatibility
6. THE Cloud_Provider_Router SHALL support mixed-provider queries in multi-account mode by routing each account to its respective connector independently

### Requirement 2: Azure Cost Data Gathering for AI Chat

**User Story:** As a member with an Azure subscription connected, I want the AI chat to retrieve my Azure cost breakdown by service, so that I can ask cost optimization questions about my Azure spend.

#### Acceptance Criteria

1. WHEN the Cloud_Provider_Router routes to the Azure_Connector, THE Azure_Connector SHALL authenticate using the stored tenant_id, client_id, and client_secret via OAuth2 client credentials flow
2. WHEN authenticated, THE Azure_Connector SHALL query Azure Cost Management API for cost data grouped by ServiceName for the last 30 days
3. WHEN authenticated, THE Azure_Connector SHALL query Azure Cost Management API for daily cost trend data for the last 7 days
4. THE Azure_Connector SHALL return cost data in the same normalized structure as the AWS_Connector (cost_by_service list with service name and cost_usd, daily_cost_trend list with date and cost_usd)
5. THE Azure_Connector SHALL limit data gathering to cost breakdowns only and SHALL NOT attempt to retrieve resource-level data (no Azure VM inventory, no Azure Monitor metrics)
6. IF Azure authentication fails, THEN THE Azure_Connector SHALL return an error message indicating credential issues without interrupting other accounts in a multi-account query

### Requirement 3: GCP Cost Data Gathering for AI Chat

**User Story:** As a member with a GCP project connected, I want the AI chat to retrieve my GCP cost breakdown by service, so that I can ask cost optimization questions about my Google Cloud spend.

#### Acceptance Criteria

1. WHEN the Cloud_Provider_Router routes to the GCP_Connector, THE GCP_Connector SHALL authenticate using the stored service account JSON key
2. WHEN authenticated, THE GCP_Connector SHALL query GCP Cloud Billing API for cost data grouped by service for the last 30 days
3. WHEN authenticated, THE GCP_Connector SHALL query GCP Cloud Billing API for daily cost trend data for the last 7 days
4. THE GCP_Connector SHALL return cost data in the same normalized structure as the AWS_Connector (cost_by_service list with service name and cost_usd, daily_cost_trend list with date and cost_usd)
5. THE GCP_Connector SHALL limit data gathering to cost breakdowns only and SHALL NOT attempt to retrieve resource-level data (no Compute Engine inventory, no Cloud Monitoring metrics)
6. IF GCP authentication fails, THEN THE GCP_Connector SHALL return an error message indicating credential issues without interrupting other accounts in a multi-account query

### Requirement 4: Tips Cache with Session-Level TTL

**User Story:** As a platform operator, I want tips queries to be cached in memory for 5 minutes per cloud provider, so that repeated AI chat questions within a session do not trigger unnecessary DynamoDB reads.

#### Acceptance Criteria

1. THE Tips_Cache SHALL store tips query results in a Lambda execution context global variable keyed by cloud provider ("aws", "azure", "gcp")
2. WHEN a tips query is requested, THE Tips_Cache SHALL return cached results if the cache entry exists and is less than 5 minutes old
3. WHEN the cache entry is older than 5 minutes, THE Tips_Cache SHALL discard the stale entry and perform a fresh DynamoDB query
4. WHEN the cache entry does not exist for the requested cloud provider, THE Tips_Cache SHALL perform a DynamoDB query and store the results with a timestamp
5. THE Tips_Cache SHALL NOT introduce any external dependencies (no Redis, no ElastiCache) and SHALL rely solely on Lambda execution context persistence

### Requirement 5: Tips Filtering by Cloud Provider

**User Story:** As a member asking about Azure costs, I want to see only Azure-relevant optimization tips, so that I am not confused by AWS-specific recommendations.

#### Acceptance Criteria

1. WHEN searching tips for an AWS account, THE AI_Chat_Handler SHALL query tips with service keys from the existing AWS keyword_to_service mapping
2. WHEN searching tips for an Azure account, THE AI_Chat_Handler SHALL query tips with Azure service name mappings (Virtual Machines, App Service, Azure SQL, Storage, Azure Functions, Cosmos DB, AKS, Azure CDN, Azure DNS, Azure Monitor, VNet, Azure Key Vault)
3. WHEN searching tips for a GCP account, THE AI_Chat_Handler SHALL query tips with GCP service name mappings (Compute Engine, Cloud Storage, Cloud SQL, Cloud Functions, BigQuery, GKE, Cloud CDN, Cloud DNS, Cloud Monitoring, VPC, Cloud KMS)
4. THE AI_Chat_Handler SHALL include tips tagged with service "General" for all cloud providers regardless of the selected account's provider
5. WHEN a multi-account query spans multiple cloud providers, THE AI_Chat_Handler SHALL merge tips from all relevant providers while deduplicating by tipId

### Requirement 6: Strengthened Tip Citation in AI Responses

**User Story:** As a member, I want the AI to explicitly reference relevant tips in its response, so that I can see curated optimization advice alongside the AI analysis.

#### Acceptance Criteria

1. WHEN tips are found for the current query, THE AI_Chat_Handler SHALL include a prompt instruction requiring the Bedrock_Model to cite at least one relevant tip in its response
2. THE prompt instruction SHALL direct the Bedrock_Model to format tip citations using a "💡 Tip:" prefix followed by the tip title and a brief explanation
3. WHEN no tips match the question, THE AI_Chat_Handler SHALL omit the citation instruction from the prompt
4. THE AI_Chat_Handler SHALL pass tip titles, descriptions, and confidence levels to the Bedrock_Model prompt context

### Requirement 7: Cache-First Cost Data Retrieval

**User Story:** As a member, I want cost data to load from cache when available, so that my AI chat queries respond faster without waiting for live Cost Explorer API calls.

#### Acceptance Criteria

1. WHEN gathering cost data for an AWS account, THE Data_Gatherer SHALL first query the Cost_Cache_Table for cached daily cost items for the requested date range
2. WHEN the Cost_Cache_Table returns valid data covering the requested date range, THE Data_Gatherer SHALL use the cached data and skip the live Cost Explorer API call
3. WHEN the Cost_Cache_Table returns no data or incomplete date coverage, THE Data_Gatherer SHALL fall back to the live Cost Explorer API
4. IF both the Cost_Cache_Table read and the live Cost Explorer API fail, THEN THE Data_Gatherer SHALL return a partial response with available data and an error indicator rather than failing the entire query
5. THE cache-first pattern SHALL apply only to AWS accounts (Azure and GCP connectors manage their own caching independently)

### Requirement 8: Parallel API Calls Within Account

**User Story:** As a member, I want my AI chat queries to complete faster by gathering EC2, CloudWatch, RDS, and S3 data concurrently, so that I do not wait for sequential API calls.

#### Acceptance Criteria

1. WHEN the Data_Gatherer collects data for a single AWS account, THE Thread_Pool SHALL execute independent API calls (EC2 describe-instances, CloudWatch get-metric-data, RDS describe-instances, S3 list-buckets) concurrently
2. THE Thread_Pool SHALL use a maximum of 5 concurrent workers per account to avoid AWS API throttling
3. IF any individual API call within the Thread_Pool fails, THEN THE Data_Gatherer SHALL log the failure, skip the failed data source, and continue with results from successful calls
4. THE Thread_Pool SHALL enforce a per-call timeout of 10 seconds to prevent a single slow API from blocking the entire query
5. WHEN gathering data from multiple accounts, THE Data_Gatherer SHALL process accounts concurrently with a maximum of 3 account-level workers

### Requirement 9: Intent-Based Data Routing

**User Story:** As a member asking about a specific service, I want the system to only fetch data relevant to my question, so that the response is faster and more focused.

#### Acceptance Criteria

1. WHEN a question is received, THE Intent_Classifier SHALL classify it into one or more target categories: ec2, rds, s3, lambda, cost-general, network, storage, or compute
2. WHEN the Intent_Classifier determines the question targets "ec2" only, THE Data_Gatherer SHALL fetch EC2 instance data and cost data but SHALL skip RDS, S3, NAT Gateway, and EBS data gathering
3. WHEN the Intent_Classifier determines the question targets "cost-general", THE Data_Gatherer SHALL fetch cost breakdown and daily trend data but SHALL skip all resource-level API calls
4. WHEN the Intent_Classifier cannot confidently classify the question (ambiguous or multi-service), THE Data_Gatherer SHALL fetch all available data sources as in current behavior
5. THE Intent_Classifier SHALL execute in under 50 milliseconds using keyword matching and pattern rules without requiring an additional LLM call

### Requirement 10: Lambda Guard Timeout Protection

**User Story:** As a platform operator, I want the AI chat to return a graceful partial response before the API Gateway timeout, so that users never see a 503 error.

#### Acceptance Criteria

1. THE AI_Chat_Handler SHALL enforce a 27-second soft timeout using `concurrent.futures` to stay within the 29-second API_Gateway_Timeout
2. WHEN the 27-second timeout is reached during data gathering, THE AI_Chat_Handler SHALL return whatever data has been collected so far with a message indicating the response is partial
3. WHEN the 27-second timeout is reached during Bedrock model invocation, THE AI_Chat_Handler SHALL return collected data with a generic message indicating the AI analysis timed out
4. THE AI_Chat_Handler SHALL NOT introduce any behavior that could exceed the existing 27-second Lambda_Guard timeout

### Requirement 11: Backward Compatibility with Existing AWS Flow

**User Story:** As a member with AWS accounts, I want the existing AI chat behavior to remain unchanged, so that the multi-cloud and performance optimizations do not introduce regressions.

#### Acceptance Criteria

1. THE AI_Chat_Handler SHALL produce identical response structure (answer, interactionId, commands, results, tipFound, agentUsed, chartData, topServices) regardless of which cloud provider was queried
2. WHEN querying AWS accounts, THE Data_Gatherer SHALL continue to support all existing data sources (Cost Explorer, EC2, CloudWatch, RDS, S3, EBS, NAT Gateway) with no behavioral changes
3. THE AI_Chat_Handler SHALL continue to support existing request parameters (question, tagKey, tagValue, accountId, accountIds) without breaking changes
4. THE AI_Chat_Handler SHALL continue to validate account IDs using the existing multi-cloud regex pattern (AWS 12-digit, Azure UUID, GCP project ID)
5. WHEN parallel execution is enabled, THE Data_Gatherer SHALL produce the same data output as the current sequential implementation for any given input

### Requirement 12: Partial Failure Handling in Multi-Cloud Queries

**User Story:** As a member with accounts across multiple providers, I want the system to continue processing other accounts when one account fails, so that a single provider outage does not block my entire query.

#### Acceptance Criteria

1. WHEN one account in a multi-account query fails authentication or data gathering, THE AI_Chat_Handler SHALL skip the failed account and continue processing remaining accounts
2. THE AI_Chat_Handler SHALL include the failed account's ID and error reason in the response metadata so the member can see which accounts were skipped
3. WHEN all accounts in a multi-account query fail, THE AI_Chat_Handler SHALL return an error response indicating no account data could be retrieved
4. THE AI_Chat_Handler SHALL log each account failure with the account ID, cloud provider, and error details for operational monitoring
