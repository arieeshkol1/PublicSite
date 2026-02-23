# Made4Net Fortress & Factory Deployment Script (PowerShell)
# For Windows environments

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Made4Net Fortress & Factory Deployment" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
Write-Host "Checking prerequisites..." -ForegroundColor Yellow

# Check AWS CLI
try {
    $awsVersion = aws --version 2>&1
    Write-Host "✓ AWS CLI found: $awsVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ AWS CLI not found. Please install it first." -ForegroundColor Red
    exit 1
}

# Check CDK
try {
    $cdkVersion = cdk --version 2>&1
    Write-Host "✓ AWS CDK found: $cdkVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ AWS CDK not found. Installing..." -ForegroundColor Yellow
    npm install -g aws-cdk
}

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python not found. Please install Python 3.9+." -ForegroundColor Red
    exit 1
}

# Verify AWS credentials
Write-Host ""
Write-Host "Verifying AWS credentials..." -ForegroundColor Yellow
try {
    $identity = aws sts get-caller-identity | ConvertFrom-Json
    Write-Host "✓ Authenticated as: $($identity.Arn)" -ForegroundColor Green
    Write-Host "  Account: $($identity.Account)" -ForegroundColor Cyan
} catch {
    Write-Host "✗ AWS credentials not configured. Run 'aws configure' first." -ForegroundColor Red
    exit 1
}

# Install Python dependencies
Write-Host ""
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
Set-Location infrastructure
pip install -r requirements.txt
Set-Location ..

# Bootstrap CDK (if needed)
Write-Host ""
Write-Host "Bootstrapping CDK environment..." -ForegroundColor Yellow
cdk bootstrap

# Deploy stack
Write-Host ""
Write-Host "Deploying Made4Net Fortress & Factory stack..." -ForegroundColor Yellow
Write-Host "This will take 3-5 minutes..." -ForegroundColor Cyan
Write-Host ""

cdk deploy --require-approval never

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Deployment Successful!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    
    # Get outputs
    Write-Host "Retrieving stack outputs..." -ForegroundColor Yellow
    $outputs = aws cloudformation describe-stacks --stack-name Made4NetFortressStack --query "Stacks[0].Outputs" | ConvertFrom-Json
    
    $apiEndpoint = ($outputs | Where-Object { $_.OutputKey -eq "APIEndpoint" }).OutputValue
    $dashboardUrl = ($outputs | Where-Object { $_.OutputKey -eq "DashboardURL" }).OutputValue
    $userPoolId = ($outputs | Where-Object { $_.OutputKey -eq "UserPoolId" }).OutputValue
    $clientId = ($outputs | Where-Object { $_.OutputKey -eq "UserPoolClientId" }).OutputValue
    
    Write-Host ""
    Write-Host "📊 Dashboard URL: $dashboardUrl" -ForegroundColor Cyan
    Write-Host "🔌 API Endpoint: $apiEndpoint" -ForegroundColor Cyan
    Write-Host "👤 User Pool ID: $userPoolId" -ForegroundColor Cyan
    Write-Host "🔑 Client ID: $clientId" -ForegroundColor Cyan
    Write-Host ""
    
    # Update dashboard with API endpoint
    Write-Host "Updating dashboard configuration..." -ForegroundColor Yellow
    $dashboardFile = "dashboard/index.html"
    $content = Get-Content $dashboardFile -Raw
    $content = $content -replace "const API_ENDPOINT = 'YOUR_API_ENDPOINT_HERE';", "const API_ENDPOINT = '$apiEndpoint';"
    Set-Content $dashboardFile $content
    
    # Redeploy dashboard with updated config
    Write-Host "Redeploying dashboard with API configuration..." -ForegroundColor Yellow
    cdk deploy --require-approval never
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Setup Complete!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor Yellow
    Write-Host "1. Open dashboard: $dashboardUrl" -ForegroundColor White
    Write-Host "2. Click 'Generate New Metrics' to populate data" -ForegroundColor White
    Write-Host "3. Review the 4 architecture layers" -ForegroundColor White
    Write-Host "4. Check interview talking points at bottom" -ForegroundColor White
    Write-Host ""
    Write-Host "For Sagi Van presentation:" -ForegroundColor Cyan
    Write-Host "- Demonstrate real-time security monitoring" -ForegroundColor White
    Write-Host "- Show 30% cost reduction metrics" -ForegroundColor White
    Write-Host "- Highlight 99.99%+ availability" -ForegroundColor White
    Write-Host "- Explain automated patch management" -ForegroundColor White
    Write-Host ""
    
} else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Deployment Failed" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please check the error messages above." -ForegroundColor Yellow
    Write-Host "Common issues:" -ForegroundColor Yellow
    Write-Host "- Wrong AWS account/region" -ForegroundColor White
    Write-Host "- Insufficient IAM permissions" -ForegroundColor White
    Write-Host "- CDK not bootstrapped" -ForegroundColor White
    Write-Host ""
}
