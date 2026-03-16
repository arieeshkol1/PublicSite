# Manual Contact Form Setup
# This script creates the Lambda function and API Gateway without CloudFormation

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Manual Contact Form Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$Region = "us-east-1"
$Email = "ariel.eshkol@gmail.com"

# Step 1: Verify email in SES
Write-Host "Step 1: Verifying email in SES..." -ForegroundColor Yellow
aws ses verify-email-identity --email-address $Email --region $Region
Write-Host "✓ Verification email sent to $Email" -ForegroundColor Green
Write-Host "  Please check your inbox and click the verification link!" -ForegroundColor Yellow
Write-Host ""

# Step 2: Create IAM role for Lambda
Write-Host "Step 2: Creating IAM role for Lambda..." -ForegroundColor Yellow

$TrustPolicy = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
"@

$TrustPolicy | Out-File -FilePath "trust-policy.json" -Encoding UTF8

try {
    aws iam create-role `
        --role-name ContactFormLambdaRole `
        --assume-role-policy-document file://trust-policy.json `
        --region $Region 2>$null
    
    Write-Host "✓ IAM role created" -ForegroundColor Green
} catch {
    Write-Host "  Role might already exist, continuing..." -ForegroundColor Yellow
}

# Attach policies
aws iam attach-role-policy `
    --role-name ContactFormLambdaRole `
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole `
    --region $Region 2>$null

$SESPolicy = @"
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "*"
    }
  ]
}
"@

$SESPolicy | Out-File -FilePath "ses-policy.json" -Encoding UTF8

aws iam put-role-policy `
    --role-name ContactFormLambdaRole `
    --policy-name SESEmailPolicy `
    --policy-document file://ses-policy.json `
    --region $Region 2>$null

Write-Host "✓ Policies attached" -ForegroundColor Green
Write-Host ""

# Step 3: Create Lambda function
Write-Host "Step 3: Creating Lambda function..." -ForegroundColor Yellow
Write-Host "  Packaging Lambda code..." -ForegroundColor Gray

# Create deployment package
if (Test-Path "lambda-package.zip") {
    Remove-Item "lambda-package.zip"
}

Compress-Archive -Path "contact-form-handler/lambda_function.py" -DestinationPath "lambda-package.zip"

# Wait for role to be ready
Write-Host "  Waiting for IAM role to propagate..." -ForegroundColor Gray
Start-Sleep -Seconds 10

$AccountId = aws sts get-caller-identity --query Account --output text

try {
    aws lambda create-function `
        --function-name ContactFormHandler `
        --runtime python3.11 `
        --role arn:aws:iam::${AccountId}:role/ContactFormLambdaRole `
        --handler lambda_function.lambda_handler `
        --zip-file fileb://lambda-package.zip `
        --timeout 30 `
        --environment "Variables={RECIPIENT_EMAIL=$Email,SENDER_EMAIL=$Email}" `
        --region $Region
    
    Write-Host "✓ Lambda function created" -ForegroundColor Green
} catch {
    Write-Host "  Function might already exist, updating..." -ForegroundColor Yellow
    
    aws lambda update-function-code `
        --function-name ContactFormHandler `
        --zip-file fileb://lambda-package.zip `
        --region $Region
    
    aws lambda update-function-configuration `
        --function-name ContactFormHandler `
        --environment "Variables={RECIPIENT_EMAIL=$Email,SENDER_EMAIL=$Email}" `
        --region $Region
    
    Write-Host "✓ Lambda function updated" -ForegroundColor Green
}

Write-Host ""

# Step 4: Create API Gateway
Write-Host "Step 4: Creating API Gateway..." -ForegroundColor Yellow

$ApiId = aws apigateway get-rest-apis `
    --query "items[?name=='ContactFormAPI'].id" `
    --output text `
    --region $Region

if ([string]::IsNullOrWhiteSpace($ApiId)) {
    $ApiId = aws apigateway create-rest-api `
        --name ContactFormAPI `
        --description "API for contact form" `
        --endpoint-configuration types=REGIONAL `
        --query 'id' `
        --output text `
        --region $Region
    
    Write-Host "✓ API Gateway created: $ApiId" -ForegroundColor Green
} else {
    Write-Host "✓ API Gateway already exists: $ApiId" -ForegroundColor Green
}

# Get root resource
$RootId = aws apigateway get-resources `
    --rest-api-id $ApiId `
    --query 'items[?path==`/`].id' `
    --output text `
    --region $Region

# Create /contact resource
$ResourceId = aws apigateway get-resources `
    --rest-api-id $ApiId `
    --query "items[?pathPart=='contact'].id" `
    --output text `
    --region $Region

if ([string]::IsNullOrWhiteSpace($ResourceId)) {
    $ResourceId = aws apigateway create-resource `
        --rest-api-id $ApiId `
        --parent-id $RootId `
        --path-part contact `
        --query 'id' `
        --output text `
        --region $Region
}

# Create POST method
aws apigateway put-method `
    --rest-api-id $ApiId `
    --resource-id $ResourceId `
    --http-method POST `
    --authorization-type NONE `
    --region $Region 2>$null

# Create OPTIONS method for CORS
aws apigateway put-method `
    --rest-api-id $ApiId `
    --resource-id $ResourceId `
    --http-method OPTIONS `
    --authorization-type NONE `
    --region $Region 2>$null

# Set up Lambda integration
$LambdaArn = "arn:aws:lambda:${Region}:${AccountId}:function:ContactFormHandler"
$IntegrationUri = "arn:aws:apigateway:${Region}:lambda:path/2015-03-31/functions/${LambdaArn}/invocations"

aws apigateway put-integration `
    --rest-api-id $ApiId `
    --resource-id $ResourceId `
    --http-method POST `
    --type AWS_PROXY `
    --integration-http-method POST `
    --uri $IntegrationUri `
    --region $Region 2>$null

# Set up OPTIONS integration for CORS
aws apigateway put-integration `
    --rest-api-id $ApiId `
    --resource-id $ResourceId `
    --http-method OPTIONS `
    --type MOCK `
    --request-templates '{"application/json":"{\"statusCode\": 200}"}' `
    --region $Region 2>$null

# Add Lambda permission
aws lambda add-permission `
    --function-name ContactFormHandler `
    --statement-id apigateway-access `
    --action lambda:InvokeFunction `
    --principal apigateway.amazonaws.com `
    --source-arn "arn:aws:execute-api:${Region}:${AccountId}:${ApiId}/*/*" `
    --region $Region 2>$null

# Deploy API
aws apigateway create-deployment `
    --rest-api-id $ApiId `
    --stage-name prod `
    --region $Region 2>$null

Write-Host "✓ API Gateway configured" -ForegroundColor Green
Write-Host ""

# Cleanup
Remove-Item "trust-policy.json" -ErrorAction SilentlyContinue
Remove-Item "ses-policy.json" -ErrorAction SilentlyContinue
Remove-Item "lambda-package.zip" -ErrorAction SilentlyContinue

# Display results
$ApiEndpoint = "https://${ApiId}.execute-api.${Region}.amazonaws.com/prod/contact"

Write-Host "========================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "API Endpoint:" -ForegroundColor Yellow
Write-Host $ApiEndpoint -ForegroundColor Cyan
Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Yellow
Write-Host "1. Check $Email for SES verification email and click the link"
Write-Host "2. Update script.js with this API endpoint"
Write-Host "3. Commit and push the changes"
Write-Host ""

$ApiEndpoint | Out-File -FilePath "api-endpoint.txt" -Encoding UTF8
Write-Host "API endpoint saved to api-endpoint.txt" -ForegroundColor Green
