"""Cross-account role Terraform template and module generation.

Generates Terraform HCL for provisioning the SlashMyBill cross-account IAM role
in a customer AWS account. Mirrors the CloudFormation template behavior including
trust policy with ExternalId (SHA-256 of member email), ReadOnlyAccess managed
policy, and inline billing/action permissions.
"""

from __future__ import annotations

import hashlib
import io
import zipfile

from hcl_generator.core import (
    HclBlock,
    HclDocument,
    HclRawExpression,
    render_provider_block,
)


# Inline policy actions for billing and action permissions
_BILLING_ACTIONS = [
    # Cost Explorer – core FinOps data
    "ce:GetCostAndUsage",
    "ce:GetCostForecast",
    "ce:GetReservationUtilization",
    "ce:GetReservationCoverage",
    "ce:GetSavingsPlansUtilization",
    "ce:GetSavingsPlansCoverage",
    "ce:GetSavingsPlansPurchaseRecommendation",
    "ce:GetReservationPurchaseRecommendation",
    "ce:GetRightsizingRecommendation",
    "ce:GetCostCategories",
    "ce:GetDimensionValues",
    "ce:GetTags",
    "ce:ListCostAllocationTags",
    "ce:GetApproximateUsageRecords",
    "ce:UpdatePreferences",
    "ce:GetPreferences",
    "ce:GetCostAndUsageWithResources",
    # AWS Invoicing API
    "invoicing:ListInvoiceSummaries",
    # Savings Plans
    "savingsplans:DescribeSavingsPlans",
    # Budgets
    "budgets:ViewBudget",
    "budgets:DescribeBudgets",
    "budgets:DescribeBudgetActionsForAccount",
    "budgets:*",
    # Cost Optimization Hub
    "cost-optimization-hub:ListRecommendations",
    "cost-optimization-hub:GetRecommendation",
    # Billing / CUR
    "cur:DescribeReportDefinitions",
    "cur:GetClassicReport",
    "cur:GetUsageReport",
    "billing:GetBillingData",
    "billing:GetBillingDetails",
    # Trusted Advisor
    "support:DescribeTrustedAdvisorChecks",
    "support:DescribeTrustedAdvisorCheckResult",
    # CloudFormation self-management
    "cloudformation:DeleteStack",
    "cloudformation:UpdateStack",
    "cloudformation:CreateStack",
    "cloudformation:DescribeStacks",
    "cloudformation:DescribeStackResources",
    "cloudformation:GetTemplate",
    # IAM role management
    "iam:GetRole",
    "iam:ListRolePolicies",
    "iam:ListAttachedRolePolicies",
    "iam:DeleteRolePolicy",
    "iam:DetachRolePolicy",
    "iam:DeleteRole",
    "iam:CreateRole",
    "iam:PutRolePolicy",
    "iam:AttachRolePolicy",
    "iam:TagRole",
    "iam:PassRole",
    # Level 1 cleanup actions
    "ec2:ReleaseAddress",
    "ec2:DeleteVolume",
    "elasticloadbalancing:DeleteLoadBalancer",
    "s3:PutBucketLifecycleConfiguration",
    "s3:GetBucketLifecycleConfiguration",
    "s3:GetBucketLocation",
    "s3:ListBucketMultipartUploads",
    "s3:AbortMultipartUpload",
    "s3:ListBucket",
    "s3:GetObject",
    "s3:HeadObject",
    "s3:DeleteObject",
    "s3:DeleteObjects",
    # Idle EC2 / RDS / Snapshot cleanup
    "ec2:StopInstances",
    "ec2:TerminateInstances",
    "ec2:DescribeInstanceAttribute",
    "ec2:ModifyInstanceAttribute",
    "autoscaling:DescribeAutoScalingInstances",
    "autoscaling:DetachInstances",
    "autoscaling:UpdateAutoScalingGroup",
    "ec2:DeleteSnapshot",
    "rds:DeleteDBInstance",
    "rds:DescribeDBInstances",
    # Resource tagging
    "tag:GetResources",
    "tag:GetTagKeys",
    "tag:GetTagValues",
    "tag:TagResources",
    "tag:UntagResources",
    "ec2:CreateTags",
    "ec2:DeleteTags",
    "rds:AddTagsToResource",
    "rds:RemoveTagsFromResource",
    "s3:PutBucketTagging",
    "s3:GetBucketTagging",
    "s3:PutObjectTagging",
    "s3:DeleteObjectTagging",
    "elasticloadbalancing:AddTags",
    "elasticloadbalancing:RemoveTags",
    "sqs:TagQueue",
    "sqs:UntagQueue",
    "logs:TagLogGroup",
    "logs:UntagLogGroup",
    "dynamodb:TagResource",
    "dynamodb:UntagResource",
    "lambda:TagResource",
    "lambda:UntagResource",
    "sns:TagResource",
    "sns:UntagResource",
    "kms:TagResource",
    "kms:UntagResource",
    "es:AddTags",
    "es:RemoveTags",
    "elasticache:AddTagsToResource",
    "elasticache:RemoveTagsFromResource",
    "ecs:TagResource",
    "ecs:UntagResource",
    "eks:TagResource",
    "eks:UntagResource",
    "secretsmanager:TagResource",
    "secretsmanager:UntagResource",
    "cloudwatch:TagResource",
    "cloudwatch:UntagResource",
    "kinesis:AddTagsToStream",
    "kinesis:RemoveTagsFromStream",
    "redshift:CreateTags",
    "redshift:DeleteTags",
    "glue:TagResource",
    "glue:UntagResource",
    "stepfunctions:TagResource",
    "stepfunctions:UntagResource",
    "sagemaker:AddTags",
    "sagemaker:DeleteTags",
    # Scheduler write actions
    "ec2:StartInstances",
    "rds:StopDBInstance",
    "rds:StartDBInstance",
    "eks:UpdateNodegroupConfig",
    "eks:DescribeNodegroup",
    "sagemaker:StopNotebookInstance",
    "sagemaker:StartNotebookInstance",
    "redshift:PauseCluster",
    "redshift:ResumeCluster",
    "workspaces:ModifyWorkspaceProperties",
    "ec2:ModifyVolume",
    # FinOps Settings Healthcheck
    "ce:GetAnomalyMonitors",
    "ce:GetAnomalySubscriptions",
    "ce:ListCostAllocationTagBackfillHistory",
    "compute-optimizer:GetEnrollmentStatus",
    "organizations:DescribeOrganization",
    "ce:UpdateCostAllocationTagsStatus",
    "ce:CreateAnomalyMonitor",
    "ce:CreateAnomalySubscription",
    "ce:StartCostAllocationTagBackfill",
    "compute-optimizer:UpdateEnrollmentStatus",
    # RI Marketplace
    "ec2:DescribeReservedInstancesOfferings",
]


