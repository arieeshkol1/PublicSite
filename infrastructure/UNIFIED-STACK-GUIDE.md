# Unified Infrastructure Stack Guide

## Overview

The unified stack manages all infrastructure as a single CloudFormation stack:
- ✓ S3 bucket for website content
- ✓ S3 bucket policy for public access
- ✓ ACM SSL certificate (auto-validated via DNS)
- ✓ CloudFront distribution with HTTPS
- ✓ Route 53 DNS record (A record alias to CloudFront)

**Benefits:**
- Single source of truth for all infrastructure
- Automatic dependency management
- Only updates what changed
- Easy rollback if needed
- Infrastructure as code

## Stack Name
`eshkolai-com-website-stack`

## How to Use

### Initial Setup (First Time)

1. Go to GitHub Actions: https://github.com/arieeshkol1/PublicSite/actions
2. Click "Deploy Infrastructure Stack"
3. Click "Run workflow"
4. Select action: `create`
5. Click "Run workflow"

This will take 20-40 minutes (certificate validation + CloudFront deployment).

### Update Stack (After Changes)

1. Modify `infrastructure/unified-stack.yaml` if needed
2. Commit and push changes
3. Go to GitHub Actions
4. Click "Deploy Infrastructure Stack"
5. Click "Run workflow"
6. Select action: `update`
7. Click "Run workflow"

CloudFormation will automatically:
- Detect what changed
- Only update changed resources
- Skip if no updates needed
- Show "No updates are to be performed" if stack is up to date

### Delete Stack (Remove Everything)

1. Go to GitHub Actions
2. Click "Deploy Infrastructure Stack"
3. Click "Run workflow"
4. Select action: `delete`
5. Click "Run workflow"

This will delete ALL resources (S3, CloudFront, Certificate, DNS).

## What Gets Updated Automatically

CloudFormation tracks all resources and only updates what changed:

### S3 Bucket
- Updates: Bucket policy, website configuration
- No update: If nothing changed
- Note: Bucket name cannot be changed (requires recreation)

### SSL Certificate
- Updates: If domain validation options change
- No update: Certificate is already issued
- Note: Certificate recreation triggers CloudFront update

### CloudFront Distribution
- Updates: Cache behaviors, origins, SSL certificate
- No update: If configuration unchanged
- Note: Updates take 10-20 minutes to deploy

### Route 53 Record
- Updates: If CloudFront domain changes
- No update: If pointing to same CloudFront distribution

## Current vs New Setup

### Current Setup (Manual)
- S3 bucket: Created manually
- Certificate: Created via GitHub Actions workflow
- CloudFront: Created via GitHub Actions workflow
- Route 53: Updated via GitHub Actions workflow
- Management: Multiple workflows, manual coordination

### New Setup (Unified Stack)
- Everything: Managed by single CloudFormation stack
- Updates: Automatic dependency resolution
- Rollback: Single command to rollback all changes
- Management: Infrastructure as code

## Migration Path

### Option 1: Keep Current Setup
- Continue using existing resources
- Use unified stack for future projects
- No migration needed

### Option 2: Migrate to Unified Stack
1. Export current CloudFront distribution ID
2. Import existing resources into CloudFormation
3. Or: Delete current resources and recreate with stack

**Recommendation:** Keep current setup since it's working. Use unified stack for future projects or major updates.

## Stack Outputs

After deployment, the stack provides:

```yaml
WebsiteURL: https://www.eshkolai.com
S3BucketName: www.eshkolai.com
CloudFrontDistributionId: E1234567890ABC
CloudFrontDomainName: d1234567890abc.cloudfront.net
CertificateArn: arn:aws:acm:us-east-1:991105135552:certificate/...
```

These outputs can be used by other stacks or scripts.

## Deployment Workflow Integration

The `deploy-to-s3.yml` workflow has been updated to:
1. Get CloudFront distribution ID from CloudFormation stack (if exists)
2. Fall back to searching by alias (for current setup)
3. Invalidate CloudFront cache after deployment

This works with both current setup and unified stack!

## Cost

Same as before:
- S3: ~$0.001/month
- Route 53: ~$0.50/month
- CloudFront: ~$0.21/month (after free tier)
- **Total: ~$0.71/month**

CloudFormation itself is FREE!

## Troubleshooting

### Stack Creation Failed
- Check CloudFormation console for error details
- Common issues:
  - Certificate validation timeout (wait and retry)
  - Resource already exists (delete manually first)
  - Insufficient permissions (check IAM role)

### Stack Update Shows "No Updates"
- This is normal if nothing changed
- CloudFormation detected no differences
- No action needed

### Stack Stuck in UPDATE_IN_PROGRESS
- CloudFront updates take 10-20 minutes
- Certificate validation takes 5-30 minutes
- Wait for completion or check AWS console

### Rollback Failed
- Check CloudFormation events for details
- May need to manually fix resources
- Contact AWS support if stuck

## Best Practices

### 1. Always Use Version Control
- Commit `unified-stack.yaml` changes
- Review changes before deploying
- Use pull requests for infrastructure changes

### 2. Test in Staging First
- Create a separate stack for testing
- Use different domain name
- Validate changes before production

### 3. Monitor Stack Events
- Watch CloudFormation events during deployment
- Check for warnings or errors
- Review rollback reasons if update fails

### 4. Document Changes
- Add comments to stack template
- Update this guide when making changes
- Keep changelog of infrastructure updates

## Advanced: Stack Parameters

You can customize the stack by modifying parameters:

```yaml
Parameters:
  DomainName:
    Default: www.eshkolai.com
  RootDomainName:
    Default: eshkolai.com
  HostedZoneId:
    Default: Z07144662HMOSSEBOKGII
```

To use different values, update the workflow to pass parameters:

```bash
aws cloudformation create-stack \
  --parameters \
    ParameterKey=DomainName,ParameterValue=www.example.com \
    ParameterKey=RootDomainName,ParameterValue=example.com
```

## Summary

The unified stack provides:
- ✓ Single source of truth
- ✓ Automatic updates (only what changed)
- ✓ Easy rollback
- ✓ Infrastructure as code
- ✓ No additional cost

Your current setup is working great! The unified stack is available when you need it for:
- Major infrastructure changes
- New projects
- Better infrastructure management
