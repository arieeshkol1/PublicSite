"""
Seed Script — Populates toolDefinition on the 11 existing tip records.

Maps each operation from the current openapi-schema.json to its corresponding
tip record in the Tips Table.
"""

import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

TIPS_TABLE_NAME = os.environ.get("TIPS_TABLE_NAME", "ViewMyBill-CostOptimizationTips")

# The 11 existing operations mapped to their tool definitions
# Matches the current openapi-schema.json exactly
SEED_TOOL_DEFINITIONS: list[dict] = [
    {
        "serviceId": "aws:ec2",
        "serviceKey": "Amazon EC2",
        "operationId": "getCostData",
        "toolDefinition": {
            "operationId": "getCostData",
            "path": "/get-cost-data",
            "httpMethod": "POST",
            "provider": "aws",
            "summary": "Get cost breakdown by service and daily trend",
            "description": "Gets cost by service for last 30 days and daily trend. Use usageTypeBreakdown=true with serviceFilter for specific service deep-dive.",
            "parameters": [
                {"name": "accountId", "in": "query", "type": "string", "required": True, "description": "The 12-digit AWS account ID"},
                {"name": "memberEmail", "in": "query", "type": "string", "required": True, "description": "Member email for role assumption"},
                {"name": "serviceFilter", "in": "query", "type": "string", "required": False, "description": "AWS service name to filter usage types e.g. Amazon Rekognition or Amazon Simple Storage Service"},
                {"name": "usageTypeBreakdown", "in": "query", "type": "string", "required": False, "description": "Set to true to get usage type level breakdown for a specific service"},
            ],
        },
    },
    {
        "serviceId": "aws:ec2",
        "serviceKey": "Amazon EC2",
        "operationId": "getMonthlyComparison",
        "toolDefinition": {
            "operationId": "getMonthlyComparison",
            "path": "/get-monthly-comparison",
            "httpMethod": "POST",
            "provider": "aws",
            "summary": "Compare costs across months",
            "description": "Gets monthly cost breakdown by service for last 3 to 6 months",
            "parameters": [
                {"name": "accountId", "in": "query", "type": "string", "required": True, "description": "The 12-digit AWS account ID"},
                {"name": "memberEmail", "in": "query", "type": "string", "required": True, "description": "Member email for role assumption"},
                {"name": "months", "in": "query", "type": "string", "required": False, "description": "Number of months default 3 max 6"},
            ],
        },
    },
    {
        "serviceId": "aws:ec2",
        "serviceKey": "Amazon EC2",
        "operationId": "getEC2Instances",
        "toolDefinition": {
            "operationId": "getEC2Instances",
            "path": "/get-ec2-instances",
            "httpMethod": "POST",
            "provider": "aws",
            "summary": "List EC2 instances with CPU metrics",
            "description": "Lists EC2 instances with type state and 14 day average CPU",
            "parameters": [
                {"name": "accountId", "in": "query", "type": "string", "required": True, "description": "The 12-digit AWS account ID"},
                {"name": "memberEmail", "in": "query", "type": "string", "required": True, "description": "Member email for role assumption"},
            ],
        },
    },
    {
        "serviceId": "aws:rds",
        "serviceKey": "Amazon RDS",
        "operationId": "getRDSInstances",
        "toolDefinition": {
            "operationId": "getRDSInstances",
            "path": "/get-rds-instances",
            "httpMethod": "POST",
            "provider": "aws",
            "summary": "List RDS instances with metrics",
            "description": "Lists RDS instances with class engine storage and CPU",
            "parameters": [
                {"name": "accountId", "in": "query", "type": "string", "required": True, "description": "The 12-digit AWS account ID"},
                {"name": "memberEmail", "in": "query", "type": "string", "required": True, "description": "Member email for role assumption"},
            ],
        },
    },
    {
        "serviceId": "aws:lambda",
        "serviceKey": "AWS Lambda",
        "operationId": "getLambdaFunctions",
        "toolDefinition": {
            "operationId": "getLambdaFunctions",
            "path": "/get-lambda-functions",
            "httpMethod": "POST",
            "provider": "aws",
            "summary": "List Lambda functions with metrics",
            "description": "Lists Lambda functions with runtime memory invocations errors",
            "parameters": [
                {"name": "accountId", "in": "query", "type": "string", "required": True, "description": "The 12-digit AWS account ID"},
                {"name": "memberEmail", "in": "query", "type": "string", "required": True, "description": "Member email for role assumption"},
            ],
        },
    },
    {
        "serviceId": "aws:s3",
        "serviceKey": "Amazon S3",
        "operationId": "getS3Buckets",
        "toolDefinition": {
            "operationId": "getS3Buckets",
            "path": "/get-s3-buckets",
            "httpMethod": "POST",
            "provider": "aws",
            "summary": "List S3 buckets",
            "description": "Lists S3 buckets with lifecycle policy status",
            "parameters": [
                {"name": "accountId", "in": "query", "type": "string", "required": True, "description": "The 12-digit AWS account ID"},
                {"name": "memberEmail", "in": "query", "type": "string", "required": True, "description": "Member email for role assumption"},
            ],
        },
    },
    {
        "serviceId": "aws:ebs",
        "serviceKey": "EC2 - Other",
        "operationId": "getEBSVolumes",
        "toolDefinition": {
            "operationId": "getEBSVolumes",
            "path": "/get-ebs-volumes",
            "httpMethod": "POST",
            "provider": "aws",
            "summary": "List EBS volumes",
            "description": "Lists EBS volumes with type size attachment status",
            "parameters": [
                {"name": "accountId", "in": "query", "type": "string", "required": True, "description": "The 12-digit AWS account ID"},
                {"name": "memberEmail", "in": "query", "type": "string", "required": True, "description": "Member email for role assumption"},
            ],
        },
    },
    {
        "serviceId": "aws:vpc",
        "serviceKey": "Amazon Virtual Private Cloud",
        "operationId": "getNetworkResources",
        "toolDefinition": {
            "operationId": "getNetworkResources",
            "path": "/get-network-resources",
            "httpMethod": "POST",
            "provider": "aws",
            "summary": "List NAT Gateways and Elastic IPs",
            "description": "Lists NAT Gateways VPC Endpoints and Elastic IPs",
            "parameters": [
                {"name": "accountId", "in": "query", "type": "string", "required": True, "description": "The 12-digit AWS account ID"},
                {"name": "memberEmail", "in": "query", "type": "string", "required": True, "description": "Member email for role assumption"},
            ],
        },
    },
    {
        "serviceId": "aws:ec2",
        "serviceKey": "Amazon EC2",
        "operationId": "getBudgets",
        "toolDefinition": {
            "operationId": "getBudgets",
            "path": "/get-budgets",
            "httpMethod": "POST",
            "provider": "aws",
            "summary": "List AWS Budgets",
            "description": "Lists AWS Budgets with spend and forecast",
            "parameters": [
                {"name": "accountId", "in": "query", "type": "string", "required": True, "description": "The 12-digit AWS account ID"},
                {"name": "memberEmail", "in": "query", "type": "string", "required": True, "description": "Member email for role assumption"},
            ],
        },
    },
    {
        "serviceId": "aws:ec2",
        "serviceKey": "Amazon EC2",
        "operationId": "getFinOpsSettings",
        "toolDefinition": {
            "operationId": "getFinOpsSettings",
            "path": "/get-finops-settings",
            "httpMethod": "POST",
            "provider": "aws",
            "summary": "Get FinOps settings healthcheck",
            "description": "Returns FinOps settings scan results for the account",
            "parameters": [
                {"name": "accountId", "in": "query", "type": "string", "required": True, "description": "The 12-digit AWS account ID"},
                {"name": "memberEmail", "in": "query", "type": "string", "required": True, "description": "Member email for role assumption"},
            ],
        },
    },
    {
        "serviceId": "aws:ec2",
        "serviceKey": "Amazon EC2",
        "operationId": "getAWSPricing",
        "toolDefinition": {
            "operationId": "getAWSPricing",
            "path": "/get-aws-pricing",
            "httpMethod": "POST",
            "provider": "aws",
            "summary": "Get real-time AWS pricing",
            "description": "Queries AWS Pricing API for current pricing data",
            "parameters": [
                {"name": "filters", "in": "query", "type": "string", "required": False, "description": "Key value filters like instanceType m5.large"},
                {"name": "region", "in": "query", "type": "string", "required": False, "description": "AWS region code default us-east-1"},
                {"name": "serviceCode", "in": "query", "type": "string", "required": True, "description": "AWS service code like AmazonEC2 AmazonRDS AmazonS3"},
            ],
        },
    },
]


