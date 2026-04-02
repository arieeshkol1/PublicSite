# Deploy Agent Action Lambda for SlashMyBill Bedrock Agent
# Packages the agent-action source code, uploads to S3, updates the Lambda,
# then re-deploys the CloudFormation stack to apply IAM policy changes.
#
# Usage: .\infrastructure\deploy-agent-action-lambda.ps1
# Run from the repository root directory.

param(
    [string]$StackName = "aws-bill-analyzer-viewmybill",
    [string]$Region = "us-east-1",
    [string]$S3Bucket = "aws-bill-analyzer-storage-991105135552",
    [string]$S3Key = "lambda-packages/agent-action.zip",
    [string]$FunctionName = "SlashMyBill-AgentAction"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Deploy Agent Action Lambda ===" -ForegroundColor Cyan

$RepoRoot = $PSScriptRoot | Split-Path -Parent
$SourceDir = Join-Path $RepoRoot "agent-action"
$BuildDir  = Join-Path $RepoRoot ".build-agent-action"
$ZipFile   = Join-Path $RepoRoot "agent-action-lambda.zip"

if (-not (Test-Path $SourceDir)) {
    Write-Host "Error: agent-action/ directory not found at $SourceDir" -ForegroundColor Red
    exit 1
}

# Step 1: Clean previous build
Write-Host "`n[1/5] Cleaning previous build artifacts..." -ForegroundColor Yellow
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
if (Test-Path $ZipFile)  { Remove-Item -Force $ZipFile }
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null
Write-Host "  Done." -ForegroundColor Green

# Step 2: Copy Lambda source (boto3 provided by runtime, no pip install needed)
Write-Host "`n[2/5] Copying Lambda source files..." -ForegroundColor Yellow
Get-ChildItem -Path $SourceDir -Filter "*.py" -File | ForEach-Object {
    Copy-Item $_.FullName -Destination $BuildDir
    Write-Host "  Copied $($_.Name)" -ForegroundColor Gray
}
Write-Host "  Source files copied." -ForegroundColor Green

# Step 3: Create ZIP
Write-Host "`n[3/5] Creating deployment package..." -ForegroundColor Yellow
Compress-Archive -Path "$BuildDir\*" -DestinationPath $ZipFile -Force
$zipSize = [math]::Round((Get-Item $ZipFile).Length / 1KB, 2)
Write-Host "  Created $ZipFile ($zipSize KB)" -ForegroundColor Green

# Step 4: Upload to S3
Write-Host "`n[4/5] Uploading to S3..." -ForegroundColor Yellow
aws s3 cp $ZipFile "s3://$S3Bucket/$S3Key" --region $Region
if ($LASTEXITCODE -ne 0) { Write-Host "Error: S3 upload failed" -ForegroundColor Red; exit 1 }
Write-Host "  Uploaded to s3://$S3Bucket/$S3Key" -ForegroundColor Green

# Step 5: Update Lambda code
Write-Host "`n[5/5] Updating Lambda function code..." -ForegroundColor Yellow
aws lambda update-function-code `
    --function-name $FunctionName `
    --s3-bucket $S3Bucket `
    --s3-key $S3Key `
    --region $Region | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "Error: Lambda update failed" -ForegroundColor Red; exit 1 }
Write-Host "  Lambda '$FunctionName' updated." -ForegroundColor Green

# Cleanup
Write-Host "`nCleaning up build artifacts..." -ForegroundColor Yellow
Remove-Item -Recurse -Force $BuildDir
Remove-Item -Force $ZipFile
Write-Host "  Done." -ForegroundColor Green

# Step 6: Update CloudFormation stack to apply IAM policy changes (pricing permissions)
Write-Host "`n[+] Updating CloudFormation stack to apply IAM policy changes..." -ForegroundColor Yellow
Write-Host "    (This adds pricing:GetProducts to the AgentAction Lambda role)" -ForegroundColor Gray

$templatePath = Join-Path $PSScriptRoot "viewmybill-stack.yaml"

# Read current parameter values from the stack so we don't need to re-supply secrets
$existingParams = aws cloudformation describe-stacks `
    --stack-name $StackName `
    --region $Region `
    --query "Stacks[0].Parameters" `
    --output json 2>$null | ConvertFrom-Json

if ($null -eq $existingParams) {
    Write-Host "  Warning: Could not read existing stack parameters. Skipping CFN update." -ForegroundColor Yellow
    Write-Host "  You can manually run: aws cloudformation deploy --template-file infrastructure/viewmybill-stack.yaml --stack-name $StackName --capabilities CAPABILITY_NAMED_IAM --no-fail-on-empty-changeset" -ForegroundColor Gray
} else {
    # Build --parameter-overrides using UsePreviousValue for all params
    $overrides = ($existingParams | ForEach-Object { "$($_.ParameterKey)=$$($_.ParameterValue)" }) -join " "

    aws cloudformation deploy `
        --template-file $templatePath `
        --stack-name $StackName `
        --capabilities CAPABILITY_NAMED_IAM `
        --no-fail-on-empty-changeset `
        --region $Region `
        --parameter-overrides `
            AdminUsername="$(($existingParams | Where-Object { $_.ParameterKey -eq 'AdminUsername' }).ParameterValue)" `
            AdminPasswordHash="$(($existingParams | Where-Object { $_.ParameterKey -eq 'AdminPasswordHash' }).ParameterValue)" `
            JWTSecret="$(($existingParams | Where-Object { $_.ParameterKey -eq 'JWTSecret' }).ParameterValue)"

    if ($LASTEXITCODE -eq 0) {
        Write-Host "  CloudFormation stack updated — IAM pricing permissions applied." -ForegroundColor Green
    } else {
        Write-Host "  CloudFormation update failed. Apply manually or via GitHub Actions." -ForegroundColor Yellow
    }
}

Write-Host "`n=== Agent Action Lambda deployed successfully! ===" -ForegroundColor Cyan
Write-Host "The agent can now answer real-time AWS pricing questions." -ForegroundColor Gray
