# SlashMyBill Migration to me-south-1 (Bahrain)

## Overview

This document describes how to deploy the SlashMyBill stack in me-south-1 while keeping
cross-region dependencies (Bedrock, SES, Pricing API) in us-east-1.

## Service Availability in me-south-1

| Service | Available in me-south-1? | Strategy |
|---------|-------------------------|----------|
| Lambda | Yes | Deploy locally |
| DynamoDB | Yes | Deploy locally |
| API Gateway (HTTP) | Yes | Deploy locally |
| S3 | Yes | Deploy locally |
| CloudFront | Global | No change needed |
| Route53 | Global | No change needed |
| Cognito | Yes, but **keep in us-east-1** | Cross-region (no user migration needed) |
| SES | **NO** | Cross-region call to us-east-1 |
| Bedrock (Nova) | **NO** | Cross-region call to us-east-1 |
| Bedrock Agents | **NO** | Cross-region call to us-east-1 |
| EventBridge Scheduler | Yes | Deploy locally |
| Pricing API | us-east-1 only | Already cross-region |
| Cost Explorer | Global | No change needed |

## Pre-requisites

1. me-south-1 is enabled in your AWS account (Account Settings > Regions)
2. Create an S3 bucket in me-south-1 for Lambda packages:
   ```
   aws s3api create-bucket --bucket slashmybill-packages-me-south-1 \
     --region me-south-1 \
     --create-bucket-configuration LocationConstraint=me-south-1
   ```
3. Verify SES identity in us-east-1 (already done: eshkolai.com)

## Step 1: Deploy CloudFormation Stack

```powershell
# From infrastructure/ directory
aws cloudformation deploy `
  --template-file viewmybill-stack-me-south-1.yaml `
  --stack-name slashmybill-me-south-1 `
  --region me-south-1 `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides `
    LambdaCodeBucket=slashmybill-packages-me-south-1 `
    BillStorageBucket=slashmybill-storage-me-south-1 `
    BedrockRegion=us-east-1 `
    SESRegion=us-east-1 `
    CognitoUserPoolId=us-east-1_FlR2CmFu0 `
    CognitoClientId=3shmdb332mm8sjheopdu9sg8o4
```

## Step 2: Cognito — No Migration Needed

Cognito stays in us-east-1. The existing pool `us-east-1_FlR2CmFu0` and client
`3shmdb332mm8sjheopdu9sg8o4` are used cross-region. All users keep their accounts.

The Lambda code already calls Cognito with `region_name='us-east-1'` hardcoded,
so no code changes needed for auth.

## Step 3: Migrate DynamoDB Data

Use the migration script: `infrastructure/migrate-dynamodb.py`

```powershell
python infrastructure/migrate-dynamodb.py --source-region us-east-1 --target-region me-south-1
```

Tables migrated:
- MemberPortal-Members
- MemberPortal-Accounts
- ViewMyBill-CostOptimizationTips
- ViewMyBill-Leads
- ViewMyBill-OTP
- MemberPortal-AgentFeedback
- MemberPortal-BusinessMetrics
- SpotSavingsLedger

## Step 4: Migrate S3 Data

```powershell
aws s3 sync s3://aws-bill-analyzer-storage-991105135552 s3://slashmybill-storage-me-south-1 --region me-south-1
```

## Step 5: Update CI/CD Pipeline

Update `.github/workflows/deploy.yml`:
- Change `AWS_REGION: me-south-1`
- Update S3 bucket names
- Update Cognito pool ID and client ID
- Update API Gateway ID (from new stack output)

## Step 6: Update Frontend

Update `members/members.js`:
- Change API endpoint to new API Gateway URL

## Step 7: Recreate Bedrock Agent

The Bedrock Agent must stay in us-east-1. Update the agent's action group
Lambda to point to the new me-south-1 Lambda (or keep the agent-action Lambda
in us-east-1 and have it call cross-region).

Simpler approach: Keep the agent-action Lambda in us-east-1, update it to
call DynamoDB in me-south-1 for tips.

## Step 8: DNS Cutover

Update CloudFront distribution to point to the new API Gateway in me-south-1.

## Rollback

Keep the us-east-1 stack running until me-south-1 is verified. DNS can be
switched back instantly via CloudFront origin update.
