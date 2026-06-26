"""AI-vendor cost-optimization tips source for the daily sync.

The daily sync previously covered AWS/Azure/GCP (+ OpenAI baseline rows) but did
NOT maintain a complete, drilldown-enabled tip set for AI vendors — GroundCover
was absent entirely, and AI tips were only written lazily at chat time. This
source contributes a provider-neutral set of AI cost-optimization tips for every
AI vendor the platform supports, so the scheduled job keeps the tips table
complete for AI accounts (each tip is keyed by the provider's ``service`` key so
the chat Tier-2 drilldown finds it, and gets an executable drilldown plan via
``drilldown_data`` at write time).

No vendor's specific models are hardcoded: tips describe levers that apply to any
token-billed AI service (attribution, prompt caching, batch processing, model
right-sizing, output-token control). Rows differ only by the provider key.
"""

# AI vendor provider keys maintained by the daily sync. Lowercase to match the
# provider key the chat resolver / connectors use as the Tips_Table PK.
AI_VENDOR_PROVIDERS = ("openai", "groundcover")

# Provider-neutral AI optimization tip templates. {suffix: {content fields}}.
_AI_TIP_TEMPLATES = [
    {
        "suffix": "attribute-spend",
        "category": "Visibility",
        "title": "Attribute AI spend by model and user",
        "description": (
            "Break your AI cost down by model/service and by user or project so "
            "you can see exactly what is driving the bill. Spend is rarely "
            "uniform: a few models and a few users usually account for most of "
            "the cost. Use the per-model and per-user breakdown to find them."
        ),
        "estimatedSavings": "Visibility (no direct savings)",
        "difficulty": "Easy",
        "actionType": "analyze",
        "actionLabel": "Break down by model and user",
    },
    {
        "suffix": "prompt-caching",
        "category": "Token efficiency",
        "title": "Enable prompt caching for repeated context",
        "description": (
            "If you resend the same large system prompt or context on many "
            "requests, prompt caching charges the repeated tokens at a steep "
            "discount instead of full input price. Cache stable context (system "
            "prompts, instructions, reference documents) and only vary the user "
            "turn."
        ),
        "estimatedSavings": "Up to ~50-90% of repeated input-token cost",
        "difficulty": "Medium",
        "actionType": "recommend",
        "actionLabel": "Review cacheable context",
    },
    {
        "suffix": "batch-processing",
        "category": "Pricing model",
        "title": "Use batch/async processing for non-interactive jobs",
        "description": (
            "Work that does not need an immediate response (evaluations, bulk "
            "summarization, back-fills) can run on the asynchronous/batch tier, "
            "which is typically billed at a large discount versus real-time "
            "requests. Move offline workloads off the interactive endpoint."
        ),
        "estimatedSavings": "Up to ~50% on eligible workloads",
        "difficulty": "Medium",
        "actionType": "recommend",
        "actionLabel": "Identify batchable workloads",
    },
    {
        "suffix": "model-rightsizing",
        "category": "Model selection",
        "title": "Right-size the model to the task",
        "description": (
            "The largest, most capable model is rarely required for every call. "
            "Route simple or high-volume tasks (classification, extraction, "
            "short replies) to a smaller, cheaper model and reserve the premium "
            "model for genuinely hard requests. This usually removes the single "
            "biggest line item."
        ),
        "estimatedSavings": "Often 40-80% on routed traffic",
        "difficulty": "Medium",
        "actionType": "recommend",
        "actionLabel": "Find premium-model traffic to downshift",
    },
    {
        "suffix": "output-token-control",
        "category": "Token efficiency",
        "title": "Cap and trim output tokens",
        "description": (
            "Output tokens usually cost several times more than input tokens. "
            "Set a sensible max-output limit, ask for concise/structured "
            "responses, and avoid having the model echo large inputs back. "
            "Trimming verbose generations directly cuts the most expensive part "
            "of the bill."
        ),
        "estimatedSavings": "10-40% of output-token cost",
        "difficulty": "Easy",
        "actionType": "recommend",
        "actionLabel": "Review output-token usage",
    },
]


def load_ai_vendor_tips():
    """Return the provider-neutral AI tip rows for all AI vendors.

    Each row is a tip dict in the sync's common shape (``id``, ``service``,
    ``cloud``, content fields). The drilldown plan is attached at write time by
    ``sync_engine`` via ``drilldown_data.get_drilldown_data(service, cloud)``,
    which now covers these provider keys. Returns ``[]`` only if something is
    structurally wrong (it never raises).
    """
    rows = []
    try:
        for provider in AI_VENDOR_PROVIDERS:
            for tpl in _AI_TIP_TEMPLATES:
                rows.append({
                    "id": f"{provider}-{tpl['suffix']}",
                    "service": provider,          # Tier-2 PK = provider key
                    "cloud": provider,            # drives drilldown_data lookup
                    "provider": provider,
                    "category": tpl["category"],
                    "title": tpl["title"],
                    "description": tpl["description"],
                    "estimatedSavings": tpl["estimatedSavings"],
                    "difficulty": tpl["difficulty"],
                    "actionType": tpl["actionType"],
                    "actionLabel": tpl["actionLabel"],
                    "level": "account",
                    "automatedCheck": "",
                    "syncSource": "ai-vendor-tips",
                })
    except Exception:
        return []
    return rows
