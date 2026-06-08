# Implementation Plan: Agent Optimization

## Overview

Reorganize and optimize the SlashMyBill AI agent (`handle_ai_query` in `member-handler/lambda_function.py`) into a modular pipeline architecture with discrete stages: Account Resolver → Session State Manager → Intent Classifier v2 → Payload Assembler → Behavioral Router → Structured Output Validator → Response Builder. Implementation uses Python 3.12 on AWS Lambda with DynamoDB, S3, and Bedrock.

## Tasks

- [ ] 1. Set up project structure, core interfaces, and shared utilities
  - [ ] 1.1 Create module directory structure and shared data models
    - Create `member-handler/agent/` package directory
    - Create `member-handler/agent/__init__.py` with pipeline exports
    - Create `member-handler/agent/models.py` with shared dataclasses: `AccountContext`, `SessionState`, `ClassificationResult`, `ContextBudget`, `ExecutionPayload`, `PromptTemplate`, `ModelConfig`, `ForecastResult`, `EnrichedTip`
    - Create `member-handler/agent/constants.py` with schema definitions (`CLASSIFICATION_SCHEMA`), delimiter constants, budget defaults
    - _Requirements: 1.1, 1.5, 3.1, 6.2, 8.1, 9.1_

  - [ ] 1.2 Create context budget manager module
    - Create `member-handler/agent/context_budget.py`
    - Implement `estimate_tokens(text: str) -> int` using chars/4 heuristic
    - Implement `allocate_budget(model_config: ModelConfig) -> ContextBudget` to partition context window
    - Implement `apply_progressive_summarization(data_text: str, max_tokens: int) -> str` with two-stage truncation
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ]* 1.3 Write property test for token estimation accuracy
    - **Property 12: Token estimation accuracy**
    - **Validates: Requirements 9.3**

- [ ] 2. Implement Account Resolver
  - [ ] 2.1 Create account resolver module
    - Create `member-handler/agent/account_resolver.py`
    - Implement `validate_account_format(account_id: str) -> str` with regex for AWS (12-digit), Azure (UUID), GCP (6-30 char lowercase project-id)
    - Implement `resolve_account(account_id: str, member_email: str) -> AccountContext` querying Accounts DynamoDB table
    - Load supported services from Tips_Table grouped by category
    - Return descriptive errors without internal system details on invalid format
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 2.2 Write property test for account ID format validation
    - **Property 1: Account ID format validation**
    - **Validates: Requirements 1.1, 1.3**

- [ ] 3. Implement Session State Manager
  - [ ] 3.1 Create session state manager module
    - Create `member-handler/agent/session_state.py`
    - Implement `load_session(member_email: str, account_id: str) -> SessionState` reading from Members DynamoDB table
    - Implement `update_session(session: SessionState, intent_result: dict) -> SessionState` carrying forward applicable parameters
    - Implement `reset_session(member_email: str, account_id: str) -> SessionState` clearing state on account change
    - Handle DynamoDB read failures by initializing fresh session with warning log
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 3.2 Write property test for session state carry-forward
    - **Property 5: Session state carry-forward**
    - **Validates: Requirements 2.2, 2.3**

- [ ] 4. Implement Intent Classifier v2
  - [ ] 4.1 Create intent classifier v2 module
    - Create `member-handler/agent/intent_classifier_v2.py`
    - Implement keyword matching for primary classification (Cost_Analysis_General, Cost_Analysis_Specific, Optimization_Tips, Forecasting)
    - Implement LLM few-shot disambiguation when keyword matching produces 3+ category matches
    - Use stop tokens to prevent over-generation in triage phase
    - Implement retry logic: on invalid JSON, retry once then fall back to `all` intent
    - Validate output against `CLASSIFICATION_SCHEMA` before returning
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.5, 6.1, 6.2, 6.3, 6.4_

  - [ ]* 4.2 Write property test for classification output schema conformance
    - **Property 6: Classification output schema conformance**
    - **Validates: Requirements 3.1, 3.2, 3.3, 6.1, 6.2, 6.4**

  - [ ]* 4.3 Write property test for few-shot disambiguation
    - **Property 7: Few-shot disambiguation resolves ambiguity**
    - **Validates: Requirements 3.4**

