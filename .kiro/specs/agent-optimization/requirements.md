# Requirements Document

## Introduction

This specification defines the reorganization and optimization of the SlashMyBill AI agent that answers cloud cost optimization questions in the Chat tab. The agent currently lives in `member-handler/lambda_function.py` (the `handle_ai_query` function), uses AWS Bedrock with model `us.amazon.nova-2-lite-v1:0`, and relies on the `intent_classifier.py` module for routing. The goal is to make the agent more reliable, cost-effective, and accurate by applying prompt management best practices: structured context injection, multi-turn session state, token budgeting, deterministic output formatting, externalized prompt templates, and prompt injection defenses.

## Glossary

- **Agent**: The AI-powered query handler in the member-handler Lambda that processes natural language questions about cloud costs
- **Intent_Classifier**: The keyword-based module (`intent_classifier.py`) that classifies user questions into service categories (ec2, rds, s3, lambda, cost-general, network, storage, compute, commitments)
- **Tips_Table**: The DynamoDB table `ViewMyBill-CostOptimizationTips` containing optimization tips grouped by cloud service category
- **Cost_Cache_Table**: The DynamoDB table `Cost_Cache_Table` storing pre-aggregated daily cost data per account
- **Prompt_Repository**: A dedicated directory or configuration store holding externalized, versioned prompt templates
- **Session_State**: The in-memory or persisted state tracking multi-turn conversation parameters (account, intent, timeframe)
- **Execution_Payload**: The structured data package assembled from validated parameters, filtered data, and prompt template before sending to Bedrock
- **Context_Budget**: A token-counting mechanism that limits the volume of data injected into the LLM context window
- **Delimiter_Boundary**: Special character sequences (e.g., `<<<USER_INPUT>>>`) used to separate user-supplied text from system instructions within the prompt
- **Provider_Abstraction_Layer**: A vendor-agnostic routing layer that maps account types to their respective cloud provider connectors (AWS, Azure, GCP) and AI model connectors (Bedrock, OpenAI GPT, Azure OpenAI)
- **AI_Model_Router**: The component within the Provider_Abstraction_Layer responsible for selecting and invoking the appropriate AI model based on tenant-level or global configuration
- **Enrichment_Process**: A periodic background job that populates the Tips_Table with runtime metadata (API endpoint mappings, parameter schemas, response formats, cost thresholds, optimization rules)
- **Forecast_Engine**: The module responsible for generating cost projections using historical data, seasonal patterns, anomaly filtering, confidence intervals, and what-if scenario modeling

## Requirements

### Requirement 1: Account Resolution and Context Discovery

**User Story:** As the Agent, I want to parse and validate the cloud account context from user input so that downstream queries target the correct environment.

#### Acceptance Criteria

1. WHEN a user submits an AI query with an `accountId` field, THE Agent SHALL validate the account identifier format against AWS (12-digit), Azure (UUID), or GCP (project-id) patterns before proceeding
2. WHEN a valid account identifier is detected, THE Agent SHALL resolve the account name, type, and cloud provider by querying the Accounts DynamoDB table
3. IF an invalid or unrecognized account identifier is provided, THEN THE Agent SHALL return a descriptive error indicating the expected format without exposing internal system details
4. WHEN account context is resolved, THE Agent SHALL query the Tips_Table for supported cloud services grouped by category to establish the reference data set
5. THE Agent SHALL structure the static system prefix (model identity, platform features, critical rules) as a fixed context block positioned first in the prompt to enable LLM context caching

### Requirement 2: Multi-Turn Session State Retention

**User Story:** As a user, I want the agent to remember my previous questions in a session so that I can have a natural back-and-forth conversation without repeating context.

#### Acceptance Criteria

1. THE Agent SHALL maintain a persistent session state object per user-account pair that tracks: resolved account context, current intent category, target scope, and active timeframe
2. WHEN a follow-up question references prior context (e.g., "what about RDS?" after an EC2 discussion), THE Agent SHALL carry forward the session parameters that remain applicable
3. IF a required parameter is missing from the session state and cannot be inferred from the question, THEN THE Agent SHALL prompt the user with a specific clarification question identifying the missing parameter
4. WHEN a new session begins or the user changes accounts, THE Agent SHALL reset the session state and re-execute account resolution

### Requirement 3: Intent Classification with Few-Shot Examples

**User Story:** As the Agent, I want to classify user intent reliably so that I call only the APIs relevant to the user's question and avoid unnecessary cost and latency.

#### Acceptance Criteria

1. THE Intent_Classifier SHALL classify each question into one of the defined intention types: Cost_Analysis_General, Cost_Analysis_Specific, Optimization_Tips, or Forecasting
2. THE Intent_Classifier SHALL validate the target scope parameter as either a specific service name or account-wide
3. THE Intent_Classifier SHALL validate the timeframe parameter as either a historical date range or a future projection period
4. WHEN a question is ambiguous and maps to more than two intention types, THE Intent_Classifier SHALL use few-shot classification examples (minimum 2 per intent type) embedded in the classifier prompt to disambiguate
5. IF intent classification confidence is below threshold after few-shot comparison, THEN THE Agent SHALL prompt the user with a clarification question presenting the possible intent options