def _compute_external_id(member_email: str) -> str:
    """Compute the ExternalId as SHA-256 hash of the member email.

    Args:
        member_email: The member's email address.

    Returns:
        Hexadecimal SHA-256 hash string.
    """
    return hashlib.sha256(member_email.encode("utf-8")).hexdigest()


def generate_cross_account_template(
    account_id: str,
    member_email: str,
    platform_account_id: str = "991105135552",
) -> HclDocument:
    """Generate single-file cross-account role Terraform template.

    Produces a complete .tf file containing:
    - terraform { required_providers {} } block with AWS provider >= 5.0
    - variable blocks for account_id and platform_account_id
    - provider "aws" block with region and assume_role
    - aws_iam_role resource with trust policy (ExternalId = SHA-256 of email)
    - aws_iam_role_policy_attachment for ReadOnlyAccess
    - aws_iam_role_policy for inline billing/action permissions
    - output block exposing the role ARN

    Args:
        account_id: The customer AWS account ID (12 digits).
        member_email: The member's email address (used for ExternalId).
        platform_account_id: The SlashMyBill platform account ID.

    Returns:
        An HclDocument representing the complete Terraform template.
    """
    external_id = _compute_external_id(member_email)
    role_name = f"SlashMyBill-{account_id}"

    blocks = []

    # 1. terraform { required_providers { aws { ... } } }
    aws_provider_config = HclBlock(
        block_type="aws",
        attributes={
            "source": "hashicorp/aws",
            "version": ">= 5.0",
        },
    )
    required_providers = HclBlock(
        block_type="required_providers",
        nested_blocks=[aws_provider_config],
    )
    terraform_block = HclBlock(
        block_type="terraform",
        nested_blocks=[required_providers],
    )
    blocks.append(terraform_block)

    # 2. variable "account_id"
    var_account_id = HclBlock(
        block_type="variable",
        labels=["account_id"],
        attributes={
            "type": HclRawExpression("string"),
            "description": "The AWS account ID where the role will be created",
            "default": account_id,
        },
    )
    blocks.append(var_account_id)

    # 3. variable "platform_account_id"
    var_platform_account_id = HclBlock(
        block_type="variable",
        labels=["platform_account_id"],
        attributes={
            "type": HclRawExpression("string"),
            "description": "The SlashMyBill platform AWS account ID",
            "default": platform_account_id,
        },
    )
    blocks.append(var_platform_account_id)

    # 4. provider "aws" with assume_role
    provider_block = render_provider_block(
        region="us-east-1",
        account_id=account_id,
        role_name="SlashMyBill",
    )
    blocks.append(provider_block)

    # 5. aws_iam_role resource with trust policy
    # Build the assume_role_policy as a JSON-encoded string using jsonencode()
    assume_role_policy_expr = HclRawExpression(
        "jsonencode({\n"
        '    Version = "2012-10-17"\n'
        "    Statement = [\n"
        "      {\n"
        '        Effect = "Allow"\n'
        "        Principal = {\n"
        f'          AWS = "arn:aws:iam::${{var.platform_account_id}}:root"\n'
        "        }\n"
        '        Action = "sts:AssumeRole"\n'
        "        Condition = {\n"
        "          StringEquals = {\n"
        f'            "sts:ExternalId" = "{external_id}"\n'
        "          }\n"
        "        }\n"
        "      }\n"
        "    ]\n"
        "  })"
    )

    iam_role = HclBlock(
        block_type="resource",
        labels=["aws_iam_role", "slashmybill"],
        attributes={
            "name": role_name,
            "assume_role_policy": assume_role_policy_expr,
        },
    )
    blocks.append(iam_role)

    # 6. aws_iam_role_policy_attachment for ReadOnlyAccess
    policy_attachment = HclBlock(
        block_type="resource",
        labels=["aws_iam_role_policy_attachment", "readonly"],
        attributes={
            "role": HclRawExpression("aws_iam_role.slashmybill.name"),
            "policy_arn": "arn:aws:iam::aws:policy/ReadOnlyAccess",
        },
    )
    blocks.append(policy_attachment)

    # 7. aws_iam_role_policy for inline billing/action permissions
    inline_policy_expr = HclRawExpression(
        "jsonencode({\n"
        '    Version = "2012-10-17"\n'
        "    Statement = [\n"
        "      {\n"
        '        Effect = "Allow"\n'
        "        Action = " + _format_actions_list() + "\n"
        '        Resource = "*"\n'
        "      }\n"
        "    ]\n"
        "  })"
    )

    inline_policy = HclBlock(
        block_type="resource",
        labels=["aws_iam_role_policy", "billing_access"],
        attributes={
            "name": "SlashMyBillBillingAccess",
            "role": HclRawExpression("aws_iam_role.slashmybill.id"),
            "policy": inline_policy_expr,
        },
    )
    blocks.append(inline_policy)

    # 8. output "role_arn"
    output_block = HclBlock(
        block_type="output",
        labels=["role_arn"],
        attributes={
            "description": "ARN of the SlashMyBill cross-account role",
            "value": HclRawExpression("aws_iam_role.slashmybill.arn"),
        },
    )
    blocks.append(output_block)

    header = (
        f"Generated by SlashMyBill - Terraform Cross-Account Role Template\n"
        f"Account: {account_id}\n"
        f"WARNING: Review this file before applying with terraform apply"
    )

    return HclDocument(blocks=blocks, header_comment=header)


