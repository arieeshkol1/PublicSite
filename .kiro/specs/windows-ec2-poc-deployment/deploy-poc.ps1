# deploy-poc.ps1
# Made4Net POC Deployment Script
# Deploys 2 Windows EC2 instances with SSM monitoring

param(
    [Parameter(Mandatory=$false)]
    [string]$Region = "us-east-1",
    
    [Parameter(Mandatory=$false)]
    [string]$StackName = "made4net-poc",
    
    [Parameter(Mandatory=$false)]
    [string]$AdminIP = "0.0.0.0/0",
    
    [Parameter(Mandatory=$false)]
    [switch]$WaitForCompletion = $true
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Made4Net POC Deployment" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check AWS CLI is installed
try {
    $awsVersion = aws --version
    Write-Host "✓ AWS CLI found: $awsVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ AWS CLI not found. Please install AWS CLI first." -ForegroundColor Red
    exit 1
}

# Check AWS credentials
try {
    $identity = aws sts get-caller-identity --output json | ConvertFrom-Json
    Write-Host "✓ AWS credentials configured" -ForegroundColor Green
    Write-Host "  Account: $($identity.Account)" -ForegroundColor Gray
    Write-Host "  User: $($identity.Arn)" -ForegroundColor Gray
} catch {
    Write-Host "✗ AWS credentials not configured. Run 'aws configure' first." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Deployment Configuration:" -ForegroundColor Yellow
Write-Host "  Region: $Region" -ForegroundColor Gray
Write-Host "  Stack Name: $StackName" -ForegroundColor Gray
Write-Host "  Admin IP: $AdminIP" -ForegroundColor Gray
Write-Host ""

# Validate CloudFormation template
Write-Host "Validating CloudFormation template..." -ForegroundColor Yellow
try {
    aws cloudformation validate-template `
        --template-body file://infrastructure.yaml `
        --region $Region | Out-Null
    Write-Host "✓ Template is valid" -ForegroundColor Green
} catch {
    Write-Host "✗ Template validation failed" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

# Check if stack already exists
Write-Host ""
Write-Host "Checking if stack already exists..." -ForegroundColor Yellow
$stackExists = $false
try {
    $existingStack = aws cloudformation describe-stacks `
        --stack-name $StackName `
        --region $Region `
        --output json 2>$null | ConvertFrom-Json
    
    if ($existingStack) {
        $stackExists = $true
        $stackStatus = $existingStack.Stacks[0].StackStatus
        Write-Host "✓ Stack exists with status: $stackStatus" -ForegroundColor Yellow
        
        if ($stackStatus -in @("CREATE_IN_PROGRESS", "UPDATE_IN_PROGRESS", "DELETE_IN_PROGRESS")) {
            Write-Host "✗ Stack is currently being modified. Please wait and try again." -ForegroundColor Red
            exit 1
        }
        
        $response = Read-Host "Stack already exists. Update it? (y/n)"
        if ($response -ne "y") {
            Write-Host "Deployment cancelled." -ForegroundColor Yellow
            exit 0
        }
    }
} catch {
    Write-Host "✓ Stack does not exist, will create new stack" -ForegroundColor Green
}

# Deploy stack
Write-Host ""
if ($stackExists) {
    Write-Host "Updating CloudFormation stack..." -ForegroundColor Yellow
    try {
        aws cloudformation update-stack `
            --stack-name $StackName `
            --template-body file://infrastructure.yaml `
            --parameters ParameterKey=AdminIP,ParameterValue=$AdminIP `
            --capabilities CAPABILITY_NAMED_IAM `
            --region $Region
        
        Write-Host "✓ Stack update initiated" -ForegroundColor Green
        $operation = "update"
    } catch {
        if ($_.Exception.Message -like "*No updates are to be performed*") {
            Write-Host "✓ No changes detected in stack" -ForegroundColor Green
            $WaitForCompletion = $false
        } else {
            Write-Host "✗ Stack update failed" -ForegroundColor Red
            Write-Host $_.Exception.Message -ForegroundColor Red
            exit 1
        }
    }
} else {
    Write-Host "Creating CloudFormation stack..." -ForegroundColor Yellow
    try {
        aws cloudformation create-stack `
            --stack-name $StackName `
            --template-body file://infrastructure.yaml `
            --parameters ParameterKey=AdminIP,ParameterValue=$AdminIP `
            --capabilities CAPABILITY_NAMED_IAM `
            --region $Region
        
        Write-Host "✓ Stack creation initiated" -ForegroundColor Green
        $operation = "create"
    } catch {
        Write-Host "✗ Stack creation failed" -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
        exit 1
    }
}

# Wait for stack completion
if ($WaitForCompletion -and $operation) {
    Write-Host ""
    Write-Host "Waiting for stack $operation to complete..." -ForegroundColor Yellow
    Write-Host "This may take 5-10 minutes..." -ForegroundColor Gray
    
    $waitCommand = if ($operation -eq "create") { "stack-create-complete" } else { "stack-update-complete" }
    
    try {
        aws cloudformation wait $waitCommand `
            --stack-name $StackName `
            --region $Region
        
        Write-Host "✓ Stack $operation completed successfully" -ForegroundColor Green
    } catch {
        Write-Host "✗ Stack $operation failed or timed out" -ForegroundColor Red
        Write-Host "Check AWS Console for details" -ForegroundColor Yellow
        exit 1
    }
}

# Get stack outputs
Write-Host ""
Write-Host "Retrieving stack outputs..." -ForegroundColor Yellow
try {
    $outputs = aws cloudformation describe-stacks `
        --stack-name $StackName `
        --region $Region `
        --query 'Stacks[0].Outputs' `
        --output json | ConvertFrom-Json
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Deployment Complete!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    foreach ($output in $outputs) {
        Write-Host "$($output.OutputKey):" -ForegroundColor Yellow
        Write-Host "  $($output.OutputValue)" -ForegroundColor White
        if ($output.Description) {
            Write-Host "  $($output.Description)" -ForegroundColor Gray
        }
        Write-Host ""
    }
    
    # Extract specific values
    $frontendIP = ($outputs | Where-Object {$_.OutputKey -eq 'FrontendPublicIP'}).OutputValue
    $frontendInstanceId = ($outputs | Where-Object {$_.OutputKey -eq 'FrontendInstanceId'}).OutputValue
    $backendInstanceId = ($outputs | Where-Object {$_.OutputKey -eq 'BackendInstanceId'}).OutputValue
    $backendPrivateIP = ($outputs | Where-Object {$_.OutputKey -eq 'BackendPrivateIP'}).OutputValue
    
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Next Steps:" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1. Wait for instances to finish initializing (5-10 minutes)" -ForegroundColor White
    Write-Host ""
    Write-Host "2. Check SSM registration:" -ForegroundColor White
    Write-Host "   aws ssm describe-instance-information --region $Region" -ForegroundColor Gray
    Write-Host ""
    Write-Host "3. Connect to frontend via Session Manager:" -ForegroundColor White
    Write-Host "   aws ssm start-session --target $frontendInstanceId --region $Region" -ForegroundColor Gray
    Write-Host ""
    Write-Host "4. Connect to backend via Session Manager:" -ForegroundColor White
    Write-Host "   aws ssm start-session --target $backendInstanceId --region $Region" -ForegroundColor Gray
    Write-Host ""
    Write-Host "5. Access frontend web server:" -ForegroundColor White
    Write-Host "   https://$frontendIP" -ForegroundColor Gray
    Write-Host ""
    Write-Host "6. Configure applications:" -ForegroundColor White
    Write-Host "   - Deploy WMS UI to frontend IIS" -ForegroundColor Gray
    Write-Host "   - Install SQL Server Express on backend" -ForegroundColor Gray
    Write-Host "   - Deploy REST API to backend" -ForegroundColor Gray
    Write-Host "   - Create InventoryDB database" -ForegroundColor Gray
    Write-Host ""
    Write-Host "7. Monitor in CloudWatch:" -ForegroundColor White
    Write-Host "   https://console.aws.amazon.com/cloudwatch/home?region=$Region" -ForegroundColor Gray
    Write-Host ""
    Write-Host "8. View instances in Systems Manager:" -ForegroundColor White
    Write-Host "   https://console.aws.amazon.com/systems-manager/fleet-manager?region=$Region" -ForegroundColor Gray
    Write-Host ""
    
} catch {
    Write-Host "✗ Failed to retrieve stack outputs" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Deployment script completed successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
