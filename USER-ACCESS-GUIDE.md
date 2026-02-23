# Made4Net Fortress & Factory - User Access Guide

## Overview

This guide explains how to access the Made4Net Fortress & Factory system as different types of users.

---

## 🎯 User Types & Access Methods

### 1. **Dashboard User (Operational Excellence Viewer)**
**Who:** Operations team, management, stakeholders viewing metrics
**Access Method:** Web browser (HTTPS)
**Authentication:** None required (read-only dashboard)

### 2. **AWS Administrator**
**Who:** Infrastructure team managing AWS resources
**Access Method:** AWS Console + CLI
**Authentication:** AWS IAM credentials + MFA

### 3. **Application Developer**
**Who:** Developers deploying code and managing Lambda functions
**Access Method:** AWS Console + CLI + GitHub Actions
**Authentication:** AWS IAM credentials + GitHub secrets

---

## 📊 Option 1: Access the Dashboard (Most Common)

### Step 1: Get the Dashboard URL

After deployment, the dashboard is hosted on:
- **CloudFront URL:** `https://[distribution-id].cloudfront.net`
- **Custom Domain (if configured):** `https://dashboard.made4net.com`

To find your CloudFront URL:

```bash
# From AWS Console:
1. Go to CloudFront service
2. Find distribution named "Made4NetFortressDashboard"
3. Copy the "Domain Name" (e.g., d1234abcd.cloudfront.net)

# Or from AWS CLI:
aws cloudfront list-distributions --query "DistributionList.Items[?Comment=='Made4Net Fortress Dashboard'].DomainName" --output text
```

### Step 2: Open the Dashboard

1. Open your web browser
2. Navigate to: `https://[your-cloudfront-domain]`
3. You should see the **Made4Net Fortress & Factory** dashboard

### Step 3: Generate Metrics

The dashboard displays operational metrics. To generate new metrics:

1. Click the **"🔄 Generate New Metrics"** button
2. Wait 1-2 seconds for metrics to load
3. Dashboard will auto-refresh every 30 seconds

### What You'll See:

- **Security Posture:** GuardDuty findings, WAF blocks, compliance score
- **Operational Health:** System availability, patch compliance, MTTR
- **Cost Optimization:** Monthly savings, idle resources
- **Multi-Region Status:** Primary/DR region health
- **WAF Protection:** Real-time threat blocking chart
- **Patch Management:** Server compliance status

---

## 🔐 Option 2: Access AWS Console (Administrators)

### Prerequisites:
- AWS account with IAM user credentials
- MFA device configured (required for production)

### Step 1: Login to AWS Console

1. Go to: https://console.aws.amazon.com
2. Enter your **AWS Account ID** (12-digit number)
3. Enter your **IAM username**
4. Enter your **password**
5. Enter **MFA code** from your authenticator app

### Step 2: Navigate to Services

Common services for Made4Net Fortress:

**Monitoring & Operations:**
- **CloudWatch:** View logs, metrics, alarms
- **Systems Manager:** Manage EC2 instances, run commands
- **X-Ray:** Trace application performance
- **GuardDuty:** View security findings

**Infrastructure:**
- **EC2:** View instances, AMIs, security groups
- **VPC:** View network configuration
- **S3:** Access dashboard bucket and backups
- **Lambda:** View/edit serverless functions

**Security:**
- **IAM:** Manage users, roles, policies
- **WAF:** View firewall rules and blocked requests
- **Config:** View configuration compliance

### Step 3: Common Admin Tasks

**View Dashboard Metrics in DynamoDB:**
```bash
# AWS Console:
1. Go to DynamoDB service
2. Find table: "Made4NetMetrics"
3. Click "Explore table items"
4. View latest metrics

# AWS CLI:
aws dynamodb scan --table-name Made4NetMetrics --max-items 10
```

**View Lambda Function Logs:**
```bash
# AWS Console:
1. Go to Lambda service
2. Click "MetricsGeneratorFunction"
3. Click "Monitor" tab
4. Click "View CloudWatch logs"

# AWS CLI:
aws logs tail /aws/lambda/MetricsGeneratorFunction --follow
```

**Trigger Manual Metrics Generation:**
```bash
# AWS Console:
1. Go to Lambda service
2. Click "MetricsGeneratorFunction"
3. Click "Test" tab
4. Click "Test" button

# AWS CLI:
aws lambda invoke --function-name MetricsGeneratorFunction response.json
```

---

## 💻 Option 3: Access via AWS CLI (Developers)

### Prerequisites:
- AWS CLI installed
- AWS credentials configured

### Step 1: Configure AWS CLI

```bash
# Configure credentials
aws configure

# Enter when prompted:
AWS Access Key ID: [Your access key]
AWS Secret Access Key: [Your secret key]
Default region name: us-east-1
Default output format: json
```

### Step 2: Verify Access

```bash
# Check your identity
aws sts get-caller-identity

# List CloudFormation stacks
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE

# Get dashboard URL
aws cloudfront list-distributions --query "DistributionList.Items[?Comment=='Made4Net Fortress Dashboard'].DomainName" --output text
```

### Step 3: Common CLI Commands

**Generate Metrics:**
```bash
# Invoke Lambda function
aws lambda invoke \
  --function-name MetricsGeneratorFunction \
  --payload '{}' \
  response.json

# View response
cat response.json
```

