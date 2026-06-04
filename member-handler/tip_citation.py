"""
Tip Citation Module - Builds prompt instructions for tip citations in AI responses.

When tips are found for a query, this module generates a prompt instruction
requiring the Bedrock model to cite at least one relevant tip using the
"💡 Tip:" prefix format. When no tips match, it returns an empty string
so the citation instruction is omitted from the prompt.
"""


def build_tip_citation_prompt(tips: list) -> str:
    """Build the tip citation instruction text for the Bedrock prompt.

    Accepts a list of tips and returns a prompt instruction string that:
    - Includes tip titles, descriptions, and confidence levels in the prompt context
    - Directs the model to cite at least one relevant tip using "💡 Tip:" format
    - Returns empty string if no tips are provided

    Args:
        tips: List of tip dicts, each with keys like 'title', 'description',
              'confidenceTag', 'estimatedSavings', etc.

    Returns:
        Instruction string for the Bedrock prompt, or empty string if tips is empty.
    """
    if not tips:
        return ""

    # Build tip context with titles, descriptions, and confidence levels
    tip_lines = []
    for tip in tips[:5]:
        title = tip.get('title', '')
        description = tip.get('description', '')
        confidence = tip.get('confidenceTag', 'standard')
        tip_lines.append(f"- Title: {title} | Description: {description} | Confidence: {confidence}")

    tips_context_block = "\n".join(tip_lines)

    citation_instruction = (
        "\n\nRELEVANT OPTIMIZATION TIPS:\n"
        f"{tips_context_block}\n\n"
        "TIP CITATION INSTRUCTION: You MUST cite at least one relevant tip from the list above "
        "in your response. Format each tip citation as:\n"
        "💡 Tip: [tip title] — [brief explanation of how it applies to this account]\n"
        "Place tip citations naturally within your analysis where they are most relevant."
    )

    return citation_instruction
