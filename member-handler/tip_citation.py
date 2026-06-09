"""
Tip Citation Module - Builds prompt instructions for tip citations in AI responses.

When tips are found for a query, this module generates a prompt instruction
requiring the Bedrock model to cite at least one relevant tip using the
"💡 Tip:" prefix format. Includes drilldown instructions and estimated savings
so the agent knows HOW to investigate each optimization opportunity.
"""


def build_tip_citation_prompt(tips: list) -> str:
    """Build the tip citation instruction text for the Bedrock prompt.

    Accepts a list of tips and returns a prompt instruction string that:
    - Includes tip titles, descriptions, estimated savings, and confidence levels
    - Includes drilldownInstructions when available (tells agent HOW to investigate)
    - Directs the model to cite at least one relevant tip using "💡 Tip:" format
    - Prioritizes service-specific tips over General tips
    - Returns empty string if no tips are provided

    Args:
        tips: List of tip dicts, each with keys like 'title', 'description',
              'confidenceTag', 'estimatedSavings', 'drilldownInstructions', etc.

    Returns:
        Instruction string for the Bedrock prompt, or empty string if tips is empty.
    """
    if not tips:
        return ""

    # Separate service-specific tips from General tips, prioritize service-specific
    service_tips = [t for t in tips if t.get('service', '') != 'General']
    general_tips = [t for t in tips if t.get('service', '') == 'General']

    # Take up to 4 service-specific + 2 general (max 6 total to keep prompt concise)
    selected_tips = service_tips[:4] + general_tips[:2]
    if not selected_tips:
        selected_tips = tips[:5]

    # Build tip context with titles, descriptions, savings, and drilldown instructions
    tip_lines = []
    for tip in selected_tips:
        title = tip.get('title', '')
        description = tip.get('description', '')
        confidence = tip.get('confidenceTag', 'standard')
        savings = tip.get('estimatedSavings', '')
        drilldown = tip.get('drilldownInstructions', '')

        # Build the tip entry
        entry = f"- Title: {title}"
        if savings:
            entry += f" | Savings: {savings}"
        entry += f" | Description: {description[:200]}"
        entry += f" | Confidence: {confidence}"
        if drilldown:
            entry += f"\n  DRILL-DOWN: {drilldown[:300]}"

        tip_lines.append(entry)

    tips_context_block = "\n".join(tip_lines)

    citation_instruction = (
        "\n\nRELEVANT OPTIMIZATION TIPS:\n"
        f"{tips_context_block}\n\n"
        "TIP CITATION INSTRUCTION: You MUST cite at least one relevant tip from the list above "
        "in your response. Format each tip citation as:\n"
        "💡 Tip: [tip title] — [brief explanation of how it applies to this account]\n"
        "Place tip citations naturally within your analysis where they are most relevant.\n"
        "When a tip has DRILL-DOWN instructions, use those steps to gather specific data "
        "before making recommendations. Call the indicated APIs to verify actual resource state."
    )

    return citation_instruction
