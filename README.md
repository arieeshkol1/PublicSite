# TSG Serverless JP2 (Clean Starter)

This is a **fail-proof minimal** serverless baseline for a JP2 Split/Unite pipeline.

### Deploy (GitHub Actions)
1) Push to a **new GitHub repo**.
2) Add secret **AWS_ROLE_ARN** with your OIDC deploy role ARN.
3) Run the workflow: **Actions → Deploy-Serverless-JP2 → Run workflow**.

### What gets created
- S3: `jp2-input-<acct>-<region>`, `jp2-output-<acct>-<region>`, `jp2-ui-<acct>-<region>`
- API Gateway HTTP API: `/split`, `/unite`, `/status/{jobId}` (Lambda stub)
- UI uploaded to the UI bucket (S3 static website)

### After deploy
- Open **UiBucketWebsiteUrl** (from stack outputs).
- Paste **ApiEndpoint** into the page and test the forms.

> This starter returns stub job IDs and `SUCCEEDED` status. Add real JP2 processing later with a Lambda container + Step Functions.

### Committing and pushing from GitHub Desktop
If you need to publish local changes (for example, adding `infrastructure/docker/tiler/tiler.py`) directly to the `main` branch on GitHub, follow these steps:

1. **Make sure you're on `main`.**
   - In GitHub Desktop, open the branch selector (top center) and choose `main`.
   - If you do not see `main`, fetch the latest branches with **Repository ▸ Fetch origin**.
2. **Pull the latest remote history.**
   - Click **Repository ▸ Pull** (or press `Ctrl/Cmd+Shift+P`) to ensure your local `main` matches GitHub.
3. **Add or update your files locally.**
   - Create missing folders if needed (e.g., `infrastructure/docker/tiler/`) and copy in the updated files.
4. **Commit the changes.**
   - Review the **Changes** tab, enter a descriptive summary, and click **Commit to main**.
5. **Push to GitHub.**
   - Click **Push origin** (top right) so the commit appears on GitHub’s `main` branch.
6. **Verify on GitHub.**
   - Visit the repository in your browser to confirm the new commit and files are present.

### Locating the tiler worker
- The ECS task image expects the Python worker at `infrastructure/docker/tiler/tiler.py`.
- If you do not see this file locally, make sure you have checked out the branch that contains the change (for example the `work` branch used for development in this repository).
- After switching branches run `git pull` (or use **Fetch origin**/**Pull** in GitHub Desktop) so your local checkout matches the remote branch before building the container image.
infrastructure/docker/tiler/tiler.py
New
