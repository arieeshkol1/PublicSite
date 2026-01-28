# JP2 Resource Cleanup Script
# Run this script after authenticating to AWS account 991105135552

Write-Host "Starting JP2 Resource Cleanup..." -ForegroundColor Green
Write-Host ""

# Verify we're in the correct account
$accountId = (aws sts get-caller-identity --query Account --output text)
Write-Host "Current AWS Account: $accountId"

if ($accountId -ne "991105135552") {
    Write-Host "ERROR: You must be authenticated to account 991105135552" -ForegroundColor Red
    Write-Host "Please switch to the correct AWS account and run this script again." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "=== Deleting API Gateways ===" -ForegroundColor Cyan

# Delete API Gateway: d41omevnl
Write-Host "Deleting API Gateway: d41omevnl"
aws apigatewayv2 delete-api --api-id d41omevnl --region us-east-1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Deleted API Gateway d41omevnl" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to delete API Gateway d41omevnl" -ForegroundColor Red
}

# Delete API Gateway: qmiu91xhgk
Write-Host "Deleting API Gateway: qmiu91xhgk"
aws apigatewayv2 delete-api --api-id qmiu91xhgk --region us-east-1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Deleted API Gateway qmiu91xhgk" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to delete API Gateway qmiu91xhgk" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Checking for S3 Buckets ===" -ForegroundColor Cyan

# List and delete JP2 S3 buckets
$buckets = aws s3api list-buckets --query "Buckets[?contains(Name, 'jp2')].Name" --output text --region us-east-1

if ($buckets) {
    foreach ($bucket in $buckets -split '\s+') {
        if ($bucket) {
            Write-Host "Found bucket: $bucket"
            Write-Host "Emptying bucket: $bucket"
            aws s3 rm s3://$bucket --recursive --region us-east-1
            Write-Host "Deleting bucket: $bucket"
            aws s3api delete-bucket --bucket $bucket --region us-east-1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✓ Deleted bucket $bucket" -ForegroundColor Green
            } else {
                Write-Host "✗ Failed to delete bucket $bucket" -ForegroundColor Red
            }
        }
    }
} else {
    Write-Host "No JP2 S3 buckets found" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Checking for Lambda Functions ===" -ForegroundColor Cyan

# List and delete Lambda functions with jp2 in name
$functions = aws lambda list-functions --query "Functions[?contains(FunctionName, 'jp2') || contains(FunctionName, 'JP2') || contains(FunctionName, 'Serverless')].FunctionName" --output text --region us-east-1

if ($functions) {
    foreach ($function in $functions -split '\s+') {
        if ($function) {
            Write-Host "Deleting Lambda function: $function"
            aws lambda delete-function --function-name $function --region us-east-1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✓ Deleted function $function" -ForegroundColor Green
            } else {
                Write-Host "✗ Failed to delete function $function" -ForegroundColor Red
            }
        }
    }
} else {
    Write-Host "No JP2 Lambda functions found" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Checking for ECS Clusters ===" -ForegroundColor Cyan

# List and delete ECS clusters
$clusters = aws ecs list-clusters --query "clusterArns[?contains(@, 'jp2') || contains(@, 'JP2') || contains(@, 'Serverless')]" --output text --region us-east-1

if ($clusters) {
    foreach ($cluster in $clusters -split '\s+') {
        if ($cluster) {
            $clusterName = $cluster.Split('/')[-1]
            Write-Host "Deleting ECS cluster: $clusterName"
            
            # First, stop all tasks
            $tasks = aws ecs list-tasks --cluster $clusterName --query "taskArns" --output text --region us-east-1
            if ($tasks) {
                foreach ($task in $tasks -split '\s+') {
                    if ($task) {
                        aws ecs stop-task --cluster $clusterName --task $task --region us-east-1
                    }
                }
            }
            
            # Delete services
            $services = aws ecs list-services --cluster $clusterName --query "serviceArns" --output text --region us-east-1
            if ($services) {
                foreach ($service in $services -split '\s+') {
                    if ($service) {
                        $serviceName = $service.Split('/')[-1]
                        aws ecs update-service --cluster $clusterName --service $serviceName --desired-count 0 --region us-east-1
                        aws ecs delete-service --cluster $clusterName --service $serviceName --force --region us-east-1
                    }
                }
            }
            
            # Delete cluster
            aws ecs delete-cluster --cluster $clusterName --region us-east-1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✓ Deleted cluster $clusterName" -ForegroundColor Green
            } else {
                Write-Host "✗ Failed to delete cluster $clusterName" -ForegroundColor Red
            }
        }
    }
} else {
    Write-Host "No JP2 ECS clusters found" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Checking for Step Functions ===" -ForegroundColor Cyan

# List and delete Step Functions
$stateMachines = aws stepfunctions list-state-machines --query "stateMachines[?contains(name, 'jp2') || contains(name, 'JP2') || contains(name, 'Serverless')].stateMachineArn" --output text --region us-east-1

if ($stateMachines) {
    foreach ($sm in $stateMachines -split '\s+') {
        if ($sm) {
            Write-Host "Deleting Step Function: $sm"
            aws stepfunctions delete-state-machine --state-machine-arn $sm --region us-east-1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✓ Deleted Step Function $sm" -ForegroundColor Green
            } else {
                Write-Host "✗ Failed to delete Step Function $sm" -ForegroundColor Red
            }
        }
    }
} else {
    Write-Host "No JP2 Step Functions found" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Checking for CloudFormation Stacks ===" -ForegroundColor Cyan

# List and delete CloudFormation stacks
$stacks = aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --query "StackSummaries[?contains(StackName, 'jp2') || contains(StackName, 'JP2') || contains(StackName, 'Serverless')].StackName" --output text --region us-east-1

if ($stacks) {
    foreach ($stack in $stacks -split '\s+') {
        if ($stack) {
            Write-Host "Deleting CloudFormation stack: $stack"
            aws cloudformation delete-stack --stack-name $stack --region us-east-1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✓ Initiated deletion of stack $stack" -ForegroundColor Green
                Write-Host "  (Stack deletion may take a few minutes)" -ForegroundColor Yellow
            } else {
                Write-Host "✗ Failed to delete stack $stack" -ForegroundColor Red
            }
        }
    }
} else {
    Write-Host "No JP2 CloudFormation stacks found" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Cleanup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Note: CloudFormation stack deletions may take several minutes to complete." -ForegroundColor Yellow
Write-Host "You can monitor progress in the AWS CloudFormation console." -ForegroundColor Yellow
