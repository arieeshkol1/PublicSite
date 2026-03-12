# HTTPS Options and Costs for www.eshkolai.com

## Can S3 Do HTTPS Without CloudFront?

**NO.** S3 static website hosting only supports HTTP. You have two options:

### Option 1: S3 Direct Access (Not Recommended)
- URL: https://www.eshkolai.com.s3.amazonaws.com/index.html
- ✓ Has HTTPS
- ✗ Ugly URL (includes .s3.amazonaws.com)
- ✗ No custom domain
- ✗ No index.html default (must specify full path)
- ✗ Not suitable for websites

### Option 2: CloudFront + S3 (Recommended)
- URL: https://www.eshkolai.com
- ✓ HTTPS with custom domain
- ✓ Free SSL certificate (AWS Certificate Manager)
- ✓ Clean URLs
- ✓ Better performance (CDN caching)
- ✓ Global edge locations
- ✓ DDoS protection

## CloudFront Costs

### Free Tier (First 12 Months)
- 1 TB data transfer out per month
- 10,000,000 HTTP/HTTPS requests per month
- 2,000,000 CloudFront Function invocations per month

**For a small website like yours, you'll likely stay within free tier!**

### After Free Tier (Pay-as-you-go)

#### Data Transfer Out (to Internet)
- First 10 TB/month: $0.085 per GB
- Next 40 TB/month: $0.080 per GB
- Next 100 TB/month: $0.060 per GB
- Over 150 TB/month: $0.040 per GB

#### HTTP/HTTPS Requests
- $0.0075 per 10,000 requests (first 10 billion requests/month)

#### SSL Certificate
- **FREE** with AWS Certificate Manager (ACM)

### Cost Examples

#### Small Website (like yours)
**Assumptions:**
- 1,000 visitors/month
- 5 pages per visitor
- 500 KB average page size (HTML + CSS + JS + images)

**Monthly Usage:**
- Requests: 5,000 (1,000 visitors × 5 pages)
- Data transfer: 2.5 GB (5,000 pages × 500 KB)

**Monthly Cost:**
- Requests: $0.0075 × 0.5 = **$0.004**
- Data transfer: $0.085 × 2.5 = **$0.21**
- SSL certificate: **$0** (free)
- **Total: ~$0.21/month** (basically free!)

#### Medium Website
**Assumptions:**
- 10,000 visitors/month
- 5 pages per visitor
- 500 KB average page size

**Monthly Usage:**
- Requests: 50,000
- Data transfer: 25 GB

**Monthly Cost:**
- Requests: $0.0075 × 5 = **$0.04**
- Data transfer: $0.085 × 25 = **$2.13**
- **Total: ~$2.17/month**

#### Large Website
**Assumptions:**
- 100,000 visitors/month
- 5 pages per visitor
- 500 KB average page size

**Monthly Usage:**
- Requests: 500,000
- Data transfer: 250 GB

**Monthly Cost:**
- Requests: $0.0075 × 50 = **$0.38**
- Data transfer: $0.085 × 250 = **$21.25**
- **Total: ~$21.63/month**

## Other AWS Costs (Already Paying)

### S3 Storage
- First 50 TB/month: $0.023 per GB
- Your website (~40 KB): **$0.001/month** (negligible)

### Route 53
- Hosted zone: $0.50/month
- Queries: $0.40 per million queries
- Your usage: **~$0.50/month**

## Total Monthly Cost Estimate

### Current Setup (HTTP only)
- S3: ~$0.001
- Route 53: ~$0.50
- **Total: ~$0.50/month**

### With CloudFront (HTTPS)
- S3: ~$0.001
- Route 53: ~$0.50
- CloudFront: ~$0.21 (for small traffic)
- **Total: ~$0.71/month**

**Additional cost for HTTPS: ~$0.21/month (basically nothing!)**

## Comparison with Alternatives

### Netlify (Free Tier)
- 100 GB bandwidth/month
- HTTPS included
- Cost: Free (but limited)

### Vercel (Free Tier)
- 100 GB bandwidth/month
- HTTPS included
- Cost: Free (but limited)

### AWS CloudFront
- Unlimited bandwidth (pay per use)
- HTTPS included
- Cost: ~$0.21/month for small sites
- ✓ More control
- ✓ Integrates with AWS services
- ✓ No vendor lock-in concerns

## Recommendation

**Use CloudFront!** The cost is negligible (~$0.21/month for your traffic), and you get:
- ✓ HTTPS with custom domain
- ✓ Free SSL certificate
- ✓ Better performance (CDN)
- ✓ Global distribution
- ✓ DDoS protection
- ✓ Professional setup

For a small website like yours, you'll likely stay within the free tier for the first 12 months, and after that, it's less than $1/month.

## Next Steps

If you want to add HTTPS with CloudFront, I can:
1. Create CloudFront distribution
2. Request SSL certificate from ACM
3. Update Route 53 to point to CloudFront
4. Configure automatic HTTPS redirect
5. Update GitHub Actions to invalidate CloudFront cache on deploy

Would you like me to set this up?
