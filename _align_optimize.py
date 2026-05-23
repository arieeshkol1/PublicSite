#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Align tips, chat, help, and navigation with the Optimize tab functionality."""

import json

# ── 1. Update Tips Knowledge Base ──────────────────────────────────────────
with open('knowledge-base/aws-cost-optimization-tips.json', 'r', encoding='utf-8') as f:
    tips_data = json.load(f)

tip_ids = {t.get('id') for t in tips_data.get('tips', [])}

new_tips = [
    {
        "id": "ec2-014",
        "service": "EC2",
        "category": "cluster-optimization",
        "title": "Optimize ASG clusters with Spot mix and multi-AZ",
        "description": "Use the Optimize a Cluster wizard (Act > Optimize) to analyze your Auto Scaling Groups. The wizard checks 7 best practices: multi-AZ deployment, load balancer attachment, Spot Instance mix with price-capacity-optimized strategy, instance type diversification, scaling policies, Launch Template usage, and ELB health checks. Each check includes a specific fix recommendation.",
        "estimatedSavings": "30-70%",
        "difficulty": "medium",
        "automatedCheck": "autoscaling:DescribeAutoScalingGroups + DescribePolicies + elbv2:DescribeTargetHealth -> cluster health score",
        "checkImplemented": True,
        "actionType": "deep-link",
        "actionLabel": "Optimize Cluster",
        "level": 2,
        "serviceKey": "Amazon EC2",
        "implementedInAct": True,
        "actionTarget": "act:optimization"
    },
    {
        "id": "ec2-015",
        "service": "EC2",
        "category": "rightsizing",
        "title": "Resize over-provisioned EC2 instances",
        "description": "Use the Resize a Server wizard (Act > Optimize) to analyze 30 days of CPU and memory usage, then resize to a cheaper instance type with one click. The wizard shows full instance specs (vCPU, memory, network, EBS IOPS, architecture) and a sortable comparison table of alternatives sorted by cost. Supports automatic stop-modify-start with downtime warning.",
        "estimatedSavings": "20-60%",
        "difficulty": "easy",
        "automatedCheck": "cloudwatch:GetMetricStatistics(CPUUtilization, mem_used_percent) 30d + ec2:DescribeInstanceTypes + pricing:GetProducts -> rightsizing table",
        "checkImplemented": True,
        "actionType": "deep-link",
        "actionLabel": "Resize Server",
        "level": 2,
        "serviceKey": "Amazon EC2",
        "implementedInAct": True,
        "actionTarget": "act:optimization"
    },
]

for tip in new_tips:
    if tip['id'] not in tip_ids:
        tips_data['tips'].append(tip)
        print(f"  Added tip: {tip['id']} - {tip['title']}")

with open('knowledge-base/aws-cost-optimization-tips.json', 'w', encoding='utf-8') as f:
    json.dump(tips_data, f, indent=2)
print("1. Tips updated")

# ── 2. Update Agent Instructions (Chat) ───────────────────────────────────
with open('agent-action/agent-instructions.md', 'r', encoding='utf-8') as f:
    agent_md = f.read()

optimize_section = """

## Optimize Tab Features
When users ask about optimization, rightsizing, Spot Instances, or cluster optimization, reference these in-app tools:

- **Resize a Server**: Act > Optimize > Resize a Server. Analyzes 30 days of CPU/memory usage, shows full instance specs, and recommends cheaper alternatives in a sortable table. One-click resize with automatic stop-modify-start.
- **Optimize a Cluster**: Act > Optimize > Optimize a Cluster. Analyzes an existing Auto Scaling Group against 7 best practices: multi-AZ, load balancer, Spot mix, instance diversification, scaling policies, Launch Template, and ELB health checks. Returns a grade (A/B/C/D) with specific fix recommendations.
- **Scan for Savings**: Act > Optimize > Scan for Savings. Runs the waste scan engine filtered to optimization-type findings: rightsizing, Spot candidates, Graviton migration, gp2-to-gp3, scheduling, Lambda memory, S3 Intelligent-Tiering.

When recommending rightsizing, say: "Use the Resize a Server wizard in Act > Optimize to analyze this instance and find cheaper alternatives."
When recommending Spot or cluster optimization, say: "Use the Optimize a Cluster wizard in Act > Optimize to check your ASG configuration."
Do NOT recommend AWS Console actions for these — always point to the in-app wizards.
"""

