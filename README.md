# AWS CDK Project

This repository is ready for your next AWS CDK project.

## Prerequisites

- Node.js 14.x or later
- AWS CLI configured with appropriate credentials
- AWS CDK CLI: `npm install -g aws-cdk`
- Python 3.9+ (if using Python for CDK)

## Getting Started

1. Initialize your CDK project:
```bash
cdk init app --language=python
# or
cdk init app --language=typescript
```

2. Install dependencies:
```bash
npm install
# or for Python
pip install -r requirements.txt
```

3. Deploy your stack:
```bash
cdk deploy
```

## Useful Commands

- `cdk ls` - List all stacks
- `cdk synth` - Synthesize CloudFormation template
- `cdk deploy` - Deploy stack to AWS
- `cdk diff` - Compare deployed stack with current state
- `cdk destroy` - Remove stack from AWS

## GitHub Actions CI/CD

This repository includes a GitHub Actions workflow for automated deployments. Configure the following secrets in your repository:

- `AWS_ACCOUNT_ID` - Your AWS account ID
- `AWS_REGION` - Target AWS region (e.g., us-east-1)

The workflow uses OIDC for secure authentication with AWS.
