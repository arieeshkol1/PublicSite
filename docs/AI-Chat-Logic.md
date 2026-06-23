# AI Chat — End-to-End Logic

This document explains how the member-portal **Chat** tab works, from the moment a
question is submitted to the moment an audited answer is stored. It is grounded in
the actual code (file paths and function names are cited so you can validate each
step).

> Scope: the AWS cost/optimization chat. OpenAI and Azure/GCP have narrower paths
> (noted where relevant).

---

## 1. High-level picture

```
Browser (Chat tab)
   │  POST /members/accounts/ai-query  { question, accountId|accountIds, tagKey?, tagValue? }
   ▼
member-handler  handle_ai_query()              ← wrapped by @transaction_log
   │  auth + credit check + account ownership
   │
   ├─ non-AWS only ──► OpenAI cached answer / Invoices redirect
   │
   └─ AWS (single account)
         │
         ├─ (A) Modular pipeline   agent/pipeline.execute_pipeline()   ← tried first
         │       resolve → classify intent → gather (cache-first) → assemble → model → build
         │
         └─ (B) Bedrock Agent      _invoke_bedrock_agent()             ← primary / fallback
                 tips lookup → Bedrock Agent + action-group tools (cache-first)
                 → INLINE AUDIT GATE → trace + follow-ups → response
   ▼
@transaction_log writes the row to Audit_Transaction_Log (audit_status = "pending")
   ▼
DynamoDB Stream (INSERT) ──► audit-evaluator Lambda  → writes audit_score + assessments back
```

Two things run **asynchronously / out of band** from the user's point of view:
- The **inline audit gate** runs *synchronously inside* the request (before the answer is returned).
- The **async audit evaluator** runs *after* the response, triggered by the DynamoDB stream.

---

## 2. Entry point — `handle_ai_query`

**File:** `member-handler/lambda_function.py` → `handle_ai_query(event)` (decorated with `@transaction_log('member-handler')`).
**Route:** `POST /members/accounts/ai-query`.

Request body:
- `question` (required)
- `accountId` (single) or `accountIds` (list)
- `tagKey` / `tagValue` (optional cost-allocation tag filter)

Steps:
1. `validate_token(event)` → `member_email`.
2. **Credit check / consume:** `_get_member_tier` then `_check_and_consume_credits(member_email, tier, AI_QUERY_CREDIT_COST)`.
   - `AI_QUERY_CREDIT_COST = 2`; tier ceilings `AI_CREDITS = {free:100, growth:300, scale:1500}`.
