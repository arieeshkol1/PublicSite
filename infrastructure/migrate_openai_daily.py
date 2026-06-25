#!/usr/bin/env python3
"""Idempotent migration: legacy ``OPENAI_DAILY#`` cache -> vendor-neutral schema.

Feature: vendor-agnostic-ai-usage (Task 10.1)

This one-time backfill converts existing ``Cost_Cache_Table`` items that use the
OpenAI-specific ``OPENAI_DAILY#{date}`` sort key into the vendor-neutral schema:

  * ``COST#{date}``                       -> Cost_Rollup_Item   (daily cost rollup)
  * ``USAGE#{date}#{actor}#{service}``    -> Usage_Detail_Item  (per-actor/service)

It preserves the original cost amount, currency, and date exactly (Req 9.3) and
writes with ``PutItem`` keyed by ``(pk, sk)`` so re-running overwrites rather
than duplicating records (Req 9.4 — idempotent). The per-actor/per-service
detail carried by a legacy item (``service_breakdown`` / ``token_breakdown`` /
``project_breakdown``) becomes ``USAGE#`` records sufficient to render the AI
dashboard widgets — the AI cost summary, the per-model cost breakdown, and the
per-user token consumption graph — with no pre-cutover data loss (Req 9.8).

On any write failure the job logs the count of items that failed and exits with
a non-zero status (Req 9.5); otherwise it exits ``0``.

IMPORTANT — production safety:
    This script performs a full table scan and writes. It is designed to run
    **backup-first via the GitHub Actions pipeline (GitHubDeployRole)**. The
    local developer user lacks DynamoDB scan/write permission, so DO NOT run it
    against a production table from a workstation.

The neutral key builders and item shapers are reused from
``member-handler/cache_service.py`` so the migrated items match the exact
field/key conventions used by the live neutral read/write path.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Reuse the neutral key builders / item shapers from member-handler so migrated
# records are byte-for-byte compatible with the live cache write path.
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_MEMBER_HANDLER = os.path.normpath(os.path.join(_THIS_DIR, '..', 'member-handler'))
if _MEMBER_HANDLER not in sys.path:
    sys.path.insert(0, _MEMBER_HANDLER)

from cache_service import (  # noqa: E402  (path injected above)
    NEUTRAL_USAGE_UNIT,
    shape_cost_rollup_item,
    shape_usage_detail_item,
)

logger = logging.getLogger("migrate_openai_daily")

# Legacy OpenAI-specific sort-key prefix being migrated away from.
LEGACY_SK_PREFIX = "OPENAI_DAILY#"

# Cost_Cache_Table name (matches member-handler's COST_CACHE_TABLE_NAME env var).
COST_CACHE_TABLE_NAME = os.environ.get("COST_CACHE_TABLE_NAME", "Cost_Cache_Table")


# ---------------------------------------------------------------------------
# Pure helpers (no AWS) — fully unit/property testable.
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _to_float(value) -> float:
    """Best-effort float coercion (Decimal/str/int/None all supported)."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def legacy_date(item: dict) -> str | None:
    """Extract the ISO date from a legacy ``OPENAI_DAILY#{date}`` sort key."""
    sk = str(item.get("sk", ""))
    if sk.startswith(LEGACY_SK_PREFIX):
        return sk[len(LEGACY_SK_PREFIX):]
    return None


def _model_cost_and_tokens(item: dict) -> dict:
    """Build a ``{service: {'cost': float, 'tokens': int}}`` map for a legacy item.

    ``service_breakdown`` carries per-model cost (a number, or a dict with a
    nested ``cost``/``cost_amount``); ``token_breakdown`` carries per-model
    ``input_tokens``/``output_tokens``. The union of both keysets is the set of
    services present for the day.
    """
    service_bd = item.get("service_breakdown") or {}
    token_bd = item.get("token_breakdown") or {}

    models: dict = {}
    for model in set(service_bd) | set(token_bd):
        raw_cost = service_bd.get(model, 0)
        if isinstance(raw_cost, dict):
            cost = _to_float(raw_cost.get("cost", raw_cost.get("cost_amount", 0)))
        else:
            cost = _to_float(raw_cost)

        tok = token_bd.get(model, {})
        if isinstance(tok, dict):
            tokens = int(_to_float(tok.get("input_tokens", 0))) + \
                int(_to_float(tok.get("output_tokens", 0)))
        else:
            tokens = int(_to_float(tok))

        models[model] = {"cost": cost, "tokens": tokens}
    return models


def _actor_shares(item: dict) -> list:
    """Return ``[(actor_label, cost_share_fraction), ...]`` from project_breakdown.

    ``project_breakdown`` maps ``project_id -> {'cost', 'name'}`` (or a bare
    number). Each project is an Actor (OpenAI's actor falls back to project_id);
    the cost share is the project's fraction of the total project cost. When no
    project detail is present the list is empty (the caller then attributes
    detail to a ``null`` actor).
    """
    proj_bd = item.get("project_breakdown") or {}
    costs: dict = {}
    for pid, pval in proj_bd.items():
        if isinstance(pval, dict):
            cost = _to_float(pval.get("cost", 0))
            label = pval.get("name") or pid
        else:
            cost = _to_float(pval)
            label = pid
        costs[label] = costs.get(label, 0.0) + cost

    total = sum(costs.values())
    if total <= 0:
        return []
    return [(label, cost / total) for label, cost in costs.items()]


