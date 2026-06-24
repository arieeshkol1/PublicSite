"""Cost Explorer account scoping.

In a multi-account (AWS Organizations) setup, calling Cost Explorer from a
PAYER / management account returns the ENTIRE consolidated organization's costs
(every linked account), not just the account the connection points at. The
SlashMyBill connection is always scoped to ONE specific account, so every
GetCostAndUsage query must be restricted to that account via a
``LINKED_ACCOUNT`` dimension filter.

For a standalone or linked (member) account, filtering by its own account ID is
harmless — Cost Explorer already only exposes that account's data — so applying
this filter unconditionally is safe and correct in all cases.

Usage:
    kwargs = apply_account_scope(kwargs, account_id)
    response = ce_client.get_cost_and_usage(**kwargs)
"""
import re

_AWS_ACCOUNT_RE = re.compile(r'^\d{12}$')


def is_aws_account_id(account_id) -> bool:
    """True if account_id looks like a 12-digit AWS account ID.

    Non-AWS identifiers (Azure UUIDs, GCP project IDs, OpenAI org names) are not
    valid LINKED_ACCOUNT values and must not be injected into a CE filter.
    """
    return bool(account_id) and bool(_AWS_ACCOUNT_RE.match(str(account_id).strip()))


def linked_account_filter(account_id: str) -> dict:
    """Return a Cost Explorer LINKED_ACCOUNT dimension filter for one account."""
    return {'Dimensions': {'Key': 'LINKED_ACCOUNT', 'Values': [str(account_id).strip()]}}


def merge_filters(existing: dict | None, addition: dict) -> dict:
    """AND-combine two Cost Explorer filter expressions.

    If ``existing`` is falsy, return ``addition`` directly. If it is already an
    ``And`` list, append to it; otherwise wrap both in a new ``And``.
    """
    if not existing:
        return addition
    if 'And' in existing and isinstance(existing['And'], list):
        # Avoid mutating the caller's dict.
        return {'And': list(existing['And']) + [addition]}
    return {'And': [existing, addition]}


def apply_account_scope(kwargs: dict, account_id: str) -> dict:
    """Inject a LINKED_ACCOUNT filter into Cost Explorer call kwargs.

    Returns a new kwargs dict scoped to ``account_id``. No-op (returns the same
    kwargs) when ``account_id`` is not a 12-digit AWS account ID.

    Combines with any existing ``Filter`` using a logical AND, so tag filters or
    service filters already present are preserved.
    """
    if not is_aws_account_id(account_id):
        return kwargs
    scoped = dict(kwargs)
    scoped['Filter'] = merge_filters(scoped.get('Filter'), linked_account_filter(account_id))
    return scoped
