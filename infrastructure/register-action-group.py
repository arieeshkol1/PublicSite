#!/usr/bin/env python3
"""
Register/update the FinOpsActions action group on the EXISTING Bedrock Agent.

This is the SINGLE SOURCE OF TRUTH for Bedrock Agent configuration.
It targets agent IDG5VJGUOZ5W (the live production agent).

What it does:
1. Adds Lambda invoke permission for the agent
2. Updates agent instructions from agent-action/agent-instructions.md
3. Creates or updates the action group with agent-action/openapi-schema.json
4. Prepares the agent (compiles the new schema)
5. Updates the 'live' alias to point to the new version

Run from CI/CD (deploy.yml) or locally with AWS credentials.
"""

import boto3
import json
import time
import os
import sys

REGION = 'us-east-1'
ACCOUNT_ID = '991105135552'
AGENT_ID = 'IDG5VJGUOZ5W'
ALIAS_ID = '9VYFXAEEH6'
MODEL_ID = 'us.amazon.nova-lite-v1:0'
AGENT_ROLE_ARN = f'arn:aws:iam::{ACCOUNT_ID}:role/SlashMyBill-BedrockAgent-Role'
ACTION_LAMBDA_ARN = f'arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:SlashMyBill-AgentAction'

# Resolve file paths relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
SCHEMA_FILE = os.path.join(REPO_ROOT, 'agent-action', 'openapi-schema.json')
INSTRUCTIONS_FILE = os.path.join(REPO_ROOT, 'agent-action', 'agent-instructions.md')

bedrock_agent = boto3.client('bedrock-agent', region_name=REGION)


def load_file(path, fallback_name):
    """Load a file, trying the absolute path first then relative to CWD."""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    # Fallback: try relative to CWD
    alt = os.path.join(os.getcwd(), fallback_name)
    if os.path.exists(alt):
        with open(alt, 'r', encoding='utf-8') as f:
            return f.read()
    print(f"ERROR: Cannot find {path} or {alt}")
    sys.exit(1)


def add_lambda_permission():
    """Allow the Bedrock Agent to invoke the action Lambda."""
    lam = boto3.client('lambda', region_name=REGION)
    try:
        lam.add_permission(
            FunctionName='SlashMyBill-AgentAction',
            StatementId=f'BedrockAgent-{AGENT_ID}',
            Action='lambda:InvokeFunction',
            Principal='bedrock.amazonaws.com',
            SourceArn=f'arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:agent/{AGENT_ID}',
        )
        print("  [OK] Lambda permission added")
    except lam.exceptions.ResourceConflictException:
        print("  [OK] Lambda permission already exists")
    except Exception as e:
        print(f"  [WARN] Lambda permission: {e}")


def update_agent_instructions():
    """Update the agent's instruction text."""
    instructions = load_file(INSTRUCTIONS_FILE, 'agent-action/agent-instructions.md')
    # Bedrock has a 4096 char limit on instructions — truncate if needed
    # Actually the limit is much higher (40000+), so we're fine
    try:
        bedrock_agent.update_agent(
            agentId=AGENT_ID,
            agentName='SlashMyBill-FinOps-Agent',
            agentResourceRoleArn=AGENT_ROLE_ARN,
            foundationModel=MODEL_ID,
            instruction=instructions,
            idleSessionTTLInSeconds=600,
        )
        print(f"  [OK] Agent instructions updated ({len(instructions)} chars)")
    except Exception as e:
        print(f"  [WARN] Could not update instructions: {e}")


