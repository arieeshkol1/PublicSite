# SlashMyBill AI Chat Q&A — Current System Architecture

*Last updated: July 7, 2026 — After pre-compute removal refactor*

## System Flow

```
Frontend (members.js)
  │
  ├─ POST /members/accounts/ai-query { accountIds, question }
  │
  ▼
Member-Handler Lambda (handle_ai_query)
  │
  ├─ 1. Auth (JWT/Cognito)
  ├─ 2. Credit check
  ├─ 3. Account ownership validation
  ├─ 4. Generate interactionId
  │
  ▼
_invoke_bedrock_agent(question, accountId, memberEmail, interactionId)
  │
  ├─ 5. Resolve provider from DynamoDB (vendor-agnostic)
  ├─ 6. Search Tips table (_search_tips)
  ├─ 7. Build enriched prompt:
  │      "[Account: X, Member: Y, Provider: Z, Today: 2026-07-07] {question}"
  │      + Tips context (if found)
  ├─ 8. Cap prompt at 3500 chars
  │
  ▼
Bedrock Agent (invoke_agent with retry)
  │
  ├─ Agent reads instructions (agent-instructions.txt)
  ├─ Agent decides which tools to call (LLM reasoning)
  ├─ Agent calls tools via action groups
  │
  ▼
Agent-Action Lambda (tool execution)
  │
  ├─ legacy_mapper.resolve_path(apiPath) → vendor-neutral tool name
  ├─ Knowledge tools (tips, pricing) → handled directly
  ├─ All others → provider_router.route_tool()
  │     │
  │     ├─ resolve_provider(accountId, memberEmail) → "aws"|"openai"|...
  │     ├─ _get_connector(provider) → AWSConnector | AIVendorConnector
  │     ├─ Check SUPPORTED_OPERATIONS
  │     ├─ Cache check (for getCostBreakdown, getMonthlyTrend)
  │     │     PK: {email}#{accountId}
  │     │     SK: {VENDOR}#{accountId}#{date}
  │     │     Staleness: 48h (per vendor_registry.json)
  │     ├─ Cache HIT → return cached data
  │     ├─ Cache MISS → call connector → write to cache → return
  │     └─ Response capped at 12KB
  │
  ▼
Agent formats answer (LLM)
  │
  ▼
Back to member-handler
  │
  ├─ 9. Quality gate (DISABLED — always skipped)
  ├─ 10. Build inferenceTrace (TraceCollector)
  ├─ 11. Generate followUpQuestions from cache data
  ├─ 12. Build chartData
  ├─ 13. Return response with interactionId
  │
  ▼
Frontend renders answer + charts + feedback widget
```

## Key Components

| Component | File | Role |
|-----------|------|------|
| Frontend | `members/members.js` | Send question, retry on 503, render answer/charts |
| API Handler | `member-handler/lambda_function.py` | Auth, credits, enrichment, Agent invocation |
| Tool Router | `agent-action/lambda_function.py` | Route tool calls to connectors |
| Provider Router | `agent-action/provider_router.py` | Resolve provider, cache-first, dispatch |
| AWS Connector | `agent-action/connectors/aws_connector.py` | AWS Cost Explorer, EC2, RDS, etc. |
| AI Vendor Connector | `agent-action/connectors/ai_vendor_connector.py` | OpenAI Org Costs/Usage API |
| Vendor Registry | `agent-action/connectors/vendor_registry.json` | Provider metadata, cache prefixes |
| Legacy Mapper | `agent-action/legacy_mapper.py` | Old API paths → neutral tool names |
| Agent Instructions | `agent-action/agent-instructions.txt` | Bedrock Agent system prompt |
| Trace Collector | `member-handler/trace_collector.py` | Capture reasoning + tool calls |
| Tips Search | `member-handler/tips_cache.py` | RAG lookup in CostOptimizationTips |
| Answer Healer | `answer-healer/lambda_function.py` | Background self-healing (Claude) |
| Audit Evaluator | `audit-evaluator/lambda_function.py` | Score answers, trigger healer |

## Design Principles (Enforced)

