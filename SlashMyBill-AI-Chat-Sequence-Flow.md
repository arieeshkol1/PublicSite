# SlashMyBill AI Chat — Question Processing Sequence Flow

## Document Version
- **Last Updated:** June 6, 2026
- **Author:** Architecture Team
- **Status:** Current Implementation

---

## 1. Overview

When a user types a question in the SlashMyBill Chat tab and clicks Send, the system executes a multi-stage pipeline that classifies the question, gathers relevant cloud data, searches the knowledge base for tips, and generates an AI-powered response using Amazon Bedrock Nova.

---

## 2. End-to-End Sequence Diagram

```
User Browser → API Gateway → Member-Handler Lambda → [Pipeline] → Bedrock Nova → Response
```

### Actors
| Actor | Role |
|-------|------|
| **User Browser** | Frontend (members.js) sends POST request |
| **API Gateway** | HTTP API (l2fd4h481h.execute-api.us-east-1.amazonaws.com) |
| **Member-Handler Lambda** | Main processing Lambda (aws-bill-analyzer-member-api) |
| **DynamoDB** | Members table, Accounts table, Cost Cache table, Tips table |
| **AWS STS** | Cross-account role assumption |
| **AWS Cost Explorer** | Cost and usage data |
| **AWS CloudWatch** | Resource metrics (CPU, invocations, etc.) |
| **AWS EC2/RDS/Lambda/S3** | Resource inventory APIs |
| **Bedrock Nova** | AI model (us.amazon.nova-2-lite-v1:0) |
| **Transaction Logger** | Audit trail to Audit_Transaction_Log table |

---

## 3. Detailed Step-by-Step Flow

### Step 1: Frontend Sends Request
- **Endpoint:** `POST /members/accounts/ai-query`
- **Payload:** `{ accountIds: ["714045115933"], question: "..." }`
- **Headers:** Bearer token (Cognito access token)
- **Timeout:** Frontend waits up to 30 seconds

### Step 2: Authentication (validate_token)
1. Extract Bearer token from Authorization header
2. Call Cognito `GetUser` with the access token
3. Extract member email from user attributes
4. If Cognito fails, fall back to legacy JWT validation

### Step 3: Credit Check (_check_and_consume_credits)
1. Read member record from DynamoDB (MemberPortal-Members)
2. Check `aiCreditsUsed` vs tier limit (Free: 100, Growth: 300, Scale: 1500)
3. If insufficient credits → return 403 with token info
4. Consume 2 credits (AI_QUERY_CREDIT_COST) atomically

### Step 4: Account Ownership Verification
1. Query MemberPortal-Accounts by memberEmail
2. Verify all requested accountIds belong to the authenticated user
3. If lateral access detected → return 403

### Step 5: Route Selection
- **Multi-account (>1 accountId):** → `_invoke_multi_account()`
- **Single account:** → `_invoke_direct_model()`

### Step 6: Intent Classification (_classify_intent)
- **Engine:** Keyword-based pattern matching (no LLM, <50ms)
- **Categories:** ec2, rds, s3, lambda, commitments, cost-general, network, storage, compute
- **Output:** Set of intent categories that control which APIs to call
- **Example:** "what about RIs and SPs?" → `{'commitments', 'cost-general'}`

### Step 7: Provider Detection (_route_to_connector)
1. Read account record from DynamoDB
2. Detect cloud provider (aws/azure/gcp) from `cloudProvider` field
3. Return provider type and credential config

### Step 8: Tips Search (_search_tips)
1. Query ViewMyBill-CostOptimizationTips DynamoDB table
2. Match question keywords against tip titles/descriptions
3. Filter by provider (aws/azure/gcp)
4. Return top 3 relevant tips for prompt context

### Step 9: Data Gathering (_gather_account_data)
- **Time Budget:** 14 seconds maximum (leaves 12s for Bedrock)
- **Time Guard:** `_time_left()` function checked before each slow API

#### 9a. STS AssumeRole
1. Compute role ARN: `arn:aws:iam::{accountId}:role/SlashMyBill-{accountId}`
2. Compute ExternalId: SHA-256 of member email
3. Call `sts:AssumeRole` → get temporary credentials

#### 9b. Cost Explorer (always runs first — fast with cache)
1. **Cache Check:** Query Cost_Cache_Table for `{email}#{accountId}` with DAILY# prefix
2. **Cache HIT (25+ days):** Use cached service breakdown, skip live CE
3. **Cache MISS:** Call `ce:GetCostAndUsage` (monthly by service, last 30 days)
4. **Daily Trend:** Call `ce:GetCostAndUsage` (daily, last 7 days)
5. **Usage Breakdown:** For top services matching the question, fetch per-usage-type breakdown

#### 9c. Monthly Cost Forecast (computed from daily data)
- Formula: `(7-day avg daily cost × days in current month) + recurring fees`
- Per-service forecast included in `cost_forecast.by_service`