def seed_tool_definitions() -> dict:
    """
    Populate toolDefinition on existing tip records in DynamoDB.

    For each entry in SEED_TOOL_DEFINITIONS, finds a matching tip record
    (by serviceKey or creates a dedicated tool-carrier record) and writes
    the toolDefinition attribute.

    Returns:
        Summary: {seeded: int, errors: int}
    """
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(TIPS_TABLE_NAME)

    seeded = 0
    errors = 0

    for seed in SEED_TOOL_DEFINITIONS:
        operation_id = seed["operationId"]
        tool_def = seed["toolDefinition"]
        service_id = seed["serviceId"]

        # Use a dedicated item for each tool definition
        # Key: service=TOOL_DEF, id=<operationId>
        try:
            table.put_item(
                Item={
                    "service": "TOOL_DEF",
                    "id": operation_id,
                    "serviceId": service_id,
                    "serviceKey": seed["serviceKey"],
                    "title": f"Tool: {tool_def['summary']}",
                    "toolDefinition": tool_def,
                }
            )
            seeded += 1
            logger.info("Seeded toolDefinition for %s", operation_id)
        except ClientError as e:
            logger.error("Failed to seed %s: %s", operation_id, e)
            errors += 1

    summary = {"seeded": seeded, "errors": errors}
    logger.info("Seed complete: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = seed_tool_definitions()
    print(f"Seed result: {result}")
