<#
.SYNOPSIS
    Creates and attaches a CloudFront Function to route slashmycloudbill.com traffic.
    Run this AFTER setup-slashmycloudbill.ps1 completes.
#>

$DISTRIBUTION_ID = "E12JIHGHK40OLE"
$FUNCTION_NAME = "SlashMyCloudBill-Router"
$FUNCTION_FILE = "$PSScriptRoot\cf-function-slashmycloudbill.js"

Write-Host "=== Deploying CloudFront Function ===" -ForegroundColor Cyan

# Create or update the function
$functionCode = Get-Content $FUNCTION_FILE -Raw

# Check if function exists
$existing = aws cloudfront list-functions --query "FunctionList.Items[?Name=='$FUNCTION_NAME'].FunctionMetadata.FunctionARN" --output text 2>&1
if ($existing -and $existing -notmatch "None") {
    Write-Host "Updating existing function..." -ForegroundColor Yellow
    $etag = aws cloudfront describe-function --name $FUNCTION_NAME --query "ETag" --output text
    aws cloudfront update-function `
        --name $FUNCTION_NAME `
        --if-match $etag `
        --function-config "Comment=Routes slashmycloudbill.com to SlashMyBill paths,Runtime=cloudfront-js-2.0" `
        --function-code $functionCode | Out-Null
} else {
    Write-Host "Creating new function..." -ForegroundColor Yellow
    aws cloudfront create-function `
        --name $FUNCTION_NAME `
        --function-config "Comment=Routes slashmycloudbill.com to SlashMyBill paths,Runtime=cloudfront-js-2.0" `
        --function-code $functionCode | Out-Null
}

# Publish the function
$etag = aws cloudfront describe-function --name $FUNCTION_NAME --query "ETag" --output text
$funcArn = aws cloudfront publish-function --name $FUNCTION_NAME --if-match $etag --query "FunctionSummary.FunctionMetadata.FunctionARN" --output text
Write-Host "Function published: $funcArn" -ForegroundColor Green

# Attach to CloudFront distribution (viewer-request on default cache behavior)
Write-Host "Attaching function to distribution $DISTRIBUTION_ID..." -ForegroundColor Yellow

$distConfig = aws cloudfront get-distribution-config --id $DISTRIBUTION_ID --output json | ConvertFrom-Json
$etag = $distConfig.ETag
$config = $distConfig.DistributionConfig

# Add function association to default cache behavior
$funcAssoc = @{
    FunctionARN = $funcArn
    EventType = "viewer-request"
}

if (-not $config.DefaultCacheBehavior.FunctionAssociations) {
    $config.DefaultCacheBehavior.FunctionAssociations = @{ Quantity = 1; Items = @($funcAssoc) }
} else {
    # Remove existing router function if present, add new one
    $existing = $config.DefaultCacheBehavior.FunctionAssociations.Items | Where-Object { $_.FunctionARN -notmatch $FUNCTION_NAME }
    $config.DefaultCacheBehavior.FunctionAssociations.Items = @($existing) + @($funcAssoc)
    $config.DefaultCacheBehavior.FunctionAssociations.Quantity = $config.DefaultCacheBehavior.FunctionAssociations.Items.Count
}

$configJson = $config | ConvertTo-Json -Depth 20
aws cloudfront update-distribution --id $DISTRIBUTION_ID --distribution-config $configJson --if-match $etag | Out-Null

Write-Host "Done! CloudFront function attached." -ForegroundColor Green
Write-Host ""
Write-Host "Test URLs:" -ForegroundColor Cyan
Write-Host "  https://slashmycloudbill.com/          → SlashMyBill landing page"
Write-Host "  https://slashmycloudbill.com/members/  → Member Portal"
Write-Host "  https://www.eshkolai.com/slashMyBill/  → Still works (unchanged)"
