# UAE Region Deployment (me-central-1) — Requirements

## Overview
Deploy the full SlashMyBill stack to the AWS Middle East (UAE) region `me-central-1` as a parallel deployment alongside the existing `us-east-1` stack. The existing US region remains fully operational — this is an additive deployment, not a migration.

## Motivation
- Reduce latency for Middle East customers
- Data residency compliance for UAE-based organizations
- Business expansion into the Middle East market
- Redundancy — two independent regional deployments

---

## Functional Requirements

### FR-1: Full Stack Deployment in me-central-1
The following resources must be deployed in `me-central-1`:
- **Lambda Functions**: bill-analyzer, upload-handler, otp-handler, admin-handler, member-handler, agent-action, scheduler-executor, paddle-webhook
- **DynamoDB Tables**: ViewMyBill-Leads, ViewMyBill-CostOptimizationTips, ViewMyBill-OTP, MemberPortal-Members, MemberPortal-Accounts, MemberPortal-AgentFeedback, MemberPortal-BusinessMetrics, SpotSavingsLedger
- **API Gateway (HTTP)**: Full route set matching us-east-1
- **S3 Bucket**: Lambda packages + bill storage
- **EventBridge Scheduler**: For scheduled actions
- **SNS Topic**: SlashMyBill-SpotInterruptions
- **Bedrock Agent**: New agent with same instructions + schema
- **SES Identity**: `eshkolai.com` verified in me-central-1

### FR-2: Service Deployment Strategy
| Service | Region | Strategy |
|---------|--------|----------|
| Lambda (all 8 functions) | me-central-1 | Deploy locally |
| DynamoDB (all 8 tables) | me-central-1 | Deploy locally |
| API Gateway (HTTP) | me-central-1 | Deploy locally |
| S3 | me-central-1 | Deploy locally |
| Bedrock (Nova model) | me-central-1 | Deploy locally (available since Sep 2025) |
| Bedrock Agent | me-central-1 | Create new agent locally with same config |
| SES | me-central-1 | Verify identity locally (available since Jun 2025) |
| EventBridge Scheduler | me-central-1 | Deploy locally |
| SNS | me-central-1 | Deploy locally |
| Cognito User Pool | us-east-1 | Reuse existing pool cross-region (no user migration) |
| Pricing API | us-east-1 | No regional endpoint in me-central-1; cross-region call (cached, no latency impact) |
| Cost Explorer | Global | No change needed |
| CloudFront | Global | No change needed |
| Route 53 | Global | No change needed |

### FR-3: Bedrock Agent in me-central-1
- A new Bedrock Agent is created in me-central-1 with the same:
  - Agent instructions (`agent-action/agent-instructions.md`)
  - OpenAPI schema (`agent-action/openapi-schema.json`)
  - Action group Lambda (agent-action deployed in me-central-1)
- New Agent ID and Alias ID will be generated — stored as Lambda environment variables
- The agent-action Lambda in me-central-1 reads DynamoDB tips from me-central-1
- Model: `us.amazon.nova-2-lite-v1:0` (or regional equivalent available in me-central-1)

### FR-4: SES Identity in me-central-1
- Verify `eshkolai.com` domain identity in me-central-1
- DKIM records are already in Route 53 (global) — SES verification should succeed automatically
- All email-sending Lambdas (OTP, notifications) use the local me-central-1 SES endpoint
- Sender: `noreply@eshkolai.com`
- CloudFormation includes `AWS::SES::EmailIdentity` resource for me-central-1

### FR-5: Shared Cognito Authentication
- The Cognito User Pool remains in us-east-1 (`us-east-1_FlR2CmFu0`)
- All Lambdas in me-central-1 authenticate against the same pool cross-region
- No user re-registration required
- Token validation works cross-region (JWT is region-agnostic)
- Lambda env vars: `COGNITO_REGION=us-east-1`, `COGNITO_USER_POOL_ID=us-east-1_FlR2CmFu0`

### FR-6: Independent Data Store
- DynamoDB tables in me-central-1 are independent (not replicated from us-east-1)
- New members signing up via the UAE endpoint get their data stored in me-central-1
- Existing us-east-1 data is NOT automatically migrated (separate migration script provided)

