"""HCL Generator package for Terraform IaC code generation.

Provides HCL serialization primitives and document rendering for generating
valid Terraform configuration files from optimization action parameters.
"""

from hcl_generator.core import (
    HclBlock,
    HclDocument,
    HclRawExpression,
    escape_hcl_string,
    render_provider_block,
)
from hcl_generator.cross_account import (
    generate_cross_account_module,
    generate_cross_account_template,
)
from hcl_generator.models import ActionDefinition


def generate_hcl(blocks, header_comment=""):
    """Generate HCL string from a list of HclBlock instances.

    Args:
        blocks: List of HclBlock instances to render.
        header_comment: Optional header comment to include at the top.

    Returns:
        A string containing valid HCL code.
    """
    doc = HclDocument(blocks=blocks, header_comment=header_comment)
    return doc.render()


__all__ = [
    "ActionDefinition",
    "generate_hcl",
    "generate_cross_account_module",
    "generate_cross_account_template",
    "HclBlock",
    "HclDocument",
    "HclRawExpression",
    "escape_hcl_string",
    "render_provider_block",
]
