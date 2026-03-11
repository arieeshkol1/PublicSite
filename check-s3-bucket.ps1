# Check S3 Bucket Status
$bucketName = "arieleshkolwebsite22feb2026"

Write-Host "Checking S3 bucket: $bucketName" -ForegroundColor Cyan
Write-Host ""

# Check if bucket exists and is accessible
Write-Host "Attempting to list bucket contents..." -ForegroundColor Yellow
aws s3 ls s3://$bucketName/ --region us-east-1

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✓ Bucket is accessible!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Checking website configuration..." -ForegroundColor Yellow
    aws s3api get-bucket-website --bucket $bucketName --region us-east-1
} else {
    Write-Host ""
    Write-Host "✗ Cannot access bucket with current credentials" -ForegroundColor Red
    Write-Host "Current AWS Account:" -ForegroundColor Yellow
    aws sts get-caller-identity
}