3. Generate `interaction_id = <ISO timestamp>-<hex>` (used for feedback + tracing).
4. **Account ID validation** (multi-cloud regex: AWS 12-digit, Azure UUID, GCP project id) and normalize `accountId → accountIds`.
5. **Ownership check:** `_verify_account_ownership` (blocks lateral access to accounts the member doesn't own).
6. If a tag filter is present, the question is prefixed with `[FILTER ACTIVE: tag=value]` so the model is aware.
7. **Branch:**
   - **Non-AWS only** → OpenAI answered from cache (`_answer_openai_query`, bounded to 20s); Azure/GCP → static "open Invoices" redirect.
   - **Single AWS account** → `_run_ai_query()` tries the modular pipeline first, then falls back to the Bedrock Agent.
   - **Multi-account** → OpenAI accounts answered from cache; AWS ids sent as `[Multi-Account Query: accounts=…]` context to the Bedrock Agent.
8. The whole `_run_ai_query` runs inside a `ThreadPoolExecutor` with `future.result(timeout=27)` (stays under API Gateway's 29s ceiling). A timeout/exception returns a graceful 200 message.
9. Before returning, `aiCredits` (used/total/remaining) is injected into the 200 body.

---

## 3. Path A — Modular agent pipeline

**File:** `member-handler/agent/pipeline.py` → `execute_pipeline(event)`. Each stage is wrapped in try/except for graceful degradation.

| Stage | Module / function | What it does |
|-------|-------------------|--------------|
| 0. Injection check | `prompt_defense.detect_injection_patterns` | Log-only, non-blocking |
| 1. Account resolution | `account_resolver.resolve_account` | Loads account from Accounts table; minimal fallback context on error |
| 2. Session state | `session_state.load_session` | Multi-turn history; attaches `account_context` |
| 3. Intent classification | `intent_classifier_v2.classify_intent` | → `ClassificationResult` (intent, scope, timeframe, confidence) |
| 4. Data gathering | `behavioral_router.execute_by_intent` | Cache-first cost / tips / forecasting (see §6, §7) |
| 5. Payload assembly | `ai_model_router.get_model_config` + `context_budget.allocate_budget` + `payload_assembler.assemble_payload("system-prefix-v3.2.txt", …)` | Builds the bounded prompt |
| 6. Model invocation | `ai_model_router.invoke_model` | Bedrock / OpenAI / Azure (see §8) |
| 7. Response builder | `response_builder.build_response` | Assembles answer + sources |
| 8. Persist session | `session_state.persist_session` | Appends user/assistant turns |

If the pipeline returns an error in its metadata (or raises), `handle_ai_query` falls back to Path B.

---

## 4. Path B — Bedrock Agent (primary single-account path)

**File:** `member-handler/lambda_function.py` → `_invoke_bedrock_agent(question, account_id, member_email, interaction_id)`.

1. **Tips lookup** — `_search_tips(question, provider)` (see §7) builds a `tips_context` block and `tip_found` flag that are injected into the agent prompt.
2. **Agent call** — `bedrock-agent-runtime` client (connect 10s / read 150s, no botocore retries), using env `BEDROCK_AGENT_ID` / `BEDROCK_AGENT_ALIAS_ID`. Session id = sanitized `member_email-account_id-interaction_id`.
   - `_invoke_agent_with_retry` consumes the streamed completion, retries transient errors (throttling/internalServer/badGateway…) up to 3 attempts with linear backoff, and feeds trace events into a `TraceCollector`.
   - The agent autonomously decides which **action-group tools** to call (see §5).
3. **Inline audit quality gate** — `_inline_audit_score` scores the answer; may rewrite or ask clarifying questions (see §8B).
4. **Trace + extras** — builds the structured inference trace (`serialize_trace`), follow-up questions, and chart data from the cache.
5. Returns 200 with `answer`, `inlineAuditScore`, `inlineAuditAction`, `interactionId`, `followUpQuestions`, `chartData`, etc., and attaches `_inference_trace` for the transaction logger.

---

## 5. Tools

There are three "tool" surfaces depending on the path. **All of them use the customer's cross-account (assumed-role) credentials** — never the platform's own credentials.

### 5A. Bedrock Agent action-group tools (Path B, primary)
Defined in `agent-action/openapi-schema.json`; executed by `agent-action/lambda_function.py`:

| operationId | Purpose |
|-------------|---------|
| `getCostData` | Cost by service (30d) + daily trend; `usageTypeBreakdown=true`+`serviceFilter` for deep-dive |
| `getMonthlyComparison` | Month-over-month cost (3–6 months) |
| `getEC2Instances` | EC2 list + 14-day CPU |
| `getRDSInstances` | RDS list + metrics |
| `getLambdaFunctions` | Lambda list + invocations/errors |
| `getS3Buckets` | S3 buckets + lifecycle status |
| `getEBSVolumes` | EBS volumes (type/size/attachment) |
| `getNetworkResources` | NAT gateways, VPC endpoints, Elastic IPs |
| `getBudgets` | AWS Budgets with spend + forecast |
| `getFinOpsSettings` | FinOps settings healthcheck |
| `getAWSPricing` | Real-time AWS Pricing API lookup |

### 5B. Parallel resource fetchers (Path A / legacy direct path)
**File:** `member-handler/parallel_executor.py`. `_gather_aws_data_parallel` runs selected fetchers concurrently (`ThreadPoolExecutor(max_workers=5)`, per-call `timeout=10s`, failures logged + skipped). Each fetcher builds clients via `_make_client(credentials, …)`:

- `_fetch_ec2_instances` → `ec2:DescribeInstances`
- `_fetch_cloudwatch_metrics` → `cloudwatch:GetMetricStatistics` (EC2 CPU)
- `_fetch_rds_instances` → `rds:DescribeDBInstances`
- `_fetch_s3_buckets` → `s3:ListBuckets`
- `_fetch_ebs_volumes` → `ec2:DescribeVolumes` (gp2→gp3 savings, unattached)
- `_fetch_nat_gateways` → NAT + Elastic IPs + VPC endpoints (one call covers `nat_gateways`/`eips`/`vpc_endpoints`)
- `_fetch_lambda_functions` → `lambda:ListFunctions`

`_gather_multi_account_parallel` processes multiple accounts (`max_workers=3`), routing each through `connectors.get_connector(provider)`.

### 5C. Direct boto3 gatherer
**File:** `member-handler/lambda_function.py` → `_gather_account_data(...)`. Time-budgeted (`_MAX_GATHER_SECONDS = 14`, raises `_TimeBudgetExhausted` when <3s remain so the model still has time). Cost Explorer is always run first (cache-first, see §6); resource APIs are gated by intent.

---

## 6. Cost data priority (cache-first)

**File:** `member-handler/cost_cache.py` → `_get_cost_data_cached(member_email, account_id, credentials, start, end)`.

Priority order (enforced):
1. **Local cache DB** — `_read_from_cache` reads `Cost_Cache_Table`.
   - Key scheme: `pk = "{member_email}#{account_id}"`, `sk` between `DAILY#{start}` and `DAILY#{end}`.
   - Coverage rule: needs ≥ `(expected_days − 2)` daily items (2-day grace for unfinalized today/yesterday), otherwise treated as a miss.
   - Aggregates each day's `service_breakdown` into a `cost_by_service` list.
2. **Customer Cost Explorer (their connection)** — `_fetch_from_cost_explorer` builds a `ce` client from the **customer's** STS credentials (`AccessKeyId/SecretAccessKey/SessionToken`). Never the platform account.
3. **Both fail** → a single `_error` indicator item (graceful, no crash).

The cache is populated out-of-band by the nightly sync and invoice-refresh jobs (also using customer credentials). OpenAI usage uses a parallel `OPENAI_DAILY#YYYY-MM-DD` key scheme in the same table.

The agent pipeline's `behavioral_router._query_cache` uses the same `Cost_Cache_Table` key scheme.

---

## 7. Tips table

**Table:** `ViewMyBill-CostOptimizationTips` (constant `TIPS_TABLE` in `agent/constants.py`; env `TIPS_TABLE_NAME` in the main handler).

**Schema:** partition key `service` (stored UPPERCASE), sort key `tipId`; fields include `title`, `description`, `apis`, `drilldownInstructions`, `estimatedSavings`, `difficulty`, `cloud`.
- `apis` is the **drilldown scheme**: the list of read-only APIs to run to validate / drill into that tip (mirrors the api ids used by the data gatherers).

**Where it's read in chat:**
- **Path B (Bedrock Agent):** `_search_tips(question, provider)` → `tips_filter._search_tips` (provider keyword→service maps, always includes the `General` service, dedup by `tipId`, max 10). Builds the `tips_context`/`tip_found` injected into the agent prompt. `_search_tips_multi_provider` merges across providers.
- **Path A (pipeline):** `behavioral_router`:
  - `_query_tips_for_service(service)` — `Query` on `service = UPPER(service)`.
  - `_get_tip_ids_for_service` + `_get_tip_detail(service, tipId)` — used by `execute_optimization_tips` (fault-tolerant sequential scan) and `execute_cost_analysis_specific`.

**Admin:** the Tips table is managed in **Admin > Tips** (search, add/edit, and JSON/CSV export of all records).

---

## 8. Intent classification

Two classifiers exist for the two paths.

### 8A. Pipeline classifier (LLM-assisted)
**File:** `member-handler/agent/intent_classifier_v2.py` → `classify_intent`.
- Intents (`VALID_INTENT_TYPES`): `Cost_Analysis_General`, `Cost_Analysis_Specific`, `Optimization_Tips`, `Forecasting`.
- Logic: keyword/regex match → 1 match = confidence 0.9; 2 matches = `_pick_more_specific` (priority Forecasting > Optimization_Tips > Cost_Analysis_Specific > Cost_Analysis_General), confidence 0.75; 0 or ≥3 = `_llm_disambiguate` (few-shot via Bedrock Nova Lite, temp 0.0, maxTokens 150).
- `_extract_scope` / `_extract_timeframe` derive `target_scope` (ec2/rds/s3/network/…) and `timeframe` (`last-30d`, `next-3m`, …).

### 8B. Legacy keyword classifier (no LLM, <50ms)
**File:** `member-handler/intent_classifier.py` → `_classify_intent(question) -> set[str]` and `get_apis_for_intent(intent) -> set[str]`.
- Categories: `ec2, rds, s3, lambda, commitments, cost-general, network, storage, compute`; returns `{'all'}` when >2 categories match or none match.
- `CATEGORY_API_MAPPING` maps a category → api ids, e.g. `network → [cost_explorer, nat_gateways, eips, vpc_endpoints]`, `storage → [cost_explorer, ebs_volumes]`, `commitments → [cost_explorer, sp_ri_coverage]`.

---

## 9. Model invocation

**File:** `member-handler/agent/ai_model_router.py`.
- `get_model_config(member_email)` — per-tenant override (`aiModelConfig` on the Members row) > default.
- **Default model:** provider `bedrock`, `model_id = us.amazon.nova-2-lite-v1:0`, max_tokens 4096, temperature 0.1.
- `invoke_model` dispatches to `_invoke_bedrock` / `_invoke_openai` / `_invoke_azure_openai`. Bedrock prompt = `system_prefix + available_metadata + user_query`; handles Nova/Titan (`results[0].outputText`) and Claude (`content[0].text`) response shapes. OpenAI/Azure call via `urllib` (30s) with the key from Secrets Manager.
- **Prompt template:** `system-prefix-v3.2.txt`, stored in S3 bucket `slashmybill-prompt-repository` under `templates/`.
- **Token budget** (`agent/constants.DEFAULT_BUDGET_CONFIG`): window 128000; system_prefix 4000; dynamic_data 12000; user_query 2000; response 4000; total_ceiling 22000.
- **Bedrock Agent (Path B):** uses `BEDROCK_AGENT_ID` / `BEDROCK_AGENT_ALIAS_ID`; the global `BEDROCK_MODEL_ID` default is also `us.amazon.nova-2-lite-v1:0`.

---

## 10. Audit agent (two mechanisms)

### 10A. Inline quality gate (synchronous, inside the request)
**File:** `member-handler/lambda_function.py` → `_inline_audit_score(question, answer)`, called from `_invoke_bedrock_agent`.
- **Code-level pre-checks** (instant, no LLM): generic-pricing-instead-of-spend (score 40), EC2-Other/Cost-Explorer confusion (30), truncated mid-sentence (45), wrong-month answer (35), vague commitment with no $ figures (45).
- **LLM scoring:** Bedrock Nova Lite (`read_timeout=5`, maxTokens 256), a strict 15-rule 0–100 prompt; returns `{score, can_improve, improvement, guiding_questions}`. Any failure → `{score:100}` (pass-through, never blocks).
- **Gate behavior** (`AUDIT_QUALITY_GATE_ENABLED` default true; `AUDIT_QUALITY_THRESHOLD` default 70). Skipped for pre-computed/forecast answers. If `score < threshold`:
  - `can_improve = true` → re-invoke the agent once with a `[QUALITY IMPROVEMENT …]` instruction → re-score. If it now passes → deliver (`inlineAuditAction = rewrite_accepted`); else return guiding questions (`rewrite_clarify`).
  - `can_improve = false` → return guiding questions immediately (`clarify`).
- The response carries `inlineAuditScore` and `inlineAuditAction` ∈ {`pass`, `rewrite`, `rewrite_accepted`, `rewrite_clarify`, `clarify`, `error`}.
- Spec: `.kiro/specs/inline-audit-quality-gate/`.

### 10B. Async audit evaluator (after the response)
**File:** `audit-evaluator/lambda_function.py`. **Trigger:** DynamoDB Stream `INSERT` on `Audit_Transaction_Log`.
- `_check_auto_score` shortcuts (no LLM): zero-activity Lambda listing → 80; forecast with $ + formula → 85.
- Else `_build_prompt` (strict **16-rule** prompt, plus a `_build_trace_scoring_section` derived from `inference_trace` when present) and invokes Bedrock `BEDROCK_MODEL_ID` (default Nova Lite; supports Nova vs Claude body shapes), maxTokens 1024, 3 retries with exponential backoff (2/4/8s).
- `_parse_bedrock_response` extracts `score` (clamped 0–100) + assessments.
- `_update_entry_with_evaluation` writes back to the same item: `audit_status` (`completed`/`failed`), `audit_evaluated_at`, `audit_score`, `audit_accuracy_assessment`, `audit_timing_assessment`, `audit_improvement_suggestions`, `audit_trace_assessment`.

The 16 scoring rules deliberately avoid false negatives on pre-computed answers, usage-type breakdowns, zero-activity inventories, and forecasts — while penalizing cost questions answered without dollar figures and generic pricing returned instead of the user's actual spend.

---

## 11. Transaction logging (the audit's data source)

**File:** `transaction_logger.py` → `transaction_log(source_handler)` decorator.
- **Table:** `Audit_Transaction_Log` (us-east-1). Payloads truncated at `MAX_PAYLOAD_BYTES = 10KB`.
- **Captured per call:** `transaction_id` (API GW requestId or uuid4, idempotent), `start_timestamp`, `end_timestamp`, `user_email`, `function_name` (routeKey), `request_payload`, `response_payload`, `duration_ms`, `source_handler`, `status`, `expiry_ttl` (now + 90 days), and `audit_status = "pending"`.
- **Sanitization:** `_sanitize` strips sensitive fields (password, token, jwt, secret, authorization, …); floats → Decimal; empty strings dropped.
- **Audit tie-in:** if the handler response contains `_inference_trace` (set by `_invoke_bedrock_agent` from `TraceCollector`), it is popped (not returned to the client) and stored as `inference_trace` on the log item. Writing the item (with `audit_status = "pending"`) fires the DynamoDB stream that triggers §10B, which updates the same row.

---

## 12. End-to-end order of operations (single-account cost question)

1. API GW → `handle_ai_query` (wrapped by `transaction_log`): validate token, get tier, **consume 2 credits**, validate + own account, build `interaction_id`, apply tag filter.
2. `_run_ai_query` (27s bounded): try `agent.pipeline.execute_pipeline`; on miss/error fall back to Bedrock Agent.
3. `_invoke_bedrock_agent`: `_search_tips` builds tips context → Bedrock Agent runs with `TraceCollector` → agent calls action-group tools (e.g. `getCostData`) which read **cache-first, then customer Cost Explorer** with assumed-role creds.
4. **Inline audit gate** (`_inline_audit_score`, Nova Lite, threshold 70): pass, or rewrite-and-rescore, or clarify.
5. Build trace + follow-ups + chart data → return 200 with `answer`, `inlineAuditScore`, `inlineAuditAction`, `interactionId`; attach `_inference_trace`.
6. `transaction_log` writes the row (incl. `inference_trace`, `audit_status="pending"`) to `Audit_Transaction_Log`; injects `aiCredits` into the body.
7. DynamoDB stream INSERT → **audit-evaluator** scores the row (Nova Lite, 16 rules + trace rules) and writes `audit_score` + assessments + `audit_status="completed"` back to the same item (visible in the Admin panel).

---

## 13. Key tables, env vars, and constants

| Item | Value / default | Where |
|------|------------------|-------|
| Cost cache table | `Cost_Cache_Table` (`COST_CACHE_TABLE_NAME`) | cost_cache.py, agent/constants.py |
| Tips table | `ViewMyBill-CostOptimizationTips` (`TIPS_TABLE_NAME`) | agent/constants.py, lambda_function.py |
| Audit/transaction table | `Audit_Transaction_Log` (`TABLE_NAME`) | transaction_logger.py, audit-evaluator |
| Default model | `us.amazon.nova-2-lite-v1:0` | ai_model_router.py, BEDROCK_MODEL_ID |
| Bedrock Agent | `BEDROCK_AGENT_ID` / `BEDROCK_AGENT_ALIAS_ID` | lambda_function.py |
| Prompt template | `system-prefix-v3.2.txt` in `slashmybill-prompt-repository/templates/` | agent/constants.py |
| AI credit cost / ceilings | 2 per query; free 100 / growth 300 / scale 1500 | lambda_function.py |
| Request budget | 27s overall; gather 14s; per-tool 10s | lambda_function.py, parallel_executor.py |
| Audit gate | `AUDIT_QUALITY_GATE_ENABLED` (true), `AUDIT_QUALITY_THRESHOLD` (70) | lambda_function.py |
| Token budget ceiling | 22000 (window 128000) | agent/constants.py |

---

## 14. Validation checklist

Use this to validate the flow against the running system:

- [ ] A cost question consumes exactly 2 AI credits (visible in the token badge).
- [ ] Cost answers are served from `Cost_Cache_Table` when daily coverage exists (check logs for `Cache HIT` / `Cache hit for …`).
- [ ] On cache miss, Cost Explorer is called with the **customer's** assumed-role credentials, not the platform's.
- [ ] Tips relevant to the question appear in the answer (and `tipFound` is true); they come from `ViewMyBill-CostOptimizationTips`.
- [ ] The response includes `inlineAuditScore` and `inlineAuditAction`; low-scoring answers either rewrite or ask guiding questions.
- [ ] A row appears in `Audit_Transaction_Log` with `audit_status="pending"` immediately, then flips to `completed` with an `audit_score` shortly after.
- [ ] For agent answers, `inference_trace` is populated on the log row (tools selected + invocations).
- [ ] Multi-account questions split OpenAI (cached) from AWS (agent) correctly.