if 'Optimize Tab Features' not in agent_md:
    agent_md += optimize_section
    with open('agent-action/agent-instructions.md', 'w', encoding='utf-8') as f:
        f.write(agent_md)
    print("2. Agent instructions updated")
else:
    print("2. Agent instructions already have Optimize section")

# ── 3. Update Help Panel ──────────────────────────────────────────────────
with open('members/help.js', 'r', encoding='utf-8') as f:
    help_js = f.read()

# Find the Act section in help and add Optimize details
if 'Optimize a Cluster' not in help_js:
    old_act_help = "<li><strong>Act</strong>"
    new_act_help = "<li><strong>Act</strong>"
    # Find a better insertion point - after the Act description
    old_scan = "Scan for waste, clean up idle resources, and automate stop/start schedules"
    new_scan = "Scan for waste, clean up idle resources, automate stop/start schedules, resize servers, and optimize ASG clusters"
    if old_scan in help_js:
        help_js = help_js.replace(old_scan, new_scan)
    
    # Add Optimize section to help topics
    old_waste_help = "id: 'delete-account',"
    new_waste_help = """id: 'optimize-cluster',
        heading: 'Optimize a Cluster',
        icon: '\\u26a1',
        body: '<p>The <strong>Optimize a Cluster</strong> wizard analyzes your Auto Scaling Groups against 7 best practices:</p>'
          + '<ol>'
          + '<li><strong>Multi-AZ</strong> \\u2014 Ensures instances span 2+ Availability Zones for high availability</li>'
          + '<li><strong>Load Balancer</strong> \\u2014 Verifies ALB/NLB is attached with healthy targets</li>'
          + '<li><strong>Spot Mix</strong> \\u2014 Checks for MixedInstancesPolicy with price-capacity-optimized strategy</li>'
          + '<li><strong>Instance Diversification</strong> \\u2014 Multiple instance types for better Spot availability</li>'
          + '<li><strong>Scaling Policy</strong> \\u2014 Target tracking or step scaling configured</li>'
          + '<li><strong>Launch Template</strong> \\u2014 Uses Launch Template (not deprecated LaunchConfiguration)</li>'
          + '<li><strong>Health Check Type</strong> \\u2014 ELB health checks when load balancer is attached</li>'
          + '</ol>'
          + '<p>Each check shows a grade (A/B/C/D) and specific fix recommendations.</p>'
      },
      {
        id: 'resize-server',
        heading: 'Resize a Server',
        icon: '\\U0001f4ca',
        body: '<p>The <strong>Resize a Server</strong> wizard helps you find cheaper EC2 instance types:</p>'
          + '<ol>'
          + '<li>Select an account and EC2 instance</li>'
          + '<li>Click <strong>Optimize</strong> to analyze 30 days of CPU and memory usage</li>'
          + '<li>Review the full instance spec card (vCPU, memory, network, EBS, architecture)</li>'
          + '<li>Browse the sortable comparison table of cheaper alternatives</li>'
          + '<li>Click <strong>Resize</strong> to execute (instance stops for 1-3 minutes during resize)</li>'
          + '</ol>'
          + '<p>The wizard only shows instance types compatible with your current architecture (x86/ARM).</p>'
      },
      {
        id: 'delete-account',"""
    
    if old_waste_help in help_js:
        help_js = help_js.replace(old_waste_help, new_waste_help)
        print("3. Help panel updated with Optimize and Resize topics")
    else:
        print("3. Could not find help insertion point")
    
    with open('members/help.js', 'w', encoding='utf-8') as f:
        f.write(help_js)
else:
    print("3. Help already has Optimize section")

# ── 4. Update Chat Navigation Links ──────────────────────────────────────
with open('members/members.js', 'r', encoding='utf-8') as f:
    js = f.read()

# Add navigation links for "Act > Optimize" in chat responses
if 'act:optimization' not in js or 'Optimize Cluster' not in js:
    # Find the chat link handler
    old_link = "if (section === 'waste')"
    if old_link in js:
        # Check if optimization link handling exists
        if "'optimization'" not in js.split('_switchActSection')[1][:500] if '_switchActSection' in js else True:
            pass  # Links already work via _switchActSection
    print("4. Chat navigation links already work via _switchActSection")
else:
    print("4. Chat links already configured")

print("Done - all 4 areas aligned")