### FR-7: Dedicated API Gateway Endpoint
- A new API Gateway is created in me-central-1
- Produces a new endpoint URL (e.g., `xxxxxxxx.execute-api.me-central-1.amazonaws.com`)
- All routes from us-east-1 are replicated (member, admin, OTP, upload, analyze)

### FR-8: CI/CD Pipeline Extension
- GitHub Actions workflow deploys to me-central-1 in addition to us-east-1
- Lambda packages uploaded to a me-central-1 S3 bucket
- CloudFormation stack deployed in me-central-1
- Lambda function code updated in me-central-1
- Bedrock Agent updated in me-central-1
- Knowledge base seeded in me-central-1

### FR-9: Frontend Region Routing
- The frontend (members.js) must be able to target the me-central-1 API
- Options: (a) separate subdomain (e.g., `uae.slashmycloudbill.com`), (b) geo-routing via CloudFront, or (c) manual region selector in settings
- Initial approach: separate deployment at `uae.slashmycloudbill.com` pointing to me-central-1 API

### FR-10: IAM Role Naming
- IAM roles in me-central-1 must have unique names (suffixed with `-me-central-1`) to avoid conflicts with us-east-1 roles in the same account

### FR-11: Knowledge Base Seeding
- The DynamoDB `ViewMyBill-CostOptimizationTips` table in me-central-1 must be seeded with the same optimization tips as us-east-1

---

## Non-Functional Requirements

### NFR-1: No Disruption to Existing Stack
- The us-east-1 stack must remain fully operational during and after the UAE deployment
- No changes to existing resource names, endpoints, or configurations in us-east-1

### NFR-2: Same Feature Parity
- The me-central-1 deployment must support all features available in us-east-1:
  - Bill analysis, waste scan, resize server, cluster optimize, spot management
  - Scheduler, budgets, tag policy, healthcheck
  - AI chat (via local Bedrock in me-central-1)
  - Email notifications (via local SES in me-central-1)

### NFR-3: Latency
- Only cross-region call: Cognito auth (~100-150ms added) and Pricing API (cached)
- Bedrock, SES, DynamoDB all local — no cross-region latency for core operations

### NFR-4: Cost Efficiency
- Use PAY_PER_REQUEST billing for all DynamoDB tables (no provisioned capacity)
- Lambda memory sizes match us-east-1 configuration
- No provisioned concurrency initially

### NFR-5: Security
- Cognito cross-region requires explicit region in boto3 client initialization
- Pricing API cross-region uses IAM role-based authentication
- All other services are local — standard IAM role access

---

## Constraints

1. **Same AWS Account**: Both regions deploy under account `991105135552`
2. **IAM is Global**: Role names must be unique across regions — use `-me-central-1` suffix
3. **Cognito stays in us-east-1**: User Pool cannot be duplicated without re-registration; cross-region auth is the only viable approach
4. **Pricing API**: Only available in us-east-1 and ap-south-1 — must call cross-region
5. **CloudFormation EarlyValidation**: The same hook issue exists — use `continue-on-error: true` in CI/CD
6. **GitHub Actions**: Single workflow file deploys to both regions sequentially
7. **Bedrock Agent ID**: New agent in me-central-1 will have a different ID/Alias than us-east-1 — frontend must use the correct one per region

---

## Out of Scope (Phase 1)
- DynamoDB Global Tables (cross-region replication)
- Active-active failover between regions
- Geo-based DNS routing (CloudFront geo-restriction)
- Automatic data migration from us-east-1 to me-central-1 (provided as optional script only)
- Cognito User Pool in me-central-1

---

## Acceptance Criteria

1. CloudFormation stack deploys successfully in me-central-1 with all resources
2. API Gateway in me-central-1 responds to all member/admin routes
3. Member can sign up, log in (via Cognito cross-region), and use all features
4. AI chat works via local Bedrock Agent in me-central-1
5. Email notifications work via local SES in me-central-1
6. Waste scan, resize, cluster optimize all function correctly
7. GitHub Actions deploys to both us-east-1 and me-central-1 on push to main
8. us-east-1 stack remains unaffected
9. Bedrock Agent in me-central-1 responds correctly to all 13 tool invocations
