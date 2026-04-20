#!/usr/bin/env python3
"""
Update (or create) the SlashMyBill Bedrock Agent with the latest OpenAPI schema.
Run from CI/CD pipeline or CloudShell.

This script:
1. Creates the agent IAM role if it doesn't exist
2. Creates or finds the existing agent
3. Updates the action group with the latest OpenAPI schema
4. Prepares the agent (compiles the new schema)
5. Creates/updates the alias

Environment: AWS credentials must be configured (CI/CD role or CloudShell).
"""

import boto3
import json
import time
import os

REGION = 'us-east-1'
ACCOUNT_ID = '991105135552'
AGENT_NAME = 'SlashMyBill-FinOps-Agent-v2'
MODEL_ID = 'us.amazon.nova-lite-v1:0'
AGENT_ROLE_NAME = 'SlashMyBill-BedrockAgent-Role'
ACTION_LAMBDA_ARN = f'arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:SlashMyBill-AgentAction'
SCHEMA_FILE = os.path.join(os.path.dirname(__file__), '..', 'agent-action', 'openapi-schema.json')

bedrock_agent = boto3.client('bedrock-agent', region_name=REGION)
iam = boto3.client('iam')

AGENT_INSTRUCTION = """You are SlashMyBill AI, a professional AWS FinOps assistant. You analyze AWS accounts for cost optimization opportunities.

SLASHMYBILL PLATFORM FEATURES (ALWAYS recommend these instead of AWS Console):
- Plan → Budget: Create/edit/delete AWS Budgets with alerts directly from SlashMyBill
- Plan → Tag Resources: Scan and bulk-tag all resources from SlashMyBill
- Act → Waste Cleanup: Scan and clean up idle resources (EBS, EIPs, ELBs, EC2, RDS, snapshots)
- Act → Scheduler: Create stop/start schedules for EC2, RDS, ASG, EKS, SageMaker, Redshift
- Configure → FinOps Settings: Check and fix AWS billing best practices
- Observe → Dashboard: View cost trends, waste detection, rightsizing, cost by region
- NEVER tell users to open the AWS Management Console — everything can be done from SlashMyBill

WORKFLOW:
1. When a user asks a question, decide which tools to call based on the question
2. Call the relevant tools to gather data
3. Analyze the data and provide specific, actionable recommendations
4. Always include dollar amounts and specific resource IDs
5. Recommend SlashMyBill features (Act → Scheduler, Plan → Budget, etc.) for implementation

RULES:
- Always provide specific dollar amounts with comma separators
- Give actionable recommendations with calculated savings
- Use bullet points for clarity
- Be concise but thorough
- For cost comparisons, always call /get-monthly-comparison
- For rightsizing, always call /get-ec2-instances or /get-rds-instances to check CPU
- For waste detection, call /get-ebs-volumes and /get-network-resources
- NEVER recommend purchasing commitments on oversized instances — check utilization first
- Recommend Compute Savings Plans as the default commitment tool (more flexible than RIs)

The accountId and memberEmail are passed in the user's message as [Account: XXXX, Email: XXXX].
Extract these values and pass them to the tools."""


def ensure_agent_role():
    """Create or get the agent IAM role."""
    role_arn = f'arn:aws:iam::{ACCOUNT_ID}:role/{AGENT_ROLE_NAME}'
    
    try:
        iam.get_role(RoleName=AGENT_ROLE_NAME)
        print(f"✓ Role exists: {AGENT_ROLE_NAME}")
        return role_arn
    except iam.exceptions.NoSuchEntityException:
        pass

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT_ID}}
        }]
    }

    iam.create_role(
        RoleName=AGENT_ROLE_NAME,
        AssumeRolePolicyDocument=json.dumps(trust_policy),
        Description='Role for SlashMyBill Bedrock Agent',
    )

    # Attach permissions
    policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                "Resource": f"arn:aws:bedrock:{REGION}::foundation-model/*"
            },
            {
                "Effect": "Allow",
                "Action": ["lambda:InvokeFunction"],
                "Resource": ACTION_LAMBDA_ARN
            }
        ]
    }
    iam.put_role_policy(
        RoleName=AGENT_ROLE_NAME,
        PolicyName='BedrockAgentPermissions',
        PolicyDocument=json.dumps(policy_doc),
    )
    print(f"✓ Created role: {AGENT_ROLE_NAME}")
    time.sleep(10)  # Wait for role propagation
    return role_arn


def find_or_create_agent(role_arn):
    """Find existing agent or create a new one."""
    # Check if agent exists
    agents = bedrock_agent.list_agents(maxResults=100)
    for agent in agents.get('agentSummaries', []):
        if agent['agentName'] == AGENT_NAME:
            agent_id = agent['agentId']
            print(f"✓ Found existing agent: {agent_id}")
            # Update instruction
            try:
                bedrock_agent.update_agent(
                    agentId=agent_id,
                    agentName=AGENT_NAME,
                    agentResourceRoleArn=role_arn,
                    foundationModel=MODEL_ID,
                    instruction=AGENT_INSTRUCTION,
                    idleSessionTTLInSeconds=600,
                )
                print(f"  Updated agent instruction")
            except Exception as e:
                print(f"  Warning: Could not update agent: {e}")
            return agent_id

    # Create new agent
    response = bedrock_agent.create_agent(
        agentName=AGENT_NAME,
        agentResourceRoleArn=role_arn,
        foundationModel=MODEL_ID,
        instruction=AGENT_INSTRUCTION,
        idleSessionTTLInSeconds=600,
        description='SlashMyBill FinOps AI Agent v2 with 12 tools',
    )
    agent_id = response['agent']['agentId']
    print(f"✓ Created agent: {agent_id}")
    time.sleep(5)
    return agent_id


