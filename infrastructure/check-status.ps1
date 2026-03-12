# Check current status of eshkol.ai domain setup
# Account: 991105135552

$RootBucket = "eshkol.ai"
$WwwBucket = "www.eshkol.ai"
$HostedZoneId = "Z06481861W6WD32QMETRV"

Write-Host "=== Eshkol.ai Domain Setup Status ===" -ForegroundColor Cyan
Write-Host ""

# Check www.eshkol.ai bucket
Write-Host "Checking www.eshkol.ai bucket..." -ForegroundColor Yellow
aws s3api head-bucket --bucket $WwwBucket 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK www.eshkol.ai bucket exists" -ForegroundColor Green
    
    # Check if static website hosting is enabled
    aws s3api get-bucket-website --bucket $WwwBucket 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK Static website hosting enabled" -ForegroundColor Green
        Write-Host "  Endpoint: http://$WwwBucket.s3-website-us-east-1.amazonaws.com" -ForegroundColor Gray
    }
    
    # List files
    Write-Host "  Files in bucket:" -ForegroundColor Gray
    aws s3 ls s3://$WwwBucket/ --human-readable
}
else {
    Write-Host "ERROR www.eshkol.ai bucket does NOT exist" -ForegroundColor Red
}

Write-Host ""

# Check eshkol.ai bucket availability
Write-Host "Checking eshkol.ai bucket..." -ForegroundColor Yellow
$rootCheckOutput = aws s3api head-bucket --bucket $RootBucket 2>&1 | Out-String
$rootCheckCode = $LASTEXITCODE

if ($rootCheckCode -eq 0) {
    Write-Host "OK eshkol.ai bucket exists in your account" -ForegroundColor Green
    
    # Check if redirect is configured
    aws s3api get-bucket-website --bucket $RootBucket 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK Redirect configured" -ForegroundColor Green
        Write-Host "  Endpoint: http://$RootBucket.s3-website-us-east-1.amazonaws.com" -ForegroundColor Gray
    }
}
elseif ($rootCheckOutput -match "403|Forbidden") {
    Write-Host "WAIT Bucket name still reserved in another account" -ForegroundColor Yellow
    Write-Host "   Wait and check again later (can take up to 24 hours)" -ForegroundColor Gray
}
elseif ($rootCheckOutput -match "404|NoSuchBucket") {
    Write-Host "READY Bucket name is AVAILABLE! Ready to create." -ForegroundColor Green
}
else {
    Write-Host "UNKNOWN Unknown status" -ForegroundColor Gray
}

Write-Host ""

# Check Route 53 records
Write-Host "Checking Route 53 DNS records..." -ForegroundColor Yellow
$recordsJson = aws route53 list-resource-record-sets --hosted-zone-id $HostedZoneId --output json
$records = $recordsJson | ConvertFrom-Json

$hasCNAME = $false
$hasARecord = $false

foreach ($record in $records.ResourceRecordSets) {
    if ($record.Name -eq "www.eshkol.ai." -and $record.Type -eq "CNAME") {
        $hasCNAME = $true
        Write-Host "OK CNAME record for www.eshkol.ai exists" -ForegroundColor Green
        Write-Host "  Points to: $($record.ResourceRecords[0].Value)" -ForegroundColor Gray
    }
    if ($record.Name -eq "eshkol.ai." -and $record.Type -eq "A") {
        $hasARecord = $true
        Write-Host "OK A record for eshkol.ai exists" -ForegroundColor Green
        if ($record.AliasTarget) {
            Write-Host "  Alias to: $($record.AliasTarget.DNSName)" -ForegroundColor Gray
        }
    }
}

if (-not $hasARecord) {
    Write-Host "WAIT A record for eshkol.ai does NOT exist yet" -ForegroundColor Yellow
    Write-Host "   Create this after eshkol.ai bucket is set up" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Current working URL: http://www.eshkol.ai" -ForegroundColor Green
Write-Host ""

Write-Host "Next steps:" -ForegroundColor Cyan
if ($rootCheckOutput -match "404|NoSuchBucket") {
    Write-Host "1. Run: ./create-redirect-bucket.ps1" -ForegroundColor White
    Write-Host "2. Or use GitHub Actions workflow: setup-root-domain-redirect" -ForegroundColor White
}
elseif ($rootCheckOutput -match "403|Forbidden") {
    Write-Host "1. Wait for bucket name to be released" -ForegroundColor White
    Write-Host "2. Run this script again to check status" -ForegroundColor White
}
else {
    Write-Host "Setup appears complete! Test your site at:" -ForegroundColor White
    Write-Host "  - http://www.eshkol.ai" -ForegroundColor White
    Write-Host "  - http://eshkol.ai (should redirect to www)" -ForegroundColor White
}
