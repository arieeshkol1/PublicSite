# UAE Region Deployment (me-central-1) — Technical Design

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          GLOBAL LAYER                                        │
│  CloudFront (E2B3GXE4TJTH4Q) ─── Route 53 ─── Cognito (us-east-1_FlR2CmFu0)│
│       │                                              │                       │
│       ├── slashmycloudbill.com → us-east-1 API       │                       │
│       └── uae.slashmycloudbill.com → me-central-1 API│                       │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────┐    ┌─────────────────────────────────┐
│        us-east-1 (existing)      │    │       me-central-1 (new)         │
│                                  │    │                                  │
│  API Gateway (l2fd4h481h)        │    │  API Gateway (new ID)            │
│  ├── member-handler Lambda       │    │  ├── member-handler Lambda       │
│  ├── admin-handler Lambda        │    │  ├── admin-handler Lambda        │
│  ├── otp-handler Lambda          │    │  ├── otp-handler Lambda          │
│  ├── upload-handler Lambda       │    │  ├── upload-handler Lambda       │
│  ├── bill-analyzer Lambda        │    │  ├── bill-analyzer Lambda        │
│  └── agent-action Lambda         │    │  └── agent-action Lambda         │
│                                  │    │                                  │
│  Bedrock Agent (IDG5VJGUOZ5W)    │    │  Bedrock Agent (new ID)          │
│  Model: nova-2-lite-v1:0         │    │  Model: nova-2-lite-v1:0         │
│                                  │    │                                  │
│  SES (eshkolai.com)              │    │  SES (eshkolai.com)              │
│                                  │    │                                  │
│  DynamoDB (8 tables)             │    │  DynamoDB (8 tables)             │
│  S3 (bill storage)               │    │  S3 (bill storage)               │
│  SNS (Spot interruptions)        │    │  SNS (Spot interruptions)        │
│  EventBridge Scheduler           │    │  EventBridge Scheduler           │
│                                  │    │                                  │
│  scheduler-executor Lambda       │    │  scheduler-executor Lambda       │
│  paddle-webhook Lambda           │    │  paddle-webhook Lambda           │
└─────────────────────────────────┘    └─────────────────────────────────┘
                                              │
                                              │ Cross-region calls:
                                              ├── Cognito (us-east-1) for auth
                                              └── Pricing API (us-east-1) for pricing lookups
```

---

## 2. CloudFormation Stack Design

### 2.1 Stack File
**File**: `infrastructure/viewmybill-stack-me-central-1.yaml`

Based on the existing `viewmybill-stack.yaml` with these modifications:

| Change | Details |
|--------|---------|
| IAM Role names | Append `-me-central-1` suffix to all role names |
| Bedrock resources | Use `${AWS::Region}` instead of hardcoded `us-east-1` |
| SES Identity | Include `AWS::SES::EmailIdentity` for me-central-1 |
| Cognito references | Parameterized: `CognitoUserPoolId`, `CognitoRegion` |
| Pricing API | Lambda env var `PRICING_REGION=us-east-1` |
| Bedrock Agent env vars | Parameterized (filled after agent creation) |
| S3 bucket names | New bucket: `slashmybill-storage-me-central-1` |

### 2.2 Parameters (additions to base stack)

```yaml
Parameters:
  # ... existing params ...
  
  BedrockRegion:
    Type: String
    Default: 'me-central-1'
    Description: Region for Bedrock model invocation (local)

  SESRegion:
    Type: String
    Default: 'me-central-1'
    Description: Region for SES email sending (local)

  CognitoUserPoolId:
    Type: String
    Default: 'us-east-1_FlR2CmFu0'
    Description: Cognito User Pool ID (cross-region from us-east-1)

  CognitoClientId:
    Type: String
    Default: '3shmdb332mm8sjheopdu9sg8o4'
    Description: Cognito App Client ID

  CognitoRegion:
    Type: String
    Default: 'us-east-1'
    Description: Region where Cognito pool lives

  PricingRegion:
    Type: String
    Default: 'us-east-1'
    Description: Region for AWS Pricing API (only available in us-east-1/ap-south-1)

  BedrockAgentId:
    Type: String
    Default: 'PLACEHOLDER'
    Description: Bedrock Agent ID in me-central-1 (set after first deploy)

  BedrockAgentAliasId:
    Type: String
    Default: 'PLACEHOLDER'
    Description: Bedrock Agent Alias ID in me-central-1 (set after first deploy)
