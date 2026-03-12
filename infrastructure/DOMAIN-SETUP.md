# Domain Setup Guide for eshkol.ai

## Overview
This guide walks you through connecting your eshkol.ai domain to your S3-hosted website using CloudFront and Route 53.

## Prerequisites
- ✓ Route 53 hosted zone for eshkol.ai (already created)
- Domain registered (purchase through Route 53 or external registrar)
- AWS CLI configured with appropriate permissions

## Step 1: Deploy CloudFront Stack

Run the deployment script:

```powershell
cd infrastructure
.\deploy-cloudfront.ps1
```

This will create:
- ACM SSL certificate for HTTPS
- CloudFront distribution for global CDN
- Route 53 A records pointing to CloudFront
- S3 bucket policy for CloudFront access

## Step 2: Purchase Domain (if not done yet)

### Option A: Purchase through Route 53
1. Go to Route 53 console
2. Click "Registered domains" → "Register domain"
3. Search for "eshkol.ai"
4. Complete purchase (Route 53 will auto-configure nameservers)

### Option B: Use External Registrar
1. Purchase eshkol.ai from your preferred registrar
2. Get nameservers from stack output or Route 53 console
3. Update nameservers at your registrar to point to Route 53

## Step 3: Wait for Deployment

### Certificate Validation (5-30 minutes)
- ACM will automatically validate via DNS
- Check status: https://console.aws.amazon.com/acm

### CloudFront Deployment (15-20 minutes)
- Distribution deploys to edge locations globally
- Check status: https://console.aws.amazon.com/cloudfront

### DNS Propagation (up to 48 hours)
- DNS changes propagate globally
- Test with: `nslookup eshkol.ai`

## Step 4: Update GitHub Workflow

Once CloudFront is deployed, update the GitHub Actions workflow to invalidate CloudFront cache on deployments.

## Verification

Once complete, your site will be accessible at:
- https://eshkol.ai
- https://www.eshkol.ai

## Troubleshooting

### Certificate stuck in "Pending validation"
- Check that Route 53 hosted zone has the validation CNAME records
- Wait up to 30 minutes for DNS propagation

### CloudFront shows "Access Denied"
- Verify S3 bucket policy allows CloudFront OAI
- Check that files are uploaded to S3

### Domain not resolving
- Verify nameservers at registrar match Route 53 nameservers
- Wait for DNS propagation (can take up to 48 hours)

## Cost Estimate

- Route 53 Hosted Zone: $0.50/month
- Domain registration: ~$20-50/year (varies by registrar)
- CloudFront: Pay-as-you-go (free tier: 1TB data transfer/month)
- ACM Certificate: Free
