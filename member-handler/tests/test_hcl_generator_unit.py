"""Unit tests for hcl_generator core module.

Tests cover:
- HCL string escaping (quotes, backslashes, interpolation sequences)
- HclBlock rendering with attributes and nesting
- HclDocument rendering with header comments
- render_provider_block() output
- generate_hcl() top-level function
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hcl_generator import generate_hcl
from hcl_generator.core import (
    HclBlock,
    HclDocument,
    HclRawExpression,
    escape_hcl_string,
    render_provider_block,
)


class TestEscapeHclString:
    """Tests for escape_hcl_string()."""

    def test_plain_string_unchanged(self):
        assert escape_hcl_string("hello world") == "hello world"

    def test_escapes_double_quotes(self):
        assert escape_hcl_string('say "hello"') == 'say \\"hello\\"'

    def test_escapes_backslashes(self):
        assert escape_hcl_string("path\\to\\file") == "path\\\\to\\\\file"

    def test_escapes_newlines(self):
        assert escape_hcl_string("line1\nline2") == "line1\\nline2"

    def test_escapes_carriage_return(self):
        assert escape_hcl_string("line1\rline2") == "line1\\rline2"

    def test_escapes_tabs(self):
        assert escape_hcl_string("col1\tcol2") == "col1\\tcol2"

    def test_escapes_interpolation_sequence(self):
        """${...} must become $${...} to prevent HCL interpolation."""
        assert escape_hcl_string("value is ${var.name}") == "value is $${var.name}"

    def test_escapes_template_sequence(self):
        """%{...} must become %%{...} to prevent HCL template directives."""
        assert escape_hcl_string("check %{if x}yes%{endif}") == "check %%{if x}yes%%{endif}"

    def test_combined_special_characters(self):
        """Multiple special characters in one string."""
        input_str = 'path\\to\n"${file}"'
        expected = 'path\\\\to\\n\\"$${file}\\"'
        assert escape_hcl_string(input_str) == expected

    def test_empty_string(self):
        assert escape_hcl_string("") == ""

    def test_dollar_without_brace_not_escaped(self):
        """A lone $ without { should not be escaped."""
        assert escape_hcl_string("cost is $100") == "cost is $100"

    def test_percent_without_brace_not_escaped(self):
        """A lone % without { should not be escaped."""
        assert escape_hcl_string("100% done") == "100% done"

    def test_backslash_before_interpolation(self):
        """Backslash followed by ${ should escape both correctly."""
        result = escape_hcl_string("\\${foo}")
        # Backslash becomes \\, then ${ becomes $${
        assert result == "\\\\$${foo}"


class TestHclBlockRendering:
    """Tests for HclBlock.render()."""

    def test_simple_block_no_labels(self):
        block = HclBlock(
            block_type="terraform",
            attributes={"required_version": ">= 1.5"},
        )
        result = block.render()
        assert 'terraform {' in result
        assert '  required_version = ">= 1.5"' in result
        assert result.endswith("}")

    def test_block_with_single_label(self):
        block = HclBlock(
            block_type="variable",
            labels=["account_id"],
            attributes={
                "type": HclRawExpression("string"),
                "description": "AWS Account ID",
            },
        )
        result = block.render()
        assert 'variable "account_id" {' in result
        assert "  type = string" in result
        assert '  description = "AWS Account ID"' in result

    def test_block_with_two_labels(self):
        block = HclBlock(
            block_type="resource",
            labels=["aws_instance", "main"],
            attributes={
                "instance_type": "t3.medium",
                "ami": "ami-12345678",
            },
        )
        result = block.render()
        assert 'resource "aws_instance" "main" {' in result
        assert '  instance_type = "t3.medium"' in result
        assert '  ami = "ami-12345678"' in result

    def test_nested_blocks(self):
        inner = HclBlock(
            block_type="assume_role",
            attributes={"role_arn": "arn:aws:iam::123456789012:role/MyRole"},
        )
        outer = HclBlock(
            block_type='provider "aws"',
            attributes={"region": "us-east-1"},
            nested_blocks=[inner],
        )
        result = outer.render()
        assert 'provider "aws" {' in result
        assert '  region = "us-east-1"' in result
        assert "  assume_role {" in result
        assert '    role_arn = "arn:aws:iam::123456789012:role/MyRole"' in result
        assert "  }" in result

    def test_boolean_attributes(self):
        block = HclBlock(
            block_type="resource",
            labels=["aws_instance", "test"],
            attributes={
                "monitoring": True,
                "disable_api_termination": False,
            },
        )
        result = block.render()
        assert "  monitoring = true" in result
        assert "  disable_api_termination = false" in result

    def test_numeric_attributes(self):
        block = HclBlock(
            block_type="resource",
            labels=["aws_ebs_volume", "data"],
            attributes={
                "size": 100,
                "iops": 3000,
            },
        )
        result = block.render()
        assert "  size = 100" in result
        assert "  iops = 3000" in result

    def test_list_attribute(self):
        block = HclBlock(
            block_type="variable",
            labels=["tags"],
            attributes={
                "default": ["web", "production"],
            },
        )
        result = block.render()
        assert "  default = [" in result
        assert '    "web",' in result
        assert '    "production",' in result
        assert "  ]" in result

    def test_map_attribute(self):
        block = HclBlock(
            block_type="resource",
            labels=["aws_instance", "main"],
            attributes={
                "tags": {"Name": "my-instance", "Environment": "prod"},
            },
        )
        result = block.render()
        assert "  tags = {" in result
        assert '    Name = "my-instance"' in result
        assert '    Environment = "prod"' in result
        assert "  }" in result

    def test_raw_expression_not_quoted(self):
        block = HclBlock(
            block_type="output",
            labels=["role_arn"],
            attributes={
                "value": HclRawExpression("aws_iam_role.slashmybill.arn"),
            },
        )
        result = block.render()
        assert "  value = aws_iam_role.slashmybill.arn" in result

    def test_indentation_uses_two_spaces(self):
        inner = HclBlock(
            block_type="nested",
            attributes={"key": "val"},
        )
        outer = HclBlock(
            block_type="outer",
            nested_blocks=[inner],
        )
        result = outer.render()
        lines = result.split("\n")
        # outer block at level 0
        assert lines[0] == "outer {"
        # nested block at level 1 (2 spaces) - no blank separator when no attributes
        assert lines[1] == "  nested {"
        # attribute at level 2 (4 spaces)
        assert lines[2] == '    key = "val"'
        assert lines[3] == "  }"
        assert lines[4] == "}"

    def test_indentation_with_attrs_and_nested(self):
        """Blank line separates attributes from nested blocks."""
        inner = HclBlock(
            block_type="nested",
            attributes={"inner_key": "inner_val"},
        )
        outer = HclBlock(
            block_type="outer",
            attributes={"outer_key": "outer_val"},
            nested_blocks=[inner],
        )
        result = outer.render()
        lines = result.split("\n")
        assert lines[0] == "outer {"
        assert lines[1] == '  outer_key = "outer_val"'
        assert lines[2] == ""  # blank separator between attrs and nested
        assert lines[3] == "  nested {"
        assert lines[4] == '    inner_key = "inner_val"'
        assert lines[5] == "  }"
        assert lines[6] == "}"

    def test_empty_list_renders_inline(self):
        block = HclBlock(
            block_type="variable",
            labels=["empty"],
            attributes={"default": []},
        )
        result = block.render()
        assert "  default = []" in result

    def test_empty_map_renders_inline(self):
        block = HclBlock(
            block_type="variable",
            labels=["empty_map"],
            attributes={"default": {}},
        )
        result = block.render()
        assert "  default = {}" in result


class TestHclDocument:
    """Tests for HclDocument rendering."""

    def test_single_block_document(self):
        block = HclBlock(
            block_type="terraform",
            attributes={"required_version": ">= 1.5"},
        )
        doc = HclDocument(blocks=[block])
        result = doc.render()
        assert result.startswith("terraform {")
        assert result.endswith("}\n")

    def test_header_comment(self):
        doc = HclDocument(
            blocks=[HclBlock(block_type="terraform")],
            header_comment="Generated by SlashMyBill\nDo not edit manually",
        )
        result = doc.render()
        lines = result.split("\n")
        assert lines[0] == "# Generated by SlashMyBill"
        assert lines[1] == "# Do not edit manually"
        assert lines[2] == ""  # Blank line after comment

    def test_multiple_blocks_separated_by_blank_lines(self):
        blocks = [
            HclBlock(block_type="terraform"),
            HclBlock(block_type='provider "aws"', attributes={"region": "us-east-1"}),
        ]
        doc = HclDocument(blocks=blocks)
        result = doc.render()
        # Should have a blank line between blocks
        assert "}\n\nprovider" in result

    def test_trailing_newline(self):
        doc = HclDocument(blocks=[HclBlock(block_type="terraform")])
        result = doc.render()
        assert result.endswith("\n")

    def test_empty_document(self):
        doc = HclDocument()
        result = doc.render()
        assert result == "\n"

    def test_header_with_empty_lines(self):
        doc = HclDocument(
            blocks=[HclBlock(block_type="terraform")],
            header_comment="Line 1\n\nLine 3",
        )
        result = doc.render()
        lines = result.split("\n")
        assert lines[0] == "# Line 1"
        assert lines[1] == "#"
        assert lines[2] == "# Line 3"


class TestRenderProviderBlock:
    """Tests for render_provider_block()."""

    def test_basic_provider_block(self):
        block = render_provider_block(
            region="us-east-1",
            account_id="123456789012",
        )
        result = block.render()
        assert 'provider "aws" {' in result
        assert '  region = "us-east-1"' in result
        assert "  assume_role {" in result
        assert '    role_arn = "arn:aws:iam::123456789012:role/SlashMyBill-123456789012"' in result

    def test_custom_role_name(self):
        block = render_provider_block(
            region="eu-west-1",
            account_id="987654321098",
            role_name="CustomRole",
        )
        result = block.render()
        assert '  region = "eu-west-1"' in result
        assert '    role_arn = "arn:aws:iam::987654321098:role/CustomRole-987654321098"' in result

    def test_provider_block_structure(self):
        block = render_provider_block(region="us-west-2", account_id="111222333444")
        # Should be a provider block with nested assume_role
        assert block.block_type == 'provider "aws"'
        assert block.attributes["region"] == "us-west-2"
        assert len(block.nested_blocks) == 1
        assert block.nested_blocks[0].block_type == "assume_role"


class TestGenerateHcl:
    """Tests for the top-level generate_hcl() function."""

    def test_generates_valid_hcl_string(self):
        blocks = [
            HclBlock(
                block_type="resource",
                labels=["aws_instance", "example"],
                attributes={"instance_type": "t3.micro"},
            )
        ]
        result = generate_hcl(blocks)
        assert 'resource "aws_instance" "example" {' in result
        assert '  instance_type = "t3.micro"' in result
        assert result.endswith("}\n")

    def test_with_header_comment(self):
        blocks = [HclBlock(block_type="terraform")]
        result = generate_hcl(blocks, header_comment="Auto-generated")
        assert result.startswith("# Auto-generated\n")

    def test_empty_blocks_list(self):
        result = generate_hcl([])
        assert result == "\n"

    def test_full_document_structure(self):
        """Test a realistic multi-block document."""
        terraform_block = HclBlock(
            block_type="terraform",
            nested_blocks=[
                HclBlock(
                    block_type="required_providers",
                    nested_blocks=[
                        HclBlock(
                            block_type="aws",
                            attributes={
                                "source": "hashicorp/aws",
                                "version": ">= 5.0",
                            },
                        )
                    ],
                )
            ],
        )
        provider_block = render_provider_block("us-east-1", "123456789012")
        resource_block = HclBlock(
            block_type="resource",
            labels=["aws_instance", "main"],
            attributes={
                "instance_type": "t3.medium",
                "tags": {"Name": "my-server"},
            },
        )

        result = generate_hcl(
            [terraform_block, provider_block, resource_block],
            header_comment="Generated by SlashMyBill",
        )

        assert "# Generated by SlashMyBill" in result
        assert "terraform {" in result
        assert "required_providers {" in result
        assert 'source = "hashicorp/aws"' in result
        assert 'provider "aws" {' in result
        assert 'resource "aws_instance" "main" {' in result
        assert '  instance_type = "t3.medium"' in result
        assert '    Name = "my-server"' in result
