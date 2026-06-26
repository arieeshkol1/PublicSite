"""Vendor-agnostic AI cost-optimization tips seed.

The chat's drill-down / "why is this costing me" / "how do I reduce" flow is
grounded in the ViewMyBill-CostOptimizationTips table (Tier-2 drilldown plan +
optimization guidance). For AI-vendor accounts that table was empty, so the
assistant could state a cost total but could not *explain* or *act* on it.

This module seeds a small, provider-neutral set of AI cost-optimization tips.
Nothing here is specific to one vendor's models: tips describe levers that apply
to any token-billed AI service (prompt caching, batch processing, model
right-sizing, output-token control, per-actor attribution). The per-provider
rows differ only by the ``service`` partition key (the provider key the resolver
already uses) and the ``drilldownApis`` operation the customer's connector runs.

The seed is idempotent — items are keyed by (service, tipId) and re-seeding
overwrites in place. It is safe to call on every cold start; a module-level
guard prevents repeated table scans within a warm container.
"""

import json
import logging

logger = logging.getLogger(__name__)

# Provider keys that are AI vendors (the resolver selects connectors by these).
AI_PROVIDER_KEYS = ('openai', 'groundcover')

# Neutral drilldown plan: the operations the customer's connector exposes to
# break a cost total down by model/service and by user/actor. Stored as a
# JSON-array string to match the existing table rows.
_AI_DRILLDOWN_APIS = json.dumps(['getAIUsage:units', 'getAIUsage:actor'])

# Provider-neutral AI cost-optimization tips. {tipId: {...fields}}. No vendor or
# model names are hardcoded — these levers apply to any token-billed AI service.
_AI_TIP_TEMPLATES = [
    {
        'tipId': 'ai-attribute-spend',
        'category': 'Visibility',
        'title': 'Attribute AI spend by model and user',
        'description': (
            'Break your AI cost down by model/service and by user or project so '
            'you can see exactly what is driving the bill. Spend is rarely '
            'uniform: a few models and a few users usually account for most of '
            'the cost. Use the per-model and per-user breakdown to find them.'
        ),
        'estimatedSavings': 'Visibility (no direct savings)',
        'difficulty': 'Easy',
        'level': 'account',
        'actionType': 'analyze',
        'actionLabel': 'Break down by model and user',
        'drilldownInstructions': (
            'Pull the per-model and per-actor usage detail for the period from '
            "the customer's own connection and rank by cost."
        ),
        'drilldownApis': _AI_DRILLDOWN_APIS,
    },
    {
        'tipId': 'ai-prompt-caching',
        'category': 'Token efficiency',
        'title': 'Enable prompt caching for repeated context',
        'description': (
            'If you resend the same large system prompt or context on many '
            'requests, prompt caching charges the repeated tokens at a steep '
            'discount instead of full input price. Cache stable context (system '
            'prompts, instructions, reference documents) and only vary the user '
            'turn.'
        ),
        'estimatedSavings': 'Up to ~50-90% of repeated input-token cost',
        'difficulty': 'Medium',
        'level': 'account',
        'actionType': 'recommend',
        'actionLabel': 'Review cacheable context',
        'drilldownInstructions': (
            'Identify models with high input-token cost relative to output; '
            'those are the best prompt-caching candidates.'
        ),
        'drilldownApis': _AI_DRILLDOWN_APIS,
    },
    {
        'tipId': 'ai-batch-processing',
        'category': 'Pricing model',
        'title': 'Use batch/async processing for non-interactive jobs',
        'description': (
            'Work that does not need an immediate response (evaluations, bulk '
            'summarization, back-fills) can run on the asynchronous/batch tier, '
            'which is typically billed at a large discount versus real-time '
            'requests. Move offline workloads off the interactive endpoint.'
        ),
        'estimatedSavings': 'Up to ~50% on eligible workloads',
        'difficulty': 'Medium',
        'level': 'account',
        'actionType': 'recommend',
        'actionLabel': 'Identify batchable workloads',
        'drilldownApis': _AI_DRILLDOWN_APIS,
    },
    {
        'tipId': 'ai-model-rightsizing',
        'category': 'Model selection',
        'title': 'Right-size the model to the task',
        'description': (
            'The largest, most capable model is rarely required for every call. '
            'Route simple or high-volume tasks (classification, extraction, '
            'short replies) to a smaller, cheaper model and reserve the premium '
            'model for genuinely hard requests. This usually removes the single '
            'biggest line item.'
        ),
        'estimatedSavings': 'Often 40-80% on routed traffic',
        'difficulty': 'Medium',
        'level': 'account',
        'actionType': 'recommend',
        'actionLabel': 'Find premium-model traffic to downshift',
        'drilldownInstructions': (
            'Rank models by cost; flag the most expensive model and estimate the '
            'share of its calls that could run on a cheaper tier.'
        ),
        'drilldownApis': _AI_DRILLDOWN_APIS,
    },
    {
        'tipId': 'ai-output-token-control',
        'category': 'Token efficiency',
        'title': 'Cap and trim output tokens',
        'description': (
            'Output tokens usually cost several times more than input tokens. '
            'Set a sensible max-output limit, ask for concise/structured '
            'responses, and avoid having the model echo large inputs back. '
            'Trimming verbose generations directly cuts the most expensive part '
            'of the bill.'
        ),
        'estimatedSavings': '10-40% of output-token cost',
        'difficulty': 'Easy',
        'level': 'account',
        'actionType': 'recommend',
        'actionLabel': 'Review output-token usage',
        'drilldownApis': _AI_DRILLDOWN_APIS,
    },
]

# Warm-container guard: provider keys already verified/seeded this lifecycle.
_seeded_providers = set()


def ensure_ai_tips_seeded(tips_table, provider_key):
    """Best-effort, idempotent seed of vendor-agnostic AI tips for a provider.

    Only writes when the provider has no tips yet, so it never clobbers
    admin-curated or feedback-learned tips. Never raises — tip grounding is
    additive and must not break the chat answer.

    Args:
        tips_table: boto3 DynamoDB Table resource for the tips table.
        provider_key: AI provider key used as the ``service`` partition key
            (e.g. 'openai', 'groundcover').

    Returns:
        True if rows were written this call, False otherwise.
    """
    if not provider_key or provider_key in _seeded_providers:
        return False
    try:
        from boto3.dynamodb.conditions import Key
        existing = tips_table.query(
            KeyConditionExpression=Key('service').eq(provider_key),
            Limit=1,
        )
        if existing.get('Items'):
            _seeded_providers.add(provider_key)
            return False

        with tips_table.batch_writer() as bw:
            for tpl in _AI_TIP_TEMPLATES:
                item = dict(tpl)
                item['service'] = provider_key
                item['provider'] = provider_key
                item['cloud'] = provider_key
                item['syncSource'] = 'ai-tips-seed'
                bw.put_item(Item=item)
        _seeded_providers.add(provider_key)
        logger.info(
            f"Seeded {len(_AI_TIP_TEMPLATES)} vendor-agnostic AI tips for "
            f"provider '{provider_key}'"
        )
        return True
    except Exception as e:
        logger.warning(
            f"AI tips seed skipped for '{provider_key}': {type(e).__name__}: {e}"
        )
        return False
