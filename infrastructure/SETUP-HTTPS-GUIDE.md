# Setup HTTPS with CloudFront - Step by Step Guide

## What This Will Do

The GitHub Actions workflow will automatically:
1. ✓ Request SSL certificate from AWS Certificate Manager (ACM)
2. ✓ Create DNS validation record in Route 53
3. ✓ Wait for certificate validation (5-30 minutes)
4. ✓ Create CloudFront distribution
5. ✓ Configure HTTPS redirect (HTTP → HTTPS)
6. ✓ Update Route 53 to point to CloudFront
7. ✓ Wait for CloudFront deployment (10-20 minutes)

**Total time: 15-50 minutes (fully automated)**

## How to Run

### Step 1: Push Changes to GitHub
```powershell
git add -A
git commit -m "Add CloudFront HTTPS setup workflow"
git push
```

### Step 2: Run the Workflow

1. Go to your GitHub repository: https://github.com/arieeshkol1/PublicSite
2. Click "Actions" tab
3. Click "Setup CloudFront with HTTPS" workflow
4. Click "Run workflow" button
5. Type `setup` in the confirmation field
6. Click "Run workflow"

### Step 3: Monitor Progress

The workflow will show progress for each step:
- Requesting SSL certificate
- Creating DNS validation record
- Waiting for certificate validation (this takes the longest)
- Creating CloudFront distribution
- Updating Route 53
- Waiting for CloudFront deployment

You can watch the logs in real-time.

### Step 4: Test Your HTTPS Website

After the workflow completes (15-50 minutes), test:

```powershell
# Test HTTPS
curl -I https://www.eshkolai.com

# Test HTTP redirect
curl -I http://www.eshkolai.com
```

Both should work, and HTTP should redirect to HTTPS!

## What Changes

### Before (Current)
- URL: http://www.eshkolai.com
- Protocol: HTTP only
- Route 53 → S3 website endpoint

### After (With CloudFront)
- URL: https://www.eshkolai.com (HTTP redirects to HTTPS)
- Protocol: HTTPS with free SSL certificate
- Route 53 → CloudFront → S3 website endpoint

## Costs

### SSL Certificate
- **FREE** (AWS Certificate Manager)

### CloudFront
- First 12 months: **FREE** (within free tier)
- After free tier: ~$0.21/month for small traffic
- See HTTPS-OPTIONS-AND-COSTS.md for details

## Automatic Cache Invalidation

The deployment workflow has been updated to automatically invalidate CloudFront cache when you deploy new files. This means:
- Push changes to GitHub
- GitHub Actions deploys to S3
- GitHub Actions invalidates CloudFront cache
- Changes appear immediately on your website

## Troubleshooting

### Certificate Validation Takes Too Long
- Certificate validation can take 5-30 minutes
- The workflow waits up to 30 minutes
- If it times out, the certificate will continue validating in the background
- Check ACM console and re-run the workflow later

### CloudFront Distribution Already Exists
- The workflow checks for existing distributions
- If found, it will update the existing one
- No duplicate distributions will be created

### DNS Not Resolving
- DNS propagation can take a few minutes
- Clear your DNS cache: `ipconfig /flushdns`
- Test with: `nslookup www.eshkolai.com 8.8.8.8`

### HTTPS Not Working
- Wait 10-20 minutes for CloudFront deployment
- Check CloudFront distribution status in AWS console
- Verify certificate is issued in ACM console

## Manual Verification

### Check Certificate Status
```powershell
aws acm list-certificates --region us-east-1
```

### Check CloudFront Distribution
```powershell
aws cloudfront list-distributions --query "DistributionList.Items[?Aliases.Items[0]=='www.eshkolai.com']"
```

### Check Route 53 Records
```powershell
aws route53 list-resource-record-sets --hosted-zone-id Z07144662HMOSSEBOKGII
```

## After Setup

Once HTTPS is working:
1. Update any hardcoded HTTP links to HTTPS
2. Test all pages work with HTTPS
3. Consider setting up HSTS headers (optional)
4. Your website will automatically redirect HTTP to HTTPS

## Rollback (If Needed)

If something goes wrong, you can rollback:

1. Delete CloudFront distribution (AWS Console)
2. Delete SSL certificate (AWS Console)
3. Update Route 53 CNAME to point back to S3:
   ```powershell
   # Point back to S3
   aws route53 change-resource-record-sets --hosted-zone-id Z07144662HMOSSEBOKGII --change-batch '{
     "Changes": [{
       "Action": "UPSERT",
       "ResourceRecordSet": {
         "Name": "www.eshkolai.com",
         "Type": "CNAME",
         "TTL": 300,
         "ResourceRecords": [{"Value": "www.eshkolai.com.s3-website-us-east-1.amazonaws.com"}]
       }
     }]
   }'
   ```

## Summary

This is a fully automated setup that will:
- Add HTTPS to your website
- Cost less than $1/month
- Take 15-50 minutes to complete
- Require no manual intervention

Just run the workflow and wait for it to complete!
