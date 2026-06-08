"""Response builder - assembles final user-facing response."""
from __future__ import annotations

import json
import logging
from typing import Any

from .models import ExecutionPayload
from .prompt_defense import sanitize_user_input, detect_injection_patterns

logger = logging.getLogger(__name__)


def build_response(
    ai_response: str,
    gathered_data: dict[str, Any],
    template_version: str,
    interaction_id: str = "",
) -> dict[str, Any]:
    """Assemble the final response with chart data, tips, and follow-up topics.

    Maintains backward compatibility with existing API contract.
    """
    # Extract chart data from gathered_data
    chart_data = _extract_chart_data(gathered_data)

    # Extract top services
    top_services = _extract_top_services(gathered_data)

    # Extract tips
    tips = _extract_tips(gathered_data)

    # Determine if tips were found
    tip_found = bool(tips)

    # Generate follow-up topics
    follow_up_topics = _generate_follow_ups(gathered_data)

    response = {
        "answer": ai_response,
        "interactionId": interaction_id,
        "commands": [],
        "results": [],
        "tipFound": tip_found,
        "agentUsed": True,
        "chartData": chart_data,
        "topServices": top_services,
        "metadata": {
            "templateVersion": template_version,
            "pipelineVersion": "2.0",
        },
    }

    if follow_up_topics:
        response["followUpTopics"] = follow_up_topics

    if tips:
        response["tips"] = tips

    return response


def build_error_response(
    error_message: str,
    interaction_id: str = "",
) -> dict[str, Any]:
    """Build an error response maintaining API contract."""
    return {
        "answer": error_message,
        "interactionId": interaction_id,
        "commands": [],
        "results": [],
        "tipFound": False,
        "agentUsed": True,
        "chartData": [],
        "topServices": [],
        "metadata": {
            "pipelineVersion": "2.0",
            "error": True,
        },
    }


def _extract_chart_data(gathered_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract chart-friendly data from gathered results."""
    chart_data = []

    # Look for cost_by_service data
    data = gathered_data.get("data", gathered_data)

    if isinstance(data, dict):
        cost_data = data.get("cost_data", data)
        if isinstance(cost_data, dict):
            cost_by_service = cost_data.get("cost_by_service", [])
        elif isinstance(cost_data, list):
            cost_by_service = cost_data
        else:
            cost_by_service = []

        for item in cost_by_service[:10]:
            if isinstance(item, dict):
                chart_data.append({
                    "service": item.get("service", "Unknown"),
                    "cost": float(item.get("cost", 0)),
                })

    return chart_data


def _extract_top_services(gathered_data: dict[str, Any]) -> list[str]:
    """Extract top service names from gathered data."""
    data = gathered_data.get("data", gathered_data)

    if isinstance(data, dict):
        cost_data = data.get("cost_data", data)
        if isinstance(cost_data, dict):
            cost_by_service = cost_data.get("cost_by_service", [])
        elif isinstance(cost_data, list):
            cost_by_service = cost_data
        else:
            cost_by_service = []

        return [
            item.get("service", "")
            for item in cost_by_service[:5]
            if isinstance(item, dict) and item.get("service")
        ]

    return []


def _extract_tips(gathered_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract optimization tips from gathered data."""
    data = gathered_data.get("data", gathered_data)

    if isinstance(data, dict):
        tips = data.get("tips", [])
        if isinstance(tips, list):
            return [
                {
                    "tipId": t.get("tipId", ""),
                    "title": t.get("title", ""),
                    "service": t.get("service", ""),
                    "estimatedSavings": t.get("estimatedSavings", ""),
                }
                for t in tips[:10]
                if isinstance(t, dict)
            ]
    return []


def _generate_follow_ups(gathered_data: dict[str, Any]) -> list[str]:
    """Generate follow-up topic suggestions based on gathered data."""
    follow_ups = []
    data = gathered_data.get("data", gathered_data)

    if isinstance(data, dict):
        sources = gathered_data.get("sources", [])

        if "tips_table" in sources:
            follow_ups.append("Show me optimization recommendations")
        if "cost_explorer" in sources or "cache" in sources:
            follow_ups.append("What are the cost trends over time?")

        # Service-specific follow-ups
        cost_data = data.get("cost_data", data)
        if isinstance(cost_data, dict):
            services = cost_data.get("cost_by_service", [])
            if services and isinstance(services, list) and len(services) > 0:
                top_service = services[0].get("service", "") if isinstance(services[0], dict) else ""
                if top_service:
                    follow_ups.append(f"How can I reduce {top_service} costs?")

    return follow_ups[:3]
