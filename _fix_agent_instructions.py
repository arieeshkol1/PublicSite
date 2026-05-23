"""
Fix agent instructions:
1. "Configure → FinOps Settings" → "Act → FinOps Healthcheck"
2. "Review in the AWS KMS console" → proper in-app guidance
3. Add tag filter context
4. Add EBS optimizer and Lambda optimizer references
"""

with open('agent-action/agent-instructions.md', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix "Configure → FinOps Settings" → "Act → FinOps Healthcheck" everywhere
content = content.replace(
    '**Configure → FinOps Settings**: Check and fix AWS billing best practices (cost allocation tags, anomaly detection, rightsizing)',
    '**Act → FinOps Healthcheck**: Check and fix AWS billing best practices (cost allocation tags, anomaly detection, Compute Optimizer enrollment)'
)
content = content.replace(
    '- **Configure → Tag Policy**: Define required tag keys for your organization',
    '- **Plan → Tag Policy**: Define required tag keys for your organization'
)
content = content.replace(
    "- FinOps settings: \"Go to Configure > FinOps Settings\"",
    "- FinOps settings/healthcheck: \"Go to Act > FinOps Healthcheck\""
)
content = content.replace(
    "- Tag policy: \"Go to Configure > Tag Policy\"",
    "- Tag policy: \"Go to Plan > Tag Policy\""
)
print("OK 1: Fixed FinOps Settings → FinOps Healthcheck")

# 2. Fix KMS console reference
content = content.replace(
    '- KMS keys → "Review in the AWS KMS console" (no in-app action available)',
    '- KMS keys → "KMS keys cost $1/key/month. Ask in Chat to list your keys and identify unused ones for deletion." (no in-app cleanup action)'
)
print("OK 2: Fixed KMS console reference")

# 3. Add tag filter context and new features to PLATFORM FEATURES
old_features_end = '- **Observe → Dashboard**: View cost trends, waste detection, rightsizing, cost by region'
new_features_end = """- **Observe → Dashboard**: View cost trends, waste detection, rightsizing, cost by region
- **Observe → Tag Filter**: Filter all dashboard widgets by a specific cost allocation tag (Tag Key → Tag Value)
- **Act → Optimize → Optimize RDS**: Analyze RDS instances for rightsizing and storage optimization
- **Act → Optimize → Optimize Lambda**: Analyze Lambda functions for memory and architecture optimization
- **Act → Optimize → Optimize EBS**: Find gp2→gp3 migration candidates and unattached volumes"""

content = content.replace(old_features_end, new_features_end)
print("OK 3: Added tag filter and new optimizer features")

# 4. Add correct navigation for new features
old_nav_end = "- Do NOT say \"Go to Plan > Tag Resources\" for S3 lifecycle policies — that is WRONG"
new_nav_end = """- Do NOT say "Go to Plan > Tag Resources" for S3 lifecycle policies — that is WRONG
- Optimize RDS: "Go to Act > Optimize > Optimize RDS Database"
- Optimize Lambda: "Go to Act > Optimize > Optimize Lambda Functions"
- Optimize EBS (gp2→gp3): "Go to Act > Optimize > Optimize EBS Volumes"
- FinOps healthcheck: "Go to Act > FinOps Healthcheck"
- Filter costs by tag: "Use the Tag Filter in the Observe tab to filter by Environment, Team, or CostCenter"
- Do NOT say "Go to Configure > FinOps Settings" — the correct path is "Go to Act > FinOps Healthcheck"
- Do NOT recommend AWS Console for ANY action — always reference SlashMyBill features"""

content = content.replace(old_nav_end, new_nav_end)
print("OK 4: Added new navigation links")

with open('agent-action/agent-instructions.md', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