```

### 2.3 IAM Role Naming Convention

All roles get `-me-central-1` suffix:

| us-east-1 Role | me-central-1 Role |
|----------------|-------------------|
| `aws-bill-analyzer-viewmybill-role` | `aws-bill-analyzer-viewmybill-role-me-central-1` |
| `aws-bill-analyzer-upload-handler-role` | `aws-bill-analyzer-upload-handler-role-me-central-1` |
| `aws-bill-analyzer-otp-handler-role` | `aws-bill-analyzer-otp-handler-role-me-central-1` |
| `aws-bill-analyzer-admin-handler-role` | `aws-bill-analyzer-admin-handler-role-me-central-1` |
| `aws-bill-analyzer-member-handler-role` | `aws-bill-analyzer-member-handler-role-me-central-1` |
| `SlashMyBill-AgentAction-Role` | `SlashMyBill-AgentAction-Role-me-central-1` |
| `slashmybill-scheduler-executor-role` | `slashmybill-scheduler-executor-role-me-central-1` |
| `SlashMyBill-EventBridge-Scheduler-Role` | `SlashMyBill-EventBridge-Scheduler-Role-me-central-1` |
| `SlashMyBill-BedrockAgent-Role` | `SlashMyBill-BedrockAgent-Role-me-central-1` |

### 2.4 Lambda Environment Variables (me-central-1 specific)

**Member Handler Lambda** additions:
```yaml
Environment:
  Variables:
    COGNITO_REGION: 'us-east-1'
    COGNITO_USER_POOL_ID: !Ref CognitoUserPoolId
    COGNITO_CLIENT_ID: !Ref CognitoClientId
    PRICING_REGION: 'us-east-1'
    BEDROCK_REGION: 'me-central-1'
    SES_REGION: 'me-central-1'
    BEDROCK_AGENT_ID: !Ref BedrockAgentId
    BEDROCK_AGENT_ALIAS_ID: !Ref BedrockAgentAliasId
```

**OTP Handler Lambda** additions:
```yaml
Environment:
  Variables:
    SES_REGION: 'me-central-1'
```

---

## 3. Bedrock Agent Setup in me-central-1

### 3.1 Agent Creation Script

**File**: `infrastructure/create-bedrock-agent-me-central-1.py`

Mirrors `update-bedrock-agent.py` with:
- `REGION = 'me-central-1'`
- `AGENT_ROLE_NAME = 'SlashMyBill-BedrockAgent-Role-me-central-1'`
- `ACTION_LAMBDA_ARN` pointing to me-central-1 Lambda
- Same `agent-instructions.md` and `openapi-schema.json`
- Model: `us.amazon.nova-2-lite-v1:0` (or `amazon.nova-lite-v1:0` if nova-2-lite not available in me-central-1)

### 3.2 Agent Update in CI/CD

The CI/CD pipeline runs the agent update script for both regions:
```yaml
- name: Update Bedrock Agent (us-east-1)
  run: python infrastructure/update-bedrock-agent.py

- name: Update Bedrock Agent (me-central-1)
  run: python infrastructure/update-bedrock-agent-me-central-1.py
```

### 3.3 Agent IAM Role Policy (me-central-1)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": "arn:aws:bedrock:me-central-1::foundation-model/*"
    },
    {
      "Effect": "Allow",
      "Action": ["lambda:InvokeFunction"],
      "Resource": "arn:aws:lambda:me-central-1:991105135552:function:SlashMyBill-AgentAction"
    }
  ]
}
```

---

## 4. SES Configuration in me-central-1

### 4.1 CloudFormation Resource

```yaml
SESEmailIdentity:
  Type: AWS::SES::EmailIdentity
  Properties:
    EmailIdentity: eshkolai.com
    DkimSigningAttributes:
      NextSigningKeyLength: RSA_2048_BIT
```

### 4.2 DNS Records

SES in me-central-1 will generate new DKIM CNAME records. These must be added to Route 53 alongside the existing us-east-1 DKIM records. Route 53 supports multiple CNAME records for different SES regions.

### 4.3 Verification Flow

1. CloudFormation creates `AWS::SES::EmailIdentity` in me-central-1
2. SES generates 3 DKIM CNAME records
3. CI/CD script adds these to Route 53 (or manual one-time setup)
4. SES verifies domain within minutes
5. Lambdas can send email from `noreply@eshkolai.com` via me-central-1

---

## 5. S3 Bucket Strategy

### 5.1 New Bucket

**Bucket name**: `slashmybill-storage-me-central-1`

Purpose:
- Lambda deployment packages (`lambda-packages/*.zip`)
- Bill uploads (`bills/`)
- Analysis reports (`reports/`)
- CloudFormation templates (`cf-templates/`)

### 5.2 Lifecycle Rules

