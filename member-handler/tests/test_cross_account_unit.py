"""Unit tests for hcl_generator.cross_account module.

Tests cover:
- Template contains required_providers block
- Template contains variable blocks with correct defaults
- Template contains aws_iam_role resource with correct trust policy
- ExternalId matches SHA-256 of email
- Template contains output block
- Template contains provider block with assume_role
"""

import hashlib
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hcl_generator.cross_account import (
    generate_cross_account_template,
    _compute_external_id,
)


class TestRequiredProviders:
    """Template contains required_providers block with AWS provider."""

    def test_contains_terraform_block(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "terraform {" in result

    def test_contains_required_providers(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "required_providers {" in result

    def test_contains_aws_provider_source(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert 'source = "hashicorp/aws"' in result

    def test_contains_aws_provider_version_constraint(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert 'version = ">= 5.0"' in result


class TestVariableBlocks:
    """Template contains variable blocks with correct defaults."""

    def test_contains_account_id_variable(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert 'variable "account_id" {' in result

    def test_account_id_default_matches_input(self):
        doc = generate_cross_account_template("987654321098", "user@example.com")
        result = doc.render()
        assert 'default = "987654321098"' in result

    def test_contains_platform_account_id_variable(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert 'variable "platform_account_id" {' in result

    def test_platform_account_id_default(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert 'default = "991105135552"' in result

    def test_custom_platform_account_id(self):
        doc = generate_cross_account_template(
            "123456789012", "user@example.com", platform_account_id="111222333444"
        )
        result = doc.render()
        assert 'default = "111222333444"' in result

    def test_variables_have_type_string(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "type = string" in result

    def test_variables_have_descriptions(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "description" in result


class TestIamRoleResource:
    """Template contains aws_iam_role resource with correct trust policy."""

    def test_contains_iam_role_resource(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert 'resource "aws_iam_role" "slashmybill" {' in result

    def test_role_name_includes_account_id(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert 'name = "SlashMyBill-123456789012"' in result

    def test_trust_policy_references_platform_account(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "var.platform_account_id" in result

    def test_trust_policy_contains_sts_assume_role(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "sts:AssumeRole" in result

    def test_trust_policy_contains_external_id_condition(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "sts:ExternalId" in result

    def test_trust_policy_contains_string_equals_condition(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "StringEquals" in result


class TestExternalIdSha256:
    """ExternalId matches SHA-256 of email."""

    def test_external_id_is_sha256_of_email(self):
        email = "user@example.com"
        expected_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
        doc = generate_cross_account_template("123456789012", email)
        result = doc.render()
        assert expected_hash in result

    def test_external_id_different_for_different_emails(self):
        doc1 = generate_cross_account_template("123456789012", "alice@example.com")
        doc2 = generate_cross_account_template("123456789012", "bob@example.com")
        result1 = doc1.render()
        result2 = doc2.render()
        hash1 = hashlib.sha256("alice@example.com".encode("utf-8")).hexdigest()
        hash2 = hashlib.sha256("bob@example.com".encode("utf-8")).hexdigest()
        assert hash1 in result1
        assert hash2 in result2
        assert hash1 != hash2

    def test_compute_external_id_helper(self):
        email = "test@domain.org"
        expected = hashlib.sha256(email.encode("utf-8")).hexdigest()
        assert _compute_external_id(email) == expected

    def test_external_id_is_64_hex_chars(self):
        result = _compute_external_id("any@email.com")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


class TestOutputBlock:
    """Template contains output block exposing role ARN."""

    def test_contains_output_block(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert 'output "role_arn" {' in result

    def test_output_references_role_arn(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "aws_iam_role.slashmybill.arn" in result

    def test_output_has_description(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "description" in result


class TestProviderBlock:
    """Template contains provider block with assume_role."""

    def test_contains_provider_aws_block(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert 'provider "aws" {' in result

    def test_provider_has_region(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert 'region = "us-east-1"' in result

    def test_provider_has_assume_role(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "assume_role {" in result

    def test_assume_role_has_correct_role_arn(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "arn:aws:iam::123456789012:role/SlashMyBill-123456789012" in result

    def test_assume_role_arn_uses_account_id(self):
        doc = generate_cross_account_template("999888777666", "user@example.com")
        result = doc.render()
        assert "arn:aws:iam::999888777666:role/SlashMyBill-999888777666" in result


class TestPolicyAttachmentAndInlinePolicy:
    """Template contains policy attachment and inline policy resources."""

    def test_contains_policy_attachment_resource(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert 'resource "aws_iam_role_policy_attachment" "readonly" {' in result

    def test_policy_attachment_references_readonly_access(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "arn:aws:iam::aws:policy/ReadOnlyAccess" in result

    def test_policy_attachment_references_role(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "aws_iam_role.slashmybill.name" in result

    def test_contains_inline_policy_resource(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert 'resource "aws_iam_role_policy" "billing_access" {' in result

    def test_inline_policy_has_billing_actions(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "ce:GetCostAndUsage" in result
        assert "budgets:ViewBudget" in result

    def test_inline_policy_references_role(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "aws_iam_role.slashmybill.id" in result


class TestHeaderComment:
    """Template includes a header comment."""

    def test_header_contains_slashmybill(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "# Generated by SlashMyBill" in result

    def test_header_contains_account_id(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "# Account: 123456789012" in result

    def test_header_contains_warning(self):
        doc = generate_cross_account_template("123456789012", "user@example.com")
        result = doc.render()
        assert "WARNING" in result


# --- Tests for generate_cross_account_module() ---

import zipfile
import io

from hcl_generator.cross_account import generate_cross_account_module


class TestModuleZipContents:
    """ZIP contains main.tf, variables.tf, outputs.tf, README.md."""

    def test_returns_bytes(self):
        result = generate_cross_account_module("123456789012", "user@example.com")
        assert isinstance(result, bytes)

    def test_is_valid_zip(self):
        result = generate_cross_account_module("123456789012", "user@example.com")
        buffer = io.BytesIO(result)
        assert zipfile.is_zipfile(buffer)

    def test_contains_main_tf(self):
        result = generate_cross_account_module("123456789012", "user@example.com")
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert "main.tf" in zf.namelist()

    def test_contains_variables_tf(self):
        result = generate_cross_account_module("123456789012", "user@example.com")
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert "variables.tf" in zf.namelist()

    def test_contains_outputs_tf(self):
        result = generate_cross_account_module("123456789012", "user@example.com")
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert "outputs.tf" in zf.namelist()

    def test_contains_readme_md(self):
        result = generate_cross_account_module("123456789012", "user@example.com")
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert "README.md" in zf.namelist()

    def test_contains_exactly_four_files(self):
        result = generate_cross_account_module("123456789012", "user@example.com")
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert len(zf.namelist()) == 4


class TestModuleVariablesTf:
    """variables.tf has account_id, platform_account_id, external_id."""

    def _get_variables_tf(self, account_id="123456789012", email="user@example.com"):
        result = generate_cross_account_module(account_id, email)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            return zf.read("variables.tf").decode("utf-8")

    def test_has_account_id_variable(self):
        content = self._get_variables_tf()
        assert 'variable "account_id" {' in content

    def test_has_platform_account_id_variable(self):
        content = self._get_variables_tf()
        assert 'variable "platform_account_id" {' in content

    def test_has_external_id_variable(self):
        content = self._get_variables_tf()
        assert 'variable "external_id" {' in content

    def test_platform_account_id_has_default(self):
        content = self._get_variables_tf()
        assert 'default = "991105135552"' in content

    def test_account_id_has_no_default(self):
        """account_id is required - should not have a default value."""
        content = self._get_variables_tf()
        # Find the account_id variable block and check it has no default
        lines = content.split("\n")
        in_account_id_block = False
        brace_depth = 0
        account_id_block_lines = []
        for line in lines:
            if 'variable "account_id"' in line:
                in_account_id_block = True
                brace_depth = 0
            if in_account_id_block:
                account_id_block_lines.append(line)
                brace_depth += line.count("{") - line.count("}")
                if brace_depth == 0 and len(account_id_block_lines) > 1:
                    break
        account_id_block = "\n".join(account_id_block_lines)
        assert "default" not in account_id_block

    def test_all_variables_have_type_string(self):
        content = self._get_variables_tf()
        assert content.count("type = string") == 3

    def test_all_variables_have_descriptions(self):
        content = self._get_variables_tf()
        assert content.count("description") >= 3


class TestModuleExternalIdSensitive:
    """external_id is marked sensitive."""

    def _get_variables_tf(self, email="user@example.com"):
        result = generate_cross_account_module("123456789012", email)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            return zf.read("variables.tf").decode("utf-8")

    def test_external_id_is_sensitive(self):
        content = self._get_variables_tf()
        # Find the external_id variable block
        lines = content.split("\n")
        in_external_id_block = False
        brace_depth = 0
        external_id_block_lines = []
        for line in lines:
            if 'variable "external_id"' in line:
                in_external_id_block = True
                brace_depth = 0
            if in_external_id_block:
                external_id_block_lines.append(line)
                brace_depth += line.count("{") - line.count("}")
                if brace_depth == 0 and len(external_id_block_lines) > 1:
                    break
        external_id_block = "\n".join(external_id_block_lines)
        assert "sensitive = true" in external_id_block


class TestModuleOutputsTf:
    """outputs.tf has role_arn and role_name."""

    def _get_outputs_tf(self):
        result = generate_cross_account_module("123456789012", "user@example.com")
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            return zf.read("outputs.tf").decode("utf-8")

    def test_has_role_arn_output(self):
        content = self._get_outputs_tf()
        assert 'output "role_arn" {' in content

    def test_has_role_name_output(self):
        content = self._get_outputs_tf()
        assert 'output "role_name" {' in content

    def test_role_arn_references_iam_role(self):
        content = self._get_outputs_tf()
        assert "aws_iam_role.slashmybill.arn" in content

    def test_role_name_references_iam_role(self):
        content = self._get_outputs_tf()
        assert "aws_iam_role.slashmybill.name" in content

    def test_outputs_have_descriptions(self):
        content = self._get_outputs_tf()
        assert content.count("description") >= 2


class TestModuleReadme:
    """README.md contains usage examples."""

    def _get_readme(self, account_id="123456789012", email="user@example.com"):
        result = generate_cross_account_module(account_id, email)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            return zf.read("README.md").decode("utf-8")

    def test_readme_contains_usage_section(self):
        content = self._get_readme()
        assert "## Usage" in content

    def test_readme_contains_module_block_example(self):
        content = self._get_readme()
        assert "module" in content
        assert "source" in content

    def test_readme_contains_account_id_in_example(self):
        content = self._get_readme(account_id="987654321098")
        assert "987654321098" in content

    def test_readme_contains_outputs_section(self):
        content = self._get_readme()
        assert "role_arn" in content
        assert "role_name" in content

    def test_readme_contains_variables_section(self):
        content = self._get_readme()
        assert "## Variables" in content
        assert "account_id" in content
        assert "platform_account_id" in content
        assert "external_id" in content

    def test_readme_contains_output_reference_example(self):
        content = self._get_readme()
        assert "module.slashmybill_role.role_arn" in content


class TestModuleExternalIdDefault:
    """external_id default is SHA-256 of member email."""

    def test_external_id_default_is_sha256_of_email(self):
        email = "user@example.com"
        expected_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
        result = generate_cross_account_module("123456789012", email)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            variables_content = zf.read("variables.tf").decode("utf-8")
        assert expected_hash in variables_content

    def test_external_id_default_changes_with_email(self):
        hash1 = hashlib.sha256("alice@example.com".encode("utf-8")).hexdigest()
        hash2 = hashlib.sha256("bob@example.com".encode("utf-8")).hexdigest()

        result1 = generate_cross_account_module("123456789012", "alice@example.com")
        result2 = generate_cross_account_module("123456789012", "bob@example.com")

        with zipfile.ZipFile(io.BytesIO(result1)) as zf:
            vars1 = zf.read("variables.tf").decode("utf-8")
        with zipfile.ZipFile(io.BytesIO(result2)) as zf:
            vars2 = zf.read("variables.tf").decode("utf-8")

        assert hash1 in vars1
        assert hash2 in vars2
        assert hash1 != hash2

    def test_external_id_default_in_readme(self):
        email = "test@domain.org"
        expected_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
        result = generate_cross_account_module("123456789012", email)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            readme_content = zf.read("README.md").decode("utf-8")
        assert expected_hash in readme_content


class TestModuleMainTf:
    """main.tf contains role resource, policy attachment, and inline policy."""

    def _get_main_tf(self):
        result = generate_cross_account_module("123456789012", "user@example.com")
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            return zf.read("main.tf").decode("utf-8")

    def test_contains_iam_role_resource(self):
        content = self._get_main_tf()
        assert 'resource "aws_iam_role" "slashmybill" {' in content

    def test_contains_policy_attachment(self):
        content = self._get_main_tf()
        assert 'resource "aws_iam_role_policy_attachment" "readonly" {' in content

    def test_contains_inline_policy(self):
        content = self._get_main_tf()
        assert 'resource "aws_iam_role_policy" "billing_access" {' in content

    def test_contains_required_providers(self):
        content = self._get_main_tf()
        assert "terraform {" in content
        assert "required_providers {" in content

    def test_role_uses_variable_reference(self):
        content = self._get_main_tf()
        assert "var.account_id" in content

    def test_trust_policy_uses_external_id_variable(self):
        content = self._get_main_tf()
        assert "var.external_id" in content

    def test_trust_policy_uses_platform_account_id_variable(self):
        content = self._get_main_tf()
        assert "var.platform_account_id" in content