### Requirement 4: Token-Optimized Execution Payload Assembly

**User Story:** As the Agent, I want to construct a minimal, structured data payload so that the LLM receives only the information needed for an accurate answer while staying within token limits.

#### Acceptance Criteria

1. THE Agent SHALL construct the execution payload using three clearly delimited sections: [CONTEXT] for static account metadata, [AVAILABLE META-DATA] for filtered data results, and [USER QUERY] for the user's question
2. THE Agent SHALL inject only filtered and pre-aggregated data into the payload, never raw database scan results
3. WHEN the gathered data exceeds 100 rows (e.g., cost_by_service entries, resource lists), THE Agent SHALL truncate to the top 10 items by value and append a summary line indicating the remaining count and total
4. THE Agent SHALL enforce a total context budget ceiling and truncate the [AVAILABLE META-DATA] section first if the combined payload exceeds the budget
5. THE Agent SHALL use stop tokens in the triage phase to prevent the model from generating beyond the classification response

### Requirement 5: Conditional Behavioral Routines by Intent

**User Story:** As the Agent, I want to execute the correct data-gathering strategy based on the classified intent so that responses are accurate and efficient.

#### Acceptance Criteria

1. WHEN the intent is Cost_Analysis_General, THE Agent SHALL query the Cost_Cache_Table first and fall back to the Cost Explorer API only on cache miss
2. WHEN the intent is Cost_Analysis_Specific, THE Agent SHALL cross-reference the Tips_Table for the target service and execute granular tool calls for resource-level data
3. WHEN the intent is Optimization_Tips, THE Agent SHALL sequentially scan through relevant TipIDs from the Tips_Table with fault-tolerant aggregation that continues processing remaining tips if an individual tip lookup fails
4. WHEN the intent is Forecasting, THE Agent SHALL validate that the requested projection period is within supported bounds (maximum 12 months forward) before pulling historical data for extrapolation
5. IF a tool call or API request fails during any behavioral routine, THEN THE Agent SHALL log the failure, skip the failed data source, and proceed with available data rather than returning a full error to the user

### Requirement 6: Deterministic Structured Output

**User Story:** As the system, I want the Agent to produce deterministic, machine-parseable outputs for internal parameter passing so that downstream logic can reliably consume the results.

#### Acceptance Criteria

1. THE Agent SHALL use JSON mode for all internal parameter passing between the intent classification step and the data-gathering step
2. THE Agent SHALL enforce a strict JSON schema for the classification output that includes fields: `intent_type`, `target_scope`, `timeframe`, and `confidence_score`
3. IF the model produces output that does not conform to the expected JSON schema, THEN THE Agent SHALL retry the classification request once before falling back to the `all` intent category
4. THE Agent SHALL validate the JSON output against the schema before passing it to the execution routines

### Requirement 7: Externalized Prompt Version Control

**User Story:** As a developer, I want prompt templates to live in a dedicated repository outside the Lambda code so that I can update agent behavior without redeploying the function.

#### Acceptance Criteria

1. THE Agent SHALL load prompt templates from a dedicated Prompt_Repository rather than using hardcoded strings in the Lambda function source
2. THE Agent SHALL assemble the final prompt by dynamically hydrating template placeholders with runtime data (account context, filtered data, user query)
3. THE Agent SHALL maintain a static system prefix that is identical across all invocations to maximize LLM context caching effectiveness
4. WHEN a prompt template is updated in the Prompt_Repository, THE Agent SHALL use the updated template on the next invocation without requiring a Lambda redeployment
5. THE Agent SHALL version-tag each prompt template so that responses can be correlated with the template version for debugging and A/B testing

### Requirement 8: Prompt Injection Defense via Delimiters

**User Story:** As the system, I want to protect the Agent's system instructions from manipulation through user-supplied input so that the agent remains trustworthy and predictable.

#### Acceptance Criteria

1. THE Agent SHALL wrap all user-supplied input within clearly defined delimiter boundaries (e.g., `<<<USER_INPUT>>>...<<<END_USER_INPUT>>>`) before injecting it into the prompt
2. THE Agent SHALL include an explicit instruction in the system prefix stating that content between user-input delimiters must be treated as data only and never as system instructions
3. THE Agent SHALL sanitize user input by escaping any occurrences of the delimiter sequences within the user's text before wrapping
4. IF user input contains patterns that resemble prompt injection attempts (e.g., "ignore previous instructions", "you are now"), THEN THE Agent SHALL log the attempt for security monitoring and proceed with the sanitized input

### Requirement 9: Context Budget and Token Conservation

**User Story:** As the Agent, I want to stay within an efficient token budget so that responses remain fast and Bedrock invocation costs stay low.

