# Deploy SlashMyBill Frontend to S3
# Uploads frontend files (HTML, CSS, JS) to the S3 website bucket and invalidates CloudFront cache.
# Optionally replaces the API Gateway URL placeholder in slashMyBill.js before deploying.
#
# Usage:
#   .\infrastructure\deploy-viewmybill-frontend.ps1
#   .\infrastructure\deploy-viewmybill-frontend.ps1 -ApiGatewayUrl "https://abc123.execute-api.us-east-1.amazonaws.com"
#
# Run from the repository root directory.

param(
    [string]$ApiGatewayUrl,
    [string]$S3Bucket = "www.eshkolai.com",
    [string]$Region = "us-east-1",
    [string]$CloudFrontDistributionId = "E12JIHGHK40OLE"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Deploy SlashMyBill Frontend ===" -ForegroundColor Cyan

# Resolve paths relative to repo root
$RepoRoot = $PSScriptRoot | Split-Path -Parent
$FrontendDir = Join-Path $RepoRoot "slashMyBill"
$TempJsFile = $null

# Validate frontend directory exists
if (-not (Test-Path $FrontendDir)) {
    Write-Host "Error: slashMyBill/ directory not found at $FrontendDir" -ForegroundColor Red
    exit 1
}

# Validate required files exist
$requiredFiles = @("index.html", "slashMyBill.css", "slashMyBill.js")
foreach ($file in $requiredFiles) {
    $filePath = Join-Path $FrontendDir $file
    if (-not (Test-Path $filePath)) {
        Write-Host "Error: Required file '$file' not found in slashMyBill/" -ForegroundColor Red
        exit 1
    }
}

Write-Host "  S3 Bucket:      $S3Bucket" -ForegroundColor Gray
Write-Host "  Region:         $Region" -ForegroundColor Gray
Write-Host "  CloudFront ID:  $CloudFrontDistributionId" -ForegroundColor Gray
if ($ApiGatewayUrl) {
    Write-Host "  API Gateway URL: $ApiGatewayUrl" -ForegroundColor Gray
}

try {
    # Step 1: Prepare JS file (replace API Gateway URL placeholder if provided)
    $jsSource = Join-Path $FrontendDir "slashMyBill.js"

    if ($ApiGatewayUrl) {
        Write-Host "`n[1/4] Replacing API Gateway URL placeholder in slashMyBill.js..." -ForegroundColor Yellow

        # Remove trailing slash if present
        $ApiGatewayUrl = $ApiGatewayUrl.TrimEnd('/')

        $TempJsFile = Join-Path $RepoRoot ".tmp-slashMyBill.js"
        $jsContent = Get-Content -Path $jsSource -Raw
        $jsContent = $jsContent -replace "https://YOUR_API_GATEWAY_URL", $ApiGatewayUrl
        Set-Content -Path $TempJsFile -Value $jsContent -NoNewline
        $jsSource = $TempJsFile
        Write-Host "  Placeholder replaced with: $ApiGatewayUrl" -ForegroundColor Green
    } else {
        Write-Host "`n[1/4] No API Gateway URL provided, deploying JS as-is..." -ForegroundColor Yellow
        Write-Host "  Warning: slashMyBill.js still contains the placeholder URL" -ForegroundColor Yellow
    }

    # Step 2: Upload files to S3 with correct content types
    Write-Host "`n[2/4] Uploading frontend files to s3://$S3Bucket/slashMyBill/..." -ForegroundColor Yellow

    # Upload index.html
    $htmlFile = Join-Path $FrontendDir "index.html"
    aws s3 cp $htmlFile "s3://$S3Bucket/slashMyBill/index.html" `
        --content-type "text/html" `
        --region $Region
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to upload index.html" -ForegroundColor Red
        exit 1
    }
    Write-Host "  Uploaded index.html (text/html)" -ForegroundColor Green

    # Upload slashMyBill.css
    $cssFile = Join-Path $FrontendDir "slashMyBill.css"
    aws s3 cp $cssFile "s3://$S3Bucket/slashMyBill/slashMyBill.css" `
        --content-type "text/css" `
        --region $Region
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to upload slashMyBill.css" -ForegroundColor Red
        exit 1
    }
    Write-Host "  Uploaded slashMyBill.css (text/css)" -ForegroundColor Green

    # Upload slashMyBill.js (possibly with replaced URL)
    aws s3 cp $jsSource "s3://$S3Bucket/slashMyBill/slashMyBill.js" `
        --content-type "application/javascript" `
        --region $Region
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to upload slashMyBill.js" -ForegroundColor Red
        exit 1
    }
    Write-Host "  Uploaded slashMyBill.js (application/javascript)" -ForegroundColor Green

    # Step 3: Invalidate CloudFront cache
    Write-Host "`n[3/4] Invalidating CloudFront cache for /slashMyBill/*..." -ForegroundColor Yellow
    $invalidationResult = aws cloudfront create-invalidation `
        --distribution-id $CloudFrontDistributionId `
        --paths "/slashMyBill/*" `
        --region $Region `
        --output json | ConvertFrom-Json

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: CloudFront invalidation failed" -ForegroundColor Red
        exit 1
    }

    $invalidationId = $invalidationResult.Invalidation.Id
    Write-Host "  Invalidation created: $invalidationId" -ForegroundColor Green
    Write-Host "  Note: Invalidation may take a few minutes to complete globally" -ForegroundColor Gray

    # Step 4: Summary
    Write-Host "`n[4/4] Deployment summary" -ForegroundColor Yellow
    Write-Host "  Files deployed to: s3://$S3Bucket/slashMyBill/" -ForegroundColor Green
    Write-Host "  CloudFront invalidation: $invalidationId" -ForegroundColor Green
    Write-Host "  URL: https://www.eshkolai.com/slashMyBill/" -ForegroundColor Green

} finally {
    # Cleanup temporary files
    if ($TempJsFile -and (Test-Path $TempJsFile)) {
        Remove-Item -Force $TempJsFile
        Write-Host "`n  Cleaned up temporary files." -ForegroundColor Gray
    }
}

Write-Host "`n=== SlashMyBill Frontend deployed successfully! ===" -ForegroundColor Cyan
