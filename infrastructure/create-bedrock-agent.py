"""
Create the SlashMyBill FinOps Bedrock Agent.
Run this from AWS CloudShell or with an IAM user that has bedrock-agent permissions.

Usage: python create-bedrock-agent.py
"""

import boto3
import json
import time

REGION = 'us-east-1'
ACCOUNT_ID = '991105135552'
AGENT_NAME = 'SlashMyBill-FinOps-Agent'
MODEL_ID = 'amazon.nova-2-lite-v1:0'
AGENT_ROLE_NAME = 'SlashMyBill-BedrockAgent-Role'

bedrock_agent = boto3.client('bedrock-agent', region_name=REGION)
iam = boto3.client('iam')


def create_agent_role():
    """Create IAM role for the Bedrock Agent."""
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {"aws:SourceAccount": ACCOUNT_ID},
            }
        }]
    }

    try:
        role = iam.create_role(
            RoleName=AGENT_ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description='IAM role for SlashMyBill Bedrock FinOps Agent',
        )
        role_arn = role['Role']['Arn']
        print(f"Created role: {role_arn}")
    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = f'arn:aws:iam::{ACCOUNT_ID}:role/{AGENT_ROLE_NAME}'
        print(f"Role already exists: {role_arn}")

    # Attach Bedrock model invocation policy
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel"],
                "Resource": [
                    f"arn:aws:bedrock:{REGION}::foundation-model/{MODEL_ID}",
                    f"arn:aws:bedrock:{REGION}::foundation-model/amazon.nova-lite-v1:0",
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan",
                    "dynamodb:PutItem",
                ],
                "Resource": [
                    f"arn:aws:dynamodb:{REGION}:{ACCOUNT_ID}:table/ViewMyBill-CostOptimizationTips"
                ]
            },
            {
                "Effect": "Allow",
                "Action": ["lambda:InvokeFunction"],
                "Resource": [
                    f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:SlashMyBill-AgentAction"
                ]
            },
            {
                "Effect": "Allow",
                "Action": ["pricing:GetProducts", "pricing:DescribeServices", "pricing:GetAttributeValues"],
                "Resource": "*"
            }
        ]
    }

    try:
        iam.put_role_policy(
            RoleName=AGENT_ROLE_NAME,
            PolicyName='BedrockAgentPolicy',
            PolicyDocument=json.dumps(policy),
        )
        print("Attached policy to role")
    except Exception as e:
        print(f"Policy attach error: {e}")

    # Wait for role propagation
    time.sleep(10)
    return role_arn


def create_agent(role_arn):
    """Create the Bedrock Agent."""
    instruction = """You are SlashMyBill AI, a professional AWS FinOps assistant. You help members analyze their AWS accounts for cost optimization.

Your capabilities:
1. Query AWS Cost Explorer for cost breakdowns by service, daily trends, and forecasts
2. Check EC2 instances for right-sizing opportunities
3. Analyze S3 buckets for storage optimization
4. Review RDS instances for cost savings
5. Check Lambda functions for optimization
6. Look up cost optimization tips from the knowledge base

When answering questions:
- Always provide specific dollar amounts with comma separators (e.g., $1,234.56)
- Give actionable recommendations with estimated savings percentages
- Use bullet points for clarity
- If you find optimization opportunities, explain the steps to implement them
- Be concise but thorough

You have access to the member's AWS account via cross-account role assumption. Use the provided action group to gather real data before answering."""

    try:
        # Check if agent already exists
        agents = bedrock_agent.list_agents()
        for agent in agents.get('agentSummaries', []):
            if agent['agentName'] == AGENT_NAME:
                print(f"Agent already exists: {agent['agentId']}")
                return agent['agentId']

        response = bedrock_agent.create_agent(
            agentName=AGENT_NAME,
            agentResourceRoleArn=role_arn,
            foundationModel=MODEL_ID,
            instruction=instruction,
            idleSessionTTLInSeconds=600,
            description='SlashMyBill FinOps AI Agent for AWS cost optimization analysis',
        )
        agent_id = response['agent']['agentId']
        print(f"Created agent: {agent_id}")
        return agent_id
    except Exception as e:
        print(f"Agent creation error: {e}")
        raise


