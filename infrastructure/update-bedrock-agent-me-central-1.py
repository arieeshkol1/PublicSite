#!/usr/bin/env python3
"""
Update (or create) the SlashMyBill Bedrock Agent in me-central-1 (UAE).
Mirrors update-bedrock-agent.py but targets me-central-1.

This script:
1. Creates the agent IAM role if it doesn't exist (with -me-central-1 suffix)
2. Creates or finds the existing agent in me-central-1
3. Updates the action group with the latest OpenAPI schema
4. Prepares the agent (compiles the new schema)
5. Creates/updates the alias

Environment: AWS credentials must be configured (CI/CD role or CloudShell).
"""

import boto3
import json
import time
import os

REGION = 'me-central-1'
ACCOUNT_ID = '991105135552'
AGENT_NAME = 'SlashMyBill-FinOps-Agent-UAE'
MODEL_ID = 'us.amazon.nova-lite-v1:0'  # Try cross-region inference prefix first
FALLBACK_MODEL_ID = 'amazon.nova-lite-v1:0'
AGENT_ROLE_NAME = 'SlashMyBill-BedrockAgent-Role-me-central-1'
ACTION_LAMBDA_ARN = f'arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:SlashMyBill-AgentAction'
SCHEMA_FILE = os.path.join(os.path.dirname(__file__), '..', 'agent-action', 'openapi-schema.json')
INSTRUCTIONS_FILE = os.path.join(os.path.dirname(__file__), '..', 'agent-action', 'agent-instructions.md')

bedrock_agent = boto3.client('bedrock-agent', region_name=REGION)
iam = boto3.client('iam')


def _load_instructions():
    """Load agent instructions from the markdown file."""
    instructions_path = INSTRUCTIONS_FILE
    if not os.path.exists(instructions_path):
        instructions_path = 'agent-action/agent-instructions.md'
    with open(instructions_path, 'r', encoding='utf-8') as f:
        return f.read()


AGENT_INSTRUCTION = _load_instructions()


def ensure_agent_role():
    """Create or get the agent IAM role."""
    role_arn = f'arn:aws:iam::{ACCOUNT_ID}:role/{AGENT_ROLE_NAME}'

    try:
        iam.get_role(RoleName=AGENT_ROLE_NAME)
        print(f"✓ Role exists: {AGENT_ROLE_NAME}")
    except iam.exceptions.NoSuchEntityException:
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
            Description='Role for SlashMyBill Bedrock Agent (me-central-1)',
        )
        print(f"✓ Created role: {AGENT_ROLE_NAME}")
        time.sleep(10)

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
    print(f"✓ Policy attached to {AGENT_ROLE_NAME}")
    return role_arn


def find_or_create_agent(role_arn):
    """Find existing agent or create a new one."""
    agents = bedrock_agent.list_agents(maxResults=100)
    for agent in agents.get('agentSummaries', []):
        if agent['agentName'] == AGENT_NAME:
            agent_id = agent['agentId']
            print(f"✓ Found existing agent: {agent_id}")
            try:
                bedrock_agent.update_agent(
                    agentId=agent_id,
                    agentName=AGENT_NAME,
                    agentResourceRoleArn=role_arn,
                    foundationModel=MODEL_ID,
                    instruction=AGENT_INSTRUCTION,
                    idleSessionTTLInSeconds=600,
                )
                print(f"  Updated agent instruction + model")
            except Exception as e:
                # Try fallback model if primary not available
                if 'model' in str(e).lower() or 'not found' in str(e).lower():
                    print(f"  Model {MODEL_ID} not available, trying {FALLBACK_MODEL_ID}...")
                    bedrock_agent.update_agent(
                        agentId=agent_id,
                        agentName=AGENT_NAME,
                        agentResourceRoleArn=role_arn,
                        foundationModel=FALLBACK_MODEL_ID,
                        instruction=AGENT_INSTRUCTION,
                        idleSessionTTLInSeconds=600,
                    )
                    print(f"  Updated with fallback model")
                else:
                    print(f"  Warning: Could not update agent: {e}")
            return agent_id

    # Create new agent
    try:
        response = bedrock_agent.create_agent(
            agentName=AGENT_NAME,
            agentResourceRoleArn=role_arn,
            foundationModel=MODEL_ID,
            instruction=AGENT_INSTRUCTION,
            idleSessionTTLInSeconds=600,
            description='SlashMyBill FinOps AI Agent - UAE (me-central-1)',
        )
    except Exception as e:
        if 'model' in str(e).lower() or 'not found' in str(e).lower():
            print(f"  Model {MODEL_ID} not available, trying {FALLBACK_MODEL_ID}...")
            response = bedrock_agent.create_agent(
                agentName=AGENT_NAME,
                agentResourceRoleArn=role_arn,
                foundationModel=FALLBACK_MODEL_ID,
                instruction=AGENT_INSTRUCTION,
                idleSessionTTLInSeconds=600,
                description='SlashMyBill FinOps AI Agent - UAE (me-central-1)',
            )
        else:
            raise

    agent_id = response['agent']['agentId']
    print(f"✓ Created agent: {agent_id}")
    time.sleep(5)
    return agent_id


def update_action_group(agent_id):
    """Create or update the action group with the latest OpenAPI schema."""
    schema_path = SCHEMA_FILE
    if not os.path.exists(schema_path):
        schema_path = 'agent-action/openapi-schema.json'

    with open(schema_path, 'r') as f:
        schema = f.read()

    try:
        groups = bedrock_agent.list_agent_action_groups(
            agentId=agent_id, agentVersion='DRAFT'
        )
        for group in groups.get('actionGroupSummaries', []):
            if group['actionGroupName'] == 'FinOpsActions':
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
        description='Production alias (UAE)',
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
    print("=== SlashMyBill Bedrock Agent Setup (me-central-1 / UAE) ===")
    print(f"Region: {REGION}, Account: {ACCOUNT_ID}")
    print(f"Model: {MODEL_ID} (fallback: {FALLBACK_MODEL_ID})")
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
    print("Update the CloudFormation stack parameters:")
    print(f"  BedrockAgentId = {agent_id}")
    print(f"  BedrockAgentAliasId = {alias_id}")
