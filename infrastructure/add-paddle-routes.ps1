# Add Paddle payment routes to existing API Gateway
# Run this once to create the routes

$ApiId = "l2fd4h481h"
$Region = "us-east-1"
$AccountId = "991105135552"
$FunctionName = "aws-bill-analyzer-member-api"

Write-Host "Adding payment routes to API Gateway..." -ForegroundColor Cyan

# Get the existing member integration ID
$Integrations = aws apigatewayv2 get-integrations --api-id $ApiId --region $Region --output json | ConvertFrom-Json
$MemberIntegration = $Integrations.Items | Where-Object { $_.IntegrationUri -like "*$FunctionName*" } | Select-Object -First 1

if (-not $MemberIntegration) {
    Write-Host "ERROR: Could not find member integration" -ForegroundColor Red
    exit 1
}

$IntegrationId = $MemberIntegration.IntegrationId
Write-Host "Found member integration: $IntegrationId" -ForegroundColor Green

# Add /member/add-tokens route
Write-Host "Adding POST /member/add-tokens..." -ForegroundColor Yellow
aws apigatewayv2 create-route `
    --api-id $ApiId `
    --route-key "POST /member/add-tokens" `
    --target "integrations/$IntegrationId" `
    --region $Region 2>$null
Write-Host "Done" -ForegroundColor Green

# Add /member/update-tier route
Write-Host "Adding POST /member/update-tier..." -ForegroundColor Yellow
aws apigatewayv2 create-route `
    --api-id $ApiId `
    --route-key "POST /member/update-tier" `
    --target "integrations/$IntegrationId" `
    --region $Region 2>$null
Write-Host "Done" -ForegroundColor Green

# Deploy
aws apigatewayv2 create-deployment --api-id $ApiId --region $Region 2>$null

Write-Host "`nRoutes added successfully!" -ForegroundColor Green
Write-Host "POST https://$ApiId.execute-api.$Region.amazonaws.com/member/add-tokens" -ForegroundColor Cyan
Write-Host "POST https://$ApiId.execute-api.$Region.amazonaws.com/member/update-tier" -ForegroundColor Cyan


# ============================================================
# Admin Subscriber Management Routes
# ============================================================
$AdminFunctionName = "aws-bill-analyzer-admin-api"

$AdminIntegration = $Integrations.Items | Where-Object { $_.IntegrationUri -like "*$AdminFunctionName*" } | Select-Object -First 1

if ($AdminIntegration) {
    $AdminIntId = $AdminIntegration.IntegrationId
    Write-Host "`nFound admin integration: $AdminIntId" -ForegroundColor Green

    Write-Host "Adding GET /admin/subscribers..." -ForegroundColor Yellow
    aws apigatewayv2 create-route --api-id $ApiId --route-key "GET /admin/subscribers" --target "integrations/$AdminIntId" --region $Region 2>$null
    Write-Host "Adding PUT /admin/subscribers/tier..." -ForegroundColor Yellow
    aws apigatewayv2 create-route --api-id $ApiId --route-key "PUT /admin/subscribers/tier" --target "integrations/$AdminIntId" --region $Region 2>$null
    Write-Host "Adding POST /admin/subscribers/tokens..." -ForegroundColor Yellow
    aws apigatewayv2 create-route --api-id $ApiId --route-key "POST /admin/subscribers/tokens" --target "integrations/$AdminIntId" --region $Region 2>$null

    aws apigatewayv2 create-deployment --api-id $ApiId --region $Region 2>$null
    Write-Host "Admin subscriber routes added!" -ForegroundColor Green
} else {
    Write-Host "WARNING: Could not find admin integration. Add routes manually." -ForegroundColor Yellow
}
