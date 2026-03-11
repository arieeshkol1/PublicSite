# GitHub Actions Setup Guide

## ✅ Workflow Created

I've created a GitHub Actions workflow at `.github/workflows/deploy-to-s3.yml` that will automatically deploy your website to S3 whenever you push changes to the main branch.

## 🔐 Required: Configure AWS Credentials

You need to add AWS credentials to GitHub Secrets so the workflow can deploy to S3.

### Option 1: Using OIDC (Recommended - More Secure)

This method uses OpenID Connect and doesn't require storing long-term credentials.

#### Step 1: Create IAM Role in AWS (Account 991105135552)

1. Go to AWS Console → IAM → Roles
2. Click "Create role"
3. Select "Web identity"
4. Choose "OpenID Connect"
5. For Provider, enter: `token.actions.githubusercontent.com`
6. For Audience, enter: `sts.amazonaws.com`
7. Click "Next"
8. Attach policy with these permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:DeleteObject"
            ],
            "Resource": [
                "arn:aws:s3:::arieleshkolwebsite22feb2026",
                "arn:aws:s3:::arieleshkolwebsite22feb2026/*"
            ]
        }
    ]
}
```

9. Name the role: `github-actions-s3-deploy`
10. Edit the trust policy to include your GitHub repo:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Federated": "arn:aws:iam::991105135552:oidc-provider/token.actions.githubusercontent.com"
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                },
                "StringLike": {
                    "token.actions.githubusercontent.com:sub": "repo:arieeshkol1/TAG-SYSTEM-POC:*"
                }
            }
        }
    ]
}
```

11. Copy the Role ARN (e.g., `arn:aws:iam::991105135552:role/github-actions-s3-deploy`)

#### Step 2: Add Role ARN to GitHub Secrets

1. Go to: https://github.com/arieeshkol1/TAG-SYSTEM-POC/settings/secrets/actions
2. Click "New repository secret"
3. Name: `AWS_ROLE_ARN`
4. Value: Paste the Role ARN from Step 1
5. Click "Add secret"

### Option 2: Using Access Keys (Simpler but Less Secure)

If you prefer to use access keys instead of OIDC:

#### Step 1: Create IAM User in AWS (Account 991105135552)

1. Go to AWS Console → IAM → Users
2. Click "Create user"
3. Username: `github-actions-deploy`
4. Click "Next"
5. Select "Attach policies directly"
6. Create and attach a policy with these permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:DeleteObject"
            ],
            "Resource": [
                "arn:aws:s3:::arieleshkolwebsite22feb2026",
                "arn:aws:s3:::arieleshkolwebsite22feb2026/*"
            ]
        }
    ]
}
```

7. Click "Create user"
8. Go to the user → Security credentials → Create access key
9. Choose "Application running outside AWS"
10. Copy the Access Key ID and Secret Access Key

#### Step 2: Add Credentials to GitHub Secrets

1. Go to: https://github.com/arieeshkol1/TAG-SYSTEM-POC/settings/secrets/actions
2. Add these secrets:
   - `AWS_ACCESS_KEY_ID` - Your access key ID
   - `AWS_SECRET_ACCESS_KEY` - Your secret access key

#### Step 3: Update Workflow File

If using access keys, modify `.github/workflows/deploy-to-s3.yml`:

Change this section:
```yaml
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
```

To this:
```yaml
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}
```

## 🚀 How to Use the Workflow

Once credentials are configured:

1. **Automatic Deployment**: 
   - Make changes to `index.html` or `styles.css`
   - Commit and push to main branch
   - GitHub Actions will automatically deploy to S3

2. **Manual Deployment**:
   - Go to: https://github.com/arieeshkol1/TAG-SYSTEM-POC/actions
   - Click "Deploy Website to S3"
   - Click "Run workflow"
   - Select branch: main
   - Click "Run workflow"

## 📊 Monitoring Deployments

View deployment status:
- Go to: https://github.com/arieeshkol1/TAG-SYSTEM-POC/actions
- Click on any workflow run to see details
- Green checkmark = successful deployment
- Red X = failed deployment (check logs for errors)

## 🔍 Troubleshooting

### Error: "User is not authorized to perform: s3:PutObject"
- Check IAM permissions include `s3:PutObject`
- Verify the bucket name is correct
- Ensure the role/user has access to the specific bucket

### Error: "No such bucket"
- Verify bucket name: `arieleshkolwebsite22feb2026`
- Check you're in the correct AWS account (991105135552)
- Ensure bucket exists in us-east-1 region

### Error: "Credentials could not be loaded"
- Verify GitHub Secrets are set correctly
- Check secret names match the workflow file
- For OIDC: Verify the trust policy includes your repo

## ✅ Next Steps

1. **Configure AWS credentials** (choose Option 1 or Option 2 above)
2. **Commit and push** the workflow file:
   ```bash
   git add .github/workflows/deploy-to-s3.yml
   git commit -m "Add GitHub Actions workflow for S3 deployment"
   git push origin main
   ```
3. **Watch the deployment** in the Actions tab
4. **Verify your website** is updated in S3

## 📝 What the Workflow Does

1. **Triggers on**:
   - Push to main branch (when HTML/CSS files change)
   - Manual trigger via GitHub UI

2. **Steps**:
   - Checks out your code
   - Configures AWS credentials
   - Uploads `index.html` and `styles.css` to S3
   - Verifies the upload
   - Shows deployment summary

3. **Cache Control**:
   - HTML files: 5 minutes (300 seconds) - for quick updates
   - CSS files: 24 hours (86400 seconds) - for better performance

## 🎯 Current Status

- ✅ Workflow file created
- ⏳ AWS credentials need to be configured
- ⏳ Workflow needs to be pushed to GitHub

Once you configure the credentials and push the workflow, your website will automatically deploy to S3 on every push!