def iter_detail(item: dict):
    """Yield ``(actor, service, usage_quantity, cost_amount)`` detail tuples.

    Reconstructs per-(actor, service) detail from a legacy item's aggregated
    breakdowns. When project (actor) detail exists, each model's cost and tokens
    are allocated across actors by the actor's cost share. This preserves both
    margins exactly: summed over actors a service's cost/tokens equals the
    legacy per-model total, and summed over services an actor's cost equals the
    legacy per-project total. When no project detail exists, each model maps to
    one record with a ``null`` actor (tokens preserved per model).

    The resulting records are sufficient to render the per-model cost breakdown
    (grouped by ``service``) and the per-user token consumption graph (grouped
    by ``actor``) dashboard widgets (Req 9.8).
    """
    models = _model_cost_and_tokens(item)
    shares = _actor_shares(item)

    if shares:
        for service, vals in models.items():
            for actor, share in shares:
                yield (
                    actor,
                    service,
                    round(vals["tokens"] * share, 4),
                    round(vals["cost"] * share, 6),
                )
    else:
        for service, vals in models.items():
            yield (None, service, vals["tokens"], round(vals["cost"], 6))


def build_neutral_items(item: dict) -> list:
    """Build the neutral Cost_Rollup_Item + Usage_Detail_Item records for a legacy item.

    Returns an empty list when the item has no parseable ``OPENAI_DAILY#`` date.
    The rollup preserves the legacy cost amount, currency, and date exactly
    (Req 9.1, 9.3); the detail records carry per-actor/per-service usage (Req
    9.2). ``cached_at`` and ``ttl`` are carried over from the legacy item when
    present so migrated records expire consistently with the originals.
    """
    date = legacy_date(item)
    if date is None:
        return []

    pk = item.get("pk")
    # Legacy items use 'fetched_at'; prefer an explicit 'cached_at' when present.
    cached_at = item.get("cached_at") or item.get("fetched_at") or _now_iso()
    # parse member_email/account_id back out of the pk for the shaper signature.
    member_email, _, account_id = str(pk).partition("#")

    items: list = []

    rollup = shape_cost_rollup_item(
        member_email=member_email,
        account_id=account_id,
        date=date,
        cost_amount=item.get("cost_amount", "0"),
        currency=item.get("currency", "USD"),
        cached_at=cached_at,
    )
    # Preserve the original pk verbatim (handles emails/account ids containing
    # extra '#' defensively) and carry over the TTL when present.
    rollup["pk"] = pk
    if item.get("ttl") is not None:
        rollup["ttl"] = item["ttl"]
    items.append(rollup)

    for actor, service, qty, cost in iter_detail(item):
        detail = shape_usage_detail_item(
            member_email=member_email,
            account_id=account_id,
            date=date,
            actor=actor if actor is not None else "unknown",
            service=service if service is not None else "unknown",
            usage_quantity=qty,
            unit=NEUTRAL_USAGE_UNIT,
            cost_amount=cost,
            cached_at=cached_at,
        )
        detail["pk"] = pk
        # Preserve the true (nullable) actor/service values per Req 2.6 even
        # though the sort key needs a concrete token.
        detail["actor"] = actor
        detail["service"] = service
        if item.get("ttl") is not None:
            detail["ttl"] = item["ttl"]
        items.append(detail)

    return items


# ---------------------------------------------------------------------------
# DynamoDB interaction.
# ---------------------------------------------------------------------------

def scan_legacy_items(table):
    """Yield every ``OPENAI_DAILY#`` item in the table, handling pagination.

    A ``begins_with`` filter on the sort key restricts the scan to legacy items
    so neutral records written by a prior run are never re-read (keeping the job
    idempotent and bounded on re-runs).
    """
    from boto3.dynamodb.conditions import Attr

    filter_expr = Attr("sk").begins_with(LEGACY_SK_PREFIX)
    response = table.scan(FilterExpression=filter_expr)
    for item in response.get("Items", []):
        yield item
    while "LastEvaluatedKey" in response:
        response = table.scan(
            FilterExpression=filter_expr,
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        for item in response.get("Items", []):
            yield item


def put_overwrite(table, neutral_item: dict) -> bool:
    """Write a neutral item with ``PutItem`` (overwrite by ``(pk, sk)``).

    Returns ``True`` on success, ``False`` on any error so the caller can count
    failures without aborting the whole migration.
    """
    try:
        table.put_item(Item=neutral_item)
        return True
    except Exception as exc:  # noqa: BLE001 — count every write failure (Req 9.5)
        logger.error(
            "Failed to write neutral item pk=%s sk=%s: %s",
            neutral_item.get("pk"), neutral_item.get("sk"), exc,
        )
        return False


def migrate(table) -> int:
    """Migrate all legacy items in ``table`` to the neutral schema.

    Returns the number of items that failed to write. Idempotent: re-running
    overwrites by primary key (Req 9.4).
    """
    failures = 0
    legacy_count = 0
    written = 0

    for legacy_item in scan_legacy_items(table):
        legacy_count += 1
        for neutral_item in build_neutral_items(legacy_item):
            if put_overwrite(table, neutral_item):
                written += 1
            else:
                failures += 1

    logger.info(
        "Migration scanned %d legacy item(s); wrote %d neutral item(s); %d failure(s).",
        legacy_count, written, failures,
    )
    return failures


def main() -> int:
    """Entry point: run the migration and return a process exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    import boto3

    table = boto3.resource("dynamodb").Table(COST_CACHE_TABLE_NAME)
    failures = migrate(table)
    if failures:
        logger.error("Migration failed for %d item(s)", failures)
        return 1
    logger.info("Migration completed successfully with no write failures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
