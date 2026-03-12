# Create eshkol.ai S3 bucket and configure it for static website hosting
# Account: 991105135552

$BucketName = "eshkol.ai"
$Region = "us-east-1"

Write-Host "Creating S3 bucket: $BucketName in region: $Region" -ForegroundColor Cyan

# Create the bucket
aws s3api create-bucket --bucket $BucketName --region $Region
if ($LASTEXITCODE -eq 0) {
    Write-Host "Bucket created successfully" -ForegroundColor Green
} else {
    Write-Host "Note: Bucket may already exist or error occurred" -ForegroundColor Yellow
}

# Enable static website hosting
Write-Host ""
Write-Host "Enabling static website hosting..." -ForegroundColor Cyan
aws s3 website s3://$BucketName/ --index-document index.html --error-document index.html
Write-Host "Static website hosting enabled" -ForegroundColor Green

# Set bucket policy for public read access and GitHub deployment
Write-Host ""
Write-Host "Setting bucket policy..." -ForegroundColor Cyan
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
                "arn:aws:s3:::$BucketName/*",
                "arn:aws:s3:::$BucketName"
            ]
        }
    ]
}
"@

$BucketPolicy | Out-File -FilePath "bucket-policy-temp.json" -Encoding utf8
aws s3api put-bucket-policy --bucket $BucketName --policy file://bucket-policy-temp.json
Remove-Item "bucket-policy-temp.json"
Write-Host "Bucket policy set" -ForegroundColor Green

# Disable block public access settings
Write-Host ""
Write-Host "Configuring public access settings..." -ForegroundColor Cyan
aws s3api put-public-access-block --bucket $BucketName --public-access-block-configuration "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"
Write-Host "Public access configured" -ForegroundColor Green

# Copy files from www.eshkol.ai bucket
Write-Host ""
Write-Host "Copying files from www.eshkol.ai bucket..." -ForegroundColor Cyan
aws s3 sync s3://www.eshkol.ai/ s3://$BucketName/ --source-region $Region --region $Region
Write-Host "Files copied successfully" -ForegroundColor Green

# Display bucket info
Write-Host ""
Write-Host "=== Bucket Information ===" -ForegroundColor Cyan
Write-Host "Bucket Name: $BucketName"
Write-Host "Region: $Region"
Write-Host "Website Endpoint: http://$BucketName.s3-website-$Region.amazonaws.com"
Write-Host ""
Write-Host "Files in bucket:" -ForegroundColor Cyan
aws s3 ls s3://$BucketName/ --human-readable

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. GitHub workflow already updated to use bucket: $BucketName"
Write-Host "2. Create A record alias in Route 53 pointing to S3 website endpoint"
Write-Host "   - Go to Route 53 > Hosted zones > eshkol.ai"
Write-Host "   - Create record > Leave name blank > Type: A"
Write-Host "   - Alias to S3 website endpoint > US East (N. Virginia)"
Write-Host "   - Select: s3-website-us-east-1.amazonaws.com"
