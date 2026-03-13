# Deploy Contact Form Infrastructure
# This script deploys the contact form backend using AWS CLI

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Deploying Contact Form Infrastructure" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Parameters
$RecipientEmail = "ariel.eshkol@gmail.com"
$SenderEmail = "ariel.eshkol@gmail.com"
$StackName = "contact-form-stack"
$Region = "us-east-1"

Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Recipient Email: $RecipientEmail"
Write-Host "  Sender Email: $SenderEmail"
Write-Host "  Stack Name: $StackName"
Write-Host "  Region: $Region"
Write-Host ""

# Deploy CloudFormation stack
Write-Host "Deploying CloudFormation stack..." -ForegroundColor Yellow
aws cloudformation deploy `
    --template-file infrastructure/contact-form-stack.yaml `
    --stack-name $StackName `
    --parameter-overrides `
        RecipientEmail=$RecipientEmail `
        SenderEmail=$SenderEmail `
        DomainName=www.eshkolai.com `
    --capabilities CAPABILITY_NAMED_IAM `
    --region $Region

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: CloudFormation deployment failed!" -ForegroundColor Red
    Write-Host "This might be due to insufficient permissions." -ForegroundColor Red
    Write-Host "Please run the GitHub Actions workflow instead." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Stack deployed successfully!" -ForegroundColor Green
Write-Host ""

# Get API endpoint
Write-Host "Retrieving API endpoint..." -ForegroundColor Yellow
$ApiEndpoint = aws cloudformation describe-stacks `
    --stack-name $StackName `
    --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' `
    --output text `
    --region $Region

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "API Endpoint:" -ForegroundColor Green
Write-Host $ApiEndpoint -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Verify email addresses in SES
Write-Host "Verifying email addresses in SES..." -ForegroundColor Yellow
aws ses verify-email-identity --email-address $SenderEmail --region $Region 2>$null
aws ses verify-email-identity --email-address $RecipientEmail --region $Region 2>$null

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "NEXT STEPS:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Check your email inbox ($RecipientEmail)" -ForegroundColor Yellow
Write-Host "   for verification emails from AWS SES"
Write-Host "   Click the verification links in the emails"
Write-Host ""
Write-Host "2. Update script.js with the API endpoint:" -ForegroundColor Yellow
Write-Host "   Replace 'YOUR_API_GATEWAY_ENDPOINT_HERE' with:"
Write-Host "   $ApiEndpoint" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. Run these commands:" -ForegroundColor Yellow
Write-Host "   git add script.js"
Write-Host "   git commit -m 'Add contact form API endpoint'"
Write-Host "   git push origin main"
Write-Host ""
Write-Host "4. The contact form will be live after deployment!" -ForegroundColor Green
Write-Host ""

# Save API endpoint to file
$ApiEndpoint | Out-File -FilePath "api-endpoint.txt" -Encoding UTF8
Write-Host "API endpoint saved to api-endpoint.txt" -ForegroundColor Green
Write-Host ""
