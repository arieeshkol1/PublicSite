# GitHub Configuration Guide

## Current GitHub Repository

**Repository URL**: https://github.com/arieeshkol1/TAG-SYSTEM-POC

## Where to Find GitHub Configurations

### 1. On GitHub Website

Visit your repository and look for these sections:

#### Settings Tab
**URL**: https://github.com/arieeshkol1/TAG-SYSTEM-POC/settings

Here you can configure:
- **General**: Repository name, visibility, features
- **Branches**: Branch protection rules, default branch
- **Secrets and variables**: Store AWS credentials securely
  - Go to: Settings → Secrets and variables → Actions
  - This is where you'd store AWS credentials for automated deployment
- **Pages**: GitHub Pages configuration (if using)
- **Webhooks**: Integration with external services

#### Actions Tab
**URL**: https://github.com/arieeshkol1/TAG-SYSTEM-POC/actions

Here you can see:
- Workflow runs (currently none, as no workflows are configured)
- Workflow files (currently none)

#### Code Tab
**URL**: https://github.com/arieeshkol1/TAG-SYSTEM-POC

Current files in your repository:
```
├── .gitignore
├── index.html
├── styles.css
├── README.md
├── DEPLOYMENT_INSTRUCTIONS.md
├── SETUP_STATUS.md
└── .kiro/
    └── specs/
        └── aws-bill-analyzer/
            ├── .config.kiro
            └── requirements.md
```

**Note**: No `.github/` folder exists yet, so no GitHub Actions workflows are configured.

### 2. In Your Local Repository

#### Git Configuration
```powershell
# View remote repository URL
git remote -v

# View current branch
git branch

# View git configuration
git config --list
```

#### GitHub Actions Workflows (Not Yet Created)
Would be located at: `.github/workflows/*.yml`

Currently: **No workflows exist**

## What's Currently Configured

### ✅ Repository Basics
- **Name**: TAG-SYSTEM-POC
- **Owner**: arieeshkol1
- **Default Branch**: main
- **Visibility**: Private (most likely)

### ❌ Not Yet Configured
- **GitHub Actions workflows**: No automated deployment
- **GitHub Secrets**: No AWS credentials stored
- **Branch protection**: No rules set
- **GitHub Pages**: Not enabled

## How to Set Up Automated Deployment to S3

If you want GitHub to automatically deploy to S3 when you push code, you need to:

### Step 1: Store AWS Credentials in GitHub Secrets

1. Go to: https://github.com/arieeshkol1/TAG-SYSTEM-POC/settings/secrets/actions
2. Click "New repository secret"
3. Add these secrets:
   - `AWS_ACCESS_KEY_ID` - Your AWS access key for account 991105135552
   - `AWS_SECRET_ACCESS_KEY` - Your AWS secret key
   - `AWS_REGION` - us-east-1
   - `S3_BUCKET` - arieleshkolwebsite22feb2026

### Step 2: Create GitHub Actions Workflow

Create file: `.github/workflows/deploy-to-s3.yml`

```yaml
name: Deploy to S3

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}

      - name: Deploy to S3
        run: |
          aws s3 cp index.html s3://${{ secrets.S3_BUCKET }}/
          aws s3 cp styles.css s3://${{ secrets.S3_BUCKET }}/
```

### Step 3: Push the Workflow File

```powershell
git add .github/workflows/deploy-to-s3.yml
git commit -m "Add GitHub Actions workflow for S3 deployment"
git push origin main
```

## Viewing Configurations on GitHub

### Method 1: GitHub Web Interface

1. **Repository Settings**
   - URL: https://github.com/arieeshkol1/TAG-SYSTEM-POC/settings
   - Shows all repository configuration options

2. **Actions Tab**
   - URL: https://github.com/arieeshkol1/TAG-SYSTEM-POC/actions
   - Shows workflow runs and status

3. **Code Tab → .github folder**
   - URL: https://github.com/arieeshkol1/TAG-SYSTEM-POC/tree/main/.github
   - Currently doesn't exist (404 error expected)

### Method 2: GitHub CLI (if installed)

```powershell
# View repository info
gh repo view arieeshkol1/TAG-SYSTEM-POC

# View workflows
gh workflow list

# View secrets (names only, not values)
gh secret list
```

### Method 3: Git Commands (Local)

```powershell
# View remote configuration
git remote show origin

# View all branches
git branch -a

# View recent commits
git log --oneline -10
```

## Current Status Summary

| Configuration | Status | Location |
|--------------|--------|----------|
| Repository | ✅ Created | https://github.com/arieeshkol1/TAG-SYSTEM-POC |
| Files | ✅ Pushed | Code tab on GitHub |
| GitHub Actions | ❌ Not configured | Would be in Actions tab |
| AWS Secrets | ❌ Not stored | Would be in Settings → Secrets |
| Automated Deployment | ❌ Not set up | Would need workflow file |

## Next Steps

Would you like me to:
1. **Create a GitHub Actions workflow** for automatic S3 deployment?
2. **Show you how to add AWS credentials** to GitHub Secrets?
3. **Set up the complete CI/CD pipeline** for your website?

Let me know which option you prefer!