#### Acceptance Criteria

1. THE Agent SHALL allocate a fixed context budget partitioned as: system prefix (static, cacheable), dynamic data section (variable, truncatable), and user query section (preserved in full)
2. WHEN the dynamic data section exceeds its allocated budget, THE Agent SHALL apply progressive summarization: first truncate individual data arrays to top-N entries, then summarize entire sections into single-paragraph digests
3. THE Agent SHALL calculate approximate token counts for each section before assembling the final payload and log the actual token distribution for monitoring
4. THE Agent SHALL avoid sending duplicate information that appears in both the Tips_Table context and the gathered account data — deduplicate before injection

### Requirement 10: Multi-Cloud Vendor Support

**User Story:** As a platform operator, I want the agent to support multiple cloud vendors and AI providers so that customers on AWS, Azure, or GCP all receive optimized cost analysis through a unified interface.

#### Acceptance Criteria

1. THE Provider_Abstraction_Layer SHALL support routing requests to AWS, Azure, and GCP cloud provider connectors based on the resolved account type
2. THE AI_Model_Router SHALL support invoking AI models from AWS Bedrock, OpenAI GPT, and Azure OpenAI through a unified invocation interface
3. WHEN a request is received for a specific account, THE Provider_Abstraction_Layer SHALL select the appropriate cloud provider connector based on the account type resolved during account context discovery
4. THE AI_Model_Router SHALL select the AI model based on tenant-level configuration when present, falling back to the global default model configuration when no tenant override exists
5. IF a configured AI model provider is unavailable or returns an error, THEN THE AI_Model_Router SHALL log the failure and return a descriptive error indicating the provider outage without exposing internal connection details

### Requirement 11: Local DB First Strategy

**User Story:** As the Agent, I want to always query local databases before making external API calls so that response latency is minimized and external API costs are reduced.

#### Acceptance Criteria

1. WHEN data is needed for any intent execution, THE Agent SHALL query the Cost_Cache_Table and Tips_Table first before initiating external cloud provider API calls
2. WHEN the local data from Cost_Cache_Table is fresh (within the configured staleness threshold), THE Agent SHALL use the cached data directly and skip the external API call
3. IF local data is missing, stale (exceeding the configured staleness threshold), or insufficient to answer the query, THEN THE Agent SHALL fall back to the live cloud provider API through the Provider_Abstraction_Layer
4. THE Agent SHALL log each data retrieval path (local cache hit, local cache miss with fallback, or direct API call) for performance monitoring and optimization tracking
5. WHEN the Agent retrieves data from an external API after a cache miss, THE Agent SHALL write the retrieved data back to the Cost_Cache_Table for subsequent queries

### Requirement 12: Tips Table Enrichment

**User Story:** As a platform operator, I want the Tips_Table pre-enriched with runtime metadata so that the agent can determine API endpoints, parameters, and optimization rules at query time without performing real-time schema lookups.

#### Acceptance Criteria

1. THE Enrichment_Process SHALL populate each record in the Tips_Table with API endpoint mappings, parameter schemas, expected response formats, cost thresholds, and optimization rules during periodic execution
2. WHEN the Agent executes a behavioral routine, THE Agent SHALL query the pre-enriched Tips_Table to determine which APIs to call and what parameters to pass for the target service category
3. THE Agent SHALL use the optimization rules stored in the Tips_Table to evaluate gathered data against defined cost thresholds without requiring external rule lookups at runtime
4. WHEN the Enrichment_Process completes a cycle, THE Enrichment_Process SHALL update a last-enriched timestamp on each modified record so the Agent can verify data freshness
5. IF a Tips_Table record lacks required enrichment fields (API endpoint, parameter schema, or response format), THEN THE Agent SHALL log a warning and fall back to a default API configuration for that service category

### Requirement 13: Cost Forecasting Logic

**User Story:** As a user, I want the agent to forecast future cloud costs using historical patterns so that I can plan budgets and model the impact of infrastructure changes.

#### Acceptance Criteria

1. WHEN the intent is Forecasting, THE Forecast_Engine SHALL generate cost projections using linear extrapolation from a minimum of 30 days of historical data from the Cost_Cache_Table
2. THE Forecast_Engine SHALL detect and apply seasonal patterns (weekly and monthly cycles) by analyzing a minimum of 90 days of historical data when available
3. WHEN generating projections, THE Forecast_Engine SHALL identify and exclude one-time cost spikes (anomalies exceeding 2 standard deviations from the rolling mean) from the baseline forecast model
4. THE Forecast_Engine SHALL produce confidence intervals (at 80% and 95% levels) alongside each cost projection to communicate prediction uncertainty
5. WHEN a user submits a what-if scenario query (e.g., "what if I add 5 more EC2 instances?"), THE Forecast_Engine SHALL calculate the incremental cost impact by applying the relevant unit pricing to the scenario parameters and adding the result to the baseline forecast
