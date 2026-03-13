# Contact Form Setup Guide

This guide explains how to set up the contact form infrastructure for www.eshkolai.com.

## Overview

The contact form uses:
- **AWS Lambda** - Processes form submissions
- **Amazon SES** - Sends emails
- **API Gateway** - Provides HTTPS endpoint for the form
- **CloudFormation** - Infrastructure as Code

## Architecture

```
Website Form → API Gateway → Lambda Function → Amazon SES → Email to ariel.eshkol@gmail.com
```

## Setup Steps

### Step 1: Deploy Infrastructure via GitHub Actions

1. Go to your GitHub repository
2. Click on **Actions** tab
3. Select **Deploy Contact Form Infrastructure** workflow
4. Click **Run workflow**
5. Enter the email addresses:
   - **Recipient Email**: `ariel.eshkol@gmail.com` (where form submissions go)
   - **Sender Email**: `noreply@eshkolai.com` (from address)
6. Click **Run workflow**

### Step 2: Verify Email Addresses in SES

After the workflow completes, you'll receive verification emails:

1. Check inbox for `ariel.eshkol@gmail.com`
   - Look for email from "Amazon Web Services"
   - Subject: "Amazon SES Email Address Verification Request"
   - Click the verification link

2. Check inbox for `noreply@eshkolai.com` (if you have access)
   - Same verification process
   - **Note**: If you don't have access to this email, you can:
     - Use `ariel.eshkol@gmail.com` as both sender and recipient
     - Or set up email forwarding for noreply@eshkolai.com

### Step 3: Get API Endpoint

The workflow will output the API Gateway endpoint URL. You can find it:

1. In the GitHub Actions workflow logs (last step)
2. In the downloaded artifact `api-endpoint.txt`
3. Or run this command:
   ```bash
   aws cloudformation describe-stacks \
     --stack-name contact-form-stack \
     --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
     --output text \
     --region us-east-1
   ```

Example endpoint:
```
https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod/contact
```

### Step 4: Update script.js

1. Open `script.js`
2. Find this line:
   ```javascript
   const apiEndpoint = 'YOUR_API_GATEWAY_ENDPOINT_HERE';
   ```
3. Replace with your actual endpoint:
   ```javascript
   const apiEndpoint = 'https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod/contact';
   ```
4. Save the file

### Step 5: Deploy Updated Website

Commit and push the changes:
```bash
git add script.js
git commit -m "Add contact form API endpoint"
git push origin main
```

The GitHub Actions deployment workflow will automatically:
- Upload files to S3
- Invalidate CloudFront cache
- Make the contact form live

## Testing the Contact Form

1. Visit https://www.eshkolai.com/#contact
2. Fill out the form with test data
3. Click "Send Message"
4. You should see a success message
5. Check `ariel.eshkol@gmail.com` for the email

## Email Format

You'll receive emails with:
- **Subject**: "New Contact Form Submission from [Name]"
- **From**: noreply@eshkolai.com
- **Reply-To**: The submitter's email (so you can reply directly)
- **Content**: Formatted HTML email with all form fields

## SES Sandbox Limitations

By default, SES is in "sandbox mode" which means:
- ✅ You can send emails to verified addresses
- ❌ You cannot send to unverified addresses
- ❌ Limited to 200 emails per day

### To Remove Sandbox Limitations

If you want to receive emails from anyone (not just verified addresses):

1. Request production access:
   ```bash
   # This opens the SES console where you can request production access
   aws ses get-account-sending-enabled --region us-east-1
   ```

2. Or use AWS Console:
   - Go to SES Console → Account Dashboard
   - Click "Request production access"
   - Fill out the form explaining your use case
   - AWS typically approves within 24 hours

## Costs

- **Lambda**: Free tier covers 1M requests/month (contact forms use ~1-2 requests each)
- **API Gateway**: Free tier covers 1M requests/month
- **SES**: $0.10 per 1,000 emails (first 62,000 emails/month are free)
- **Estimated monthly cost**: $0 (well within free tier for typical contact form usage)

## Troubleshooting

### Form shows "Failed to send message"

1. Check browser console for errors
2. Verify API endpoint is correct in script.js
3. Check Lambda logs:
   ```bash
   aws logs tail /aws/lambda/ContactFormHandler --follow --region us-east-1
   ```

### Email not received

1. Verify both email addresses in SES:
   ```bash
   aws ses list-verified-email-addresses --region us-east-1
   ```
2. Check spam folder
3. Check SES sending statistics:
   ```bash
   aws ses get-send-statistics --region us-east-1
   ```

### "Email address not verified" error

- Both sender and recipient emails must be verified in SES
- Check your inbox for verification emails
- Resend verification:
  ```bash
  aws ses verify-email-identity --email-address ariel.eshkol@gmail.com --region us-east-1
  ```

## Security Features

- ✅ CORS enabled for www.eshkolai.com
- ✅ Input validation on required fields
- ✅ Lambda execution role with minimal permissions
- ✅ HTTPS only (via API Gateway)
- ✅ No sensitive data stored
- ✅ Reply-To header set to submitter's email

## Updating the Infrastructure

To update the Lambda function or configuration:

1. Modify `infrastructure/contact-form-stack.yaml`
2. Run the GitHub Actions workflow again
3. CloudFormation will update only what changed

Or use AWS CLI:
```bash
aws cloudformation deploy \
  --template-file infrastructure/contact-form-stack.yaml \
  --stack-name contact-form-stack \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

## Deleting the Infrastructure

To remove all contact form resources:

```bash
aws cloudformation delete-stack \
  --stack-name contact-form-stack \
  --region us-east-1
```

This will delete:
- Lambda function
- API Gateway
- IAM roles
- (SES verified emails will remain)

---

## Quick Reference

**Stack Name**: `contact-form-stack`  
**Region**: `us-east-1`  
**Lambda Function**: `ContactFormHandler`  
**API Name**: `ContactFormAPI`  
**Recipient**: `ariel.eshkol@gmail.com`  
**Sender**: `noreply@eshkolai.com`
