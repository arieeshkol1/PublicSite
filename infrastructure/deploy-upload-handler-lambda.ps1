# Deploy Upload Handler Lambda for ViewMyBill
# Packages the upload handler source code, uploads to S3, and updates the Lambda function.
# No pip dependencies needed — boto3 is provided by the Lambda runtime.
#
# Usage: .\infrastructure\deploy-upload-handler-lambda.ps1
# Run from the repository root directory.

param(
    [string]$StackName = "aws-bill-analyzer-viewmybill",
    [string]$Region = "us-east-1",
    [string]$S3Bucket = "aws-bill-analyzer-storage-991105135552",
    [string]$S3Key = "lambda-packages/upload-handler.zip"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Deploy Upload Handler Lambda ===" -ForegroundColor Cyan

# Resolve paths relative to repo root
$RepoRoot = $PSScriptRoot | Split-Path -Parent
$SourceDir = Join-Path $RepoRoot "upload-handler"
$BuildDir = Join-Path $RepoRoot ".build-upload-handler"
$ZipFile = Join-Path $RepoRoot "upload-handler-lambda.zip"

# Validate source directory exists
if (-not (Test-Path $SourceDir)) {
    Write-Host "Error: upload-handler/ directory not found at $SourceDir" -ForegroundColor Red
    exit 1
}

# Step 1: Clean up any previous build artifacts
Write-Host "`n[1/5] Cleaning previous build artifacts..." -ForegroundColor Yellow
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
if (Test-Path $ZipFile) { Remove-Item -Force $ZipFile }
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null
Write-Host "  Done." -ForegroundColor Green

# Step 2: Copy Lambda source file (no pip install needed — boto3 is in the runtime)
Write-Host "`n[2/5] Copying Lambda source files..." -ForegroundColor Yellow
$sourceFiles = Get-ChildItem -Path $SourceDir -Filter "*.py" -File
foreach ($file in $sourceFiles) {
    Copy-Item $file.FullName -Destination $BuildDir
    Write-Host "  Copied $($file.Name)" -ForegroundColor Gray
}
Write-Host "  Source files copied." -ForegroundColor Green

# Step 3: Create ZIP package
Write-Host "`n[3/5] Creating deployment package..." -ForegroundColor Yellow
Compress-Archive -Path "$BuildDir\*" -DestinationPath $ZipFile -Force
if (-not (Test-Path $ZipFile)) {
    Write-Host "Error: Failed to create ZIP file" -ForegroundColor Red
    exit 1
}
$zipSize = (Get-Item $ZipFile).Length / 1KB
Write-Host "  Created $ZipFile ($([math]::Round($zipSize, 2)) KB)" -ForegroundColor Green

# Step 4: Upload ZIP to S3
Write-Host "`n[4/5] Uploading to S3..." -ForegroundColor Yellow
aws s3 cp $ZipFile "s3://$S3Bucket/$S3Key" --region $Region
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: S3 upload failed" -ForegroundColor Red
    exit 1
}
Write-Host "  Uploaded to s3://$S3Bucket/$S3Key" -ForegroundColor Green

# Step 5: Update Lambda function code
Write-Host "`n[5/5] Updating Lambda function code..." -ForegroundColor Yellow

# Look up the Lambda function name from CloudFormation
$functionName = aws cloudformation describe-stack-resource `
    --stack-name $StackName `
    --logical-resource-id UploadHandlerFunction `
    --query "StackResourceDetail.PhysicalResourceId" `
    --output text `
    --region $Region 2>$null

if ([string]::IsNullOrEmpty($functionName) -or $LASTEXITCODE -ne 0) {
    Write-Host "  Could not look up function name from stack '$StackName'. Using default." -ForegroundColor Yellow
    $functionName = "aws-bill-analyzer-upload-handler"
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

Write-Host "`n=== Upload Handler Lambda deployed successfully! ===" -ForegroundColor Cyan
