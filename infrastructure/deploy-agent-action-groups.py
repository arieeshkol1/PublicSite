"""
Deploy all 6 vendor-neutral action groups to the SlashMyBill Bedrock Agent.

This script:
1. Creates or updates each of the 6 action groups with their OpenAPI schemas
2. Updates the agent instructions to the vendor-neutral version
3. Calls PrepareAgent to create a new prepared agent version

Usage: python deploy-agent-action-groups.py

Requirements:
- boto3 installed
- AWS credentials with bedrock-agent permissions
- Schema files in agent-action/schemas/
- Agent instructions in agent-action/agent-instructions.txt
"""

import boto3
import json
import sys
import os
import time

# Configuration
REGION = 'us-east-1'
AGENT_ID = 'G5VJGUOZ5W'
LAMBDA_ARN = 'arn:aws:lambda:us-east-1:991105135552:function:Agent_Action_Lambda'

# Action group definitions: (name, schema filename, description)
ACTION_GROUPS = [
    {
        'name': 'CostAnalysis',
        'schema_file': 'cost-analysis.json',
        'description': 'Cost analysis tools: getCostBreakdown, getMonthlyTrend, getCostForecast, getCostAnomalies',
    },
    {
        'name': 'ComputeOptimize',
        'schema_file': 'compute-optimize.json',
        'description': 'Compute optimization tools: getComputeInstances, getRightsizingRecommendations, getSpotCandidates, getLicensingAnalysis',
    },
    {
        'name': 'DatabaseStorage',
        'schema_file': 'database-storage.json',
        'description': 'Database and storage tools: getDatabaseInstances, getStorageVolumes, getObjectStorage',
    },
    {
        'name': 'NetworkServerless',
        'schema_file': 'network-serverless.json',
        'description': 'Network and serverless tools: getNetworkResources, getServerlessFunctions, getContainerClusters',
    },
    {
        'name': 'FinOpsPlatform',
        'schema_file': 'finops-platform.json',
        'description': 'FinOps platform tools: getBudgets, getFinOpsSettings, getCommitmentCoverage, getTagCompliance, getBusinessMetrics',
    },
    {
        'name': 'Knowledge',
        'schema_file': 'knowledge.json',
        'description': 'Knowledge and pricing tools: getOptimizationTips, getPricingData, getAIVendorUsage',
    },
]


def get_project_root():
    """Determine the project root directory (parent of infrastructure/)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(script_dir)


def load_schema(project_root, schema_file):
    """Load and validate an OpenAPI schema file."""
    schema_path = os.path.join(project_root, 'agent-action', 'schemas', schema_file)
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    return json.dumps(schema)


def load_agent_instructions(project_root):
    """Load the agent instructions text file."""
    instructions_path = os.path.join(project_root, 'agent-action', 'agent-instructions.txt')
    with open(instructions_path, 'r', encoding='utf-8') as f:
        return f.read()


def get_existing_action_groups(client, agent_id):
    """Retrieve existing action groups and return a dict keyed by name."""
    existing = {}
    paginator = client.get_paginator('list_agent_action_groups')
    for page in paginator.paginate(agentId=agent_id, agentVersion='DRAFT'):
        for group in page.get('actionGroupSummaries', []):
            existing[group['actionGroupName']] = group['actionGroupId']
    return existing


def create_or_update_action_group(client, agent_id, group_config, schema_payload, existing_groups):
    """Create a new action group or update an existing one by name."""
    group_name = group_config['name']

    if group_name in existing_groups:
        # Update existing action group
        action_group_id = existing_groups[group_name]
        print(f"  Updating existing action group '{group_name}' (ID: {action_group_id})...")
        client.update_agent_action_group(
            agentId=agent_id,
            agentVersion='DRAFT',
            actionGroupId=action_group_id,
            actionGroupName=group_name,
            actionGroupExecutor={'lambda': LAMBDA_ARN},
            apiSchema={'payload': schema_payload},
            description=group_config['description'],
        )
        print(f"  ✓ Updated '{group_name}'")
    else:
        # Create new action group
        print(f"  Creating new action group '{group_name}'...")
        response = client.create_agent_action_group(
            agentId=agent_id,
            agentVersion='DRAFT',
            actionGroupName=group_name,
            actionGroupExecutor={'lambda': LAMBDA_ARN},
            apiSchema={'payload': schema_payload},
            description=group_config['description'],
        )
        action_group_id = response['agentActionGroup']['actionGroupId']
        print(f"  ✓ Created '{group_name}' (ID: {action_group_id})")

    return group_name


def update_agent_instructions(client, agent_id, instructions):
    """Update the Bedrock Agent's instructions."""
    print("\nUpdating agent instructions...")
    # Get current agent config to preserve other settings
    agent_response = client.get_agent(agentId=agent_id)
    agent = agent_response['agent']

    client.update_agent(
        agentId=agent_id,
        agentName=agent['agentName'],
        agentResourceRoleArn=agent['agentResourceRoleArn'],
        foundationModel=agent['foundationModel'],
        instruction=instructions,
        idleSessionTTLInSeconds=agent.get('idleSessionTTLInSeconds', 600),
        description=agent.get('description', ''),
    )
    print("✓ Agent instructions updated")


