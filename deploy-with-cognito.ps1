# Deploy TAG Video Systems Stack with Cognito Authentication
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TAG Video Systems - Cognito Deployment" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Deploy CDK Stack
Write-Host "[1/5] Deploying CDK Stack..." -ForegroundColor Yellow
cdk deploy --require-approval never

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to deploy CDK stack" -ForegroundColor Red
    exit 1
}

Write-Host "CDK Stack deployed successfully" -ForegroundColor Green
Write-Host ""

# Step 2: Get Cognito outputs
Write-Host "[2/5] Retrieving Cognito configuration..." -ForegroundColor Yellow
$outputs = aws cloudformation describe-stacks --stack-name TagVideoProbeStack --region us-east-1 --query "Stacks[0].Outputs" | ConvertFrom-Json

$userPoolId = ($outputs | Where-Object { $_.OutputKey -eq "UserPoolId" }).OutputValue
$clientId = ($outputs | Where-Object { $_.OutputKey -eq "UserPoolClientId" }).OutputValue

Write-Host "User Pool ID: $userPoolId" -ForegroundColor Cyan
Write-Host "Client ID: $clientId" -ForegroundColor Cyan
Write-Host ""

# Step 3: Update login.html
Write-Host "[3/5] Updating login.html..." -ForegroundColor Yellow
.\update-cognito-config.ps1 -UserPoolId $userPoolId -ClientId $clientId
Write-Host ""

# Step 4: Set admin password
Write-Host "[4/5] Setting admin password..." -ForegroundColor Yellow
aws cognito-idp admin-set-user-password --user-pool-id $userPoolId --username admin --password "TagVideo2024!" --permanent --region us-east-1
Write-Host ""

# Step 5: Re-deploy
Write-Host "[5/5] Re-deploying..." -ForegroundColor Yellow
cdk deploy --require-approval never
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
