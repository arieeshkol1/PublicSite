# Deploy Domain Setup Stack
# This script deploys the Route 53, CloudFront, and ACM certificate for eshkol.ai

$StackName = "eshkol-ai-domain-stack"
$TemplateFile = "domain-setup.yaml"
$Region = "us-east-1"

Write-Host "Deploying domain setup stack..." -ForegroundColor Cyan

# Deploy the CloudFormation stack
aws cloudformation deploy `
    --template-file $TemplateFile `
    --stack-name $StackName `
    --region $Region `
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
    
    Write-Host "`n=== IMPORTANT: Next Steps ===" -ForegroundColor Yellow
    Write-Host "`n1. DOMAIN REGISTRATION:" -ForegroundColor White
    Write-Host "   - Purchase eshkol.ai domain through Route 53 or your preferred registrar"
    Write-Host "   - If using external registrar, update nameservers to:"
    
    $nameServers = ($outputs | Where-Object { $_.OutputKey -eq "HostedZoneNameServers" }).OutputValue
    Write-Host "   $nameServers" -ForegroundColor Cyan
    
    Write-Host "`n2. CERTIFICATE VALIDATION:" -ForegroundColor White
    Write-Host "   - The ACM certificate will auto-validate via DNS (may take 5-30 minutes)"
    Write-Host "   - Check status in ACM console: https://console.aws.amazon.com/acm"
    
    Write-Host "`n3. CLOUDFRONT DEPLOYMENT:" -ForegroundColor White
    $cfDomain = ($outputs | Where-Object { $_.OutputKey -eq "CloudFrontDomainName" }).OutputValue
    Write-Host "   - CloudFront is deploying (takes 15-20 minutes)"
    Write-Host "   - Temporary URL: https://$cfDomain"
    
    Write-Host "`n4. FINAL WEBSITE URL:" -ForegroundColor White
    Write-Host "   - https://eshkol.ai (once DNS propagates)"
    Write-Host "   - https://www.eshkol.ai"
    
    Write-Host "`n=== Stack Outputs ===" -ForegroundColor Cyan
    $outputs | ForEach-Object {
        Write-Host "$($_.OutputKey): $($_.OutputValue)" -ForegroundColor White
    }
} else {
    Write-Host "`n✗ Stack deployment failed!" -ForegroundColor Red
    exit 1
}