1. **NO hardcoded keyword lists** — The LLM (Agent) handles ALL intent classification
2. **Vendor-agnostic** — Same flow for AWS, OpenAI, Azure, GCP. No `if provider == 'x'` in member-handler
3. **Cache-first** — Tools check DynamoDB cache before calling live APIs
4. **LLM-in-the-loop** — Agent decides tools, parameters, and answer formatting
5. **Date grounding** — `Today: YYYY-MM-DD` in every prompt prevents year hallucination

## Prompt Enrichment (What member-handler injects)

```python
enriched_prompt = f"[Account: {account_id}, Member: {member_email}, Provider: {provider}, Today: {today}] {question}"
if tips_context:
    enriched_prompt += f"\n\n{tips_text}"
```

That's it. No keyword matching, no pre-computation, no intent routing.

## Tool Execution (What agent-action does)

```
getCostBreakdown  → cache check → AIVendorConnector.get_cost_breakdown() or AWSConnector.get_cost_breakdown()
getMonthlyTrend   → cache check → same connector pattern
getAIUsage        → AIVendorConnector.get_ai_usage() (dimensions: cost/units/actor)
getComputeInstances → AWSConnector.get_compute_instances() (STS AssumeRole)
getFinOpsSettings   → AWSConnector.get_finops_settings()
getPricingData      → AWS Pricing API (direct, no account needed)
getOptimizationTips → DynamoDB Tips table scan
```

## OpenAI Connector Specifics

- Timeout: **15s** per API call (was 30s)
- Pagination: max **2 pages** (was 5)
- APIs used:
  - `/v1/organization/costs` — cost by model/day
  - `/v1/organization/usage/completions` — per-actor token usage
- Credentials: API key from DynamoDB → KMS decrypt
- Supported tools: `getCostBreakdown`, `getAIUsage`, `getMonthlyTrend`

## Cache Schema

```
Table: Cost_Cache_Table
PK: {memberEmail}#{accountId}
SK: {VENDOR}#{accountId}#{YYYY-MM-DD}
    Examples: AWS#123456789012#2026-07-05
              OPENAI#openai-accc537d369e#2026-06-15
Fields: cost_amount, service_breakdown, cached_at
Legacy SK formats (read-only fallback): DAILY#, OPENAI_DAILY#, COST#
Staleness: 48h (configurable per vendor in vendor_registry.json)
```

## Quality Gate (DISABLED)

```python
_gate_enabled = os.environ.get('AUDIT_QUALITY_GATE_ENABLED', 'false') == 'true'
_skip_gate = not _gate_enabled  # True → entire gate skipped
```

The gate code remains in the codebase but never executes. The `needsClarification` response path is unreachable.

## Self-Healing Pipeline

```
Audit_Transaction_Log (DynamoDB Stream)
  → audit-evaluator Lambda (scores answer, 0-100)
    → if score < 50: invoke answer-healer async
      → answer-healer:
        1. Gap analysis (Claude)
        2. Research certified sources
        3. Generate corrected tip (Claude)
        4. Upsert to Tips table
        5. Re-answer via Agent
        6. Score + write healed_answer to audit log
```

**Status**: Deploy step for DynamoDB Stream → audit-evaluator mapping was added but needs AWS Console verification.

## Feedback Loop

```
User clicks 👍/👎 → POST /members/accounts/ai-feedback
  → handle_ai_feedback():
    - Validate fields
    - Derive relatedService from question keywords (SERVICE_KEYWORD_MAP)
    - Write to MemberPortal-AgentFeedback table
    - If positive: save tip with confidenceTag: high-confidence
  → _search_tips() sorts high-confidence first
  → Agent prompt annotates with [Validated] label
```

## Timeouts & Limits

| Layer | Timeout | Notes |
|-------|---------|-------|
| API Gateway | 29s | Hard limit |
| handle_ai_query ThreadPoolExecutor | 27s | Returns "taking longer" message |
| Bedrock Agent runtime read_timeout | 150s | For agent orchestration stream |
| OpenAI API per-request | 15s | Reduced from 30s |
| Agent retry | 3 attempts | Linear backoff 1s, 2s |
| Prompt length | 3500 chars | Prevents Bedrock EventStreamError |
| Tool response | 12KB | Trimmed if exceeded |