def _format_actions_list() -> str:
    """Format the billing actions list as a Terraform list expression.

    Returns:
        A multi-line string representing the actions as a Terraform list.
    """
    lines = ["["]
    for action in _BILLING_ACTIONS:
        lines.append(f'          "{action}",')
    lines.append("        ]")
    return "\n".join(lines)


def generate_cross_account_module(
    account_id: str,
    member_email: str,
    platform_account_id: str = "991105135552",
) -> bytes:
    """Generate ZIP archive containing the Terraform module for cross-account role.

    The module contains:
    - main.tf: IAM role resource, policy attachment, and inline policy
    - variables.tf: Input variables (account_id, platform_account_id, external_id)
    - outputs.tf: Exported role_arn and role_name
    - README.md: Usage examples

    Args:
        account_id: The customer AWS account ID (12 digits).
        member_email: The member's email address (used for external_id default).
        platform_account_id: The SlashMyBill platform account ID.

    Returns:
        Bytes of the ZIP archive containing the module files.
    """
    external_id = _compute_external_id(member_email)

    main_tf = _generate_module_main_tf(platform_account_id)
    variables_tf = _generate_module_variables_tf(platform_account_id, external_id)
    outputs_tf = _generate_module_outputs_tf()
    readme_md = _generate_module_readme(account_id, external_id)

    # Create ZIP archive in memory
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("main.tf", main_tf)
        zf.writestr("variables.tf", variables_tf)
        zf.writestr("outputs.tf", outputs_tf)
        zf.writestr("README.md", readme_md)

    return buffer.getvalue()