#### 9d. Conditional API Calls (based on intent + time budget)
| API | Condition | Time Gate |
|-----|-----------|-----------|
| EC2 DescribeInstances | Intent includes `ec2_describe_instances` | `_time_left() > 5` |
| RDS DescribeDBInstances | Intent includes `rds_describe_instances` | `_time_left() > 3` |
| Lambda ListFunctions | Intent includes `lambda_list_functions` | Always (fast) |
| S3 ListBuckets | Intent includes `s3_list_buckets` | `_time_left() > 2` |
| NAT Gateways | Intent includes `nat_gateways` | `_time_left() > 3` |
| SP/RI Coverage | Intent includes `sp_ri_coverage` | `_time_left() > 3` |
| Pricing API | Always (last) | `_time_left() > 4` |

#### 9e. CloudWatch Metrics (per discovered resources)
- Lambda: invocations, duration, errors per function (30 days)
- EC2: CPU utilization per instance (30 days)
- RDS: CPU, connections per DB (30 days)

#### 9f. Cost Efficiency Calculation
- Compute potential savings from: EBS waste, idle EIPs, over-provisioned instances
- Calculate efficiency score: `(1 - savings/total) × 100`

### Step 10: Prompt Assembly
1. Serialize gathered data as JSON (trimmed to ~10KB max)
2. Build prompt with:
   - System rules (anti-hallucination, pricing, platform features)
   - Tip citations from Step 8
   - User question
   - Account data from Step 9

### Step 11: Bedrock Model Invocation
- **Model:** `us.amazon.nova-2-lite-v1:0`
- **Max Tokens:** 3000
- **Temperature:** 0.3
- **Timeout:** 27 seconds (enforced by ThreadPoolExecutor)
- **If timeout:** Return generic "analysis taking longer" message

### Step 12: Response Assembly
1. Parse model output text
2. Build chart data (service costs bar, daily trend line, efficiency doughnut)
3. Include: answer, interactionId, commands list, tips found, chart data, top services
4. Inject AI credits remaining

### Step 13: Transaction Logging (@transaction_log decorator)
1. Capture request/response payloads (sanitized, truncated to 10KB)
2. Record duration, status, user email, function name
3. Write to Audit_Transaction_Log DynamoDB table
4. Conditional write (`attribute_not_exists`) prevents duplicates

### Step 14: Response to Client
- **Status:** 200 (always, even for errors — error in body)
- **Headers:** CORS enabled
- **Body:** JSON with answer, charts, commands, credits

---

## 4. Multi-Account Flow Differences

When `accountIds.length > 1`:
1. Detect provider per account via _route_to_connector
2. Process all accounts **concurrently** (ThreadPoolExecutor, max 3 workers)
3. Each account runs Steps 9a-9f independently
4. Merge results: aggregate cost_by_service, daily trends, monthly trends
5. Use multi-account prompt with per-account breakdown
6. Build aggregate charts

---

## 5. Performance Characteristics

| Metric | Target | Actual (typical) |
|--------|--------|-----------------|
| Cache HIT + simple question | <8s | 5-12s |
| Cache MISS (full CE fetch) | <15s | 15-25s |
| Multi-account (2 accounts) | <15s | 10-20s |
| Timeout threshold | 27s | Lambda returns fallback |
| Bedrock model latency | 3-8s | 3-12s |

---

## 6. Error Handling

| Error | Handling |
|-------|----------|
| Auth failure | 401 returned immediately |
| Account not owned | 403 returned |
| STS AssumeRole fails | 403 with guidance to redeploy CFN |
| API timeout (27s) | Generic "taking longer" message |
| Bedrock model error | "AI analysis error" with error detail |
| Individual API fails | Silently skipped, data gathered from other sources |
| Transaction logger fails | Swallowed (never affects response) |

---

## 7. Key Configuration

| Setting | Value |
|---------|-------|
| Lambda function | aws-bill-analyzer-member-api |
| API Gateway | l2fd4h481h (HTTP API, $default stage) |
| Bedrock Model | us.amazon.nova-2-lite-v1:0 |
| Region | us-east-1 |
| Lambda timeout | 30s |
| API Gateway timeout | 29s |
| Code timeout | 27s (ThreadPoolExecutor) |
| Max gather time | 14s |
| Credit cost | 2 per query |
| Max response tokens | 3000 |

---

## 8. Files Involved

| File | Role |
|------|------|
| `members/members.js` | Frontend: sends question, renders response |
| `member-handler/lambda_function.py` | Main handler: routing, data gathering, prompt |
| `member-handler/intent_classifier.py` | Question → intent category mapping |
| `member-handler/sts_assume_role.py` | Cross-account credential handling |
| `member-handler/provider_registry.py` | Multi-cloud provider config |
| `member-handler/cache_service.py` | DynamoDB cost cache read/write |
| `member-handler/tip_citation.py` | Tips formatting for prompt |
| `transaction_logger.py` | Audit logging decorator |
| `knowledge-base/aws-cost-optimization-tips.json` | Tips knowledge base |
