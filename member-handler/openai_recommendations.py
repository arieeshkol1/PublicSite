"""OpenAI Optimization Recommendation Engine.

Analyzes OpenAI usage patterns from normalized records and generates
0–10 actionable cost optimization recommendations, ordered by
estimated monthly savings descending.

Each recommendation contains:
  - title: max 80 characters
  - description: max 300 characters
  - estimated_monthly_savings: float (dollars)
  - difficulty: 'easy' | 'medium' | 'hard'
"""
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# GPT-4 model identifiers (lowercase) used for the model-switch rule
GPT4_MODEL_NAMES = {'gpt-4', 'gpt-4-turbo', 'gpt-4-0125-preview', 'gpt-4-1106-preview',
                    'gpt-4-0613', 'gpt-4-0314', 'gpt-4-32k', 'gpt-4-32k-0613'}

# Cost ratio: GPT-4o-mini is approximately 1/30th the cost of GPT-4
GPT4_TO_MINI_COST_RATIO = 1 / 30

# Prompt optimization assumes 30% reduction in input tokens
PROMPT_OPTIMIZATION_SAVINGS_RATIO = 0.30


def generate_recommendations(usage_records: list) -> list:
    """Generate optimization recommendations based on OpenAI usage patterns.

    Analyzes normalized usage records and produces 0–10 recommendations
    sorted by estimated monthly savings descending.

    Args:
        usage_records: List of normalized records from normalize_openai(), each with:
            {date, service_name, cost_amount, currency, cloud_provider, account_id,
             input_tokens, output_tokens}

    Returns:
        List of recommendation dicts (0–10 items), each containing:
            - title: str (max 80 chars)
            - description: str (max 300 chars)
            - estimated_monthly_savings: float (dollars, rounded to 2 decimal places)
            - difficulty: str ('easy', 'medium', or 'hard')
        Sorted by estimated_monthly_savings descending.
        Returns empty list if no rules match or input is empty.
    """
    if not usage_records:
        return []

    recommendations = []

    # Run each rule and collect recommendations
    model_switch_rec = _check_model_switch_rule(usage_records)
    if model_switch_rec:
        recommendations.append(model_switch_rec)

    prompt_opt_rec = _check_prompt_optimization_rule(usage_records)
    if prompt_opt_rec:
        recommendations.append(prompt_opt_rec)

    # Sort by estimated_monthly_savings descending
    recommendations.sort(key=lambda r: r['estimated_monthly_savings'], reverse=True)

    # Cap at 10 recommendations
    recommendations = recommendations[:10]

    return recommendations


def _check_model_switch_rule(usage_records: list) -> dict | None:
    """Model-switch recommendation rule.

    Triggers when BOTH conditions are met:
      1. More than 50% of total token spend (cost) is on GPT-4 models
      2. Average output length for GPT-4 requests is ≤500 tokens

    Savings estimate: assumes switching to GPT-4o-mini at 1/30th the cost.
    The estimated monthly savings = GPT-4 cost × (1 - 1/30) = GPT-4 cost × 29/30.

    Returns:
        Recommendation dict if rule fires, None otherwise.
    """
    total_cost = 0.0
    gpt4_cost = 0.0
    gpt4_total_output_tokens = 0
    gpt4_request_count = 0

    for record in usage_records:
        cost = float(record.get('cost_amount', 0))
        total_cost += cost

        service_name = record.get('service_name', '').lower()
        if service_name in GPT4_MODEL_NAMES:
            gpt4_cost += cost
            output_tokens = int(record.get('output_tokens', 0))
            gpt4_total_output_tokens += output_tokens
            gpt4_request_count += 1

    # Check condition 1: GPT-4 > 50% of total spend
    if total_cost <= 0 or (gpt4_cost / total_cost) <= 0.50:
        return None

    # Check condition 2: average output length for GPT-4 ≤ 500 tokens
    if gpt4_request_count == 0:
        return None

    avg_output = gpt4_total_output_tokens / gpt4_request_count
    if avg_output > 500:
        return None

    # Both conditions met — calculate savings
    # Savings = GPT-4 cost minus what it would cost on GPT-4o-mini
    estimated_savings = gpt4_cost * (1 - GPT4_TO_MINI_COST_RATIO)
    estimated_savings = round(estimated_savings, 2)

    gpt4_pct = round(gpt4_cost / total_cost * 100, 0)

    title = "Switch short-output GPT-4 tasks to GPT-4o-mini"
    description = (
        f"{int(gpt4_pct)}% of your token spend is on GPT-4 with average output of "
        f"{int(avg_output)} tokens. These short-output tasks likely work well with "
        f"GPT-4o-mini at 1/30th the cost."
    )

    # Truncate to field limits
    title = title[:80]
    description = description[:300]

    return {
        'title': title,
        'description': description,
        'estimated_monthly_savings': estimated_savings,
        'difficulty': 'easy',
    }


def _check_prompt_optimization_rule(usage_records: list) -> dict | None:
    """Prompt optimization recommendation rule.

    Triggers when the ratio of total input tokens to total output tokens
    exceeds 4:1 across the billing period.

    Does NOT trigger if ratio is 4:1 or lower.

    Savings estimate: assumes 30% reduction in input tokens. The savings
    is calculated as 30% of the cost attributable to input tokens.

    Returns:
        Recommendation dict if rule fires, None otherwise.
    """
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0

    for record in usage_records:
        total_input_tokens += int(record.get('input_tokens', 0))
        total_output_tokens += int(record.get('output_tokens', 0))
        total_cost += float(record.get('cost_amount', 0))

    # Need output tokens > 0 to compute ratio
    if total_output_tokens <= 0:
        return None

    ratio = total_input_tokens / total_output_tokens

    # Only trigger when ratio EXCEEDS 4:1 (strictly greater than 4)
    if ratio <= 4.0:
        return None

    # Estimate savings: 30% reduction in input tokens
    # Approximate input cost proportion based on token ratio
    # input_cost_fraction = input_tokens / (input_tokens + output_tokens) as a rough proxy
    # But for a more meaningful estimate, we use 30% of total cost weighted by input proportion
    total_tokens = total_input_tokens + total_output_tokens
    input_cost_fraction = total_input_tokens / total_tokens if total_tokens > 0 else 0
    estimated_savings = total_cost * input_cost_fraction * PROMPT_OPTIMIZATION_SAVINGS_RATIO
    estimated_savings = round(estimated_savings, 2)

    ratio_display = round(ratio, 1)

    title = "Optimize prompts to reduce input token usage"
    description = (
        f"Your input:output token ratio is {ratio_display}:1, exceeding the 4:1 threshold. "
        f"Consider prompt compression, removing redundant context, or using structured "
        f"prompts to reduce input tokens by up to 30%."
    )

    # Truncate to field limits
    title = title[:80]
    description = description[:300]

    return {
        'title': title,
        'description': description,
        'estimated_monthly_savings': estimated_savings,
        'difficulty': 'medium',
    }
