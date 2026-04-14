"""
Patch aws-cost-optimization-tips.json to add:
  - checkImplemented: bool  (true = registry has a check function)
  - actionType: "delete"|"modify"|"advisory"|"deep-link"|"pending"
  - actionLabel: str  (button label in Act tab)
  - level: 1|2|3  (hygiene / optimization / architecture)
  - serviceKey: str  (normalized service name for presence check)
"""
import json

TIPS_FILE = "knowledge-base/aws-cost-optimization-tips.json"

# Map tip.id → (checkImplemented, actionType, actionLabel, level, serviceKey)
# serviceKey must match what CE returns in cost_by_service (normalized)
PATCH = {
    # ── Level 1: Resource Hygiene ──────────────────────────────────────────
    "ebs-004":        (True,  "delete",    "Delete Volumes",      1, "EC2 - Other"),
    "ebs-002":        (True,  "delete",    "Delete Snapshots",    1, "EC2 - Other"),
    "ebs-003":        (True,  "advisory",  "Archive Snapshots",   1, "EC2 - Other"),
    "vpc-001":        (True,  "delete",    "Release EIPs",        1, "Amazon Virtual Private Cloud"),
    "elb-001":        (True,  "delete",    "Delete Idle LBs",     1, "Amazon Elastic Load Balancing"),
    "s3-002":         (True,  "modify",    "Apply Lifecycle",     1, "Amazon Simple Storage Service"),
    "s3-003":         (True,  "modify",    "Fix Multipart",       1, "Amazon Simple Storage Service"),
    "kms-001":        (True,  "advisory",  "Audit KMS Keys",      1, "AWS Key Management Service"),
    "general-004":    (True,  "advisory",  "Audit Resources",     1, "General"),

    # ── Level 2: Cost Optimization ─────────────────────────────────────────
    "ec2-001":        (True,  "advisory",  "View Rightsizing",    2, "Amazon EC2"),
    "ec2-004":        (True,  "advisory",  "Schedule Instances",  2, "Amazon EC2"),
    "ec2-011":        (True,  "advisory",  "Setup Scheduler",     2, "Amazon EC2"),
    "ec2-006":        (True,  "advisory",  "View Graviton Opts",  2, "Amazon EC2"),
    "ec2-003":        (True,  "deep-link", "View Spot Savings",   2, "Amazon EC2"),
    "ec2-009":        (True,  "deep-link", "Configure Spot Fleet", 2, "Amazon EC2"),
    "ec2-002":        (True,  "advisory",  "Analyze Savings Plans",2,"Amazon EC2"),
    "ec2-010":        (True,  "advisory",  "Match Instance Type", 2, "Amazon EC2"),
    "ebs-001":        (True,  "advisory",  "Migrate gp2→gp3",     2, "EC2 - Other"),
    "ebs-005":        (True,  "advisory",  "Setup DLM Policy",    2, "EC2 - Other"),
    "s3-001":         (True,  "modify",    "Enable IT",           2, "Amazon Simple Storage Service"),
    "s3-004":         (True,  "advisory",  "Manage Versions",     2, "Amazon Simple Storage Service"),
    "s3-005":         (True,  "advisory",  "Enable Storage Lens", 2, "Amazon Simple Storage Service"),
    "rds-001":        (True,  "advisory",  "View Rightsizing",    2, "Amazon Relational Database Service"),
    "rds-002":        (True,  "advisory",  "Analyze RDS RIs",     2, "Amazon Relational Database Service"),
    "rds-003":        (True,  "advisory",  "Evaluate Serverless", 2, "Amazon Relational Database Service"),
    "rds-004":        (True,  "advisory",  "Optimize Storage",    2, "Amazon Relational Database Service"),
    "rds-005":        (True,  "advisory",  "Add Read Replica",    2, "Amazon Relational Database Service"),
    "rds-006":        (True,  "advisory",  "Plan DB Migration",   2, "Amazon Relational Database Service"),
    "lambda-001":     (True,  "advisory",  "Tune Memory",         2, "AWS Lambda"),
    "lambda-002":     (True,  "advisory",  "Enable ARM64",        2, "AWS Lambda"),
    "lambda-003":     (True,  "advisory",  "Review Concurrency",  2, "AWS Lambda"),
    "nat-001":        (True,  "advisory",  "Add VPC Endpoints",   2, "Amazon Virtual Private Cloud"),
    "nat-002":        (True,  "advisory",  "Consolidate NATs",    2, "Amazon Virtual Private Cloud"),
    "kms-002":        (True,  "advisory",  "Enable Key Caching",  2, "AWS Key Management Service"),
    "elb-002":        (True,  "advisory",  "Right-size LB Type",  2, "Amazon Elastic Load Balancing"),
    "elb-003":        (True,  "advisory",  "Add CloudFront",      2, "Amazon Elastic Load Balancing"),
    "ecs-001":        (True,  "advisory",  "Right-size Tasks",    2, "Amazon Elastic Container Service"),
    "ecs-002":        (True,  "advisory",  "Enable Auto Scaling", 2, "Amazon Elastic Container Service"),
    "dynamodb-001":   (True,  "advisory",  "Switch Capacity Mode",2, "Amazon DynamoDB"),
    "dynamodb-002":   (True,  "advisory",  "Buy Reserved Cap.",   2, "Amazon DynamoDB"),
    "elasticache-001":(True,  "advisory",  "Right-size Nodes",    2, "Amazon ElastiCache"),
    "elasticache-002":(True,  "advisory",  "Buy Reserved Nodes",  2, "Amazon ElastiCache"),
    "efs-001":        (True,  "advisory",  "Optimize EFS",        2, "Amazon Elastic File System"),
    "data-transfer-001":(True,"advisory",  "Reduce Cross-Region", 2, "EC2 - Other"),
    "data-transfer-002":(True,"advisory",  "Use CloudFront",      2, "EC2 - Other"),
    "data-transfer-003":(True,"advisory",  "Use AZ Affinity",     2, "EC2 - Other"),
    "data-transfer-004":(True,"advisory",  "Compress Transfers",  2, "EC2 - Other"),
    "cloudfront-001": (True,  "advisory",  "Improve Cache Ratio", 2, "Amazon CloudFront"),
    "cloudfront-002": (True,  "advisory",  "Buy CF Bundle",       2, "Amazon CloudFront"),
    "general-001":    (True,  "advisory",  "Enable Cost Explorer",2, "General"),
    "general-002":    (True,  "advisory",  "Create Budgets",      2, "General"),
    "general-003":    (True,  "advisory",  "Enable Anomaly Det.", 2, "General"),
    "general-005":    (True,  "advisory",  "Tag Resources",       2, "General"),
    "general-011":    (True,  "advisory",  "Automate Tagging",    2, "General"),
    "general-012":    (True,  "advisory",  "Use Opt. Hub",        2, "General"),
    "general-017":    (True,  "advisory",  "Create Billing Alarm",2, "General"),
    "general-018":    (False, "advisory",  "Contact AWS",         2, "General"),

    # ── Level 3: Architecture / Commitment ────────────────────────────────
    "ec2-005":        (True,  "advisory",  "Setup Auto Scaling",  3, "Amazon EC2"),
    "ec2-007":        (True,  "advisory",  "Compare Regions",     3, "Amazon EC2"),
    "ec2-008":        (True,  "advisory",  "Tune ASG Policies",   3, "Amazon EC2"),
    "ec2-012":        (True,  "advisory",  "Enable Hibernation",  3, "Amazon EC2"),
    "general-006":    (True,  "deep-link", "Buy Compute SP",      3, "General"),
    "general-007":    (True,  "deep-link", "Buy EC2 Instance SP", 3, "General"),
    "general-008":    (True,  "deep-link", "Buy Database SP",     3, "General"),
    "general-009":    (True,  "deep-link", "Buy Standard RIs",    3, "General"),
    "general-010":    (True,  "deep-link", "Buy Convertible RIs", 3, "General"),
    "general-013":    (True,  "advisory",  "Setup Chargeback",    3, "General"),
    "general-014":    (True,  "deep-link", "Sell on RI Mktplace", 3, "General"),
    "general-015":    (True,  "advisory",  "Migrate Serverless",  3, "General"),
    "general-016":    (True,  "advisory",  "Evaluate Lightsail",  3, "General"),
    "eks-001":        (True,  "advisory",  "Right-size EKS",      3, "Amazon Elastic Kubernetes Service"),
    "eks-002":        (True,  "advisory",  "Enable Karpenter",    3, "Amazon Elastic Kubernetes Service"),
}