**Query Metrics from DynamoDB:**
```bash
# Get latest metrics
aws dynamodb scan \
  --table-name Made4NetMetrics \
  --limit 10 \
  --output table
```

**View CloudWatch Logs:**
```bash
# List log groups
aws logs describe-log-groups --log-group-name-prefix /aws/lambda

# Tail logs in real-time
aws logs tail /aws/lambda/MetricsGeneratorFunction --follow
```

**Update Dashboard:**
```bash
# Upload new dashboard version
aws s3 cp dashboard/index.html s3://made4net-fortress-dashboard-[account-id]/

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id [your-distribution-id] \
  --paths "/*"
```

---

## 🚀 Option 4: Deploy via GitHub Actions (CI/CD)

### Prerequisites:
- GitHub repository access
- AWS credentials configured in GitHub Secrets

### Step 1: Configure GitHub Secrets

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Add the following secrets:
   - `AWS_ACCESS_KEY_ID`: Your AWS access key
   - `AWS_SECRET_ACCESS_KEY`: Your AWS secret key
   - `AWS_REGION`: Your AWS region (e.g., us-east-1)
   - `AWS_ACCOUNT_ID`: Your 12-digit AWS account ID

### Step 2: Trigger Deployment

**Automatic Deployment:**
- Push to `main` branch triggers automatic deployment

**Manual Deployment:**
1. Go to **Actions** tab in GitHub
2. Select **"Deploy to AWS"** workflow
3. Click **"Run workflow"**
4. Select branch and click **"Run workflow"**

### Step 3: Monitor Deployment

1. Click on the running workflow
2. View logs for each step:
   - Install dependencies
   - CDK bootstrap
   - CDK deploy
   - Update dashboard

---

## 🔧 Troubleshooting

### Dashboard Not Loading

**Problem:** Dashboard shows blank page or errors

**Solutions:**
1. Check CloudFront distribution status (must be "Deployed")
2. Verify S3 bucket has index.html file
3. Check browser console for JavaScript errors
4. Verify API endpoint is configured in dashboard/index.html

```bash
# Check CloudFront status
aws cloudfront get-distribution --id [distribution-id] --query "Distribution.Status"

# Verify S3 bucket contents
aws s3 ls s3://made4net-fortress-dashboard-[account-id]/
```

### Metrics Not Generating

**Problem:** Dashboard shows "Loading..." or old metrics

**Solutions:**
1. Check Lambda function exists and is active
2. Verify DynamoDB table exists
3. Check Lambda execution role has permissions
4. View Lambda logs for errors

```bash
# Test Lambda function
aws lambda invoke --function-name MetricsGeneratorFunction test-output.json

# Check Lambda logs
aws logs tail /aws/lambda/MetricsGeneratorFunction --since 10m
```

### Access Denied Errors

**Problem:** "Access Denied" when accessing AWS resources

**Solutions:**
1. Verify IAM user has correct permissions
2. Check MFA is configured (required for production)
3. Verify AWS credentials are current
4. Check IAM policy attachments

```bash
# Check your IAM user
aws iam get-user

# List attached policies
aws iam list-attached-user-policies --user-name [your-username]
```

---

## 📱 Mobile Access

The dashboard is responsive and works on mobile devices:

1. Open mobile browser (Chrome, Safari, Firefox)
2. Navigate to dashboard URL
3. Dashboard adapts to mobile screen size
4. All metrics and charts are viewable
5. Tap "Generate New Metrics" button to refresh

---

## 🎤 Demo Mode (For Presentations)

To demonstrate the system without AWS access:

1. Open `dashboard/index.html` locally in browser
2. Click "Generate New Metrics" button
3. Dashboard generates random realistic metrics
4. Use for presentations, training, or demos
5. No AWS credentials required

---

## 📞 Support & Help

### Getting Help:

**For Dashboard Issues:**
- Check browser console (F12) for errors
- Verify API endpoint configuration
- Contact infrastructure team

**For AWS Access Issues:**
- Contact AWS administrator
- Verify IAM permissions
- Check MFA configuration

**For Deployment Issues:**
- Check GitHub Actions logs
- Verify AWS credentials in GitHub Secrets
- Review CloudFormation stack events

### Useful Links:

- **AWS Console:** https://console.aws.amazon.com
- **GitHub Repository:** https://github.com/arieeshkol1/TAG-SYSTEM-POC
- **AWS Documentation:** https://docs.aws.amazon.com
- **CDK Documentation:** https://docs.aws.amazon.com/cdk

---

## ✅ Quick Start Checklist

### For Dashboard Users:
- [ ] Get CloudFront URL from admin
- [ ] Open URL in web browser
- [ ] Click "Generate New Metrics"
- [ ] Bookmark URL for future access

### For AWS Administrators:
- [ ] Configure AWS CLI with credentials
- [ ] Login to AWS Console with MFA
- [ ] Verify CloudFormation stack deployed
- [ ] Test Lambda function execution
- [ ] Share dashboard URL with team

### For Developers:
- [ ] Clone GitHub repository
- [ ] Configure AWS credentials locally
- [ ] Install AWS CDK (`npm install -g aws-cdk`)
- [ ] Run `cdk deploy` to test deployment
- [ ] Configure GitHub Secrets for CI/CD

---

**Last Updated:** $(date)
**Version:** 1.0
**Status:** ✅ Ready for Use
