# Deploy Tips Sync Lambda for SlashMyBill
# Creates the IAM execution role and Lambda function if they don't exist,
# then packages and deploys the tips-sync code.
#
# Usage: .\infrastructure\deploy-tips-sync-lambda.ps1
# Run from the repository root directory.

param(
    [string]$Region = "us-east-1",
    [string]$AccountId = "991105135552",
    [string]$S3Bucket = "aws-bill-analyzer-storage-991105135552",
    [string]$S3Key = "lambda-packages/tips-sync.zip",
    [string]$FunctionName = "slashmybill-tips-sync",
    [string]$RoleName = "slashmybill-tips-sync-role"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Deploy Tips Sync Lambda ===" -ForegroundColor Cyan

# Resolve paths relative to repo root
$RepoRoot = $PSScriptRoot | Split-Path -Parent
$SourceDir = Join-Path $RepoRoot "tips-sync"
$BuildDir = Join-Path $RepoRoot ".build-tips-sync"
$ZipFile = Join-Path $RepoRoot "tips-sync-lambda.zip"

# Validate source directory exists
if (-not (Test-Path $SourceDir)) {
    Write-Host "Error: tips-sync/ directory not found at $SourceDir" -ForegroundColor Red
    exit 1
}

# ============================================================
# Step 1: Create IAM Execution Role (if it doesn't exist)
# ============================================================
Write-Host "`n[1/7] Ensuring IAM execution role exists..." -ForegroundColor Yellow

$roleExists = $false
try {
    aws iam get-role --role-name $RoleName --region $Region 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $roleExists = $true
        Write-Host "  Role '$RoleName' already exists." -ForegroundColor Green
    }
} catch {
    $roleExists = $false
}

if (-not $roleExists) {
    Write-Host "  Creating role '$RoleName'..." -ForegroundColor Gray

    # Trust policy for Lambda
    $trustPolicy = @'
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
'@

    $trustPolicyFile = Join-Path $env:TEMP "tips-sync-trust-policy.json"
    $trustPolicy | Out-File -FilePath $trustPolicyFile -Encoding utf8

    aws iam create-role `
        --role-name $RoleName `
        --assume-role-policy-document "file://$trustPolicyFile" `
        --description "Execution role for slashmybill-tips-sync Lambda" `
        --region $Region | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to create IAM role" -ForegroundColor Red
        exit 1
    }

    Remove-Item -Force $trustPolicyFile -ErrorAction SilentlyContinue
    Write-Host "  Role created." -ForegroundColor Green

    # Wait for role to propagate
    Write-Host "  Waiting for role to propagate..." -ForegroundColor Gray
    Start-Sleep -Seconds 10
}

# ============================================================
# Step 2: Attach IAM policies to the role
# ============================================================
Write-Host "`n[2/7] Attaching IAM policies..." -ForegroundColor Yellow

# DynamoDB permissions
$dynamoDbPolicy = @"
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "DynamoDBTipsTable",
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:BatchWriteItem",
                "dynamodb:DeleteItem"
            ],
            "Resource": "arn:aws:dynamodb:${Region}:${AccountId}:table/ViewMyBill-CostOptimizationTips"
        }
    ]
}
"@

$dynamoDbPolicyFile = Join-Path $env:TEMP "tips-sync-dynamodb-policy.json"
$dynamoDbPolicy | Out-File -FilePath $dynamoDbPolicyFile -Encoding utf8

aws iam put-role-policy `
    --role-name $RoleName `
    --policy-name "TipsSyncDynamoDBAccess" `
    --policy-document "file://$dynamoDbPolicyFile" `
    --region $Region

Remove-Item -Force $dynamoDbPolicyFile -ErrorAction SilentlyContinue
Write-Host "  DynamoDB policy attached." -ForegroundColor Green

# Trusted Advisor permissions
$trustedAdvisorPolicy = @'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "TrustedAdvisorAccess",
            "Effect": "Allow",
            "Action": [
                "support:DescribeTrustedAdvisorChecks",
                "support:DescribeTrustedAdvisorCheckResult"
            ],
            "Resource": "*"
        }
    ]
}
'@

$trustedAdvisorPolicyFile = Join-Path $env:TEMP "tips-sync-ta-policy.json"
$trustedAdvisorPolicy | Out-File -FilePath $trustedAdvisorPolicyFile -Encoding utf8

