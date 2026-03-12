# Manual Domain Setup for eshkol.ai

The automated CloudFormation deployment is having issues. Here's how to set it up manually through the AWS Console:

## Step 1: Request SSL Certificate (ACM)

1. Go to AWS Certificate Manager: https://console.aws.amazon.com/acm
2. Click "Request certificate"
3. Choose "Request a public certificate"
4. Add domain names:
   - eshkol.ai
   - www.eshkol.ai
5. Choose "DNS validation"
6. Click "Request"
7. Click "Create records in Route 53" (this will auto-validate)
8. Wait 5-30 minutes for validation to complete

## Step 2: Create CloudFront Distribution

1. Go to CloudFront: https://console.aws.amazon.com/cloudfront
2. Click "Create distribution"
3. Configure:
   - **Origin domain**: arieleshkolwebsite22feb2026.s3-website-us-east-1.amazonaws.com
   - **Protocol**: HTTP only
   - **Name**: Leave default
   - **Viewer protocol policy**: Redirect HTTP to HTTPS
   - **Allowed HTTP methods**: GET, HEAD, OPTIONS
   - **Cache policy**: CachingOptimized
   - **Alternate domain names (CNAMEs)**: 
     - eshkol.ai
     - www.eshkol.ai
   - **Custom SSL certificate**: Select the certificate from Step 1
   - **Default root object**: index.html
4. Click "Create distribution"
5. Wait 15-20 minutes for deployment

## Step 3: Update Route 53 Records

1. Go to Route 53: https://console.aws.amazon.com/route53
2. Click on "eshkol.ai" hosted zone
3. Create A record for root domain:
   - Click "Create record"
   - Record name: (leave empty for root)
   - Record type: A
   - Toggle "Alias" ON
   - Route traffic to: "Alias to CloudFront distribution"
   - Choose your CloudFront distribution
   - Click "Create records"
4. Create A record for www:
   - Click "Create record"
   - Record name: www
   - Record type: A
   - Toggle "Alias" ON
   - Route traffic to: "Alias to CloudFront distribution"
   - Choose your CloudFront distribution
   - Click "Create records"

## Step 4: Update GitHub Workflow

Once CloudFront is deployed, get the Distribution ID and update the workflow to invalidate cache.

## Verification

After DNS propagates (up to 48 hours), your site will be at:
- https://eshkol.ai
- https://www.eshkol.ai

## Quick Test

Test CloudFront directly (works immediately):
- https://[your-cloudfront-id].cloudfront.net
