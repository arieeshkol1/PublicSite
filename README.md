# AWS CDK Deployment Pipeline

This repository contains a GitHub Actions pipeline for deploying AWS CDK infrastructure.

## Overview

Clean starter repository with automated CDK deployment pipeline configured for AWS.

## Prerequisites

- AWS Account with appropriate permissions
- GitHub repository with OIDC configured
- AWS IAM role for GitHub Actions deployment

## Setup

1. **Configure AWS OIDC Role**
   - Create an IAM role with trust relationship for GitHub Actions
   - Add the role ARN as a GitHub secret: `AWS_ROLE_ARN`

2. **Deploy Infrastructure**
   - Push your CDK infrastructure code to this repository
   - The GitHub Actions pipeline will automatically deploy on push to main
   - Or manually trigger deployment from Actions tab

## Repository Structure

```
.github/workflows/  # GitHub Actions deployment pipeline
.kiro/             # Kiro AI assistant configuration
```

## Deployment Pipeline

The deployment pipeline is located in `.github/workflows/` and handles:
- AWS authentication via OIDC
- CDK bootstrap (if needed)
- CDK deployment to your AWS account

## Getting Started

1. Add your CDK infrastructure code
2. Configure stack parameters as needed
3. Push to main branch or manually trigger deployment
4. Monitor deployment in GitHub Actions tab

## Notes

- AWS resources are deployed to account: 960915223703
- Default region: us-east-1
- Ensure your CDK code follows AWS best practices
