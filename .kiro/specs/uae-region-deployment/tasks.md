# UAE Region Deployment (me-central-1) — Tasks

## Task 1: Create me-central-1 CloudFormation Stack Template
- [x] Copy `infrastructure/viewmybill-stack.yaml` to `infrastructure/viewmybill-stack-me-central-1.yaml`
- [x] Add new parameters: `BedrockRegion`, `SESRegion`, `CognitoUserPoolId`, `CognitoClientId`, `CognitoRegion`, `PricingRegion`, `BedrockAgentId`, `BedrockAgentAliasId`
- [x] Rename all IAM roles with `-me-central-1` suffix
- [x] Update S3 bucket default to `slashmybill-storage-me-central-1`
- [x] Update Member Handler Lambda env vars to include `COGNITO_REGION`, `PRICING_REGION`, `BEDROCK_REGION`, `SES_REGION`
- [x] Update OTP Handler Lambda env vars to include `SES_REGION`
- [x] Update Bedrock resource ARNs to use `${BedrockRegion}` parameter
- [x] Update Cognito resource ARN to use `CognitoRegion` and `CognitoUserPoolId` parameters
- [x] Keep `AWS::SES::EmailIdentity` resource (SES available in me-central-1)
- [x] Verify all `!Sub` references use `${AWS::Region}` not hardcoded regions

## Task 2: Make Lambda Code Region-Aware
- [x] Update `member-handler/lambda_function.py` — use `os.environ.get('COGNITO_REGION', 'us-east-1')` for Cognito client
- [x] Update `member-handler/lambda_function.py` — use `os.environ.get('PRICING_REGION', 'us-east-1')` for Pricing client
- [x] Update `member-handler/lambda_function.py` — use `os.environ.get('BEDROCK_REGION', ...)` for Bedrock clients
- [x] Update `member-handler/lambda_function.py` — use `os.environ.get('SES_REGION', ...)` for SES client
- [x] Update `otp-handler/lambda_function.py` — use `os.environ.get('SES_REGION', ...)` for SES client
- [x] Update `agent-action/lambda_function.py` — use `os.environ.get('PRICING_REGION', 'us-east-1')` for Pricing client
- [x] Update `bill-analyzer/bedrock_client.py` — use `os.environ.get('BEDROCK_REGION', ...)` for Bedrock client
- [x] Ensure all changes are backward-compatible (defaults to us-east-1 when env var not set)

## Task 3: Create Bedrock Agent Script for me-central-1
- [x] Create `infrastructure/update-bedrock-agent-me-central-1.py` based on `infrastructure/update-bedrock-agent.py`
- [x] Set `REGION = 'me-central-1'`
- [x] Set `AGENT_ROLE_NAME = 'SlashMyBill-BedrockAgent-Role-me-central-1'`
- [x] Set `ACTION_LAMBDA_ARN` to `arn:aws:lambda:me-central-1:991105135552:function:SlashMyBill-AgentAction`
- [x] Use same `agent-instructions.md` and `openapi-schema.json`
- [x] Update IAM policy to reference me-central-1 Bedrock model ARNs
- [x] Test model availability: try `us.amazon.nova-lite-v1:0`, fallback to `amazon.nova-lite-v1:0`

## Task 4: Create S3 Bucket and Seed Knowledge Base
- [x] Update `knowledge-base/seed-dynamodb.py` to accept `--region` parameter
- [x] S3 bucket creation handled in CI/CD pipeline step
- [x] CI/CD step seeds `ViewMyBill-CostOptimizationTips` table in me-central-1
- [x] S3 lifecycle rules applied in CI/CD pipeline step

## Task 5: Data Migration Script
- [x] `infrastructure/migrate-dynamodb.py` already supports `--source-region` and `--target-region`
- [x] Updated default target region from `me-south-1` to `me-central-1`
- [x] Migrates all 8 DynamoDB tables (skips OTP as ephemeral but included for completeness)
- [x] Has progress logging (items migrated per table)
- [x] Handles pagination (LastEvaluatedKey)
- [x] Has `--dry-run` flag
- [x] S3 sync command documented in deployment guide

## Task 6: Extend CI/CD Pipeline
- [x] Add `deploy-uae` job to `.github/workflows/deploy.yml`
- [x] Set job dependency: `needs: deploy` (runs after us-east-1)
- [x] Configure AWS credentials for me-central-1 region
- [x] Package all 8 Lambdas and upload to `slashmybill-storage-me-central-1`
- [x] Deploy CloudFormation stack `slashmybill-me-central-1` in me-central-1
- [x] Update Lambda function code in me-central-1 (all 8 functions)
- [x] Ensure API Gateway routes exist in me-central-1
- [x] Seed DynamoDB knowledge base in me-central-1
- [x] Run `update-bedrock-agent-me-central-1.py`
- [x] S3 lifecycle rules configured
- [x] Add `continue-on-error: true` for CloudFormation deploy step

## Task 7: SES Domain Verification in me-central-1
- [x] CloudFormation creates `AWS::SES::EmailIdentity` for `eshkolai.com` in me-central-1
- [ ] Retrieve DKIM CNAME records from SES in me-central-1 (first deploy)
- [ ] Add DKIM records to Route 53 hosted zone (one-time manual step)
- [ ] Verify domain identity status becomes `SUCCESS`
- [ ] Test email sending from me-central-1 (`noreply@eshkolai.com`)

## Task 8: Frontend UAE Deployment
- [x] CI/CD deploys frontend to `s3://slashmycloudbill.com/uae/members/`
- [x] API URL injected via sed during deploy
- [x] Shared assets copied to `/uae/` prefix
- [ ] Create DNS record: `uae.slashmycloudbill.com` → CloudFront (manual)
- [ ] Add ACM certificate for `uae.slashmycloudbill.com` (or use wildcard)
- [x] `uae.slashmycloudbill.com` added to API Gateway CORS allowed origins

## Task 9: Update Existing Stack for Compatibility
- [x] Add `COGNITO_REGION`, `PRICING_REGION`, `BEDROCK_REGION`, `SES_REGION` env vars to us-east-1 Member Handler
- [x] Add `PRICING_REGION` to us-east-1 Agent Action Lambda
- [x] Add `SES_REGION` to us-east-1 OTP Handler Lambda
- [x] Add `BEDROCK_REGION` to us-east-1 Bill Analyzer Lambda
- [x] All set to `us-east-1` for backward compatibility

## Task 10: Create Deployment Guide
- [x] Created `infrastructure/DEPLOY-ME-CENTRAL-1.md` with:
  - Prerequisites (enable me-central-1 region, create S3 bucket)
  - Step-by-step deployment instructions
  - SES verification steps
  - Bedrock Agent creation steps
  - Data migration instructions
  - DNS setup for `uae.slashmycloudbill.com`
  - Verification checklist
  - Rollback instructions

## Task 11: End-to-End Verification
- [ ] Deploy stack to me-central-1
- [ ] Verify API Gateway responds (health check)
- [ ] Test member registration (Cognito cross-region)
- [ ] Test member login
- [ ] Test AI chat (Bedrock Agent in me-central-1)
- [ ] Test waste scan
- [ ] Test resize server wizard
- [ ] Test cluster optimize
- [ ] Test email notifications (SES in me-central-1)
- [ ] Test scheduler creation
- [ ] Verify us-east-1 stack still works (no regression)
- [ ] Verify data migration completed (spot check records)
