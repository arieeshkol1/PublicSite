# SlashMyBill AI Chat Q&A — Architecture & Flow

## How It Should Work (Design Intent)

```
User Question → Member-Handler → Bedrock Agent → Agent-Action Lambda → Provider Router → Connector → Data Source
                     ↓                                                                                    ↓
              [Enrich prompt:                                                                    [Cache-first,
               Account, Provider,                                                                live API fallback]
               Today's date, Tips]                                                                       ↓
                     ↓                                                                           Response ← ←
              Bedrock Agent decides                                                                       
              which tools to call ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←
                     ↓
              Agent formats answer
                     ↓
              Response → Frontend
```

## Core Principle: VENDOR-AGNOSTIC, LLM-DRIVEN

The Bedrock Agent (LLM) is the ONLY decision-maker for:
- Which tools to call
- What parameters to use (dates, service names, dimensions)
- How to format the answer

The member-handler MUST NOT:
- Use hardcoded keyword lists to detect intent
- Branch logic based on provider-specific words
- Pre-compute answers based on static pattern matching

The member-handler SHOULD ONLY:
- Provide context: Account ID, Provider, Today's date, Tips
- Let the Agent autonomously select tools and act

---

## Current Flow (Step by Step)

### 1. Frontend (`members.js` → `askAI()`)

```
POST /members/accounts/ai-query
Body: { accountIds: ["openai-accc537d369e"], question: "what was the monthly cost for june?" }
```

- Single-account only
- Retry on 503 (3s, 6s backoff)
- 27s timeout before showing "taking longer than expected"

### 2. Member-Handler (`handle_ai_query()`)

1. Validate JWT token
2. Check AI credits
3. Validate account ownership
4. Generate `interactionId`
5. Call `_invoke_bedrock_agent(question, accountId, memberEmail, interactionId)`

### 3. Prompt Enrichment (`_invoke_bedrock_agent()`)

**What it does correctly:**
- Resolves provider from DynamoDB (no hardcoded logic)
- Searches Tips table for relevant optimization tips
- Injects: `[Account: X, Member: Y, Provider: Z, Today: 2026-07-06]`
- Appends tips context

**What it does WRONG (anti-patterns):**
- **Hardcoded keyword lists** for intent detection:
  - `_BREAKDOWN_WORDS` — detects "cost of", "how much", "breakdown"
  - `_SAVINGS_KEYWORDS` — detects "save money", "reduce cost"
  - `_TOKEN_KEYWORDS` — detects "token", "tokens"
  - `_EFFICIENCY_KEYWORDS` — detects "efficient", "health"
  - `_COMPARISON_KEYWORDS` — detects "compare", "versus"
  - `_FORECAST_KEYWORDS` — detects "forecast", "estimate"
  - `_SERVICE_NAMES` — hardcoded map of 20 AWS service names
- **Pre-computes answers** from cache based on detected keywords, then injects them as `[PRE-COMPUTED...]` blocks that tell the Agent what to say
- This bypasses the Agent's tool selection — the Agent becomes a formatter, not a reasoner

### 4. Bedrock Agent Invocation

- Model: Defined by Bedrock Agent configuration
- Input: enriched prompt (capped at 3500 chars)
- Timeout: `read_timeout=150s`
- Retry: Up to 3 attempts on transient EventStream errors
- Trace collection: `TraceCollector` captures tool calls and reasoning

### 5. Agent-Action Lambda (Tool Execution)

When the Agent decides to call a tool:

```
Agent → agent-action Lambda
  → legacy_mapper.resolve_path(apiPath) → vendor-neutral tool name
  → _execute_tool(toolName, accountId, memberEmail, params)
    → Knowledge tools (getOptimizationTips, getPricingData): handled directly
    → All others: provider_router.route_tool(toolName, accountId, memberEmail, params)
      → resolve_provider(accountId, memberEmail) → "aws" | "openai" | "azure" | ...
      → _get_connector(provider) → AWSConnector | AIVendorConnector | ...
      → Check SUPPORTED_OPERATIONS
      → For cacheable tools (getCostBreakdown, getMonthlyTrend): check Cost_Cache_Table first
      → Dispatch to connector method
      → Write to cache on success
```

### 6. Provider Router Cache Logic

```
Cache Key: PK = "{memberEmail}#{accountId}", SK = "{VENDOR}#{accountId}#{YYYY-MM-DD}"
Staleness: 48 hours (configurable per vendor in vendor_registry.json)
Fallback: Legacy SK prefixes (DAILY#, OPENAI_DAILY#, COST#)
```

For `getCostBreakdown`:
- Returns last ~60 days of daily costs + service breakdown
- Aggregates into totalCost30Days, topServices, dailyCosts, forecastHint

### 7. AI Vendor Connector (OpenAI, Anthropic)

Supported tools: `getCostBreakdown`, `getAIUsage`, `getMonthlyTrend`

