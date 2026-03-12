# Option 1: Use www.eshkol.ai as Primary Domain

This guide sets up www.eshkol.ai as your primary domain with a redirect from the root domain (eshkol.ai) once the bucket name becomes available.

## Current Status
- ✓ S3 bucket `www.eshkol.ai` exists and is configured
- ✓ Static website hosting enabled
- ✓ Files deployed successfully
- ✓ GitHub workflow configured to deploy to www.eshkol.ai
- ✓ S3 website endpoint: http://www.eshkol.ai.s3-website-us-east-1.amazonaws.com
- ⏳ Bucket name `eshkol.ai` not yet available (can take up to 24 hours after deletion)

## Step 1: Verify Current CNAME Record (Already Done)

Your Route 53 should already have this record:
- **Record name**: www.eshkol.ai
- **Type**: CNAME
- **Value**: www.eshkol.ai.s3-website-us-east-1.amazonaws.com
- **TTL**: 300 seconds

This makes www.eshkol.ai work correctly.

## Step 2: Test www.eshkol.ai

Open your browser and go to: http://www.eshkol.ai

This should work now! If not, wait a few minutes for DNS propagation.

## Step 3: Create Root Domain Redirect (When eshkol.ai bucket becomes available)

Once the bucket name `eshkol.ai` is released (check by running the script below), follow these steps:

### 3a. Create the eshkol.ai bucket with redirect

Run this PowerShell script:

```powershell
cd infrastructure
./create-redirect-bucket.ps1
```

This will:
1. Create the `eshkol.ai` bucket
2. Configure it to redirect all requests to www.eshkol.ai
3. Set up the necessary permissions

### 3b. Create A Record Alias in Route 53

1. Go to Route 53 console: https://console.aws.amazon.com/route53/
2. Click "Hosted zones"
3. Click "eshkol.ai"
4. Click "Create record"
5. Configure:
   - **Record name**: Leave blank (root domain)
   - **Record type**: A - Routes traffic to an IPv4 address and some AWS resources
   - **Toggle on**: "Alias"
   - **Route traffic to**: 
     - Select "Alias to S3 website endpoint"
     - Select region: "US East (N. Virginia) [us-east-1]"
     - The dropdown should show: `s3-website-us-east-1.amazonaws.com` or `eshkol.ai.s3-website-us-east-1.amazonaws.com`
   - **Evaluate target health**: No
6. Click "Create records"

### 3c. Test the redirect

After DNS propagates (a few minutes):
- http://eshkol.ai → should redirect to → http://www.eshkol.ai
- http://www.eshkol.ai → should show your website

## Check if eshkol.ai bucket name is available

Run this command periodically to check:

```powershell
aws s3api head-bucket --bucket eshkol.ai 2>&1
```

- If you get "404" or "NoSuchBucket" → Bucket name is available! Proceed to Step 3
- If you get "403" or "Forbidden" → Bucket still exists in another account, wait longer
- If you get "200" or no error → Bucket exists in your account (shouldn't happen unless you created it)

## Troubleshooting

### www.eshkol.ai not working
1. Check nameservers at your domain registrar - they should point to Route 53:
   - ns-1673.awsdns-17.co.uk
   - ns-286.awsdns-35.com
   - ns-690.awsdns-22.net
   - ns-1252.awsdns-28.org

2. Verify CNAME record exists in Route 53 for www.eshkol.ai

3. Test the S3 endpoint directly: http://www.eshkol.ai.s3-website-us-east-1.amazonaws.com

### Root domain (eshkol.ai) not redirecting
- Make sure you completed Step 3 (only possible after bucket name is released)
- Verify A record alias exists in Route 53
- Check that eshkol.ai bucket is configured for redirect (not static hosting)
- Wait for DNS propagation (up to 48 hours, usually minutes)

## Summary

**Right now**: www.eshkol.ai should work

**After eshkol.ai bucket is available**: Both eshkol.ai and www.eshkol.ai will work, with root redirecting to www
