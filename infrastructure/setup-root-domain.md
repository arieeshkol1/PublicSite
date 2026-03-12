# Setup Root Domain (eshkol.ai) in Route 53

## Prerequisites
- S3 bucket `eshkol.ai` created and configured for static website hosting
- Bucket name MUST match domain name exactly for alias records to work
- Files deployed to the bucket

## Steps to Create A Record Alias

### 1. Run the bucket creation script
```powershell
cd infrastructure
./create-eshkol-bucket.ps1
```

This will:
- Create the `eshkol.ai` bucket
- Enable static website hosting
- Set bucket policy for public access and GitHub deployment
- Copy all files from `www.eshkol.ai` bucket
- Display the S3 website endpoint

### 2. Create A Record in Route 53

1. Go to Route 53 console: https://console.aws.amazon.com/route53/
2. Click on "Hosted zones"
3. Click on "eshkol.ai"
4. Click "Create record"
5. Configure the record:
   - **Record name**: Leave blank (this creates a record for the root domain)
   - **Record type**: A - Routes traffic to an IPv4 address and some AWS resources
   - **Value/Route traffic to**: 
     - Select "Alias to S3 website endpoint"
     - Select region: "US East (N. Virginia) [us-east-1]"
     - Select endpoint: Should show `s3-website-us-east-1.amazonaws.com` or `eshkol.ai.s3-website-us-east-1.amazonaws.com`
   - **Evaluate target health**: No
6. Click "Create records"

### 3. Verify DNS Configuration

After creating the A record, verify:

```powershell
# Check DNS resolution
nslookup eshkol.ai

# Test the website
curl http://eshkol.ai
```

### 4. Update www subdomain (optional)

If you want www.eshkol.ai to redirect to eshkol.ai:

1. Keep the existing CNAME record for www.eshkol.ai pointing to www.eshkol.ai.s3-website-us-east-1.amazonaws.com
2. Or delete the www.eshkol.ai bucket and CNAME record if you only want the root domain

## Important Notes

- The bucket name MUST be exactly `eshkol.ai` for the alias record to work
- You cannot use CNAME records for the root domain (apex)
- A records with alias to S3 website endpoint only work when bucket name matches domain name
- DNS propagation can take a few minutes

## Troubleshooting

### "Not a valid S3 website endpoint"
- Make sure you selected "Alias to S3 website endpoint" (not "Alias to S3 bucket")
- The bucket must be configured for static website hosting
- The bucket name must match the domain name exactly

### Website not loading
- Check that bucket policy allows public read access
- Verify static website hosting is enabled on the bucket
- Check that index.html exists in the bucket
- Wait for DNS propagation (can take up to 48 hours, usually much faster)

### Access Denied errors in GitHub Actions
- Verify GitHubDeployRole has permissions in the bucket policy
- Check that the role trust policy allows GitHub OIDC