def prepare_agent(client, agent_id):
    """Call PrepareAgent to create a new prepared version."""
    print("\nPreparing agent (creating new version)...")
    client.prepare_agent(agentId=agent_id)

    # Poll for preparation completion
    for attempt in range(30):
        time.sleep(5)
        agent_response = client.get_agent(agentId=agent_id)
        status = agent_response['agent']['agentStatus']
        print(f"  Status: {status}")
        if status == 'PREPARED':
            print("✓ Agent prepared successfully")
            return True
        if status == 'FAILED':
            print("✗ Agent preparation failed")
            return False

    print("✗ Agent preparation timed out after 150 seconds")
    return False


def main():
    """Main deployment flow."""
    print("=" * 60)
    print("SlashMyBill - Deploy Vendor-Neutral Agent Action Groups")
    print("=" * 60)
    print(f"\nAgent ID: {AGENT_ID}")
    print(f"Region:   {REGION}")
    print(f"Lambda:   {LAMBDA_ARN}")
    print()

    project_root = get_project_root()
    succeeded = []
    failed = []

    # Initialize Bedrock Agent client
    client = boto3.client('bedrock-agent', region_name=REGION)

    # Get existing action groups to determine create vs update
    try:
        existing_groups = get_existing_action_groups(client, AGENT_ID)
        print(f"Found {len(existing_groups)} existing action group(s): {list(existing_groups.keys())}\n")
    except Exception as e:
        print(f"✗ Failed to list existing action groups: {e}")
        sys.exit(1)

    # Remove legacy 'FinOpsActions' group if it exists (superseded by vendor-neutral groups)
    if 'FinOpsActions' in existing_groups:
        try:
            print("Removing legacy 'FinOpsActions' action group (superseded by CostAnalysis)...")
            client.delete_agent_action_group(
                agentId=AGENT_ID,
                agentVersion='DRAFT',
                actionGroupId=existing_groups['FinOpsActions'],
                skipResourceInUseCheck=True,
            )
            print("✓ Removed legacy 'FinOpsActions' group")
            del existing_groups['FinOpsActions']
        except Exception as e:
            print(f"  Warning: Could not remove legacy FinOpsActions: {e}")
            # Non-fatal — continue with deployment

    # Deploy each action group
    print("Deploying action groups...")
    print("-" * 40)

    for group_config in ACTION_GROUPS:
        group_name = group_config['name']
        try:
            schema_payload = load_schema(project_root, group_config['schema_file'])
            create_or_update_action_group(client, AGENT_ID, group_config, schema_payload, existing_groups)
            succeeded.append(group_name)
        except FileNotFoundError as e:
            print(f"  ✗ Schema file not found for '{group_name}': {e}")
            failed.append((group_name, str(e)))
        except Exception as e:
            print(f"  ✗ Failed to deploy '{group_name}': {e}")
            failed.append((group_name, str(e)))

    # Report action group results
    print(f"\n{'=' * 40}")
    print(f"Action Groups: {len(succeeded)} succeeded, {len(failed)} failed")
    if succeeded:
        print(f"  Succeeded: {', '.join(succeeded)}")
    if failed:
        print(f"  Failed:")
        for name, error in failed:
            print(f"    - {name}: {error}")

    # If any action group failed, report and exit
    if failed:
        print(f"\n✗ Deployment incomplete. {len(failed)} action group(s) failed.")
        sys.exit(1)

    # Update agent instructions
    try:
        instructions = load_agent_instructions(project_root)
        update_agent_instructions(client, AGENT_ID, instructions)
    except FileNotFoundError as e:
        print(f"\n✗ Agent instructions file not found: {e}")
        print(f"  Succeeded action groups: {', '.join(succeeded)}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Failed to update agent instructions: {e}")
        print(f"  Succeeded action groups: {', '.join(succeeded)}")
        sys.exit(1)

    # Prepare the agent
    try:
        prepared = prepare_agent(client, AGENT_ID)
        if not prepared:
            print(f"\n✗ Agent preparation failed.")
            print(f"  Succeeded action groups: {', '.join(succeeded)}")
            print(f"  Instructions: updated")
            sys.exit(1)
    except Exception as e:
        print(f"\n✗ Failed to prepare agent: {e}")
        print(f"  Succeeded action groups: {', '.join(succeeded)}")
        print(f"  Instructions: updated")
        sys.exit(1)

    # All done
    print(f"\n{'=' * 60}")
    print("✓ Deployment complete!")
    print(f"  - {len(succeeded)} action groups deployed")
    print(f"  - Agent instructions updated")
    print(f"  - Agent prepared (new version ready)")
    print("=" * 60)


if __name__ == '__main__':
    main()
