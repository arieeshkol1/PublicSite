"""Context budget manager - token estimation and progressive summarization."""
from __future__ import annotations

import json
import logging

from .models import ContextBudget, ModelConfig
from .constants import DEFAULT_BUDGET_CONFIG

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """Approximate token count using chars/4 heuristic for English text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def allocate_budget(model_config: ModelConfig) -> ContextBudget:
    """Partition context window into system/data/query sections based on model config."""
    config = DEFAULT_BUDGET_CONFIG.copy()

    # Scale budgets if model has smaller context window
    max_tokens = model_config.max_tokens
    if max_tokens and max_tokens < config["total_ceiling"]:
        ratio = max_tokens / config["total_ceiling"]
        config["dynamic_data_budget"] = int(config["dynamic_data_budget"] * ratio)
        config["total_ceiling"] = max_tokens

    return ContextBudget(
        system_prefix_tokens=config["system_prefix_budget"],
        dynamic_data_tokens=config["dynamic_data_budget"],
        user_query_tokens=config["user_query_budget"],
        total_ceiling=config["total_ceiling"],
    )


def apply_progressive_summarization(data_text: str, max_tokens: int) -> str:
    """Two-stage truncation to fit data within budget.

    Stage 1: Truncate JSON arrays to top-N entries by value.
    Stage 2: Summarize entire sections into single-paragraph digests.
    """
    current_tokens = estimate_tokens(data_text)
    if current_tokens <= max_tokens:
        return data_text

    # Stage 1: Try to parse as JSON and truncate arrays
    try:
        data = json.loads(data_text)
        truncated = _truncate_arrays(data, max_entries=10)
        result = json.dumps(truncated, indent=2)
        if estimate_tokens(result) <= max_tokens:
            return result
        # Still too large - go to stage 2
        data_text = result
    except (json.JSONDecodeError, TypeError):
        pass

    # Stage 2: Hard truncate to fit budget
    target_chars = max_tokens * 4
    if len(data_text) > target_chars:
        truncated_text = data_text[:target_chars]
        truncated_text += "\n... [truncated: data exceeded budget]"
        return truncated_text

    return data_text


def _truncate_arrays(data: dict | list, max_entries: int = 10) -> dict | list:
    """Recursively truncate arrays in data to max_entries."""
    if isinstance(data, list):
        if len(data) > max_entries:
            # Try to sort by a value field if items are dicts
            sorted_items = _sort_by_value(data)
            truncated = sorted_items[:max_entries]
            remaining_count = len(data) - max_entries
            remaining_total = sum(
                _extract_numeric_value(item) for item in sorted_items[max_entries:]
            )
            truncated.append({
                "_summary": f"{remaining_count} more items (total: {remaining_total:.2f})"
            })
            return truncated
        return data
    elif isinstance(data, dict):
        return {k: _truncate_arrays(v, max_entries) for k, v in data.items()}
    return data


def _sort_by_value(items: list) -> list:
    """Sort items by their primary numeric value descending."""
    try:
        return sorted(items, key=lambda x: _extract_numeric_value(x), reverse=True)
    except (TypeError, ValueError):
        return items


def _extract_numeric_value(item) -> float:
    """Extract the primary numeric value from a dict item."""
    if isinstance(item, (int, float)):
        return float(item)
    if isinstance(item, dict):
        # Look for common value field names
        for key in ("cost", "amount", "value", "total", "spend", "spending"):
            if key in item:
                try:
                    return float(item[key])
                except (TypeError, ValueError):
                    continue
    return 0.0
