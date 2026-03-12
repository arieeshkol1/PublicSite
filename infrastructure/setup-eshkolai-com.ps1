# Setup eshkolai.com domain with S3 static website hosting
# Account: 991105135552

$WwwBucket = "www.eshkolai.com"
$RootBucket = "eshkolai.com"
$SourceBucket = "www.eshkol.ai"
$Region = "us-east-1"

Write-Host "=== Setting up eshkolai.com ===" -ForegroundColor Cyan
Write-Host ""

# Create www.eshkolai.com bucket
Write-Host "Creating www.eshkolai.com bucket..." -ForegroundColor Yellow
aws s3api create-bucket --bucket $WwwBucket --region $Region
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK Bucket created" -ForegroundColor Green
} else {
    Write-Host "Note: Bucket may already exist" -ForegroundColor Yellow
}

# Enable static website hosting
Write-Host ""
Write-Host "Enabling static website hosting..." -ForegroundColor Yellow
aws s3 website s3://$WwwBucket/ --index-document index.html --error-document index.html
Write-Host "OK Static website hosting enabled" -ForegroundColor Green

# Set bucket policy
Write-Host ""
Write-Host "Setting bucket policy..." -ForegroundColor Yellow
$BucketPolicy = @"
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::$WwwBucket/*"
        },
        {
            "Sid": "GitHubDeployAccess",
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::991105135552:role/GitHubDeployRole"
            },
            "Action": [
                "s3:PutObject",
                "s3:PutObjectAcl",
                "s3:DeleteObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::$WwwBucket/*",
                "arn:aws:s3:::$WwwBucket"
            ]
        }
    ]
}
"@

$BucketPolicy | Out-File -FilePath "bucket-policy-temp.json" -Encoding utf8
aws s3api put-bucket-policy --bucket $WwwBucket --policy file://bucket-policy-temp.json
Remove-Item "bucket-policy-temp.json"
Write-Host "OK Bucket policy set" -ForegroundColor Green

# Disable block public access
Write-Host ""
Write-Host "Configuring public access..." -ForegroundColor Yellow
aws s3api put-public-access-block --bucket $WwwBucket --public-access-block-configuration "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"
Write-Host "OK Public access configured" -ForegroundColor Green

# Copy files from source bucket
Write-Host ""
Write-Host "Copying files from $SourceBucket..." -ForegroundColor Yellow
aws s3 sync s3://$SourceBucket/ s3://$WwwBucket/ --source-region $Region --region $Region
Write-Host "OK Files copied" -ForegroundColor Green

Write-Host ""
Write-Host "=== www.eshkolai.com Setup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Bucket: $WwwBucket" -ForegroundColor Cyan
Write-Host "Website Endpoint: http://$WwwBucket.s3-website-$Region.amazonaws.com" -ForegroundColor Cyan
Write-Host ""

# List files
Write-Host "Files in bucket:" -ForegroundColor Cyan
aws s3 ls s3://$WwwBucket/ --human-readable

Write-Host ""
Write-Host "=== Creating Root Domain Redirect Bucket ===" -ForegroundColor Cyan
Write-Host ""

# Create root domain bucket
Write-Host "Creating eshkolai.com bucket..." -ForegroundColor Yellow
aws s3api create-bucket --bucket $RootBucket --region $Region
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK Bucket created" -ForegroundColor Green
} else {
    Write-Host "Note: Bucket may already exist" -ForegroundColor Yellow
}

# Configure redirect
Write-Host ""
Write-Host "Configuring redirect to www.eshkolai.com..." -ForegroundColor Yellow
$RedirectConfig = @"
{
    "RedirectAllRequestsTo": {
        "HostName": "$WwwBucket",
        "Protocol": "http"
    }
}
"@

$RedirectConfig | Out-File -FilePath "redirect-config-temp.json" -Encoding utf8
aws s3api put-bucket-website --bucket $RootBucket --website-configuration file://redirect-config-temp.json
Remove-Item "redirect-config-temp.json"
Write-Host "OK Redirect configured" -ForegroundColor Green

# Set bucket policy for root
Write-Host ""
Write-Host "Setting bucket policy for root domain..." -ForegroundColor Yellow
$RootBucketPolicy = @"
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::$RootBucket/*"
        }
    ]
}
"@

$RootBucketPolicy | Out-File -FilePath "bucket-policy-temp.json" -Encoding utf8
aws s3api put-bucket-policy --bucket $RootBucket --policy file://bucket-policy-temp.json
Remove-Item "bucket-policy-temp.json"
Write-Host "OK Bucket policy set" -ForegroundColor Green

# Disable block public access for root
Write-Host ""
Write-Host "Configuring public access for root domain..." -ForegroundColor Yellow
aws s3api put-public-access-block --bucket $RootBucket --public-access-block-configuration "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"
Write-Host "OK Public access configured" -ForegroundColor Green

Write-Host ""
Write-Host "=== Complete Setup Summary ===" -ForegroundColor Green
Write-Host ""
Write-Host "WWW Bucket: $WwwBucket" -ForegroundColor Cyan
Write-Host "  Endpoint: http://$WwwBucket.s3-website-$Region.amazonaws.com" -ForegroundColor Gray
Write-Host ""
Write-Host "Root Bucket: $RootBucket" -ForegroundColor Cyan
Write-Host "  Endpoint: http://$RootBucket.s3-website-$Region.amazonaws.com" -ForegroundColor Gray
Write-Host "  Redirects to: www.eshkolai.com" -ForegroundColor Gray
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Test S3 endpoint: http://$WwwBucket.s3-website-$Region.amazonaws.com"
Write-Host "2. Create Route 53 hosted zone for eshkolai.com"
Write-Host "3. Create CNAME record: www.eshkolai.com -> $WwwBucket.s3-website-$Region.amazonaws.com"
Write-Host "4. Create A record alias: eshkolai.com -> S3 website endpoint"
Write-Host "5. Update nameservers at domain registrar to Route 53 nameservers"