aws iam put-role-policy `
    --role-name $RoleName `
    --policy-name "TipsSyncTrustedAdvisorAccess" `
    --policy-document "file://$trustedAdvisorPolicyFile" `
    --region $Region

Remove-Item -Force $trustedAdvisorPolicyFile -ErrorAction SilentlyContinue
Write-Host "  Trusted Advisor policy attached." -ForegroundColor Green

# Cost Optimization Hub permissions
$cohPolicy = @'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "CostOptimizationHubAccess",
            "Effect": "Allow",
            "Action": [
                "cost-optimization-hub:ListRecommendations",
                "cost-optimization-hub:GetRecommendation"
            ],
            "Resource": "*"
        }
    ]
}
'@

$cohPolicyFile = Join-Path $env:TEMP "tips-sync-coh-policy.json"
$cohPolicy | Out-File -FilePath $cohPolicyFile -Encoding utf8

aws iam put-role-policy `
    --role-name $RoleName `
    --policy-name "TipsSyncCostOptimizationHubAccess" `
    --policy-document "file://$cohPolicyFile" `
    --region $Region

Remove-Item -Force $cohPolicyFile -ErrorAction SilentlyContinue
Write-Host "  Cost Optimization Hub policy attached." -ForegroundColor Green

# CloudWatch Metrics permissions
$cwMetricsPolicy = @'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "CloudWatchMetrics",
            "Effect": "Allow",
            "Action": [
                "cloudwatch:PutMetricData"
            ],
            "Resource": "*"
        }
    ]
}
'@

$cwMetricsPolicyFile = Join-Path $env:TEMP "tips-sync-cw-metrics-policy.json"
$cwMetricsPolicy | Out-File -FilePath $cwMetricsPolicyFile -Encoding utf8

aws iam put-role-policy `
    --role-name $RoleName `
    --policy-name "TipsSyncCloudWatchMetrics" `
    --policy-document "file://$cwMetricsPolicyFile" `
    --region $Region

Remove-Item -Force $cwMetricsPolicyFile -ErrorAction SilentlyContinue
Write-Host "  CloudWatch Metrics policy attached." -ForegroundColor Green

# CloudWatch Logs permissions
$cwLogsPolicy = @"
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "CloudWatchLogs",
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:${Region}:${AccountId}:log-group:/aws/lambda/${FunctionName}:*"
        }
    ]
}
"@

$cwLogsPolicyFile = Join-Path $env:TEMP "tips-sync-cw-logs-policy.json"
$cwLogsPolicy | Out-File -FilePath $cwLogsPolicyFile -Encoding utf8

aws iam put-role-policy `
    --role-name $RoleName `
    --policy-name "TipsSyncCloudWatchLogs" `
    --policy-document "file://$cwLogsPolicyFile" `
    --region $Region

Remove-Item -Force $cwLogsPolicyFile -ErrorAction SilentlyContinue
Write-Host "  CloudWatch Logs policy attached." -ForegroundColor Green

# ============================================================
# Step 3: Clean up previous build artifacts
# ============================================================
Write-Host "`n[3/7] Cleaning previous build artifacts..." -ForegroundColor Yellow
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
if (Test-Path $ZipFile) { Remove-Item -Force $ZipFile }
Write-Host "  Done." -ForegroundColor Green

# ============================================================
# Step 4: Install dependencies and copy source files
# ============================================================
Write-Host "`n[4/7] Installing dependencies and copying source files..." -ForegroundColor Yellow
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null

$RequirementsFile = Join-Path $SourceDir "requirements.txt"
if (Test-Path $RequirementsFile) {
    pip install -r $RequirementsFile -t $BuildDir --quiet 2>$null
}

# Copy all Python source files (preserving directory structure)
$sourceFiles = Get-ChildItem -Path $SourceDir -Filter "*.py" -File
foreach ($file in $sourceFiles) {
    Copy-Item $file.FullName -Destination $BuildDir
    Write-Host "  Copied $($file.Name)" -ForegroundColor Gray
}

