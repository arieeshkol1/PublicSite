# Deploy AWS Bill Analyzer Infrastructure
# This script deploys the CloudFormation stack for S3 bucket and IAM roles

$StackName = "aws-bill-analyzer-infrastructure"
$TemplateFile = "infrastructure/cloudformation-infrastructure.yaml"
$Region = "us-east-1"

Write-Host "Deploying AWS Bill Analyzer Infrastructure..." -ForegroundColor Green
Write-Host "Stack Name: $StackName" -ForegroundColor Cyan
Write-Host "Region: $Region" -ForegroundColor Cyan
Write-Host ""

# Deploy CloudFormation stack
aws cloudformation deploy `
    --template-file $TemplateFile `
    --stack-name $StackName `
    --region $Region `
    --capabilities CAPABILITY_NAMED_IAM `
    --parameter-overrides AWSAccountId=991105135552

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Infrastructure deployment successful!" -ForegroundColor Green
    Write-Host ""
    
    # Get stack outputs
    Write-Host "Stack Outputs:" -ForegroundColor Yellow
    aws cloudformation describe-stacks `
        --stack-name $StackName `
        --region $Region `
        --query 'Stacks[0].Outputs' `
        --output table
    
    Write-Host ""
    Write-Host "Verifying Bedrock model access..." -ForegroundColor Yellow
    
    # Check Bedrock model access
    aws bedrock list-foundation-models `
        --region $Region `
        --by-provider anthropic `
        --query 'modelSummaries[?contains(modelId, `nova-lite`)].{ModelId:modelId, ModelName:modelName}' `
        --output table
    
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Verify the S3 bucket was created: aws-bill-analyzer-storage-991105135552"
    Write-Host "2. Verify IAM roles were created: aws-bill-analyzer-upload-role, aws-bill-analyzer-question-role"
    Write-Host "3. Ensure Bedrock model access is enabled for amazon.nova-lite-v1:0"
    Write-Host "4. Proceed to Task 2: Implement Upload Handler Lambda function"
} else {
    Write-Host ""
    Write-Host "Infrastructure deployment failed!" -ForegroundColor Red
    Write-Host "Please check the error messages above and try again."
    exit 1
}