def create_agent_action_group(agent_id):
    """Create an action group for the agent to call AWS APIs."""
    api_schema = {
        "openapi": "3.0.0",
        "info": {"title": "SlashMyBill FinOps Actions", "version": "1.0.0"},
        "paths": {
            "/get-cost-data": {
                "post": {
                    "operationId": "getCostData",
                    "summary": "Get AWS cost and usage data from Cost Explorer",
                    "description": "Retrieves cost breakdown by service for the last 30 days and daily cost trend for the last 7 days",
                    "parameters": [
                        {"name": "accountId", "in": "query", "required": True, "schema": {"type": "string"}, "description": "12-digit AWS account ID"},
                        {"name": "memberEmail", "in": "query", "required": True, "schema": {"type": "string"}, "description": "Member email for role assumption"},
                    ],
                    "responses": {"200": {"description": "Cost data retrieved successfully"}}
                }
            },
            "/get-ec2-instances": {
                "post": {
                    "operationId": "getEC2Instances",
                    "summary": "List EC2 instances with their types, states, and tags",
                    "parameters": [
                        {"name": "accountId", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "memberEmail", "in": "query", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "EC2 instances listed"}}
                }
            },
            "/get-s3-buckets": {
                "post": {
                    "operationId": "getS3Buckets",
                    "summary": "List S3 buckets in the account",
                    "parameters": [
                        {"name": "accountId", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "memberEmail", "in": "query", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "S3 buckets listed"}}
                }
            },
            "/get-optimization-tips": {
                "post": {
                    "operationId": "getOptimizationTips",
                    "summary": "Search the cost optimization tips knowledge base",
                    "parameters": [
                        {"name": "service", "in": "query", "required": False, "schema": {"type": "string"}, "description": "AWS service name (e.g., EC2, S3, RDS)"},
                    ],
                    "responses": {"200": {"description": "Tips retrieved"}}
                }
            },
            "/get-aws-pricing": {
                "post": {
                    "operationId": "getAWSPricing",
                    "summary": "Get real-time AWS pricing for any service",
                    "description": "Queries the AWS Pricing API for current pricing. Use this when customers ask about AWS service costs, pricing comparisons, or want to understand what they will be charged.",
                    "parameters": [
                        {"name": "serviceCode", "in": "query", "required": True, "schema": {"type": "string"}, "description": "AWS service code, e.g. AmazonEC2, AmazonS3, AWSLambda, AmazonRDS"},
                        {"name": "filters", "in": "query", "required": False, "schema": {"type": "string"}, "description": "Comma-separated key=value filters, e.g. instanceType=m5.large,operatingSystem=Linux"},
                        {"name": "region", "in": "query", "required": False, "schema": {"type": "string"}, "description": "AWS region code, e.g. us-east-1, eu-west-1. Defaults to us-east-1"},
                    ],
                    "responses": {"200": {"description": "Pricing data retrieved"}}
                }
            },
        }
    }

    lambda_arn = f'arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:SlashMyBill-AgentAction'

    try:
        response = bedrock_agent.create_agent_action_group(
            agentId=agent_id,
            agentVersion='DRAFT',
            actionGroupName='FinOpsActions',
            actionGroupExecutor={'lambda': lambda_arn},
            apiSchema={'payload': json.dumps(api_schema)},
            description='Actions for querying AWS account data and optimization tips',
        )
        print(f"Created action group: {response['agentActionGroup']['actionGroupId']}")
    except Exception as e:
        if 'ConflictException' in str(type(e).__name__) or 'already exists' in str(e).lower():
            print("Action group already exists")
        else:
            print(f"Action group error: {e}")


def prepare_and_create_alias(agent_id):
    """Prepare the agent and create an alias."""
    try:
        bedrock_agent.prepare_agent(agentId=agent_id)
        print("Agent preparation started...")
        # Wait for preparation
        for _ in range(30):
            time.sleep(5)
            agent = bedrock_agent.get_agent(agentId=agent_id)
            status = agent['agent']['agentStatus']
            print(f"  Status: {status}")
            if status == 'PREPARED':
                break
            if status == 'FAILED':
                print("Agent preparation failed!")
                return None

        # Create alias
        try:
            response = bedrock_agent.create_agent_alias(
                agentId=agent_id,
                agentAliasName='live',
                description='Production alias',
            )
            alias_id = response['agentAlias']['agentAliasId']
            print(f"Created alias 'live': {alias_id}")
            return alias_id
        except Exception as e:
            if 'ConflictException' in str(type(e).__name__):
                aliases = bedrock_agent.list_agent_aliases(agentId=agent_id)
                for a in aliases.get('agentAliasSummaries', []):
                    if a['agentAliasName'] == 'live':
                        print(f"Alias 'live' already exists: {a['agentAliasId']}")
                        return a['agentAliasId']
            print(f"Alias error: {e}")
            return None
    except Exception as e:
        print(f"Prepare error: {e}")
        return None


if __name__ == '__main__':
    print("=== Creating SlashMyBill Bedrock Agent ===")
    role_arn = create_agent_role()
    agent_id = create_agent(role_arn)
    create_agent_action_group(agent_id)
    alias_id = prepare_and_create_alias(agent_id)
    print(f"\n=== Done ===")
    print(f"Agent ID: {agent_id}")
    print(f"Alias ID: {alias_id}")
    print(f"\nSet these environment variables in the Member Handler Lambda:")
    print(f"  BEDROCK_AGENT_ID={agent_id}")
    print(f"  BEDROCK_AGENT_ALIAS_ID={alias_id}")