Same as us-east-1:
```json
{
  "Rules": [
    {"ID": "DeleteReportsAfter1Day", "Filter": {"Prefix": "reports/"}, "Status": "Enabled", "Expiration": {"Days": 1}},
    {"ID": "DeleteBillsAfter1Day", "Filter": {"Prefix": "bills/"}, "Status": "Enabled", "Expiration": {"Days": 1}}
  ]
}
```

---

## 6. CI/CD Pipeline Design

### 6.1 Workflow Structure

The existing `.github/workflows/deploy.yml` is extended with a second job:

```yaml
jobs:
  deploy-us-east-1:
    # ... existing job (unchanged) ...

  deploy-me-central-1:
    needs: deploy-us-east-1  # Sequential to avoid race conditions
    runs-on: ubuntu-latest
    env:
      AWS_REGION: me-central-1
      STORAGE_BUCKET: slashmybill-storage-me-central-1
      STACK_NAME: slashmybill-me-central-1
    steps:
      - Checkout
      - Configure AWS credentials (same role, different region)
      - Package all Lambdas → upload to me-central-1 S3
      - Deploy CloudFormation stack in me-central-1
      - Update Lambda function code in me-central-1
      - Seed DynamoDB knowledge base in me-central-1
      - Update Bedrock Agent in me-central-1
      - Ensure API Gateway routes in me-central-1
      - Deploy frontend to uae.slashmycloudbill.com
```

### 6.2 IAM: GitHubDeployRole Permissions

The existing `GitHubDeployRole` needs additional permissions for me-central-1:
- CloudFormation in me-central-1
- Lambda in me-central-1
- S3 in me-central-1
- DynamoDB in me-central-1
- Bedrock Agent in me-central-1
- SES in me-central-1
- API Gateway in me-central-1

Since the role is global, adding `Resource: "*"` or region-specific ARNs covers both regions.

### 6.3 Secrets