- [ ] 5. Implement Prompt Repository and Defense
  - [ ] 5.1 Create prompt repository module
    - Create `member-handler/agent/prompt_repository.py`
    - Implement `load_template(template_name: str) -> PromptTemplate` loading versioned templates from S3
    - Implement `hydrate_template(template: PromptTemplate, variables: dict) -> str` replacing `{{variable_name}}` placeholders
    - Include template version in payload metadata
    - Handle template-not-found by falling back to hardcoded default template with critical log
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ] 5.2 Create prompt injection defense module
    - Create `member-handler/agent/prompt_defense.py`
    - Implement `sanitize_user_input(raw_input: str) -> str` that escapes delimiter sequences and wraps with `<<<USER_INPUT>>>` / `<<<END_USER_INPUT>>>`
    - Implement `detect_injection_patterns(raw_input: str) -> list[str]` scanning for known injection patterns
    - Log detected injection attempts for security monitoring
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [ ]* 5.3 Write property test for template hydration completeness
    - **Property 10: Template hydration completeness**
    - **Validates: Requirements 7.2, 7.5**

  - [ ]* 5.4 Write property test for prompt injection defense
    - **Property 11: Prompt injection defense**
    - **Validates: Requirements 8.1, 8.3, 8.4**

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement Payload Assembler
  - [ ] 7.1 Create payload assembler module
    - Create `member-handler/agent/payload_assembler.py`
    - Implement `assemble_payload(template_name, account_context, gathered_data, user_question, budget) -> ExecutionPayload`
    - Structure payload with three delimited sections: [CONTEXT], [AVAILABLE META-DATA], [USER QUERY]
    - Ensure static system prefix is identical across all invocations
    - Implement `truncate_to_budget(data: dict, max_tokens: int) -> str` with progressive truncation (top-N arrays, then paragraph summaries)
    - Truncate data arrays exceeding 100 rows to top 10 by value with summary line
    - Deduplicate overlapping data between Tips_Table context and gathered account data
    - Enforce budget ceiling: truncate [AVAILABLE META-DATA] first, preserve system prefix and user query intact
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 9.1, 9.2, 9.4_

  - [ ]* 7.2 Write property test for payload structural integrity
    - **Property 2: Payload structural integrity**
    - **Validates: Requirements 4.1, 1.5, 7.3**

  - [ ]* 7.3 Write property test for data truncation invariant
    - **Property 3: Data truncation invariant**
    - **Validates: Requirements 4.3**

  - [ ]* 7.4 Write property test for budget enforcement preserves priority sections
    - **Property 4: Budget enforcement preserves priority sections**
    - **Validates: Requirements 4.4, 9.1, 9.2**

  - [ ]* 7.5 Write property test for data deduplication
    - **Property 13: Data deduplication between tips and account data**
    - **Validates: Requirements 9.4**

- [ ] 8. Implement Provider Abstraction Layer and AI Model Router
  - [ ] 8.1 Create AI model router module
    - Create `member-handler/agent/ai_model_router.py`
    - Implement `get_model_config(member_email: str) -> ModelConfig` resolving tenant override > global default
    - Implement `invoke_model(config: ModelConfig, payload: ExecutionPayload) -> str` with unified interface across Bedrock, OpenAI GPT, Azure OpenAI
    - Handle provider unavailability with descriptive error (no internal connection details)
    - _Requirements: 10.2, 10.3, 10.4, 10.5_

  - [ ] 8.2 Create provider abstraction layer with cloud connectors
    - Create `member-handler/agent/provider_connectors.py`
    - Implement AWS connector for Cost Explorer, Compute Optimizer APIs
    - Implement Azure connector stub for Azure Cost Management
    - Implement GCP connector stub for BigQuery billing export
    - Route to correct connector based on resolved account `cloud_provider` field
    - _Requirements: 10.1, 10.3_

  - [ ]* 8.3 Write property test for provider routing correctness
    - **Property 14: Provider routing correctness**
    - **Validates: Requirements 10.1, 10.3, 10.4**

