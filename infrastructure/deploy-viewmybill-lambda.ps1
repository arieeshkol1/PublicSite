# Deploy Bill Analyzer Lambda for ViewMyBill
# Packages Python dependencies + source code, uploads to S3, and updates the Lambda function.
#
# Usage: .\infrastructure\deploy-viewmybill-lambda.ps1
# Run from the repository root directory.

param(
    [string]$StackName = "aws-bill-analyzer-viewmybill",
    [string]$Region = "us-east-1",
    [string]$S3Bucket = "aws-bill-analyzer-storage-991105135552",
    [string]$S3Key = "lambda-packages/bill-analyzer.zip"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Deploy Bill Analyzer Lambda ===" -ForegroundColor Cyan

# Resolve paths relative to repo root
$RepoRoot = $PSScriptRoot | Split-Path -Parent
$SourceDir = Join-Path $RepoRoot "bill-analyzer"
$RequirementsFile = Join-Path $SourceDir "requirements.txt"
$BuildDir = Join-Path $RepoRoot ".build-bill-analyzer"
$ZipFile = Join-Path $RepoRoot "bill-analyzer-lambda.zip"

# Validate source directory exists
if (-not (Test-Path $SourceDir)) {
    Write-Host "Error: bill-analyzer/ directory not found at $SourceDir" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $RequirementsFile)) {
    Write-Host "Error: requirements.txt not found at $RequirementsFile" -ForegroundColor Red
    exit 1
}

# Step 1: Clean up any previous build artifacts
Write-Host "`n[1/6] Cleaning previous build artifacts..." -ForegroundColor Yellow
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
if (Test-Path $ZipFile) { Remove-Item -Force $ZipFile }
Write-Host "  Done." -ForegroundColor Green

# Step 2: Install Python dependencies into build directory
Write-Host "`n[2/6] Installing Python dependencies..." -ForegroundColor Yellow
pip install -r $RequirementsFile -t $BuildDir --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: pip install failed" -ForegroundColor Red
    exit 1
}
Write-Host "  Dependencies installed to $BuildDir" -ForegroundColor Green

# Step 3: Copy Lambda source files (exclude tests/ and __pycache__/)
Write-Host "`n[3/6] Copying Lambda source files..." -ForegroundColor Yellow
$sourceFiles = Get-ChildItem -Path $SourceDir -Filter "*.py" -File | Where-Object { $_.Name -ne "__init__.py" }
foreach ($file in $sourceFiles) {
    Copy-Item $file.FullName -Destination $BuildDir
    Write-Host "  Copied $($file.Name)" -ForegroundColor Gray
}
Write-Host "  Source files copied." -ForegroundColor Green

# Step 4: Create ZIP package
Write-Host "`n[4/6] Creating deployment package..." -ForegroundColor Yellow
Compress-Archive -Path "$BuildDir\*" -DestinationPath $ZipFile -Force
if (-not (Test-Path $ZipFile)) {
    Write-Host "Error: Failed to create ZIP file" -ForegroundColor Red
    exit 1
}
$zipSize = (Get-Item $ZipFile).Length / 1MB
Write-Host "  Created $ZipFile ($([math]::Round($zipSize, 2)) MB)" -ForegroundColor Green

# Step 5: Upload ZIP to S3
Write-Host "`n[5/6] Uploading to S3..." -ForegroundColor Yellow
aws s3 cp $ZipFile "s3://$S3Bucket/$S3Key" --region $Region
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: S3 upload failed" -ForegroundColor Red
    exit 1
}
Write-Host "  Uploaded to s3://$S3Bucket/$S3Key" -ForegroundColor Green

# Step 6: Update Lambda function code
Write-Host "`n[6/6] Updating Lambda function code..." -ForegroundColor Yellow

# Look up the Lambda function name from CloudFormation
$functionName = aws cloudformation describe-stack-resource `
    --stack-name $StackName `
    --logical-resource-id BillAnalyzerFunction `
    --query "StackResourceDetail.PhysicalResourceId" `
    --output text `
    --region $Region 2>$null

if ([string]::IsNullOrEmpty($functionName) -or $LASTEXITCODE -ne 0) {
    Write-Host "  Could not look up function name from stack '$StackName'. Using default." -ForegroundColor Yellow
    $functionName = "aws-bill-analyzer-viewmybill"
}

Write-Host "  Updating function: $functionName" -ForegroundColor Gray
aws lambda update-function-code `
    --function-name $functionName `
    --s3-bucket $S3Bucket `
    --s3-key $S3Key `
    --region $Region | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Lambda update failed" -ForegroundColor Red
    exit 1
}
Write-Host "  Lambda function updated." -ForegroundColor Green

# Cleanup
Write-Host "`nCleaning up build artifacts..." -ForegroundColor Yellow
Remove-Item -Recurse -Force $BuildDir
Remove-Item -Force $ZipFile
Write-Host "  Cleanup complete." -ForegroundColor Green

Write-Host "`n=== Bill Analyzer Lambda deployed successfully! ===" -ForegroundColor Cyan