- `getCostBreakdown`: Calls OpenAI `/v1/organization/costs` API (15s timeout, max 2 pages)
- `getAIUsage`: Calls both `/v1/organization/costs` and `/v1/organization/usage/completions` (per-actor, per-model token data)
- Credentials: API key from DynamoDB → KMS decrypt

### 8. Response Flow Back

```
Agent answer → inline audit gate (DISABLED) → build inferenceTrace → build followUpQuestions → build chartData → return to frontend
```

---

## Known Problems

| Problem | Root Cause | Impact |
|---------|-----------|--------|
| Agent uses wrong year (2023 instead of 2026) | `Today:` now injected in prompt but Agent may still hallucinate from training data | Auth errors on OpenAI API |
| Token questions timeout on OpenAI | `getAIUsage` calls 2 OpenAI API endpoints sequentially (15s each = 30s total) within Agent's orchestration window | "Taking longer than expected" |
| Pre-compute keyword lists are brittle | Static lists miss variations, create false positives | Wrong answers, violations of vendor-agnostic principle |
| Efficiency questions return vague answers | Agent only calls `getFinOpsSettings` (not `getCostBreakdown`) | Low audit scores |
| Quality gate DISABLED but clarification still appears | Legacy code paths from old gate remain (e.g., `needsClarification: true`) | "I need more detail" responses |
| AI vendor accounts treated differently | `_TOKEN_KEYWORDS` + `_is_ai_vendor_account` creates AI-specific branching | Violates vendor-neutral principle |

---

## How It SHOULD Work (Target Architecture)

### Principle: Remove ALL keyword-based pre-compute

The member-handler should:
1. Resolve provider
2. Search tips
3. Build prompt: `[Account: X, Member: Y, Provider: Z, Today: YYYY-MM-DD] {question}`
4. Append tips (if found)
5. Send to Agent — DONE

The **Agent** (via its instructions) decides which tools to call. The **tools** (via provider_router) handle cache-first logic. The **connector** handles API calls with proper timeouts.

### What to Keep

- Provider resolution from DynamoDB ✓
- Tips search and injection ✓  
- `Today:` date injection ✓
- Provider_router cache-first logic ✓
- 15s timeout + 2-page pagination limit on OpenAI connector ✓
- `agent-instructions.txt` tool selection guide ✓

### What to Remove

All pre-compute blocks in `_invoke_bedrock_agent()`:
- `_SERVICE_NAMES` dict and service detection logic
- `_BREAKDOWN_WORDS` and service-breakdown pre-compute
- `_SAVINGS_KEYWORDS` and savings pre-compute
- `_TOKEN_KEYWORDS` and token pre-compute
- `_EFFICIENCY_KEYWORDS` and efficiency pre-compute
- `_COMPARISON_KEYWORDS` and comparison pre-compute
- `_FORECAST_KEYWORDS` and forecast pre-compute

### Why Cache-First Still Works Without Pre-Compute

When the Agent calls `getCostBreakdown` with correct dates:
1. `agent-action` Lambda receives the call
2. `provider_router.route_tool()` checks cache FIRST
3. If cache hit → returns cached data immediately (no live API call)
4. If cache miss → calls live API → writes to cache → returns

This is IDENTICAL for AWS and OpenAI. No keyword matching needed.

### How to Fix the Year Hallucination

The `Today: 2026-07-06` injection (already deployed) gives the Agent the current date. The Agent instructions already say:
> "Extract these values and pass them to every tool call"

If the Agent still uses wrong dates, the fix is in `agent-instructions.txt` — add:
```
The current date is provided in [Today: YYYY-MM-DD]. When the user says "June" without a year, 
use the current year. If that month hasn't happened yet in the current year, use the previous year.
NEVER use a year from your training data (e.g., 2023). Always derive the year from Today.
```

---

## Files Reference

| File | Role |
|------|------|
| `members/members.js` | Frontend: sends question, handles response, renders charts |
| `member-handler/lambda_function.py` | API handler: auth, credits, enrichment, Agent invocation |
| `agent-action/lambda_function.py` | Tool executor: routes tool calls to connectors |
| `agent-action/provider_router.py` | Provider resolution + cache-first + connector dispatch |
| `agent-action/connectors/ai_vendor_connector.py` | OpenAI/Anthropic API calls |
| `agent-action/connectors/aws_connector.py` | AWS API calls (STS assume role) |
| `agent-action/legacy_mapper.py` | Maps old API paths → vendor-neutral tool names |
| `agent-action/agent-instructions.txt` | Bedrock Agent system prompt |
| `member-handler/trace_collector.py` | Captures Agent reasoning + tool calls for audit |
| `answer-healer/lambda_function.py` | Background self-healing (researches + corrects Tips) |
| `audit-evaluator/lambda_function.py` | Scores answers, triggers healer if score < threshold |
