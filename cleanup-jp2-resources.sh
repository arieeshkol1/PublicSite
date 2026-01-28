#!/bin/bash

# JP2 Resource Cleanup Script
# Run this script after authenticating to AWS account 991105135552

echo -e "\033[0;32mStarting JP2 Resource Cleanup...\033[0m"
echo ""

# Verify we're in the correct account
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Current AWS Account: $ACCOUNT_ID"

if [ "$ACCOUNT_ID" != "991105135552" ]; then
    echo -e "\033[0;31mERROR: You must be authenticated to account 991105135552\033[0m"
    echo -e "\033[0;33mPlease switch to the correct AWS account and run this script again.\033[0m"
    exit 1
fi

echo ""
echo -e "\033[0;36m=== Deleting API Gateways ===\033[0m"

# Delete API Gateway: d41omevnl
echo "Deleting API Gateway: d41omevnl"
if aws apigatewayv2 delete-api --api-id d41omevnl --region us-east-1 2>/dev/null; then
    echo -e "\033[0;32m✓ Deleted API Gateway d41omevnl\033[0m"
else
    echo -e "\033[0;31m✗ Failed to delete API Gateway d41omevnl (may not exist)\033[0m"
fi

# Delete API Gateway: qmiu91xhgk
echo "Deleting API Gateway: qmiu91xhgk"
if aws apigatewayv2 delete-api --api-id qmiu91xhgk --region us-east-1 2>/dev/null; then
    echo -e "\033[0;32m✓ Deleted API Gateway qmiu91xhgk\033[0m"
else
    echo -e "\033[0;31m✗ Failed to delete API Gateway qmiu91xhgk (may not exist)\033[0m"
fi

echo ""
echo -e "\033[0;36m=== Checking for S3 Buckets ===\033[0m"

# List and delete JP2 S3 buckets
BUCKETS=$(aws s3api list-buckets --query "Buckets[?contains(Name, 'jp2')].Name" --output text --region us-east-1 2>/dev/null)

if [ -n "$BUCKETS" ]; then
    for bucket in $BUCKETS; do
        echo "Found bucket: $bucket"
        echo "Emptying bucket: $bucket"
        aws s3 rm s3://$bucket --recursive --region us-east-1 2>/dev/null
        echo "Deleting bucket: $bucket"
        if aws s3api delete-bucket --bucket $bucket --region us-east-1 2>/dev/null; then
            echo -e "\033[0;32m✓ Deleted bucket $bucket\033[0m"
        else
            echo -e "\033[0;31m✗ Failed to delete bucket $bucket\033[0m"
        fi
    done
else
    echo -e "\033[0;33mNo JP2 S3 buckets found\033[0m"
fi

echo ""
echo -e "\033[0;36m=== Checking for Lambda Functions ===\033[0m"

# List and delete Lambda functions with jp2 in name
FUNCTIONS=$(aws lambda list-functions --query "Functions[?contains(FunctionName, 'jp2') || contains(FunctionName, 'JP2') || contains(FunctionName, 'Serverless')].FunctionName" --output text --region us-east-1 2>/dev/null)

if [ -n "$FUNCTIONS" ]; then
    for function in $FUNCTIONS; do
        echo "Deleting Lambda function: $function"
        if aws lambda delete-function --function-name $function --region us-east-1 2>/dev/null; then
            echo -e "\033[0;32m✓ Deleted function $function\033[0m"
        else
            echo -e "\033[0;31m✗ Failed to delete function $function\033[0m"
        fi
    done
else
    echo -e "\033[0;33mNo JP2 Lambda functions found\033[0m"
fi

echo ""
echo -e "\033[0;36m=== Checking for ECS Clusters ===\033[0m"

# List and delete ECS clusters
CLUSTERS=$(aws ecs list-clusters --query "clusterArns[?contains(@, 'jp2') || contains(@, 'JP2') || contains(@, 'Serverless')]" --output text --region us-east-1 2>/dev/null)

