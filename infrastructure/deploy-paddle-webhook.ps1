# Deploy Paddle Webhook Handler Lambda
# Run this once to create the Lambda, then GitHub Actions handles updates

$FunctionName = "slashmybill-paddle-webhook"
$RoleName = "SlashMyBill-PaddleWebhook-Role"
$Region = "us-east-1"
$AccountId = "991105135552"
$ApiId = "l2fd4h481h"
$MembersTable = "MemberPortal-Members"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Deploying Paddle Webhook Handler" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Prompt for webhook secret
$WebhookSecret = Read-Host "Enter your Paddle Webhook Secret (from Paddle Dashboard > Developer Tools > Notifications)"

# 1. Create IAM Role
Write-Host "`nCreating IAM role..." -ForegroundColor Yellow
$TrustPolicy = @'
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
    aws iam create-role `
        --role-name $RoleName `
        --assume-role-policy-document $TrustPolicy `
        --region $Region 2>$null
    Write-Host "Role created" -ForegroundColor Green
} catch {
    Write-Host "Role already exists" -ForegroundColor Gray
}

# Attach policies
aws iam attach-role-policy --role-name $RoleName --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" 2>$null

# DynamoDB policy for Members table
$DynamoPolicy = @"
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:PutItem"],
    "Resource": "arn:aws:dynamodb:${Region}:${AccountId}:table/${MembersTable}"
  }]
}
"@

aws iam put-role-policy `
    --role-name $RoleName `
    --policy-name "DynamoDBAccess" `
    --policy-document $DynamoPolicy 2>$null

Write-Host "Waiting for role propagation..." -ForegroundColor Gray
Start-Sleep -Seconds 10

# 2. Package Lambda
Write-Host "`nPackaging Lambda..." -ForegroundColor Yellow
if (Test-Path "paddle-webhook-lambda.zip") { Remove-Item "paddle-webhook-lambda.zip" }
Compress-Archive -Path "paddle-webhook-handler/lambda_function.py" -DestinationPath "paddle-webhook-lambda.zip"
Write-Host "Package created" -ForegroundColor Green

# 3. Create Lambda function
Write-Host "`nCreating Lambda function..." -ForegroundColor Yellow
try {
    aws lambda create-function `
        --function-name $FunctionName `
        --runtime python3.11 `
        --handler lambda_function.lambda_handler `
        --role "arn:aws:iam::${AccountId}:role/${RoleName}" `
        --zip-file "fileb://paddle-webhook-lambda.zip" `
        --timeout 30 `
        --memory-size 128 `
        --environment "Variables={MEMBERS_TABLE_NAME=${MembersTable},PADDLE_WEBHOOK_SECRET=${WebhookSecret}}" `
        --region $Region
    Write-Host "Lambda created" -ForegroundColor Green
} catch {
    Write-Host "Lambda may already exist, updating..." -ForegroundColor Gray
    aws lambda update-function-code `
        --function-name $FunctionName `
        --zip-file "fileb://paddle-webhook-lambda.zip" `
        --region $Region
    aws lambda update-function-configuration `
        --function-name $FunctionName `
        --environment "Variables={MEMBERS_TABLE_NAME=${MembersTable},PADDLE_WEBHOOK_SECRET=${WebhookSecret}}" `
        --region $Region
}

# 4. Add API Gateway integration
Write-Host "`nAdding API Gateway route..." -ForegroundColor Yellow

# Create integration
$IntegrationId = aws apigatewayv2 create-integration `
    --api-id $ApiId `
    --integration-type AWS_PROXY `
    --integration-uri "arn:aws:lambda:${Region}:${AccountId}:function:${FunctionName}" `
    --payload-format-version "2.0" `
    --region $Region `
    --query "IntegrationId" --output text

Write-Host "Integration created: $IntegrationId" -ForegroundColor Green

# Create route
aws apigatewayv2 create-route `
    --api-id $ApiId `
    --route-key "POST /paddle-webhook" `
    --target "integrations/$IntegrationId" `
    --region $Region

Write-Host "Route created: POST /paddle-webhook" -ForegroundColor Green

# 5. Grant API Gateway permission to invoke Lambda
aws lambda add-permission `
    --function-name $FunctionName `
    --statement-id "apigateway-paddle-webhook" `
    --action "lambda:InvokeFunction" `
    --principal "apigateway.amazonaws.com" `
    --source-arn "arn:aws:execute-api:${Region}:${AccountId}:${ApiId}/*/*/paddle-webhook" `
    --region $Region 2>$null

# 6. Deploy API
aws apigatewayv2 create-deployment `
    --api-id $ApiId `
    --region $Region 2>$null

# Cleanup
Remove-Item "paddle-webhook-lambda.zip" -ErrorAction SilentlyContinue

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "Paddle Webhook Handler Deployed!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Webhook URL:" -ForegroundColor Yellow
Write-Host "  https://${ApiId}.execute-api.${Region}.amazonaws.com/paddle-webhook" -ForegroundColor Cyan
Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Yellow
Write-Host "1. Go to Paddle Dashboard > Developer Tools > Notifications" -ForegroundColor White
Write-Host "2. Add a new webhook destination with URL:" -ForegroundColor White
Write-Host "   https://${ApiId}.execute-api.${Region}.amazonaws.com/paddle-webhook" -ForegroundColor Cyan
Write-Host "3. Select these events:" -ForegroundColor White
Write-Host "   - subscription.activated" -ForegroundColor White
Write-Host "   - subscription.canceled" -ForegroundColor White
Write-Host "   - subscription.updated" -ForegroundColor White
Write-Host "   - transaction.completed" -ForegroundColor White
Write-Host "4. Copy the webhook secret key and update the Lambda env var if different" -ForegroundColor White
Write-Host ""