def _generate_module_main_tf(platform_account_id: str) -> str:
    """Generate main.tf for the cross-account module.

    Contains:
    - terraform { required_providers {} } block
    - aws_iam_role resource with trust policy using var.external_id
    - aws_iam_role_policy_attachment for ReadOnlyAccess
    - aws_iam_role_policy for inline billing/action permissions
    """
    blocks = []

    # terraform { required_providers { aws { ... } } }
    aws_provider_config = HclBlock(
        block_type="aws",
        attributes={
            "source": "hashicorp/aws",
            "version": ">= 5.0",
        },
    )
    required_providers = HclBlock(
        block_type="required_providers",
        nested_blocks=[aws_provider_config],
    )
    terraform_block = HclBlock(
        block_type="terraform",
        nested_blocks=[required_providers],
    )
    blocks.append(terraform_block)

    # aws_iam_role resource with trust policy
    assume_role_policy_expr = HclRawExpression(
        "jsonencode({\n"
        '    Version = "2012-10-17"\n'
        "    Statement = [\n"
        "      {\n"
        '        Effect = "Allow"\n'
        "        Principal = {\n"
        '          AWS = "arn:aws:iam::${var.platform_account_id}:root"\n'
        "        }\n"
        '        Action = "sts:AssumeRole"\n'
        "        Condition = {\n"
        "          StringEquals = {\n"
        '            "sts:ExternalId" = var.external_id\n'
        "          }\n"
        "        }\n"
        "      }\n"
        "    ]\n"
        "  })"
    )

    iam_role = HclBlock(
        block_type="resource",
        labels=["aws_iam_role", "slashmybill"],
        attributes={
            "name": HclRawExpression('"SlashMyBill-${var.account_id}"'),
            "assume_role_policy": assume_role_policy_expr,
        },
    )
    blocks.append(iam_role)

    # aws_iam_role_policy_attachment for ReadOnlyAccess
    policy_attachment = HclBlock(
        block_type="resource",
        labels=["aws_iam_role_policy_attachment", "readonly"],
        attributes={
            "role": HclRawExpression("aws_iam_role.slashmybill.name"),
            "policy_arn": "arn:aws:iam::aws:policy/ReadOnlyAccess",
        },
    )
    blocks.append(policy_attachment)

    # aws_iam_role_policy for inline billing/action permissions
    inline_policy_expr = HclRawExpression(
        "jsonencode({\n"
        '    Version = "2012-10-17"\n'
        "    Statement = [\n"
        "      {\n"
        '        Effect = "Allow"\n'
        "        Action = " + _format_actions_list() + "\n"
        '        Resource = "*"\n'
        "      }\n"
        "    ]\n"
        "  })"
    )

    inline_policy = HclBlock(
        block_type="resource",
        labels=["aws_iam_role_policy", "billing_access"],
        attributes={
            "name": "SlashMyBillBillingAccess",
            "role": HclRawExpression("aws_iam_role.slashmybill.id"),
            "policy": inline_policy_expr,
        },
    )
    blocks.append(inline_policy)

    header = (
        "SlashMyBill Cross-Account Role Module - main.tf\n"
        "This file defines the IAM role, policy attachment, and inline policy."
    )

    doc = HclDocument(blocks=blocks, header_comment=header)
    return doc.render()


