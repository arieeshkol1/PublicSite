# TSG Sandbox – GitHub Actions + AWS CDK (Python) Pipeline

This repo is a **starting template** to stand up the end‑to‑end pipeline for the TSG exercise in a fresh AWS account (“Sandbox”).
It uses **GitHub OIDC** (no long‑lived keys), **GitHub Actions** for CI/CD, and **AWS CDK (Python)** to provision infra.

## What you get

- ✅ GitHub OIDC federated **deploy role** (CloudFormation template)
- ✅ CDK Python app with stacks:
  - `NetworkStack`: VPC with private/public subnets and VPC endpoints for S3
  - `StorageStack`: S3 buckets `tsg-demo-dirty-in`, `tsg-demo-white-library`, `tsg-demo-ui-dashboard` (+KMS, lifecycle, policies)
  - `ComputeStack`: EC2 Auto Scaling Group (8 vCPU / 16 GiB), SSM, ALB security groups
  - `IamCiStack`: IAM role for GitHub OIDC to allow CDK deploys (admin in sandbox; tighten later)
- ✅ **FastAPI** placeholder service (`/split`, `/unite`) – containerize later
- ✅ GitHub Actions workflow: on push to `main` → `cdk bootstrap` (first run) and `cdk deploy --all --require-approval never`
- ✅ `Makefile` for local dev (bootstrap, deploy, destroy)

> This is a scaffold for the pipeline and infra. The JP2 processing code (tiling, RAW/TIFF conversion, QA) can be added incrementally.

---

## 1) One‑time in the Sandbox AWS account

1. **Create the GitHub OIDC provider + deploy role** (AdministratorAccess for sandbox) by launching the included CloudFormation stack:
   - In the AWS Console → CloudFormation → *Create stack*
   - Upload `scripts/github-oidc-role.yaml`
   - Parameters: `GitHubOrg`, `GitHubRepo`, `RoleName` (`GitHubDeployRole` default)
   - Create stack.

   This will create:
   - An OIDC provider for token.actions.githubusercontent.com (if not present)
   - An **assumable role** trusted by your repo’s `ref:refs/heads/main` and `pull_request`
   - Output: the **Role ARN**

2. In **GitHub repo → Settings → Secrets and variables → Actions → Secrets**, add:
   - `AWS_ROLE_ARN` = *the ARN from step 1*
   - `AWS_REGION` = e.g. `us-east-1`

3. In the AWS Console (same account), ensure:
   - **SSM** is enabled (for Session Manager)
   - **Default VPC limits** allow one small VPC (or request more if needed)

---

## 2) First CI/CD run

Push this repo to GitHub (default branch `main`). The workflow:
- Configures AWS credentials via OIDC
- Runs `cdk bootstrap` (idempotent; harmless if already bootstrapped)
- Deploys stacks: Network → Storage → Compute → IamCi

After success you’ll have:
- VPC + endpoints
- Three S3 buckets
- EC2 Auto Scaling Group with 8 vCPU / 16 GiB instances (e.g., `c6a.2xlarge`)
- An IAM deploy role bound to your repo (you can later down‑scope policies)

---

## 3) Local development (optional)

```bash
# Python 3.11 recommended
python -m venv .venv && source .venv/bin/activate
pip install -r infrastructure/requirements.txt

# Bootstrap (if needed) & deploy
cd infrastructure
cdk bootstrap
cdk deploy --all
```

---

## 4) Next steps (suggested)

- Containerize `application/fastapi_service` with an ECR repo & ECS/Fargate service or keep the EC2 ASG pattern.
- Add an S3 Event → SQS → Step Functions Orchestration for: validate → tile → convert → scan → diode-export → reunite → re-encode → QA.
- Replace sandbox Admin on the deploy role with a least‑privilege policy for CDK (start with CloudFormation + the specific AWS services you use).
- Add KMS CMKs and bucket policies to enforce encryption and VPC endpoint‑only access.