Same GitHub secrets used for both regions:
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD_HASH`
- `JWT_SECRET`

New secret needed:
- `BEDROCK_AGENT_ID_ME_CENTRAL_1` (set after first agent creation)
- `BEDROCK_AGENT_ALIAS_ID_ME_CENTRAL_1` (set after first agent creation)

---

## 7. Frontend Routing

### 7.1 Subdomain Approach

| Domain | Points to |
|--------|-----------|
| `slashmycloudbill.com` | us-east-1 API (`l2fd4h481h.execute-api.us-east-1.amazonaws.com`) |
| `uae.slashmycloudbill.com` | me-central-1 API (`<new-id>.execute-api.me-central-1.amazonaws.com`) |

### 7.2 Frontend Build

The `members/members.js` file has the API URL configured. For the UAE deployment:
- A separate copy of the frontend is deployed to `slashmycloudbill.com/uae/` (or a separate S3 bucket)
- The API_URL is injected at deploy time via `sed` (same pattern as existing pipeline)

### 7.3 CloudFront Configuration

Option A (recommended): Single CloudFront distribution with path-based routing:
- `/uae/*` → me-central-1 S3 bucket (UAE frontend)
- `/*` → existing S3 bucket (US frontend)

Option B: Separate CloudFront distribution for `uae.slashmycloudbill.com`

### 7.4 DNS

```
uae.slashmycloudbill.com → CNAME → CloudFront distribution domain
```

---

## 8. Data Migration (Optional)

### 8.1 Script

**File**: `infrastructure/migrate-dynamodb.py` (already exists)

Migrates data from us-east-1 tables to me-central-1 tables:
- Scans source table
- Batch-writes to target table
- Handles pagination

### 8.2 Tables to Migrate

| Table | Migrate? | Reason |
|-------|----------|--------|
| MemberPortal-Members | Optional | Only if existing users need UAE access |
| MemberPortal-Accounts | Optional | Linked to members |
| ViewMyBill-CostOptimizationTips | **Yes** | Knowledge base must be seeded |
| ViewMyBill-Leads | No | Region-specific leads |
| ViewMyBill-OTP | No | Ephemeral |
| MemberPortal-AgentFeedback | No | Region-specific |
| MemberPortal-BusinessMetrics | No | Region-specific |
| SpotSavingsLedger | No | Region-specific |

---

## 9. Cross-Region Call Patterns

### 9.1 Cognito (us-east-1)

```python
# In member-handler Lambda (me-central-1)
cognito_region = os.environ.get('COGNITO_REGION', 'us-east-1')
cognito = boto3.client('cognito-idp', region_name=cognito_region)
```

### 9.2 Pricing API (us-east-1)

```python
# In member-handler and agent-action Lambda
pricing_region = os.environ.get('PRICING_REGION', 'us-east-1')
pricing = boto3.client('pricing', region_name=pricing_region)
```

### 9.3 Bedrock (local me-central-1)

```python
# In member-handler Lambda (me-central-1)
bedrock_region = os.environ.get('BEDROCK_REGION', os.environ.get('AWS_REGION', 'us-east-1'))
bedrock = boto3.client('bedrock-runtime', region_name=bedrock_region)
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=bedrock_region)
```

### 9.4 SES (local me-central-1)

```python
# In otp-handler and member-handler Lambda
ses_region = os.environ.get('SES_REGION', os.environ.get('AWS_REGION', 'us-east-1'))
ses = boto3.client('ses', region_name=ses_region)
```

---

## 10. Lambda Code Changes

### 10.1 Region-Aware Client Initialization

The Lambda code must use environment variables for service regions instead of hardcoding. Changes needed in:

| File | Change |
|------|--------|
| `member-handler/lambda_function.py` | Use `COGNITO_REGION`, `PRICING_REGION`, `BEDROCK_REGION`, `SES_REGION` env vars for boto3 clients |
| `otp-handler/lambda_function.py` | Use `SES_REGION` env var |
| `agent-action/lambda_function.py` | Use `PRICING_REGION` env var for pricing client |
| `bill-analyzer/lambda_function.py` | Use `BEDROCK_REGION` env var |

### 10.2 Backward Compatibility

All env vars default to `us-east-1` if not set, so existing us-east-1 deployment continues working without changes:

```python
region = os.environ.get('COGNITO_REGION', 'us-east-1')
```

---

## 11. Deployment Sequence

### Phase 1: Infrastructure Setup (one-time)
1. Enable me-central-1 region in AWS account settings
2. Create S3 bucket `slashmybill-storage-me-central-1`
3. Deploy CloudFormation stack (creates DynamoDB, Lambda, API Gateway, SES, SNS)
4. Verify SES domain identity (add DKIM records to Route 53)
5. Create Bedrock Agent in me-central-1 (run `create-bedrock-agent-me-central-1.py`)
6. Note Agent ID + Alias ID → update stack parameters
7. Re-deploy stack with correct Bedrock Agent IDs
8. Seed knowledge base (`seed-dynamodb.py` targeting me-central-1)

### Phase 2: CI/CD Integration
1. Update `.github/workflows/deploy.yml` with me-central-1 job
2. Add GitHub secrets for me-central-1 Bedrock Agent IDs
3. Update `GitHubDeployRole` permissions for me-central-1 resources
4. Test pipeline end-to-end

### Phase 3: Frontend & DNS
1. Create `uae.slashmycloudbill.com` DNS record
2. Deploy frontend with me-central-1 API URL
3. Configure CloudFront for UAE subdomain
4. Test full user flow

---

## 12. Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `infrastructure/viewmybill-stack-me-central-1.yaml` | CloudFormation stack for UAE region |
| `infrastructure/update-bedrock-agent-me-central-1.py` | Bedrock Agent setup script for me-central-1 |
| `infrastructure/DEPLOY-ME-CENTRAL-1.md` | Deployment guide |
| `infrastructure/setup-ses-me-central-1.ps1` | SES DKIM verification helper |

### Modified Files
| File | Change |
|------|--------|
| `.github/workflows/deploy.yml` | Add me-central-1 deployment job |
| `member-handler/lambda_function.py` | Region-aware boto3 clients (env var based) |
| `otp-handler/lambda_function.py` | SES region from env var |
| `agent-action/lambda_function.py` | Pricing region from env var |
| `bill-analyzer/lambda_function.py` | Bedrock region from env var |
| `knowledge-base/seed-dynamodb.py` | Accept `--region` parameter |

---

## 13. Rollback Strategy

- CloudFormation stack can be deleted entirely without affecting us-east-1
- DNS record for `uae.slashmycloudbill.com` can be removed
- Bedrock Agent in me-central-1 can be deleted independently
- No shared state between regions (except Cognito users)

---

## 14. Cost Estimate (me-central-1 at rest)

| Resource | Monthly Cost |
|----------|-------------|
| DynamoDB (8 tables, PAY_PER_REQUEST) | ~$0 (pay per use) |
| Lambda (8 functions, no provisioned) | ~$0 (pay per invocation) |
| API Gateway | ~$0 (pay per request) |
| S3 bucket | ~$0.02 (Lambda packages only) |
| Bedrock Agent | ~$0 (pay per invocation) |
| SES | ~$0 (pay per email) |
| SNS | ~$0 (pay per message) |
| **Total at rest** | **< $1/month** |

The stack costs nothing until customers start using it.
