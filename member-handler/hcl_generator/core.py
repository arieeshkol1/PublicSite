"""HCL serialization primitives for Terraform code generation.

Provides HclBlock, HclDocument, escape_hcl_string(), and render_provider_block()
for building and rendering valid Terraform HCL configuration files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


INDENT = "  "


def escape_hcl_string(value: str) -> str:
    """Escape special characters per HCL string literal rules.

    Handles:
    - Backslashes (must be escaped first to avoid double-escaping)
    - Double quotes
    - Newlines, carriage returns, tabs
    - ${  interpolation sequences (escaped as $${)
    - %{  template sequences (escaped as %%{)

    Args:
        value: The raw string value to escape.

    Returns:
        The escaped string safe for embedding in HCL double-quoted literals.
    """
    # Backslashes first to avoid double-escaping
    result = value.replace("\\", "\\\\")
    # Double quotes
    result = result.replace('"', '\\"')
    # Newlines, carriage returns, tabs
    result = result.replace("\n", "\\n")
    result = result.replace("\r", "\\r")
    result = result.replace("\t", "\\t")
    # HCL interpolation sequences: ${ must become $${ to prevent interpolation
    result = result.replace("${", "$${")
    # HCL template sequences: %{ must become %%{ to prevent template directives
    result = result.replace("%{", "%%{")
    return result


def _render_value(value: Any, indent_level: int = 0) -> str:
    """Render a Python value as an HCL expression.

    Args:
        value: The value to render (str, int, float, bool, list, dict, or HclRawExpression).
        indent_level: Current indentation level for nested structures.

    Returns:
        HCL expression string.
    """
    if isinstance(value, HclRawExpression):
        return value.expression
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{escape_hcl_string(value)}"'
    if isinstance(value, list):
        if not value:
            return "[]"
        items = []
        for item in value:
            items.append(f"{INDENT * (indent_level + 1)}{_render_value(item, indent_level + 1)}")
        return "[\n" + ",\n".join(items) + f",\n{INDENT * indent_level}]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = []
        for k, v in value.items():
            rendered_val = _render_value(v, indent_level + 1)
            lines.append(f"{INDENT * (indent_level + 1)}{k} = {rendered_val}")
        return "{\n" + "\n".join(lines) + f"\n{INDENT * indent_level}}}"
    return f'"{escape_hcl_string(str(value))}"'


@dataclass
class HclRawExpression:
    """Represents a raw HCL expression that should not be quoted.

    Use this for references, function calls, and other expressions
    that should be rendered verbatim.
    """

    expression: str


@dataclass
class HclBlock:
    """Represents an HCL block (resource, variable, output, etc.).

    Attributes:
        block_type: The block type keyword (e.g., "resource", "variable", "output").
        labels: Block labels (e.g., ["aws_instance", "main"] for resource blocks).
        attributes: Key-value pairs for block attributes.
        nested_blocks: Child HclBlock instances nested within this block.
    """

    block_type: str
    labels: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    nested_blocks: list["HclBlock"] = field(default_factory=list)

    def render(self, indent_level: int = 0) -> str:
        """Render this block as HCL text with 2-space indentation.

        Args:
            indent_level: Current indentation depth.

        Returns:
            Formatted HCL block string.
        """
        prefix = INDENT * indent_level
        inner_prefix = INDENT * (indent_level + 1)

        # Build block header: block_type "label1" "label2" {
        label_parts = " ".join(f'"{label}"' for label in self.labels)
        if label_parts:
            header = f"{prefix}{self.block_type} {label_parts} {{"
        else:
            header = f"{prefix}{self.block_type} {{"

        lines = [header]

        # Render attributes
        for key, value in self.attributes.items():
            rendered_val = _render_value(value, indent_level + 1)
            lines.append(f"{inner_prefix}{key} = {rendered_val}")

        # Render nested blocks
        for i, nested in enumerate(self.nested_blocks):
            if self.attributes or i > 0:
                lines.append("")  # Blank line separator
            lines.append(nested.render(indent_level + 1))

        lines.append(f"{prefix}}}")
        return "\n".join(lines)


@dataclass
class HclDocument:
    """A complete .tf file composed of blocks.

    Attributes:
        blocks: List of top-level HclBlock instances.
        header_comment: Optional comment text to include at the top of the file.
    """

    blocks: list[HclBlock] = field(default_factory=list)
    header_comment: str = ""

    def render(self) -> str:
        """Serialize the document to an HCL string with 2-space indentation.

        Returns:
            Complete HCL file content as a string.
        """
        parts = []

        # Render header comment
        if self.header_comment:
            for line in self.header_comment.splitlines():
                if line.strip():
                    parts.append(f"# {line}")
                else:
                    parts.append("#")
            parts.append("")  # Blank line after header comment

        # Render blocks with blank line separators
        for i, block in enumerate(self.blocks):
            if i > 0:
                parts.append("")  # Blank line between top-level blocks
            parts.append(block.render(indent_level=0))

        # Ensure trailing newline
        result = "\n".join(parts)
        if not result.endswith("\n"):
            result += "\n"
        return result

    @classmethod
    def parse(cls, hcl_string: str) -> "HclDocument":
        """Parse a rendered HCL string back into an HclDocument.

        This is a simplified parser designed for round-trip testing — it only
        needs to handle the HCL that our generator produces (not arbitrary HCL).

        Handles:
        - Block types with labels (resource "type" "name" {})
        - Attributes: string, number, bool, list, map
        - Nested blocks
        - Raw expressions (unquoted values)
        - Header comments (lines starting with #)

        Args:
            hcl_string: A rendered HCL string produced by HclDocument.render().

        Returns:
            An HclDocument with parsed blocks and header comment.
        """
        lines = hcl_string.split("\n")
        header_lines: list[str] = []
        body_lines: list[str] = []

        # Separate header comment from body
        in_header = True
        for line in lines:
            if in_header:
                if line.startswith("#"):
                    # Strip the "# " prefix or just "#"
                    if line == "#":
                        header_lines.append("")
                    elif line.startswith("# "):
                        header_lines.append(line[2:])
                    else:
                        header_lines.append(line[1:])
                elif line.strip() == "" and header_lines:
                    # Blank line after header comment ends the header
                    in_header = False
                else:
                    in_header = False
                    body_lines.append(line)
            else:
                body_lines.append(line)

        header_comment = "\n".join(header_lines) if header_lines else ""

        # Parse blocks from body lines
        blocks = _parse_blocks(body_lines)

        return cls(blocks=blocks, header_comment=header_comment)


# ---------------------------------------------------------------------------
# HCL Parsing Helpers (for round-trip testing)
# ---------------------------------------------------------------------------

# Regex to match a block header line: block_type "label1" "label2" {
_BLOCK_HEADER_RE = re.compile(
    r'^(\s*)'                    # leading indentation
    r'(.+?)'                     # block type (greedy minimal up to labels or {)
    r'\s*\{\s*$'                 # opening brace
)

# Regex to extract quoted labels from a block header
_LABEL_RE = re.compile(r'"([^"]*)"')

# Regex to match an attribute line: key = value
_ATTR_RE = re.compile(r'^(\s*)(\w+)\s*=\s*(.+)$')


def _parse_blocks(lines: list[str]) -> list[HclBlock]:
    """Parse a list of lines into top-level HclBlock instances.

    Args:
        lines: Lines of HCL body text (no header comments).

    Returns:
        List of parsed HclBlock instances.
    """
    blocks: list[HclBlock] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Skip blank lines between blocks
        if line.strip() == "":
            i += 1
            continue
        # Try to parse a block starting at this line
        block, end_idx = _parse_single_block(lines, i)
        if block is not None:
            blocks.append(block)
            i = end_idx + 1
        else:
            i += 1
    return blocks


def _parse_single_block(lines: list[str], start: int) -> tuple[HclBlock | None, int]:
    """Parse a single block starting at the given line index.

    Args:
        lines: All lines.
        start: Index of the block header line.

    Returns:
        Tuple of (parsed HclBlock or None, index of closing brace line).
    """
    header_line = lines[start]
    match = _BLOCK_HEADER_RE.match(header_line)
    if not match:
        return None, start

    indent = match.group(1)
    header_content = match.group(2).strip()

    # Extract labels from the header content
    labels = _LABEL_RE.findall(header_content)

    # Determine block_type: everything before the first quoted label
    # For "resource "aws_instance" "main"" -> block_type = "resource"
    # For 'provider "aws"' -> block_type = 'provider "aws"'
    # For "terraform" -> block_type = "terraform"
    block_type = _extract_block_type(header_content, labels)

    # Find the matching closing brace at the same indentation level
    closing_brace = f"{indent}}}"
    attributes: dict[str, Any] = {}
    nested_blocks: list[HclBlock] = []

    i = start + 1
    while i < len(lines):
        line = lines[i]

        # Check for closing brace at the expected indentation
        if line == closing_brace:
            return HclBlock(
                block_type=block_type,
                labels=labels,
                attributes=attributes,
                nested_blocks=nested_blocks,
            ), i

        # Skip blank lines (separators between attrs and nested blocks)
        if line.strip() == "":
            i += 1
            continue

        # Try to parse as an attribute FIRST (before nested block check)
        # This is important because "key = {" looks like a block header
        # but is actually a map attribute
        attr_match = _ATTR_RE.match(line)
        if attr_match:
            key = attr_match.group(2)
            value_str = attr_match.group(3)
            # Parse the value - may span multiple lines (lists, maps)
            value, end_idx = _parse_value(lines, i, value_str)
            attributes[key] = value
            i = end_idx + 1
            continue

        # Try to parse as a nested block
        nested_match = _BLOCK_HEADER_RE.match(line)
        if nested_match:
            nested_block, end_idx = _parse_single_block(lines, i)
            if nested_block is not None:
                nested_blocks.append(nested_block)
                i = end_idx + 1
                continue

        # Unknown line, skip
        i += 1

    # If we reach here without finding closing brace, return what we have
    return HclBlock(
        block_type=block_type,
        labels=labels,
        attributes=attributes,
        nested_blocks=nested_blocks,
    ), len(lines) - 1


def _extract_block_type(header_content: str, labels: list[str]) -> str:
    """Extract the block type from header content.

    For blocks like 'provider "aws"', the block type includes the quoted part
    that is part of the type itself (not a label in the HclBlock sense).

    Our generator uses two patterns:
    - Standard blocks: resource "aws_instance" "main" -> type="resource", labels=["aws_instance", "main"]
    - Provider blocks: provider "aws" -> type='provider "aws"', labels=[]

    We detect this by looking at how the original code renders blocks:
    - If block_type contains a quote, it's rendered as-is (e.g., 'provider "aws"')
    - Otherwise, labels are rendered separately

    For parsing, we need to figure out which labels belong to the block_type
    vs which are actual labels. The heuristic: if the first word is "provider",
    the first label is part of the block_type.
    """
    if not labels:
        return header_content.strip()

    # Find position of first quote in header_content
    first_quote_pos = header_content.find('"')
    if first_quote_pos < 0:
        return header_content.strip()

    # Get the keyword before the first quote
    keyword = header_content[:first_quote_pos].strip()

    # Standard block types that use labels normally
    standard_block_types = {
        "resource", "variable", "output", "data", "module",
        "import", "removed", "moved", "locals",
    }

    if keyword.lower() in standard_block_types:
        return keyword
    else:
        # The block type includes quoted parts (e.g., 'provider "aws"')
        # Reconstruct: keyword "first_label"
        if labels:
            block_type = f'{keyword} "{labels[0]}"'
            # Remove the first label from the labels list since it's part of block_type
            labels.pop(0)
            return block_type
        return keyword


def _parse_value(lines: list[str], line_idx: int, value_str: str) -> tuple[Any, int]:
    """Parse an attribute value that may span multiple lines.

    Args:
        lines: All lines.
        line_idx: Current line index.
        value_str: The value portion from the attribute line.

    Returns:
        Tuple of (parsed value, last line index consumed).
    """
    value_str = value_str.rstrip()

    # Boolean
    if value_str == "true":
        return True, line_idx
    if value_str == "false":
        return False, line_idx

    # Quoted string
    if value_str.startswith('"') and value_str.endswith('"'):
        return _unescape_hcl_string(value_str[1:-1]), line_idx

    # Empty list
    if value_str == "[]":
        return [], line_idx

    # Empty map
    if value_str == "{}":
        return {}, line_idx

    # Multi-line list starting with [
    if value_str == "[":
        return _parse_multiline_list(lines, line_idx)

    # Multi-line map starting with {
    if value_str == "{":
        return _parse_multiline_map(lines, line_idx)

    # Number (int or float)
    try:
        if "." in value_str:
            return float(value_str), line_idx
        return int(value_str), line_idx
    except ValueError:
        pass

    # Raw expression (anything else - references, function calls, etc.)
    return HclRawExpression(value_str), line_idx


def _parse_multiline_list(lines: list[str], start_idx: int) -> tuple[list, int]:
    """Parse a multi-line list value.

    Args:
        lines: All lines.
        start_idx: Line index where the list starts (the line with `[`).

    Returns:
        Tuple of (parsed list, last line index consumed).
    """
    items: list[Any] = []
    i = start_idx + 1
    while i < len(lines):
        line = lines[i].strip()

        # End of list
        if line.startswith("]"):
            return items, i

        # Remove trailing comma
        if line.endswith(","):
            line = line[:-1].strip()

        if not line:
            i += 1
            continue

        # Parse the item value
        if line.startswith('"') and line.endswith('"'):
            items.append(_unescape_hcl_string(line[1:-1]))
        elif line == "true":
            items.append(True)
        elif line == "false":
            items.append(False)
        elif line == "[":
            sub_list, end_idx = _parse_multiline_list(lines, i)
            items.append(sub_list)
            i = end_idx
        elif line == "{":
            sub_map, end_idx = _parse_multiline_map(lines, i)
            items.append(sub_map)
            i = end_idx
        else:
            try:
                if "." in line:
                    items.append(float(line))
                else:
                    items.append(int(line))
            except ValueError:
                items.append(HclRawExpression(line))

        i += 1

    return items, len(lines) - 1


def _parse_multiline_map(lines: list[str], start_idx: int) -> tuple[dict, int]:
    """Parse a multi-line map value.

    Args:
        lines: All lines.
        start_idx: Line index where the map starts (the line with `{`).

    Returns:
        Tuple of (parsed dict, last line index consumed).
    """
    result: dict[str, Any] = {}
    i = start_idx + 1
    while i < len(lines):
        line = lines[i].strip()

        # End of map
        if line == "}" or line.startswith("}"):
            return result, i

        if not line:
            i += 1
            continue

        # Parse key = value
        map_attr_match = re.match(r'^(\w+)\s*=\s*(.+)$', line)
        if map_attr_match:
            key = map_attr_match.group(1)
            val_str = map_attr_match.group(2).rstrip()
            value, end_idx = _parse_value(lines, i, val_str)
            result[key] = value
            i = end_idx + 1
        else:
            i += 1

    return result, len(lines) - 1


def _unescape_hcl_string(escaped: str) -> str:
    """Unescape an HCL string literal back to its original value.

    Reverses the escaping done by escape_hcl_string().

    Args:
        escaped: The escaped string content (without surrounding quotes).

    Returns:
        The original unescaped string.
    """
    result = []
    i = 0
    while i < len(escaped):
        if escaped[i] == "\\" and i + 1 < len(escaped):
            next_char = escaped[i + 1]
            if next_char == "\\":
                result.append("\\")
                i += 2
            elif next_char == '"':
                result.append('"')
                i += 2
            elif next_char == "n":
                result.append("\n")
                i += 2
            elif next_char == "r":
                result.append("\r")
                i += 2
            elif next_char == "t":
                result.append("\t")
                i += 2
            else:
                result.append(escaped[i])
                i += 1
        elif escaped[i] == "$" and i + 1 < len(escaped) and escaped[i + 1] == "$":
            # $${ -> ${
            if i + 2 < len(escaped) and escaped[i + 2] == "{":
                result.append("${")
                i += 3
            else:
                result.append(escaped[i])
                i += 1
        elif escaped[i] == "%" and i + 1 < len(escaped) and escaped[i + 1] == "%":
            # %%{ -> %{
            if i + 2 < len(escaped) and escaped[i + 2] == "{":
                result.append("%{")
                i += 3
            else:
                result.append(escaped[i])
                i += 1
        else:
            result.append(escaped[i])
            i += 1
    return "".join(result)


def render_provider_block(region: str, account_id: str, role_name: str = "SlashMyBill") -> HclBlock:
    """Generate a provider "aws" block with assume_role configuration.

    Args:
        region: AWS region (e.g., "us-east-1").
        account_id: The AWS account ID to assume role in.
        role_name: The role name prefix (default "SlashMyBill").

    Returns:
        An HclBlock representing the provider configuration.
    """
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}-{account_id}"

    assume_role_block = HclBlock(
        block_type="assume_role",
        labels=[],
        attributes={
            "role_arn": role_arn,
        },
    )

    provider_block = HclBlock(
        block_type='provider "aws"',
        labels=[],
        attributes={
            "region": region,
        },
        nested_blocks=[assume_role_block],
    )

    return provider_block
