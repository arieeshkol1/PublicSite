"""Integration tests asserting deployment IAM policy contents for the
vendor-agnostic AI usage feature.

Feature: vendor-agnostic-ai-usage (Task 11.2)

Validates that the deployment definitions grant exactly the scoped permissions
the design (section 8) requires:
  - cache read+write covering the neutral COST#/USAGE# key families (Req 7.1)
  - ViewMyBill-CostOptimizationTips read for Tier-2 drilldown (Req 7.2)
  - MemberPortal-Invoices read as the drilldown source (Req 7.2 supporting)
  - kms:Decrypt scoped to the credential CMK with {memberEmail, accountId}
    encryption context (Req 7.3)

The policies live in two places (Req 7.4):
  - infrastructure/viewmybill-stack.yaml  (MemberHandlerRole, CloudFormation)
  - .github/workflows/deploy.yml          (SlashMyBill-AgentAction-Role, inline)
"""
import os
import re
import json
import yaml
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STACK_PATH = os.path.join(REPO_ROOT, "infrastructure", "viewmybill-stack.yaml")
DEPLOY_PATH = os.path.join(REPO_ROOT, ".github", "workflows", "deploy.yml")


def _load_cfn(path):
    """Load a CloudFormation YAML template, tolerating the intrinsic-function
    short tags (!GetAtt, !Sub, !Ref, ...) that PyYAML's SafeLoader rejects."""

    class CfnLoader(yaml.SafeLoader):
        pass

    def _any_tag(loader, tag_suffix, node):
        if isinstance(node, yaml.ScalarNode):
            return loader.construct_scalar(node)
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node)
        return loader.construct_mapping(node)

    CfnLoader.add_multi_constructor("!", _any_tag)
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=CfnLoader)


@pytest.fixture(scope="module")
def member_role_policies():
    """Return {PolicyName: PolicyDocument} for the MemberHandlerRole."""
    template = _load_cfn(STACK_PATH)
    role = template["Resources"]["MemberHandlerRole"]
    policies = role["Properties"]["Policies"]
    return {p["PolicyName"]: p["PolicyDocument"] for p in policies}


def _statements(policy_doc):
    stmts = policy_doc["Statement"]
    return stmts if isinstance(stmts, list) else [stmts]


def _actions(stmt):
    a = stmt.get("Action", [])
    return a if isinstance(a, list) else [a]


class TestMemberHandlerCacheReadWrite:
    """Req 7.1 - cache RW covering the neutral COST#/USAGE# key families."""

    def test_cost_cache_policy_present(self, member_role_policies):
        assert "DynamoDBCostCacheAccess" in member_role_policies

    def test_cost_cache_grants_read_and_write_actions(self, member_role_policies):
        actions = set()
        for stmt in _statements(member_role_policies["DynamoDBCostCacheAccess"]):
            actions.update(_actions(stmt))
        # Read+write covering neutral keys: Query, GetItem, PutItem, BatchWriteItem
        for required in (
            "dynamodb:Query",
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:BatchWriteItem",
        ):
            assert required in actions, f"missing {required}"

    def test_cost_cache_targets_cost_cache_table(self, member_role_policies):
        resources = []
        for stmt in _statements(member_role_policies["DynamoDBCostCacheAccess"]):
            res = stmt.get("Resource", [])
            resources.extend(res if isinstance(res, list) else [res])
        joined = json.dumps(resources)
        assert "CostCacheTable" in joined


class TestMemberHandlerTipsRead:
    """Req 7.2 - Tips_Table read for Tier-2 drilldown."""

    def test_tips_policy_present(self, member_role_policies):
        assert "DynamoDBTipsAccess" in member_role_policies

    def test_tips_grants_query_and_getitem(self, member_role_policies):
        actions = set()
        for stmt in _statements(member_role_policies["DynamoDBTipsAccess"]):
            actions.update(_actions(stmt))
        assert "dynamodb:Query" in actions
        assert "dynamodb:GetItem" in actions

    def test_tips_targets_cost_optimization_tips_table(self, member_role_policies):
        resources = []
        for stmt in _statements(member_role_policies["DynamoDBTipsAccess"]):
            res = stmt.get("Resource", [])
            resources.extend(res if isinstance(res, list) else [res])
        assert "CostOptimizationTipsTable" in json.dumps(resources)


