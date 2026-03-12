# Create eshkol.ai S3 bucket configured to redirect to www.eshkol.ai
# Account: 991105135552
# Run this script ONLY after the bucket name eshkol.ai becomes available

$BucketName = "eshkol.ai"
$RedirectTarget = "www.eshkol.ai"
$Region = "us-east-1"

Write-Host "Checking if bucket name is available..." -ForegroundColor Cyan
$checkResult = aws s3api head-bucket --bucket $BucketName 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "ERROR: Bucket already exists in your account!" -ForegroundColor Red
    Write-Host "This script is for creating a NEW redirect bucket." -ForegroundColor Red
    exit 1
}

if ($checkResult -like "*403*" -or $checkResult -like "*Forbidden*") {
    Write-Host "ERROR: Bucket name is still reserved in another account." -ForegroundColor Red
    Write-Host "Please wait and try again later (can take up to 24 hours)." -ForegroundColor Yellow
    exit 1
}

Write-Host "Bucket name is available! Creating redirect bucket..." -ForegroundColor Green
Write-Host ""

# Create the bucket
Write-Host "Creating S3 bucket: $BucketName" -ForegroundColor Cyan
aws s3api create-bucket --bucket $BucketName --region $Region
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to create bucket" -ForegroundColor Red
    exit 1
}
Write-Host "Bucket created successfully" -ForegroundColor Green

# Configure redirect (not static website hosting)
Write-Host ""
Write-Host "Configuring redirect to $RedirectTarget..." -ForegroundColor Cyan

$RedirectConfig = @"
{
    "RedirectAllRequestsTo": {
        "HostName": "$RedirectTarget",
        "Protocol": "http"
    }
}
"@

$RedirectConfig | Out-File -FilePath "redirect-config-temp.json" -Encoding utf8
aws s3api put-bucket-website --bucket $BucketName --website-configuration file://redirect-config-temp.json
Remove-Item "redirect-config-temp.json"

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to configure redirect" -ForegroundColor Red
    exit 1
}
Write-Host "Redirect configured successfully" -ForegroundColor Green

# Set bucket policy for public read access
Write-Host ""
Write-Host "Setting bucket policy for public access..." -ForegroundColor Cyan
$BucketPolicy = @"
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::$BucketName/*"
        }
    ]
}
"@

$BucketPolicy | Out-File -FilePath "bucket-policy-temp.json" -Encoding utf8
aws s3api put-bucket-policy --bucket $BucketName --policy file://bucket-policy-temp.json
Remove-Item "bucket-policy-temp.json"

if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Failed to set bucket policy (may not be needed for redirect)" -ForegroundColor Yellow
} else {
    Write-Host "Bucket policy set successfully" -ForegroundColor Green
}

# Disable block public access settings
Write-Host ""
Write-Host "Configuring public access settings..." -ForegroundColor Cyan
aws s3api put-public-access-block --bucket $BucketName --public-access-block-configuration "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"

if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Failed to configure public access" -ForegroundColor Yellow
} else {
    Write-Host "Public access configured successfully" -ForegroundColor Green
}

# Display bucket info
Write-Host ""
Write-Host "=== Redirect Bucket Setup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Bucket Name: $BucketName" -ForegroundColor Cyan
Write-Host "Redirects to: $RedirectTarget" -ForegroundColor Cyan
Write-Host "Region: $Region" -ForegroundColor Cyan
Write-Host "Website Endpoint: http://$BucketName.s3-website-$Region.amazonaws.com" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Go to Route 53 console"
Write-Host "2. Create A record for root domain (eshkol.ai):"
Write-Host "   - Record name: Leave blank"
Write-Host "   - Type: A"
Write-Host "   - Alias: Yes"
Write-Host "   - Route traffic to: Alias to S3 website endpoint"
Write-Host "   - Region: US East (N. Virginia)"
Write-Host "   - Endpoint: s3-website-us-east-1.amazonaws.com"
Write-Host ""
Write-Host "3. Test the redirect:"
Write-Host "   http://eshkol.ai should redirect to http://www.eshkol.ai"
Write-Host ""
Write-Host "Done!" -ForegroundColor Green
