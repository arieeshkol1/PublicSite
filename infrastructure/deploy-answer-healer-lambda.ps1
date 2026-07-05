# Deploy Answer Healer Lambda (Bedrock Investigator)
# Creates or updates the slashmybill-answer-healer Lambda function

$ErrorActionPreference = "Stop"
$REGION = "us-east-1"
$FUNCTION_NAME = "slashmybill-answer-healer"
$ROLE_NAME = "SlashMyBill-AnswerHealer-Role"
$ACCOUNT_ID = "991105135552"
$ROLE_ARN = "arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
$TIMEOUT = 120
$MEMORY = 256
$RUNTIME = "python3.12"

Write-Host "=== Deploying $FUNCTION_NAME ===" -ForegroundColor Cyan

# Step 1: Create IAM role if it doesn't exist
$trustPolicy = @'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
'@

try {
    aws iam get-role --role-name $ROLE_NAME --region $REGION 2>$null | Out-Null
    Write-Host "  Role exists: $ROLE_NAME" -ForegroundColor Green
} catch {
    Write-Host "  Creating IAM role: $ROLE_NAME" -ForegroundColor Yellow
    $trustPolicy | Out-File -Encoding utf8 trust-policy-healer.json
    aws iam create-role --role-name $ROLE_NAME --assume-role-policy-document file://trust-policy-healer.json --region $REGION
    Remove-Item trust-policy-healer.json -Force
    Start-Sleep -Seconds 10
}

# Attach policies
$policies = @(
    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
)
foreach ($p in $policies) {
    aws iam attach-role-policy --role-name $ROLE_NAME --policy-arn $p 2>$null
}

# Inline policy for DynamoDB + Bedrock + Lambda invoke
$inlinePolicy = @'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:991105135552:table/Audit_Transaction_Log",
        "arn:aws:dynamodb:us-east-1:991105135552:table/ViewMyBill-CostOptimizationTips",
        "arn:aws:dynamodb:us-east-1:991105135552:table/ViewMyBill-CostOptimizationTips/index/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeAgent", "bedrock:Retrieve"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["lambda:InvokeFunction"],
      "Resource": "arn:aws:lambda:us-east-1:991105135552:function:*"
    }
  ]
}
'@
$inlinePolicy | Out-File -Encoding utf8 healer-inline-policy.json
aws iam put-role-policy --role-name $ROLE_NAME --policy-name AnswerHealerAccess --policy-document file://healer-inline-policy.json --region $REGION
Remove-Item healer-inline-policy.json -Force

# Step 2: Package the Lambda
Write-Host "  Packaging Lambda..." -ForegroundColor Yellow
$srcDir = Join-Path $PSScriptRoot "..\answer-healer"
$zipFile = Join-Path $PSScriptRoot "answer-healer-deploy.zip"

if (Test-Path $zipFile) { Remove-Item $zipFile -Force }
Compress-Archive -Path "$srcDir\*" -DestinationPath $zipFile

# Step 3: Create or update the Lambda function
$envVars = "Variables={AUDIT_TABLE_NAME=Audit_Transaction_Log,TIPS_TABLE_NAME=ViewMyBill-CostOptimizationTips,CLAUDE_MODEL_ID=us.anthropic.claude-sonnet-4-20250514-v1:0,BEDROCK_MODEL_ID=us.amazon.nova-2-lite-v1:0,BEDROCK_AGENT_ID=G5VJGUOZ5W,BEDROCK_AGENT_ALIAS_ID=TSTALIASID}"

try {
    aws lambda get-function --function-name $FUNCTION_NAME --region $REGION 2>$null | Out-Null
    Write-Host "  Updating existing function..." -ForegroundColor Yellow
    aws lambda update-function-code --function-name $FUNCTION_NAME --zip-file "fileb://$zipFile" --region $REGION | Out-Null
    Start-Sleep -Seconds 5
    aws lambda update-function-configuration --function-name $FUNCTION_NAME --timeout $TIMEOUT --memory-size $MEMORY --environment $envVars --region $REGION | Out-Null
} catch {
    Write-Host "  Creating new function..." -ForegroundColor Yellow
    aws lambda create-function `
        --function-name $FUNCTION_NAME `
        --runtime $RUNTIME `
        --role $ROLE_ARN `
        --handler lambda_function.lambda_handler `
        --zip-file "fileb://$zipFile" `
        --timeout $TIMEOUT `
        --memory-size $MEMORY `
        --environment $envVars `
        --region $REGION | Out-Null
}

Remove-Item $zipFile -Force

# Step 4: Update audit-evaluator with healer function name env var
Write-Host "  Updating audit-evaluator env var..." -ForegroundColor Yellow
try {
    $evalConfig = aws lambda get-function-configuration --function-name slashmybill-audit-evaluator --region $REGION 2>$null | ConvertFrom-Json
    # Add ANSWER_HEALER_FUNCTION_NAME to existing env vars
    Write-Host "  (Manual step: add ANSWER_HEALER_FUNCTION_NAME=$FUNCTION_NAME to audit-evaluator env vars)" -ForegroundColor Magenta
} catch {
    Write-Host "  audit-evaluator not found — skip env var update" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== $FUNCTION_NAME deployed successfully ===" -ForegroundColor Green
Write-Host "  Next: Add ANSWER_HEALER_FUNCTION_NAME=$FUNCTION_NAME to audit-evaluator Lambda env vars" -ForegroundColor Magenta
