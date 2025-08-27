# Minimal Risk-Free AWS CDK Package

This is a clean, minimal CDK project that **creates an empty CloudFormation stack** (no resources).
It's safe to synthesize and deploy, and serves as a stable baseline to rebuild your pipeline.

## Structure
```
.
├── cdk.json                        # points to python -m infrastructure.app
├── infrastructure/
│   ├── __init__.py
│   ├── app.py                      # CDK entrypoint
│   ├── hello_stack.py              # empty Stack (no resources)
│   └── requirements.txt
├── .github/workflows/deploy.yml    # manual-run GitHub Actions CDK pipeline
└── README.md
```

## How to use

1. **Set the GitHub secret** `AWS_ROLE_ARN` to the role you use for OIDC deployments
   (e.g., `arn:aws:iam::991105135552:role/GitHubDeployRole`).

2. Commit this package to your repo (or replace your repo contents with this).

3. Run the workflow manually:
   - Go to **Actions** → **CI-CDK-Deploy** → **Run workflow**.

4. Local test (optional but recommended):
   ```bash
   npm install -g aws-cdk
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r infrastructure/requirements.txt
   cdk synth
   cdk bootstrap aws://991105135552/us-east-1
   cdk deploy --all --require-approval never
   ```

## Notes
- `cdk.json` is configured for **account 991105135552**, **region us-east-1**.
- The stack is intentionally empty → **free** and **safe**.
- After confirming the pipeline works end-to-end, you can introduce your real stacks and resources.
- If you want to re-enable auto-deploy on push to `main`, change `on:` in `.github/workflows/deploy.yml` to include:
  ```yaml
  on:
    push:
      branches: [ "main" ]
    workflow_dispatch:
  ```
