# Tips Drilldown ("Check") Validation

**Question validated:** *Does every tip have a working drilldown — in OpenAPI format, through the relevant connection — so the system can drill into the specific tip and return live data?*

**Source data:** `ViewMyBill-CostOptimizationTips` export (`tips-20260623-184521.csv`, 523 tips).
**Drilldown engine:** the Bedrock Agent action group defined in `agent-action/openapi-schema.json`, executed by `agent-action/lambda_function.py` against the customer's connection (assumed-role credentials).

---

## 1. What the system can actually execute

The action group exposes **11 OpenAPI operations, and every one is AWS-only** (each requires a *12-digit AWS account ID*):

| operationId | Returns | Service coverage |
|-------------|---------|------------------|
| getCostData | Cost by service + daily trend (supports `usageTypeBreakdown` + `serviceFilter`) | Any AWS service (cost level) |
| getMonthlyComparison | Month-over-month cost | Any AWS service (cost level) |
| getAWSPricing | Live AWS price list | Any AWS service (rates) |
| getBudgets | AWS Budgets + forecast | Budgets |
| getFinOpsSettings | FinOps healthcheck | Account-level |
| getEC2Instances | EC2 list + CPU | EC2 |
| getRDSInstances | RDS list + metrics | RDS |
| getLambdaFunctions | Lambda list + metrics | Lambda |
| getS3Buckets | S3 buckets + lifecycle | S3 |
| getEBSVolumes | EBS volumes | EBS |
| getNetworkResources | NAT GW / Elastic IP / VPC endpoints | NAT Gateway, Elastic IP, VPC, Data Transfer |

There are **no Azure, GCP, or OpenAI operations** in the schema.

---

## 2. The core inconsistency

The tip records describe their "check" in two free-text fields — `automatedCheck` and `drilldownApis` — and these are **CLI strings** (`aws ...`, `az ...`, `gcloud ...`, `bq ...`), e.g.:

```
automatedCheck : "aws apigateway get-stages --rest-api-id <api-id>"
drilldownApis  : ["az aks list", "az monitor metrics list (node_cpu_usage)"]
```

The agent **cannot execute CLI commands**. It can only call the 11 OpenAPI operations above. So `automatedCheck` / `drilldownApis` are *documentation*, not an executable drilldown. Whether a tip can actually drill down and return data is determined by **service + provider mapping to one of the 11 operations**, not by these fields.

---

## 3. Coverage result (per tip)

| Class | Meaning | Count | % |
|-------|---------|-------|---|
| **FULL** | AWS + a resource-level operation exists for the service (real check returns resource data) | 99 | 19% |
| **COST_ONLY** | AWS, no resource operation, but `getCostData(serviceFilter)` returns spend | 132 | 25% |
| **NONE** | non-AWS — no OpenAPI operation exists, so no drilldown returns live data | 292 | 56% |

**NONE breakdown:** Azure 154, GCP 119, OpenAI 19.

**AWS COST_ONLY** (resource-level check not available — only cost drilldown): EKS, SageMaker, Glue, ELB, SNS, AppSync, EventBridge, GuardDuty, CloudFront, ElastiCache, Kinesis, MSK, OpenSearch, WAF, API Gateway, Athena, DynamoDB, ECS, EMR, KMS, Redshift, EFS, and ~20 more.

Separately, **231 tips have no `check` content at all** (no `automatedCheck` and no `drilldownApis`): Azure 113, GCP 99, OpenAI 16, AWS 3.

---

## 4. Gaps (what's missing / inconsistent)

1. **No drilldown path for 292 non-AWS tips (56%).** Azure/GCP/OpenAI tips cannot be drilled to live data through the action group — there is no Azure/GCP/OpenAI OpenAPI operation. (Cost-level data *does* exist for these providers in `Cost_Cache_Table` / invoices, but that is a different connection than the agent action group, and it is service-total only — not the resource-level check the tip describes.)
2. **Check fields are not executable.** `automatedCheck` / `drilldownApis` are CLI text, not an operationId + parameters. Nothing maps a tip to a callable operation, so the agent can't deterministically "run the check for this tip."
3. **132 AWS tips are cost-only.** Their tip text implies a resource inspection (e.g., "find idle EKS nodes", "unused WAF rules") but no resource operation exists — only `getCostData`.
4. **231 tips have no check content**, so even as documentation there's nothing to drive a drilldown.

---

## 5. Recommended fix (proposed, not yet applied)

To make "every tip is drillable and returns data" true and verifiable, I propose adding an explicit, executable mapping to each tip and closing the operation gaps:

- **Add a `checkOperation` field** to every tip: the OpenAPI `operationId` (one of the 11) plus the parameters needed (e.g. `{ "operationId": "getEBSVolumes" }` or `{ "operationId": "getCostData", "serviceFilter": "Amazon Elastic Kubernetes Service", "usageTypeBreakdown": true }`). This replaces ambiguous CLI text with something the agent can actually call.
- **AWS FULL/COST_ONLY tips:** map to the resource op where it exists, else to `getCostData(serviceFilter=<CUR service name>)`. The `serviceKey` field already holds the CUR service name for many tips, which is exactly what `serviceFilter` needs.
- **Non-AWS tips (the 292):** either
  - (a) mark `checkOperation` as a cost-only drilldown that reads `Cost_Cache_Table` for that provider/service (works today for all providers), or
  - (b) extend the action group with Azure/GCP/OpenAI operations (larger effort).
- **231 no-check tips:** at minimum assign the cost-level `checkOperation` so they return spend.

---

## 6. Artifacts

- `tips-drilldown-validation.json` — full per-tip classification (cloud, service, tipId, class, mapped operation, whether check content exists).
- Validation scripts: `_validate_drilldown.py`, `_analyze_checks.py`.

> Note on "make sure it is returning data": confirming a *live* 200-with-data response requires calling each operation against a connected AWS account with real credentials. That is a live, per-account call and was not executed here. This validation confirms the *capability* mapping (which tips can be served by an implemented operation) and that all 11 operations are routed/implemented in `agent-action/lambda_function.py`.