def _generate_module_variables_tf(platform_account_id: str, external_id: str) -> str:
    """Generate variables.tf for the cross-account module.

    Defines:
    - account_id (required, string)
    - platform_account_id (string, default "991105135552")
    - external_id (required, sensitive string, default = SHA-256 of member email)
    """
    blocks = []

    # variable "account_id" - required
    var_account_id = HclBlock(
        block_type="variable",
        labels=["account_id"],
        attributes={
            "type": HclRawExpression("string"),
            "description": "The AWS account ID where the cross-account role will be created",
        },
    )
    blocks.append(var_account_id)

    # variable "platform_account_id" - with default
    var_platform_account_id = HclBlock(
        block_type="variable",
        labels=["platform_account_id"],
        attributes={
            "type": HclRawExpression("string"),
            "description": "The SlashMyBill platform AWS account ID",
            "default": platform_account_id,
        },
    )
    blocks.append(var_platform_account_id)

    # variable "external_id" - required, sensitive, default = SHA-256 hash
    var_external_id = HclBlock(
        block_type="variable",
        labels=["external_id"],
        attributes={
            "type": HclRawExpression("string"),
            "description": "External ID for STS AssumeRole condition (SHA-256 of member email)",
            "sensitive": True,
            "default": external_id,
        },
    )
    blocks.append(var_external_id)

    header = "SlashMyBill Cross-Account Role Module - variables.tf"

    doc = HclDocument(blocks=blocks, header_comment=header)
    return doc.render()


def _generate_module_outputs_tf() -> str:
    """Generate outputs.tf for the cross-account module.

    Exports:
    - role_arn: The ARN of the created IAM role
    - role_name: The name of the created IAM role
    """
    blocks = []

    # output "role_arn"
    output_arn = HclBlock(
        block_type="output",
        labels=["role_arn"],
        attributes={
            "description": "ARN of the SlashMyBill cross-account role",
            "value": HclRawExpression("aws_iam_role.slashmybill.arn"),
        },
    )
    blocks.append(output_arn)

    # output "role_name"
    output_name = HclBlock(
        block_type="output",
        labels=["role_name"],
        attributes={
            "description": "Name of the SlashMyBill cross-account role",
            "value": HclRawExpression("aws_iam_role.slashmybill.name"),
        },
    )
    blocks.append(output_name)

    header = "SlashMyBill Cross-Account Role Module - outputs.tf"

    doc = HclDocument(blocks=blocks, header_comment=header)
    return doc.render()


def _generate_module_readme(account_id: str, external_id: str) -> str:
    """Generate README.md for the cross-account module.

    Includes usage examples showing how to call the module with required
    variables and how to reference the outputs.
    """
    return f"""# SlashMyBill Cross-Account Role Module

This Terraform module creates the IAM role required for SlashMyBill to access
your AWS account for cost optimization analysis and actions.

## Resources Created

- **aws_iam_role** - Cross-account IAM role with trust policy
- **aws_iam_role_policy_attachment** - ReadOnlyAccess managed policy
- **aws_iam_role_policy** - Inline policy for billing and action permissions

## Usage

```hcl
module "slashmybill_role" {{
  source = "./slashmybill-cross-account-module"

  account_id  = "{account_id}"
  external_id = "{external_id}"
}}
```

### With Custom Platform Account ID

```hcl
module "slashmybill_role" {{
  source = "./slashmybill-cross-account-module"

  account_id          = "{account_id}"
  external_id         = "{external_id}"
  platform_account_id = "991105135552"
}}
```

## Outputs

| Name | Description |
|------|-------------|
| `role_arn` | ARN of the SlashMyBill cross-account role |
| `role_name` | Name of the SlashMyBill cross-account role |

### Referencing Outputs

```hcl
output "slashmybill_role_arn" {{
  value = module.slashmybill_role.role_arn
}}

output "slashmybill_role_name" {{
  value = module.slashmybill_role.role_name
}}
```

## Variables

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `account_id` | string | yes | - | The AWS account ID where the role will be created |
| `platform_account_id` | string | no | "991105135552" | The SlashMyBill platform AWS account ID |
| `external_id` | string | yes | (SHA-256 of member email) | External ID for STS AssumeRole condition |

## Requirements

- Terraform >= 1.0
- AWS Provider >= 5.0

## Notes

- The `external_id` is pre-populated with the SHA-256 hash of your member email for security.
- Review the generated code before applying with `terraform apply`.
- This module does NOT manage Terraform state — it only provisions the IAM role.
"""
