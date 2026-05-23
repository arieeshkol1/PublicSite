#!/usr/bin/env python3
"""Fix: Add correct navigation links for S3 actions in agent instructions."""

with open('agent-action/agent-instructions.md', 'r', encoding='utf-8') as f:
    content = f.read()

nav_section = """

## CORRECT NAVIGATION LINKS (use these exact paths)
- Lifecycle policies for S3 buckets: "Go to Act > Waste Cleanup" (S3 card has "Apply Lifecycle" button)
- Tag resources: "Go to Plan > Tag Resources"
- Delete unused buckets: "Go to Act > Waste Cleanup" (S3 card has "Browse" then "Delete")
- Resize EC2 instances: "Go to Act > Optimize > Resize a Server"
- Optimize ASG clusters: "Go to Act > Optimize > Optimize a Cluster"
- Create budgets: "Go to Plan > Budget"
- Create schedules: "Go to Act > Scheduler"
- FinOps settings: "Go to Configure > FinOps Settings"
- Tag policy: "Go to Configure > Tag Policy"
- Do NOT say "Go to Plan > Tag Resources" for S3 lifecycle policies — that is WRONG
"""

if 'CORRECT NAVIGATION LINKS' not in content:
    content += nav_section
    with open('agent-action/agent-instructions.md', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Navigation links section added")
else:
    print("Already present")