# Copy sources/ subdirectory
$sourcesDir = Join-Path $SourceDir "sources"
if (Test-Path $sourcesDir) {
    $destSourcesDir = Join-Path $BuildDir "sources"
    New-Item -ItemType Directory -Path $destSourcesDir -Force | Out-Null
    $sourcesFiles = Get-ChildItem -Path $sourcesDir -Filter "*.py" -File
    foreach ($file in $sourcesFiles) {
        Copy-Item $file.FullName -Destination $destSourcesDir
        Write-Host "  Copied sources/$($file.Name)" -ForegroundColor Gray
    }
}

# Bundle the knowledge-base tips file
$tipsFile = Join-Path $RepoRoot "knowledge-base" "aws-cost-optimization-tips.json"
if (Test-Path $tipsFile) {
    $kbDir = Join-Path $BuildDir "knowledge-base"
    New-Item -ItemType Directory -Path $kbDir -Force | Out-Null
    Copy-Item $tipsFile -Destination $kbDir
    Write-Host "  Bundled knowledge-base/aws-cost-optimization-tips.json" -ForegroundColor Gray
}

Write-Host "  Source files copied." -ForegroundColor Green

# ============================================================
# Step 5: Create ZIP package
# ============================================================
Write-Host "`n[5/7] Creating deployment package..." -ForegroundColor Yellow
Compress-Archive -Path "$BuildDir\*" -DestinationPath $ZipFile -Force
if (-not (Test-Path $ZipFile)) {
    Write-Host "Error: Failed to create ZIP file" -ForegroundColor Red
    exit 1
}
$zipSize = (Get-Item $ZipFile).Length / 1MB
Write-Host "  Created $ZipFile ($([math]::Round($zipSize, 2)) MB)" -ForegroundColor Green

# ============================================================
# Step 6: Upload ZIP to S3
# ============================================================
Write-Host "`n[6/7] Uploading to S3..." -ForegroundColor Yellow
aws s3 cp $ZipFile "s3://$S3Bucket/$S3Key" --region $Region
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: S3 upload failed" -ForegroundColor Red
    exit 1
}
Write-Host "  Uploaded to s3://$S3Bucket/$S3Key" -ForegroundColor Green

# ============================================================
# Step 7: Create or Update Lambda function
# ============================================================
Write-Host "`n[7/7] Creating or updating Lambda function..." -ForegroundColor Yellow

$RoleArn = "arn:aws:iam::${AccountId}:role/${RoleName}"

$functionExists = $false
try {
    aws lambda get-function --function-name $FunctionName --region $Region 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $functionExists = $true
    }
} catch {
    $functionExists = $false
}

if ($functionExists) {
    Write-Host "  Function '$FunctionName' already exists. Updating code..." -ForegroundColor Gray
    aws lambda update-function-code `
        --function-name $FunctionName `
        --s3-bucket $S3Bucket `
        --s3-key $S3Key `
        --region $Region | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Lambda code update failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "  Lambda function code updated." -ForegroundColor Green
} else {
    Write-Host "  Creating function '$FunctionName'..." -ForegroundColor Gray
    aws lambda create-function `
        --function-name $FunctionName `
        --runtime python3.12 `
        --handler lambda_function.lambda_handler `
        --role $RoleArn `
        --code "S3Bucket=$S3Bucket,S3Key=$S3Key" `
        --timeout 300 `
        --memory-size 256 `
        --region $Region `
        --description "Tips Auto-Sync: fetches cost optimization tips from AWS sources and syncs to DynamoDB" | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Lambda function creation failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "  Lambda function created." -ForegroundColor Green
}

# ============================================================
# Cleanup
# ============================================================
Write-Host "`nCleaning up build artifacts..." -ForegroundColor Yellow
Remove-Item -Recurse -Force $BuildDir
Remove-Item -Force $ZipFile
Write-Host "  Cleanup complete." -ForegroundColor Green

Write-Host "`n=== Tips Sync Lambda deployed successfully! ===" -ForegroundColor Cyan
Write-Host "  Function: $FunctionName" -ForegroundColor Gray
Write-Host "  Runtime:  python3.12" -ForegroundColor Gray
Write-Host "  Timeout:  300s" -ForegroundColor Gray
Write-Host "  Memory:   256 MB" -ForegroundColor Gray
Write-Host "  Role:     $RoleName" -ForegroundColor Gray
