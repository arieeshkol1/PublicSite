# SlashMyBill — Deploy to me-central-1 (UAE)

## Overview

This guide deploys the full SlashMyBill stack to `me-central-1` (UAE) as a parallel
deployment alongside the existing `us-east-1` stack.

**What runs locally in me-central-1:**
- All 8 Lambda functions
- All 8 DynamoDB tables
- API Gateway (HTTP)
- Bedrock Agent + Nova model
- SES (email sending)
- S3, SNS, EventBridge Scheduler

**What stays cross-region (us-east-1):**
- Cognito User Pool (shared, no re-registration)
- AWS Pricing API (only available in us-east-1)

---

## Prerequisites

1. **Enable me-central-1** in AWS Account Settings > Regions
2. **AWS CLI** configured with credentials for account `991105135552`
3. **Python 3.12** installed

---

## Step 1: Create S3 Bucket

```powershell
aws s3api create-bucket `
  --bucket slashmybill-storage-me-central-1 `
  --region me-central-1 `
  --create-bucket-configuration LocationConstraint=me-central-1
```

## Step 2: Upload Lambda Packages

Build and upload all Lambda packages (or let CI/CD handle this):

```powershell
# From repo root
pip install -r bill-analyzer/requirements.txt -t .build-bill-analyzer/
cp bill-analyzer/*.py .build-bill-analyzer/
cp bill-analyzer/SlashMyBill.png .build-bill-analyzer/
cd .build-bill-analyzer; zip -r ../bill-analyzer-lambda.zip .; cd ..
aws s3 cp bill-analyzer-lambda.zip s3://slashmybill-storage-me-central-1/lambda-packages/bill-analyzer.zip

# Repeat for: upload-handler, otp-handler, admin-handler, member-handler,
# agent-action, scheduler-executor, paddle-webhook-handler
```

## Step 3: Deploy CloudFormation Stack

```powershell
aws cloudformation deploy `
  --template-file infrastructure/viewmybill-stack-me-central-1.yaml `
  --stack-name slashmybill-me-central-1 `
  --region me-central-1 `
  --capabilities CAPABILITY_NAMED_IAM `
  --no-fail-on-empty-changeset `
  --parameter-overrides `
    AdminUsername='YOUR_ADMIN_USER' `
    AdminPasswordHash='YOUR_BCRYPT_HASH' `
    JWTSecret='YOUR_JWT_SECRET'
```

## Step 4: Verify SES Domain Identity

The stack creates an `AWS::SES::EmailIdentity` for `eshkolai.com`. Check verification:

```powershell
aws ses get-identity-verification-attributes `
  --identities eshkolai.com `
  --region me-central-1
```

If not verified, add the DKIM CNAME records to Route 53:

```powershell
aws sesv2 get-email-identity --email-identity eshkolai.com --region me-central-1
# Copy the 3 DKIM tokens and add as CNAME records in Route 53
```

## Step 5: Create Bedrock Agent

```powershell
python infrastructure/update-bedrock-agent-me-central-1.py
```

Note the output:
```
Agent ID: XXXXXXXXXX
Alias ID: YYYYYYYYYY
```

## Step 6: Update Stack with Agent IDs

```powershell
aws cloudformation deploy `
  --template-file infrastructure/viewmybill-stack-me-central-1.yaml `
  --stack-name slashmybill-me-central-1 `
  --region me-central-1 `
  --capabilities CAPABILITY_NAMED_IAM `
  --no-fail-on-empty-changeset `
  --parameter-overrides `
    AdminUsername='YOUR_ADMIN_USER' `
    AdminPasswordHash='YOUR_BCRYPT_HASH' `
    JWTSecret='YOUR_JWT_SECRET' `
    BedrockAgentId='XXXXXXXXXX' `
    BedrockAgentAliasId='YYYYYYYYYY'
```

## Step 7: Seed Knowledge Base

```powershell
$env:AWS_REGION = "me-central-1"
python knowledge-base/seed-dynamodb.py --region me-central-1
```

## Step 8: Migrate Data (Optional)

Migrate all DynamoDB tables from us-east-1:

```powershell
python infrastructure/migrate-dynamodb.py --source-region us-east-1 --target-region me-central-1
```

Dry run first:
```powershell
python infrastructure/migrate-dynamodb.py --source-region us-east-1 --target-region me-central-1 --dry-run
```

Migrate S3 data:
```powershell
aws s3 sync s3://aws-bill-analyzer-storage-991105135552 s3://slashmybill-storage-me-central-1 --region me-central-1
```

## Step 9: Get API Gateway URL

```powershell
aws cloudformation describe-stacks `
  --stack-name slashmybill-me-central-1 `
  --region me-central-1 `
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" `
  --output text
```

## Step 10: Test

```powershell
# Health check
curl https://<API_URL>/members/login -X POST -d '{"email":"test@test.com","password":"test"}'

# Should return 401 (unauthorized) — confirms API is responding
```

---

## CI/CD

After initial setup, the GitHub Actions pipeline automatically deploys to me-central-1
on every push to `main`. The `deploy-uae` job runs after the us-east-1 deploy.

---

## Rollback

To remove the UAE deployment entirely:

```powershell
# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name slashmybill-me-central-1 --region me-central-1

# Delete S3 bucket (empty first)
aws s3 rm s3://slashmybill-storage-me-central-1 --recursive
aws s3api delete-bucket --bucket slashmybill-storage-me-central-1 --region me-central-1

# Delete Bedrock Agent
python -c "
import boto3
client = boto3.client('bedrock-agent', region_name='me-central-1')
agents = client.list_agents()
for a in agents['agentSummaries']:
    if 'UAE' in a['agentName']:
        client.delete_agent(agentId=a['agentId'], skipResourceInUseCheck=True)
        print(f'Deleted agent {a[\"agentId\"]}')
"
```

The us-east-1 stack is completely unaffected.

---

## Architecture

```
User (UAE) → CloudFront → uae.slashmycloudbill.com
                              ↓
                    API Gateway (me-central-1)
                              ↓
                    Lambda (me-central-1)
                     ├── DynamoDB (me-central-1)
                     ├── Bedrock (me-central-1)
                     ├── SES (me-central-1)
                     ├── Cognito (us-east-1) ← cross-region
                     └── Pricing API (us-east-1) ← cross-region
```