class TestMemberHandlerInvoicesRead:
    """Req 7.2 (supporting) - MemberPortal-Invoices read as drilldown source."""

    def test_invoices_policy_present(self, member_role_policies):
        assert "DynamoDBInvoicesCRUDAccess" in member_role_policies

    def test_invoices_grants_query_and_getitem(self, member_role_policies):
        actions = set()
        for stmt in _statements(member_role_policies["DynamoDBInvoicesCRUDAccess"]):
            actions.update(_actions(stmt))
        assert "dynamodb:Query" in actions
        assert "dynamodb:GetItem" in actions

    def test_invoices_targets_invoices_table(self, member_role_policies):
        resources = []
        for stmt in _statements(member_role_policies["DynamoDBInvoicesCRUDAccess"]):
            res = stmt.get("Resource", [])
            resources.extend(res if isinstance(res, list) else [res])
        assert "InvoicesTable" in json.dumps(resources)


class TestMemberHandlerScopedKmsDecrypt:
    """Req 7.3 - kms:Decrypt scoped to the credential CMK with the
    {memberEmail, accountId} encryption context."""

    def test_kms_policy_present(self, member_role_policies):
        assert "KMSCredentialEncryption" in member_role_policies

    def test_grants_kms_decrypt(self, member_role_policies):
        actions = set()
        for stmt in _statements(member_role_policies["KMSCredentialEncryption"]):
            actions.update(_actions(stmt))
        assert "kms:Decrypt" in actions

    def test_targets_credential_cmk(self, member_role_policies):
        resources = []
        for stmt in _statements(member_role_policies["KMSCredentialEncryption"]):
            res = stmt.get("Resource", [])
            resources.extend(res if isinstance(res, list) else [res])
        assert "CredentialEncryptionKey" in json.dumps(resources)

    def test_scoped_to_member_and_account_encryption_context(self, member_role_policies):
        # At least one statement must restrict the allowed encryption-context keys
        # to exactly {memberEmail, accountId}.
        found = False
        for stmt in _statements(member_role_policies["KMSCredentialEncryption"]):
            condition = stmt.get("Condition")
            if not condition:
                continue
            for _op, mapping in condition.items():
                ctx_keys = mapping.get("kms:EncryptionContextKeys")
                if ctx_keys is None:
                    continue
                ctx_keys = ctx_keys if isinstance(ctx_keys, list) else [ctx_keys]
                if set(ctx_keys) == {"memberEmail", "accountId"}:
                    found = True
        assert found, "kms:Decrypt is not scoped to {memberEmail, accountId} context"


class TestDeployWorkflowAgentActionPolicy:
    """Req 7.4 - the IAM changes are also expressed in deploy.yml for the
    AgentAction role (cache RW on neutral keys + Tips/Invoices read)."""

    @pytest.fixture(scope="class")
    def deploy_text(self):
        with open(DEPLOY_PATH, encoding="utf-8") as f:
            return f.read()

    def test_agent_action_policy_includes_invoices_drilldown_source(self, deploy_text):
        # The authoritative (always-run) inline policy update must grant the
        # AgentAction role read of MemberPortal-Invoices.
        assert "table/MemberPortal-Invoices" in deploy_text

    def test_agent_action_policy_includes_cache_and_tips(self, deploy_text):
        assert "table/Cost_Cache_Table" in deploy_text
        assert "table/ViewMyBill-CostOptimizationTips" in deploy_text

    def test_agent_action_policy_grants_neutral_cache_write(self, deploy_text):
        # BatchWriteItem appears in the AgentAction inline policy for neutral
        # write-back. Scope the search to the AgentAction policy region.
        idx = deploy_text.find("AgentActionPermissions")
        assert idx != -1
        region = deploy_text[idx:idx + 2000]
        assert "dynamodb:BatchWriteItem" in region

    def test_deploy_yaml_is_valid(self, deploy_text):
        # deploy.yml uses no CloudFormation intrinsic tags; safe_load must work.
        assert yaml.safe_load(deploy_text) is not None