- [ ] 9. Implement Behavioral Router and Cache Strategy
  - [ ] 9.1 Create behavioral router module
    - Create `member-handler/agent/behavioral_router.py`
    - Implement `execute_cost_analysis_general` — query Cost_Cache_Table first, fall back to Cost Explorer API on miss
    - Implement `execute_cost_analysis_specific` — cross-reference Tips_Table, execute granular tool calls
    - Implement `execute_optimization_tips` — sequential tip scan with fault-tolerant aggregation
    - Implement `execute_forecasting` — validate projection bounds (1-12 months), pull historical data
    - Implement fault-tolerant data gathering: skip failed sources, continue with available data, error only when all sources fail
    - Write retrieved data back to Cost_Cache_Table on cache miss
    - Log each data retrieval path (cache hit, miss + fallback, direct API)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ]* 9.2 Write property test for fault-tolerant data gathering
    - **Property 8: Fault-tolerant data gathering**
    - **Validates: Requirements 5.3, 5.5**

  - [ ]* 9.3 Write property test for forecast projection period validation
    - **Property 9: Forecast projection period validation**
    - **Validates: Requirements 5.4**

  - [ ]* 9.4 Write property test for cache freshness determines retrieval path
    - **Property 15: Cache freshness determines retrieval path**
    - **Validates: Requirements 11.2, 11.3, 11.5**

- [ ] 10. Implement Tips Enrichment and Rule Evaluation
  - [ ] 10.1 Create tips enrichment module
    - Create `member-handler/agent/tips_enrichment.py`
    - Implement `enrich_tips_table() -> dict` populating API mappings, parameter schemas, response formats, cost thresholds, and optimization rules
    - Implement `get_enriched_tip(service: str, tip_id: str) -> EnrichedTip | None` querying pre-enriched records
    - Update `last_enriched` timestamp on each modified record
    - Log warning and fall back to default API config when enrichment fields are missing
    - _Requirements: 12.1, 12.2, 12.4, 12.5_

  - [ ] 10.2 Create rule evaluator for optimization thresholds
    - Implement optimization rule evaluation logic within the tips enrichment module
    - Evaluate gathered metric data against defined cost thresholds (e.g., avg_cpu < threshold → flag over-provisioned)
    - Ensure no false negatives for values clearly beyond threshold boundaries
    - _Requirements: 12.3_

  - [ ]* 10.3 Write property test for optimization rule evaluation
    - **Property 16: Optimization rule evaluation**
    - **Validates: Requirements 12.3**

- [ ] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Implement Forecast Engine
  - [ ] 12.1 Create forecast engine module
    - Create `member-handler/agent/forecast_engine.py`
    - Implement `generate_forecast(historical_data, projection_months, scenario) -> ForecastResult` with linear extrapolation
    - Require minimum 30 days of historical data; return error for insufficient data
    - Accept projection periods of 1-12 months; reject periods >12 months with descriptive error
    - _Requirements: 13.1_

  - [ ] 12.2 Implement seasonal pattern detection
    - Implement weekly and monthly cycle detection from 90+ days of historical data
    - Skip seasonal adjustment when fewer than 90 data points available
    - Apply seasonal factors to baseline linear extrapolation
    - _Requirements: 13.2_

  - [ ] 12.3 Implement anomaly detection and exclusion
    - Implement `detect_anomalies(daily_costs, std_threshold=2.0) -> list[dict]` identifying spikes >2 std dev from rolling mean
    - Exclude identified anomalies from baseline forecast model
    - Include excluded anomalies in forecast output with date, actual cost, and expected cost
    - _Requirements: 13.3_

  - [ ] 12.4 Implement confidence intervals and what-if scenarios
    - Generate 80% and 95% confidence intervals for each projected month
    - Enforce ordering: ci_95_low ≤ ci_80_low ≤ projected_cost ≤ ci_80_high ≤ ci_95_high
    - Implement `apply_what_if_scenario(baseline, scenario, pricing_data) -> ForecastResult`
    - Calculate scenario_impact = unit_price × quantity × projection_period_months
    - Add scenario impact to baseline projection for each month
    - _Requirements: 13.4, 13.5_

  - [ ]* 12.5 Write property test for forecast linear extrapolation validity
    - **Property 17: Forecast linear extrapolation validity**
    - **Validates: Requirements 13.1**

  - [ ]* 12.6 Write property test for seasonal pattern detection threshold
    - **Property 18: Seasonal pattern detection threshold**
    - **Validates: Requirements 13.2**

  - [ ]* 12.7 Write property test for anomaly exclusion from forecast baseline
    - **Property 19: Anomaly exclusion from forecast baseline**
    - **Validates: Requirements 13.3**

  - [ ]* 12.8 Write property test for confidence interval ordering
    - **Property 20: Confidence interval ordering**
    - **Validates: Requirements 13.4**

  - [ ]* 12.9 Write property test for what-if scenario incremental cost calculation
    - **Property 21: What-if scenario incremental cost calculation**
    - **Validates: Requirements 13.5**

