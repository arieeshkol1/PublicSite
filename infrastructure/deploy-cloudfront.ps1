# Deploy CloudFront and Certificate Stack for eshkol.ai
# Prerequisites: Route 53 hosted zone for eshkol.ai must exist

$StackName = "eshkol-ai-cloudfront-stack"
$TemplateFile = "cloudfront-setup.yaml"
$Region = "us-east-1"  # Must be us-east-1 for ACM certificates used with CloudFront

Write-Host "=== CloudFront Setup for eshkol.ai ===" -ForegroundColor Cyan

# Get the Hosted Zone ID
Write-Host "`nFetching Route 53 Hosted Zone ID..." -ForegroundColor Yellow
$hostedZones = aws route53 list-hosted-zones-by-name `
    --dns-name "eshkol.ai" `
    --query "HostedZones[?Name=='eshkol.ai.'].Id" `
    --output text

if ([string]::IsNullOrEmpty($hostedZones)) {
    Write-Host "✗ Error: Could not find hosted zone for eshkol.ai" -ForegroundColor Red
    Write-Host "Please create the hosted zone first in Route 53" -ForegroundColor Yellow
    exit 1
}

$HostedZoneId = $hostedZones.Split('/')[-1]
Write-Host "✓ Found Hosted Zone ID: $HostedZoneId" -ForegroundColor Green

# Deploy the stack
Write-Host "`nDeploying CloudFormation stack..." -ForegroundColor Yellow
aws cloudformation deploy `
    --template-file $TemplateFile `
    --stack-name $StackName `
    --region $Region `
    --parameter-overrides `
        DomainName=eshkol.ai `
        HostedZoneId=$HostedZoneId `
        S3BucketName=arieleshkolwebsite22feb2026 `
    --capabilities CAPABILITY_NAMED_IAM `
    --no-fail-on-empty-changeset

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✓ Stack deployed successfully!" -ForegroundColor Green
    
    # Get the outputs
    Write-Host "`nFetching stack outputs..." -ForegroundColor Cyan
    $outputs = aws cloudformation describe-stacks `
        --stack-name $StackName `
        --region $Region `
        --query 'Stacks[0].Outputs' `
        --output json | ConvertFrom-Json
    
    Write-Host "`n=== Stack Outputs ===" -ForegroundColor Cyan
    foreach ($output in $outputs) {
        Write-Host "$($output.OutputKey): $($output.OutputValue)" -ForegroundColor White
    }
    
    Write-Host "`n=== IMPORTANT: Next Steps ===" -ForegroundColor Yellow
    Write-Host "`n1. CERTIFICATE VALIDATION (5-30 minutes):" -ForegroundColor White
    Write-Host "   - ACM certificate will auto-validate via DNS"
    Write-Host "   - Check status: https://console.aws.amazon.com/acm"
    
    Write-Host "`n2. CLOUDFRONT DEPLOYMENT (15-20 minutes):" -ForegroundColor White
    Write-Host "   - CloudFront distribution is being deployed globally"
    Write-Host "   - Check status: https://console.aws.amazon.com/cloudfront"
    
    Write-Host "`n3. DNS PROPAGATION (up to 48 hours):" -ForegroundColor White
    Write-Host "   - DNS changes may take time to propagate globally"
    Write-Host "   - Test with: nslookup eshkol.ai"
    
    Write-Host "`n4. WEBSITE ACCESS:" -ForegroundColor White
    Write-Host "   - https://eshkol.ai"
    Write-Host "   - https://www.eshkol.ai"
    
    Write-Host "`n✓ Setup complete! Monitor the AWS console for deployment progress." -ForegroundColor Green
} else {
    Write-Host "`n✗ Stack deployment failed!" -ForegroundColor Red
    Write-Host "Check the CloudFormation console for error details" -ForegroundColor Yellow
    exit 1
}