def update_action_group(agent_id):
    """Create or update the action group with the latest OpenAPI schema."""
    # Load schema
    schema_path = SCHEMA_FILE
    if not os.path.exists(schema_path):
        # Try relative to CWD
        schema_path = 'agent-action/openapi-schema.json'
    
    with open(schema_path, 'r') as f:
        schema = f.read()

    # Check if action group exists
    try:
        groups = bedrock_agent.list_agent_action_groups(
            agentId=agent_id, agentVersion='DRAFT'
        )
        for group in groups.get('actionGroupSummaries', []):
            if group['actionGroupName'] == 'FinOpsActions':
                # Update existing
                bedrock_agent.update_agent_action_group(
                    agentId=agent_id,
                    agentVersion='DRAFT',
                    actionGroupId=group['actionGroupId'],
                    actionGroupName='FinOpsActions',
                    actionGroupExecutor={'lambda': ACTION_LAMBDA_ARN},
                    apiSchema={'payload': schema},
                    description='FinOps tools: cost analysis, resource inventory, optimization',
                )
                print(f"✓ Updated action group: {group['actionGroupId']}")
                return
    except Exception:
        pass

    # Create new action group
    response = bedrock_agent.create_agent_action_group(
        agentId=agent_id,
        agentVersion='DRAFT',
        actionGroupName='FinOpsActions',
        actionGroupExecutor={'lambda': ACTION_LAMBDA_ARN},
        apiSchema={'payload': schema},
        description='FinOps tools: cost analysis, resource inventory, optimization',
    )
    print(f"✓ Created action group: {response['agentActionGroup']['actionGroupId']}")


def prepare_and_alias(agent_id):
    """Prepare the agent and create/update alias."""
    bedrock_agent.prepare_agent(agentId=agent_id)
    print("  Preparing agent...")

    for _ in range(24):
        time.sleep(5)
        agent = bedrock_agent.get_agent(agentId=agent_id)
        status = agent['agent']['agentStatus']
        if status == 'PREPARED':
            print(f"✓ Agent prepared")
            break
        if status == 'FAILED':
            print(f"✗ Agent preparation failed")
            return None
    else:
        print("✗ Agent preparation timed out")
        return None

    # Create or update alias
    try:
        aliases = bedrock_agent.list_agent_aliases(agentId=agent_id)
        for alias in aliases.get('agentAliasSummaries', []):
            if alias['agentAliasName'] == 'live':
                bedrock_agent.update_agent_alias(
                    agentId=agent_id,
                    agentAliasId=alias['agentAliasId'],
                    agentAliasName='live',
                )
                print(f"✓ Updated alias: {alias['agentAliasId']}")
                return alias['agentAliasId']
    except Exception:
        pass

    response = bedrock_agent.create_agent_alias(
        agentId=agent_id,
        agentAliasName='live',
        description='Production alias',
    )
    alias_id = response['agentAlias']['agentAliasId']
    print(f"✓ Created alias: {alias_id}")
    return alias_id


def add_lambda_permission(agent_id):
    """Allow the Bedrock Agent to invoke the action Lambda."""
    lam = boto3.client('lambda', region_name=REGION)
    try:
        lam.add_permission(
            FunctionName='SlashMyBill-AgentAction',
            StatementId=f'BedrockAgent-{agent_id}',
            Action='lambda:InvokeFunction',
            Principal='bedrock.amazonaws.com',
            SourceArn=f'arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:agent/{agent_id}',
        )
        print("✓ Lambda permission added")
    except lam.exceptions.ResourceConflictException:
        print("✓ Lambda permission already exists")
    except Exception as e:
        print(f"  Warning: Lambda permission: {e}")


if __name__ == '__main__':
    print("=== SlashMyBill Bedrock Agent Setup ===")
    print(f"Region: {REGION}, Account: {ACCOUNT_ID}")
    print(f"Model: {MODEL_ID}")
    print()

    role_arn = ensure_agent_role()
    agent_id = find_or_create_agent(role_arn)
    add_lambda_permission(agent_id)
    update_action_group(agent_id)
    alias_id = prepare_and_alias(agent_id)

    print()
    print("=== Done ===")
    print(f"Agent ID: {agent_id}")
    print(f"Alias ID: {alias_id}")
    print()
    print("Set these environment variables on the member-handler Lambda:")
    print(f"  BEDROCK_AGENT_ID = {agent_id}")
    print(f"  BEDROCK_AGENT_ALIAS_ID = {alias_id}")
