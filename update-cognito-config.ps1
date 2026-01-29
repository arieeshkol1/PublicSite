# Update Cognito configuration in login.html after deployment
param(
    [Parameter(Mandatory=$true)]
    [string]$UserPoolId,
    
    [Parameter(Mandatory=$true)]
    [string]$ClientId
)

$loginFile = "dashboard/login.html"

if (-not (Test-Path $loginFile)) {
    Write-Error "File not found: $loginFile"
    exit 1
}

# Read the file
$content = Get-Content $loginFile -Raw

# Replace placeholders
$content = $content -replace 'REPLACE_WITH_USER_POOL_ID', $UserPoolId
$content = $content -replace 'REPLACE_WITH_CLIENT_ID', $ClientId

# Write back
Set-Content $loginFile -Value $content

Write-Host "✓ Updated Cognito configuration in login.html" -ForegroundColor Green
Write-Host "  User Pool ID: $UserPoolId" -ForegroundColor Cyan
Write-Host "  Client ID: $ClientId" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Set admin password: aws cognito-idp admin-set-user-password --user-pool-id $UserPoolId --username admin --password TagVideo2024! --permanent --region us-east-1"
Write-Host "2. Re-deploy: cdk deploy"