if [ -n "$CLUSTERS" ]; then
    for cluster in $CLUSTERS; do
        CLUSTER_NAME=$(basename $cluster)
        echo "Deleting ECS cluster: $CLUSTER_NAME"
        
        # First, stop all tasks
        TASKS=$(aws ecs list-tasks --cluster $CLUSTER_NAME --query "taskArns" --output text --region us-east-1 2>/dev/null)
        if [ -n "$TASKS" ]; then
            for task in $TASKS; do
                aws ecs stop-task --cluster $CLUSTER_NAME --task $task --region us-east-1 2>/dev/null
            done
        fi
        
        # Delete services
        SERVICES=$(aws ecs list-services --cluster $CLUSTER_NAME --query "serviceArns" --output text --region us-east-1 2>/dev/null)
        if [ -n "$SERVICES" ]; then
            for service in $SERVICES; do
                SERVICE_NAME=$(basename $service)
                aws ecs update-service --cluster $CLUSTER_NAME --service $SERVICE_NAME --desired-count 0 --region us-east-1 2>/dev/null
                aws ecs delete-service --cluster $CLUSTER_NAME --service $SERVICE_NAME --force --region us-east-1 2>/dev/null
            done
        fi
        
        # Delete cluster
        if aws ecs delete-cluster --cluster $CLUSTER_NAME --region us-east-1 2>/dev/null; then
            echo -e "\033[0;32m✓ Deleted cluster $CLUSTER_NAME\033[0m"
        else
            echo -e "\033[0;31m✗ Failed to delete cluster $CLUSTER_NAME\033[0m"
        fi
    done
else
    echo -e "\033[0;33mNo JP2 ECS clusters found\033[0m"
fi

echo ""
echo -e "\033[0;36m=== Checking for Step Functions ===\033[0m"

# List and delete Step Functions
STATE_MACHINES=$(aws stepfunctions list-state-machines --query "stateMachines[?contains(name, 'jp2') || contains(name, 'JP2') || contains(name, 'Serverless')].stateMachineArn" --output text --region us-east-1 2>/dev/null)

if [ -n "$STATE_MACHINES" ]; then
    for sm in $STATE_MACHINES; do
        echo "Deleting Step Function: $sm"
        if aws stepfunctions delete-state-machine --state-machine-arn $sm --region us-east-1 2>/dev/null; then
            echo -e "\033[0;32m✓ Deleted Step Function $sm\033[0m"
        else
            echo -e "\033[0;31m✗ Failed to delete Step Function $sm\033[0m"
        fi
    done
else
    echo -e "\033[0;33mNo JP2 Step Functions found\033[0m"
fi

echo ""
echo -e "\033[0;36m=== Checking for CloudFormation Stacks ===\033[0m"

# List and delete CloudFormation stacks
STACKS=$(aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --query "StackSummaries[?contains(StackName, 'jp2') || contains(StackName, 'JP2') || contains(StackName, 'Serverless')].StackName" --output text --region us-east-1 2>/dev/null)

if [ -n "$STACKS" ]; then
    for stack in $STACKS; do
        echo "Deleting CloudFormation stack: $stack"
        if aws cloudformation delete-stack --stack-name $stack --region us-east-1 2>/dev/null; then
            echo -e "\033[0;32m✓ Initiated deletion of stack $stack\033[0m"
            echo -e "\033[0;33m  (Stack deletion may take a few minutes)\033[0m"
        else
            echo -e "\033[0;31m✗ Failed to delete stack $stack\033[0m"
        fi
    done
else
    echo -e "\033[0;33mNo JP2 CloudFormation stacks found\033[0m"
fi

echo ""
echo -e "\033[0;32m=== Cleanup Complete ===\033[0m"
echo ""
echo -e "\033[0;33mNote: CloudFormation stack deletions may take several minutes to complete.\033[0m"
echo -e "\033[0;33mYou can monitor progress in the AWS CloudFormation console.\033[0m"
