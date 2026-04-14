#!/usr/bin/env python3
"""Add new scheduling/stop-start tips based on the guidelines."""

import json

with open('knowledge-base/aws-cost-optimization-tips.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Check existing tip IDs
existing_ids = {t['id'] for t in data['tips']}

new_tips = [
    {
        "id": "rds-007",
        "service": "RDS",
        "category": "scheduling",
        "title": "Schedule non-production RDS & Aurora databases",
        "description": "Stop non-production RDS and Aurora databases during nights and weekends. RDS databases are often expensive idle resources. Note: RDS has a maximum stopped duration of 7 days before auto-restart. Use EventBridge + Lambda to re-stop if needed.",
        "estimatedSavings": "40-70%",
        "difficulty": "easy",
        "automatedCheck": "rds:DescribeDBInstances → check tags for Environment=dev/test/staging. If running 24/7 with low connections → recommend stop schedule. rds_cpu_metrics + rds_conn_14d for idle detection.",
        "checkImplemented": True,
        "actionType": "advisory",
        "actionLabel": "Schedule RDS Stop",
        "level": 2,
        "serviceKey": "Amazon Relational Database Service",
        "implementedInAct": False
    },
    {
        "id": "ec2-013",
        "service": "EC2",
        "category": "scheduling",
        "title": "Scale Auto Scaling Groups to zero after hours",
        "description": "For development environments using Auto Scaling Groups, update the desired, minimum, and maximum capacity to 0 at night and reset them in the morning. This eliminates all compute costs during idle periods while preserving the ASG configuration.",
        "estimatedSavings": "40-70%",
        "difficulty": "easy",
        "automatedCheck": "autoscaling:DescribeAutoScalingGroups → check tags for Environment=dev/test. If running 24/7 with non-prod tags → recommend scaling to 0 after hours.",
        "checkImplemented": True,
        "actionType": "advisory",
        "actionLabel": "Scale ASG to Zero",
        "level": 2,
        "serviceKey": "Amazon EC2",
        "implementedInAct": False
    },
    {
        "id": "eks-003",
        "service": "EKS",
        "category": "scheduling",
        "title": "Scale EKS node groups to zero after hours",
        "description": "Scale non-production EKS node groups down to zero instances during nights and weekends to stop paying for worker nodes. Use EventBridge + Lambda or the AWS Instance Scheduler to automate the scaling.",
        "estimatedSavings": "40-70%",
        "difficulty": "medium",
        "automatedCheck": "eks:ListNodegroups + eks:DescribeNodegroup → check scaling config. If min > 0 and non-prod tags → recommend scaling to 0 after hours.",
        "checkImplemented": True,
        "actionType": "advisory",
        "actionLabel": "Scale EKS Nodes",
        "level": 2,
        "serviceKey": "Amazon Elastic Kubernetes Service",
        "implementedInAct": False
    },
    {
        "id": "sagemaker-001",
        "service": "SageMaker",
        "category": "scheduling",
        "title": "Stop idle SageMaker notebook instances",
        "description": "SageMaker notebook instances run on compute instances that charge by the hour. Stop them when not in use. Use lifecycle configurations to auto-stop notebooks after a period of inactivity (e.g., 1 hour idle).",
        "estimatedSavings": "40-80%",
        "difficulty": "easy",
        "automatedCheck": "sagemaker:ListNotebookInstances → check status. If InService with no recent activity → recommend stop or auto-stop lifecycle config.",
        "checkImplemented": True,
        "actionType": "advisory",
        "actionLabel": "Stop Notebooks",
        "level": 2,
        "serviceKey": "Amazon SageMaker",
        "implementedInAct": False
    },
    {
        "id": "redshift-001",
        "service": "Redshift",
        "category": "scheduling",
        "title": "Pause non-production Redshift clusters",
        "description": "Pause non-production Redshift clusters during nights and weekends to eliminate high hourly compute charges. Paused clusters only incur storage costs. Use the Redshift console or API to schedule pause/resume cycles.",
        "estimatedSavings": "40-70%",
        "difficulty": "easy",
        "automatedCheck": "redshift:DescribeClusters → check tags for Environment=dev/test. If running 24/7 → recommend pause schedule.",
        "checkImplemented": True,
        "actionType": "advisory",
        "actionLabel": "Pause Cluster",
        "level": 2,
        "serviceKey": "Amazon Redshift",
        "implementedInAct": False
    },
    {
        "id": "workspaces-001",
        "service": "WorkSpaces",
        "category": "scheduling",
        "title": "Enable auto-stop mode for WorkSpaces",
        "description": "Enable auto-stop mode on Amazon WorkSpaces virtual desktops to automatically suspend them when users are not active. This switches from always-on billing to usage-based billing, saving costs during nights and weekends.",
        "estimatedSavings": "30-60%",
        "difficulty": "easy",
        "automatedCheck": "workspaces:DescribeWorkspaces → check RunningMode. If ALWAYS_ON → recommend AUTO_STOP for non-critical users.",
        "checkImplemented": True,
        "actionType": "advisory",
        "actionLabel": "Enable Auto-Stop",
        "level": 2,
        "serviceKey": "Amazon WorkSpaces",
        "implementedInAct": False
    },
    {
        "id": "elb-003",
        "service": "ELB",
        "category": "scheduling",
        "title": "Tear down non-production load balancers after hours",
        "description": "Non-production ALBs and NLBs incur persistent hourly fees (~$16-22/month each) even with zero traffic. Tear them down after hours and rebuild with CI/CD in the morning. Use Infrastructure as Code (CloudFormation/Terraform) to make this repeatable.",
        "estimatedSavings": "40-70%",
        "difficulty": "medium",
        "automatedCheck": "elbv2:DescribeLoadBalancers → check tags for Environment=dev/test. If non-prod with low traffic → recommend teardown schedule.",
        "checkImplemented": True,
        "actionType": "advisory",
        "actionLabel": "Schedule LB Teardown",
        "level": 2,
        "serviceKey": "Amazon Elastic Load Balancing",
        "implementedInAct": False
    },
    {
        "id": "general-015",
        "service": "General",
        "category": "scheduling",
        "title": "Use tagging to automate start/stop schedules",
        "description": "Tag resources with a Schedule tag (e.g., Schedule=office-hours) and use AWS Instance Scheduler to automatically start/stop based on the tag value. This enables different schedules for different environments without manual intervention.",
        "estimatedSavings": "40-70%",
        "difficulty": "easy",
        "automatedCheck": "resourcegroupstaggingapi:GetResources → check for Schedule tag. Resources without Schedule tag in non-prod environments → recommend adding Schedule tag.",
        "checkImplemented": True,
        "actionType": "advisory",
        "actionLabel": "Add Schedule Tags",
        "level": 2,
        "serviceKey": "General",
        "implementedInAct": False
    }
]

# Update existing ec2-004 with richer description
for tip in data['tips']:
    if tip['id'] == 'ec2-004':
        tip['description'] = "Stop dev/test/staging EC2 instances outside business hours. Use AWS Instance Scheduler or Lambda functions with EventBridge to automate start/stop schedules. A dev environment running only during office hours (10h/day, 5d/week) saves ~70%. Remember: stopped instances still incur EBS storage charges — terminate if data is not needed."
        print(f"  Updated: {tip['id']} - {tip['title']}")
    if tip['id'] == 'ec2-011':
        tip['description'] = "Deploy the AWS Instance Scheduler solution to automatically start and stop EC2 instances and RDS databases on a schedule. Supports multiple schedules, time zones, and tag-based targeting. A dev environment used only during office hours (10hrs/day, 5 days/week) saves ~70% by shutting down the remaining 118 hours per week."
        print(f"  Updated: {tip['id']} - {tip['title']}")

# Add new tips (skip if already exists)
added = 0
for tip in new_tips:
    if tip['id'] not in existing_ids:
        data['tips'].append(tip)
        added += 1
        print(f"  Added: {tip['id']} - {tip['title']}")
    else:
        print(f"  Skipped (exists): {tip['id']}")

with open('knowledge-base/aws-cost-optimization-tips.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"\nDone! Added {added} new tips. Total: {len(data['tips'])}")