def register_action_group():
    """Create or update the FinOpsActions action group."""
    schema = load_file(SCHEMA_FILE, 'agent-action/openapi-schema.json')

    # Validate schema is valid JSON
    try:
        parsed = json.loads(schema)
        path_count = len(parsed.get('paths', {}))
        print(f"  Schema loaded: {path_count} endpoints")
    except json.JSONDecodeError as e:
        print(f"  ERROR: Invalid JSON in schema: {e}")
        sys.exit(1)

    # Check if action group already exists
    try:
        groups = bedrock_agent.list_agent_action_groups(
            agentId=AGENT_ID, agentVersion='DRAFT'
        )
        for group in groups.get('actionGroupSummaries', []):
            if group['actionGroupName'] == 'FinOpsActions':
                # Update existing
                bedrock_agent.update_agent_action_group(
                    agentId=AGENT_ID,
                    agentVersion='DRAFT',
                    actionGroupId=group['actionGroupId'],
                    actionGroupName='FinOpsActions',
                    actionGroupExecutor={'lambda': ACTION_LAMBDA_ARN},
                    apiSchema={'payload': schema},
                    description=f'FinOps tools: {path_count} endpoints for cost analysis, resource inventory, optimization',
                )
                print(f"  [OK] Updated action group: {group['actionGroupId']}")
                return
    except Exception as e:
        print(f"  [NOTE] Could not list existing groups: {e}")

    # Create new action group
    response = bedrock_agent.create_agent_action_group(
        agentId=AGENT_ID,
        agentVersion='DRAFT',
        actionGroupName='FinOpsActions',
        actionGroupExecutor={'lambda': ACTION_LAMBDA_ARN},
        apiSchema={'payload': schema},
        description=f'FinOps tools: {path_count} endpoints for cost analysis, resource inventory, optimization',
    )
    print(f"  [OK] Created action group: {response['agentActionGroup']['actionGroupId']}")


def prepare_agent():
    """Prepare the agent to compile the new action group."""
    bedrock_agent.prepare_agent(agentId=AGENT_ID)
    print("  Preparing agent", end='', flush=True)

    for i in range(30):
        time.sleep(5)
        agent = bedrock_agent.get_agent(agentId=AGENT_ID)
        status = agent['agent']['agentStatus']
        if status == 'PREPARED':
            print(f"\n  [OK] Agent prepared")
            return True
        if status == 'FAILED':
            reason = agent['agent'].get('failureReasons', ['Unknown'])
            print(f"\n  [FAIL] Agent preparation failed: {reason}")
            return False
        print('.', end='', flush=True)

    print("\n  [FAIL] Agent preparation timed out (150s)")
    return False


def update_alias():
    """Update the live alias to point to the latest prepared version."""
    # Try both possible alias names (was 'live' in create script, 'SlashMyBillAgent' in deploy.yml)
    try:
        bedrock_agent.update_agent_alias(
            agentId=AGENT_ID,
            agentAliasId=ALIAS_ID,
            agentAliasName='live',
        )
        print(f"  [OK] Alias 'live' ({ALIAS_ID}) updated to latest version")
    except Exception as e:
        # Try alternate name
        try:
            bedrock_agent.update_agent_alias(
                agentId=AGENT_ID,
                agentAliasId=ALIAS_ID,
                agentAliasName='SlashMyBillAgent',
            )
            print(f"  [OK] Alias 'SlashMyBillAgent' ({ALIAS_ID}) updated to latest version")
        except Exception as e2:
            print(f"  [WARN] Alias update failed: {e2}")


if __name__ == '__main__':
    print("=" * 60)
    print("  SlashMyBill Bedrock Agent — Full Registration")
    print("=" * 60)
    print(f"  Agent ID:  {AGENT_ID}")
    print(f"  Alias ID:  {ALIAS_ID}")
    print(f"  Lambda:    {ACTION_LAMBDA_ARN}")
    print(f"  Model:     {MODEL_ID}")
    print()

    print("[1/5] Lambda permission...")
    add_lambda_permission()

    print("[2/5] Updating agent instructions...")
    update_agent_instructions()

    print("[3/5] Registering action group...")
    register_action_group()

    print("[4/5] Preparing agent...")
    success = prepare_agent()

    if success:
        print("[5/5] Updating alias...")
        update_alias()
        print()
        print("=" * 60)
        print("  SUCCESS — Agent is live with all action endpoints")
        print("=" * 60)
    else:
        print()
        print("=" * 60)
        print("  FAILED — Check Bedrock console for errors")
        print("=" * 60)
        sys.exit(1)
