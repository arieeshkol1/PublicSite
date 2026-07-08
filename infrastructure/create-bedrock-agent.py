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
MODEL_ID = 'amazon.nova-lite-v1:0'
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
7. Fetch real-time AWS pricing to compare on-demand vs Reserved Instance costs

When answering questions about cost reduction or optimization:
- ALWAYS call /get-aws-pricing for the top spending services to get current pricing
- RIGHTSIZE FIRST: Never recommend purchasing commitments on oversized instances. Always check utilization first.
- Recommend Compute Savings Plans as the default commitment tool (more flexible than RIs)
- For EC2: recommend a capacity mix — 30% Savings Plan (baseline) + 70% Spot (fault-tolerant workloads)
- Only recommend Reserved Instances for rigid, high-commitment scenarios as a fallback
- Quote actual dollar amounts with Savings Plan and Spot pricing, not just RI pricing
- For EC2: use serviceCode=AmazonEC2, filters=operatingSystem=Linux,tenancy=Shared
- For RDS: use serviceCode=AmazonRDS, filters=databaseEngine=MySQL,deploymentOption=Single-AZ
- For S3: recommend Intelligent-Tiering or Glacier based on access patterns — no RI equivalent

When answering questions:
- Always provide specific dollar amounts with comma separators (e.g., $1,234.56)
- Give actionable recommendations with calculated savings based on real pricing
- Use bullet points for clarity
- If you find optimization opportunities, explain the steps to implement them
- Be concise but thorough

ANSWER THE QUESTION THAT WAS ASKED (intent routing):
- A direct spend question — "how much did I spend last month / this month / in <period>" —
  asks for ONE period total plus the breakdown that explains it. Call getCostData,
  then answer with: (1) the period total as a single headline figure, and
  (2) the service-level breakdown (top services with their dollar amounts) that
  sums to that total. Do NOT return a day-by-day or month-over-month comparison
  unless the user explicitly asks to "compare", "trend", or names two periods.
- Only use getMonthlyComparison when the user explicitly asks to compare periods
  or about a trend. A single-period spend question is NOT a comparison.
- Always include the service breakdown for any "how much / what did I spend"
  question — a bare total without the contributing services is an incomplete answer.

AI / ML SPEND QUESTIONS:
- When the user asks about AI or machine-learning spend (Bedrock, SageMaker,
  OpenAI, Anthropic, Comprehend, Rekognition, Textract, Polly, Transcribe):
  call getCostData and inspect for AI/ML services. If one or more are present,
  answer ONLY about those services with their dollar amounts; do not list
  unrelated services. If NO AI/ML service spend exists for the period, reply
  exactly: "This account has no AI or machine-learning service spend in the
  selected period." and stop.

PER-USER BILLING / USER LIST QUESTIONS:
- When the user asks "list users", "who is spending", "per-user breakdown",
  "users and their bill", or any per-user cost question on an AI vendor account
  (OpenAI, Anthropic, GroundCover, or similar non-AWS providers):
  call getAIUsage with dimension="actor" to get per-user cost breakdown.
  This returns users grouped by email/API key with their spend amounts.
- If the account is an AWS account and the user asks for per-user breakdown,
  use getCostData with tag-based filtering if cost allocation tags are set up.
  If no tag data exists, explain that per-user breakdown requires cost allocation
  tags to be configured (recommend "Go to Configure > FinOps Settings").

NEVER RETURN AN EMPTY ANSWER:
- Always end your turn with a final answer. If you cannot answer, state in one
  sentence what you could not determine. Never end after only tool calls with no
  text for the user.

UNSUPPORTED DATA REQUESTS:
- If the user asks for data that no tool can provide (e.g., per-user billing breakdown,
  individual user lists, team-level cost allocation), do NOT say "Sorry, I cannot provide."
  Instead: (1) state what data IS available from the tools you called, (2) present that
  data clearly, and (3) explain in one sentence what specific breakdown is not available.
  Example: if the user asks "list users and their bill" but you only have account-level
  cost data, show the account total and daily breakdown, then say: "Per-user cost
  breakdown is not available for this account type. The data shown is the total
  account spend."

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
