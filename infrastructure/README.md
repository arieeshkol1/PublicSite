# AWS Bill Analyzer - Infrastructure Setup

This directory contains the infrastructure setup for the AWS Bill Analyzer feature.

## Prerequisites

- AWS CLI configured with credentials for account 991105135552
- PowerShell (for Windows) or Bash (for Linux/Mac)
- Permissions to create CloudFormation stacks, S3 buckets, and IAM roles

## What Gets Created

### S3 Bucket
- **Name**: `aws-bill-analyzer-storage-991105135552`
- **Region**: us-east-1
- **Encryption**: AES256 (server-side)
- **Lifecycle Policy**: Deletes objects in `bills/` prefix after 24 hours
- **Public Access**: Blocked (all public access disabled)

### IAM Roles

#### Upload Handler Role
- **Name**: `aws-bill-analyzer-upload-role`
- **Permissions**:
  - S3 PutObject on `bills/*` prefix
  - S3 PutObjectTagging on `bills/*` prefix
  - CloudWatch Logs (basic execution role)

#### Question Processor Role
- **Name**: `aws-bill-analyzer-question-role`
- **Permissions**:
  - S3 GetObject on `bills/*` prefix
  - Bedrock InvokeModel for `amazon.nova-lite-v1:0`
  - CloudWatch Logs (basic execution role)

## Deployment Instructions

### Option 1: Using PowerShell (Windows)

```powershell
cd infrastructure
./deploy-infrastructure.ps1
```

### Option 2: Using AWS CLI Directly

```bash
aws cloudformation deploy \
    --template-file infrastructure/cloudformation-infrastructure.yaml \
    --stack-name aws-bill-analyzer-infrastructure \
    --region us-east-1 \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides AWSAccountId=991105135552
```

## Verification

After deployment, verify the resources:

### 1. Check S3 Bucket
```bash
aws s3 ls | grep aws-bill-analyzer-storage
```

### 2. Check IAM Roles
```bash
aws iam get-role --role-name aws-bill-analyzer-upload-role
aws iam get-role --role-name aws-bill-analyzer-question-role
```

### 3. Check Bedrock Model Access
```bash
aws bedrock list-foundation-models \
    --region us-east-1 \
    --query 'modelSummaries[?contains(modelId, `nova-lite`)]'
```

## Bedrock Model Access

If you don't have access to the Amazon Bedrock Nova Lite model:

1. Go to AWS Console → Amazon Bedrock
2. Navigate to "Model access" in the left sidebar
3. Click "Manage model access"
4. Find "Nova Lite" and enable access
5. Wait for access to be granted (usually instant)

## Cleanup

To delete all infrastructure resources:

```bash
# Delete the CloudFormation stack
aws cloudformation delete-stack \
    --stack-name aws-bill-analyzer-infrastructure \
    --region us-east-1

# Wait for deletion to complete
aws cloudformation wait stack-delete-complete \
    --stack-name aws-bill-analyzer-infrastructure \
    --region us-east-1
```

**Note**: The S3 bucket must be empty before the stack can be deleted. If you have uploaded bills, delete them first:

```bash
aws s3 rm s3://aws-bill-analyzer-storage-991105135552/bills/ --recursive
```

## Troubleshooting

### Issue: Stack creation fails with "Bucket already exists"
**Solution**: The bucket name must be globally unique. If someone else has used this name, modify the `AWSAccountId` parameter or change the bucket naming pattern in the template.

### Issue: IAM role creation fails
**Solution**: Ensure you have `iam:CreateRole` and `iam:PutRolePolicy` permissions.

### Issue: Bedrock model not available
**Solution**: Amazon Bedrock may not be available in all regions. Ensure you're using us-east-1 and have requested model access.

## Next Steps

After successful infrastructure deployment:
1. Proceed to Task 2: Implement Upload Handler Lambda function
2. The Lambda functions will reference these IAM roles
3. The S3 bucket will be used for bill storage