- [ ] 13. Implement Structured Output Validator and Response Builder
  - [ ] 13.1 Create structured output validator
    - Create `member-handler/agent/output_validator.py`
    - Implement JSON schema validation for all internal state passing between pipeline stages
    - Implement retry logic: on malformed output, retry once then fall back gracefully
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 13.2 Create response builder module
    - Create `member-handler/agent/response_builder.py`
    - Assemble final user-facing response with chart data, tips, and follow-up topics
    - Integrate prompt defense (sanitize user input before injection into prompt)
    - Include template version in response metadata for debugging
    - _Requirements: 7.3, 7.5, 8.2_

- [ ] 14. Wire pipeline together and integrate into Lambda handler
  - [ ] 14.1 Create pipeline orchestrator
    - Create `member-handler/agent/pipeline.py`
    - Implement `execute_pipeline(event: dict) -> dict` orchestrating: Account Resolver → Session State → Intent Classifier → Payload Assembler → Behavioral Router → Structured Output Validator → Response Builder
    - Implement graceful degradation chain: keyword-only classifier → no session → fallback template → partial data response
    - Log token distribution for each invocation via CloudWatch custom metrics
    - _Requirements: 1.5, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1, 8.1, 9.1_

  - [ ] 14.2 Refactor `handle_ai_query` in `member-handler/lambda_function.py`
    - Replace monolithic `handle_ai_query` with call to `execute_pipeline`
    - Preserve existing API contract (request/response format)
    - Remove old hardcoded prompts and inline intent classification
    - Ensure backward compatibility with existing API Gateway integration
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_

- [ ] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis (Python PBT library)
- Unit tests validate specific examples and edge cases
- All modules are placed under `member-handler/agent/` to keep the pipeline self-contained
- The existing `intent_classifier.py` remains as fallback until the v2 module is validated
- Provider connectors for Azure and GCP are stubs initially — full implementation follows in the multi-cloud vendor integration spec

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "5.1", "5.2"] },
    { "id": 2, "tasks": ["1.3", "2.2", "3.1", "4.1", "5.3", "5.4"] },
    { "id": 3, "tasks": ["3.2", "4.2", "4.3", "7.1", "8.1", "8.2"] },
    { "id": 4, "tasks": ["7.2", "7.3", "7.4", "7.5", "8.3", "9.1", "10.1"] },
    { "id": 5, "tasks": ["9.2", "9.3", "9.4", "10.2", "12.1"] },
    { "id": 6, "tasks": ["10.3", "12.2", "12.3", "12.4"] },
    { "id": 7, "tasks": ["12.5", "12.6", "12.7", "12.8", "12.9", "13.1"] },
    { "id": 8, "tasks": ["13.2"] },
    { "id": 9, "tasks": ["14.1"] },
    { "id": 10, "tasks": ["14.2"] }
  ]
}
```
