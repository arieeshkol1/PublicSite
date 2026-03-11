# Deployment Instructions

## ✅ Completed Steps

1. ✓ Cleaned up old Mobile Knowledge Assistant project
2. ✓ Created baseline website files:
   - `index.html` - Main HTML page
   - `styles.css` - Stylesheet
3. ✓ Committed to GitHub repository: https://github.com/arieeshkol1/TAG-SYSTEM-POC
4. ✓ Pushed to GitHub (commit: f27984a)

## 📋 Next Step: Upload to S3

The files need to be uploaded to your S3 bucket:
- **Bucket Name**: arieleshkolwebsite22feb2026
- **Bucket ARN**: arn:aws:s3:::arieleshkolwebsite22feb2026
- **AWS Account**: 991105135552

### Option 1: Upload via AWS Console (Easiest)

1. Go to AWS Console: https://console.aws.amazon.com/
2. Make sure you're logged into account **991105135552**
3. Navigate to S3 service
4. Find bucket: `arieleshkolwebsite22feb2026`
5. Click "Upload"
6. Drag and drop these files:
   - `index.html`
   - `styles.css`
7. Click "Upload"

### Option 2: Upload via AWS CLI

First, configure AWS CLI with credentials for account 991105135552:

```powershell
# Configure AWS CLI for the correct account
aws configure --profile ariel-website

# Then upload files
aws s3 cp index.html s3://arieleshkolwebsite22feb2026/ --profile ariel-website --region us-east-1
aws s3 cp styles.css s3://arieleshkolwebsite22feb2026/ --profile ariel-website --region us-east-1
```

### Option 3: Fix IAM Permissions

Add permissions to your current IAM user (github-cicd) to access the bucket:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::arieleshkolwebsite22feb2026",
                "arn:aws:s3:::arieleshkolwebsite22feb2026/*"
            ]
        }
    ]
}
```

## 🌐 After Upload: Configure Static Website Hosting

Once files are uploaded, configure the bucket for static website hosting:

1. Go to S3 bucket properties
2. Scroll to "Static website hosting"
3. Click "Edit"
4. Enable static website hosting
5. Set:
   - **Index document**: index.html
   - **Error document**: index.html (optional)
6. Save changes
7. Note the website endpoint URL (e.g., http://arieleshkolwebsite22feb2026.s3-website-us-east-1.amazonaws.com)

## 🔒 Make Files Public (if needed)

If you want the website to be publicly accessible:

1. Go to bucket permissions
2. Uncheck "Block all public access" (if needed)
3. Add bucket policy:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::arieleshkolwebsite22feb2026/*"
        }
    ]
}
```

## 📁 Current Files in Repository

```
.
├── index.html          # Main HTML file
├── styles.css          # CSS stylesheet
├── README.md           # Project documentation
└── .git/               # Git repository
```

## 🎯 This is Your Baseline

These files are now the baseline for your website. Any future changes should be made to these files and then:

1. Commit to GitHub
2. Upload to S3

## ✅ Verification

After uploading to S3 and configuring static website hosting, test your website:

1. Get the S3 website endpoint URL
2. Open it in a browser
3. You should see your website with:
   - Header with navigation
   - Hero section
   - About, Projects, Contact sections
   - Footer

## 🚀 Next Steps

Now that you have a clean baseline, you can:

1. Modify `index.html` and `styles.css` as needed
2. Add more pages
3. Add JavaScript functionality
4. Set up a custom domain (optional)
5. Set up CloudFront for HTTPS (optional)

---

**Status**: Files are in GitHub ✓ | Files need to be uploaded to S3 ⏳