# CE service name → normalized key used in active_services detection
# These must match what CE returns in GroupBy SERVICE dimension
SERVICE_CE_NAMES = {
    "Amazon EC2":                                    "Amazon EC2",
    "EC2 - Other":                                   "EC2 - Other",
    "Amazon Simple Storage Service":                 "Amazon Simple Storage Service",
    "Amazon Relational Database Service":            "Amazon Relational Database Service",
    "AWS Lambda":                                    "AWS Lambda",
    "Amazon Virtual Private Cloud":                  "Amazon Virtual Private Cloud",
    "Amazon Elastic Load Balancing":                 "Amazon Elastic Load Balancing",
    "AWS Key Management Service":                    "AWS Key Management Service",
    "Amazon Elastic Container Service":              "Amazon Elastic Container Service",
    "Amazon Elastic Kubernetes Service":             "Amazon Elastic Kubernetes Service",
    "Amazon ElastiCache":                            "Amazon ElastiCache",
    "Amazon DynamoDB":                               "Amazon DynamoDB",
    "Amazon CloudFront":                             "Amazon CloudFront",
    "Amazon Elastic File System":                    "Amazon Elastic File System",
    "General":                                       "General",  # always run
}

with open(TIPS_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

patched = 0
for tip in data["tips"]:
    tid = tip["id"]
    if tid in PATCH:
        impl, atype, alabel, level, skey = PATCH[tid]
        tip["checkImplemented"] = impl
        tip["actionType"] = atype
        tip["actionLabel"] = alabel
        tip["level"] = level
        tip["serviceKey"] = skey
        patched += 1
    else:
        # Default: pending placeholder
        tip.setdefault("checkImplemented", False)
        tip.setdefault("actionType", "pending")
        tip.setdefault("actionLabel", "Coming Soon")
        tip.setdefault("level", 2)
        tip.setdefault("serviceKey", tip.get("service", "General"))

with open(TIPS_FILE, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Patched {patched}/{len(data['tips'])} tips")
print(f"Unpatched (pending): {len(data['tips']) - patched}")
