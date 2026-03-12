# Simple Domain Setup for eshkol.ai (HTTP only, no SSL)

## Step 1: Enable S3 Website Hosting

1. Go to S3 Console: https://s3.console.aws.amazon.com/s3/buckets/arieleshkolwebsite22feb2026
2. Click on "Properties" tab
3. Scroll to "Static website hosting"
4. Click "Edit"
5. Select "Enable"
6. Index document: `index.html`
7. Error document: `index.html`
8. Click "Save changes"
9. Copy the "Bucket website endpoint" URL (e.g., http://arieleshkolwebsite22feb2026.s3-website-us-east-1.amazonaws.com)

## Step 2: Create Route 53 Alias Record

1. Go to Route 53: https://console.aws.amazon.com/route53
2. Click "Hosted zones"
3. Click on "eshkol.ai"
4. Click "Create record"
5. Configure:
   - Record name: (leave empty for root domain)
   - Record type: A
   - Toggle "Alias" to ON
   - Route traffic to: "Alias to S3 website endpoint"
   - Region: US East (N. Virginia) [us-east-1]
   - S3 endpoint: Choose your bucket from dropdown
6. Click "Create records"

## Step 3: Create www Record (Optional)

1. Click "Create record" again
2. Configure:
   - Record name: www
   - Record type: CNAME
   - Value: eshkol.ai
   - TTL: 300
3. Click "Create records"

## Done!

Your site will be accessible at:
- http://eshkol.ai (after DNS propagates, up to 48 hours)
- http://www.eshkol.ai

Note: This is HTTP only. For HTTPS, you'll need CloudFront + ACM certificate.
