"""Session state manager - multi-turn conversation tracking."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import boto3

from .models import SessionState, AccountContext
from .constants import MEMBERS_TABLE

logger = logging.getLogger(__name__)


def load_session(member_email: str, account_id: str) -> SessionState:
    """Load session from DynamoDB Members table or initialize a fresh session.

    Reads the 'agentSession' attribute from the member record.
    On any failure, returns a fresh empty session.
    """
    try:
        dynamodb = boto3.resource("dynamodb")
        members_table = dynamodb.Table(MEMBERS_TABLE)
        response = members_table.get_item(
            Key={"email": member_email},
            ProjectionExpression="agentSession",
        )
        item = response.get("Item", {})
        session_data = item.get("agentSession")

        if not session_data:
            return _fresh_session()

        # Parse stored session
        if isinstance(session_data, str):
            session_data = json.loads(session_data)

        # Only return stored session if it's for the same account
        if session_data.get("accountId") != account_id:
            return _fresh_session()

        return SessionState(
            account_context=None,  # Will be re-resolved by pipeline
            current_intent=session_data.get("currentIntent"),
            target_scope=session_data.get("targetScope"),
            active_timeframe=session_data.get("activeTimeframe"),
            conversation_history=session_data.get("conversationHistory", []),
            last_updated=session_data.get("lastUpdated", ""),
        )
    except Exception as e:
        logger.warning(f"Failed to load session, initializing fresh: {e}")
        return _fresh_session()


def update_session(session: SessionState, intent_result: dict) -> SessionState:
    """Update session with new intent classification result.

    Carries forward parameters that remain applicable:
    - If intent_result provides a new value, use it
    - If intent_result doesn't specify a field, keep the existing session value
    """
    new_intent = intent_result.get("intent_type", session.current_intent)
    new_scope = intent_result.get("target_scope", session.target_scope)
    new_timeframe = intent_result.get("timeframe", session.active_timeframe)

    session.current_intent = new_intent
    session.target_scope = new_scope
    session.active_timeframe = new_timeframe
    session.last_updated = datetime.now(timezone.utc).isoformat()

    return session


def reset_session(member_email: str, account_id: str) -> SessionState:
    """Reset session state for an account change or explicit reset."""
    fresh = _fresh_session()

    # Persist the reset
    try:
        _persist_session(member_email, account_id, fresh)
    except Exception as e:
        logger.warning(f"Failed to persist session reset: {e}")

    return fresh


def persist_session(member_email: str, account_id: str, session: SessionState) -> None:
    """Save session state to DynamoDB."""
    _persist_session(member_email, account_id, session)


def _persist_session(member_email: str, account_id: str, session: SessionState) -> None:
    """Internal persist helper."""
    try:
        dynamodb = boto3.resource("dynamodb")
        members_table = dynamodb.Table(MEMBERS_TABLE)

        session_data = {
            "accountId": account_id,
            "currentIntent": session.current_intent,
            "targetScope": session.target_scope,
            "activeTimeframe": session.active_timeframe,
            "conversationHistory": session.conversation_history[-10:],  # Keep last 10 turns
            "lastUpdated": session.last_updated or datetime.now(timezone.utc).isoformat(),
        }

        members_table.update_item(
            Key={"email": member_email},
            UpdateExpression="SET agentSession = :s",
            ExpressionAttributeValues={":s": session_data},
        )
    except Exception as e:
        logger.warning(f"Failed to persist session: {e}")


def _fresh_session() -> SessionState:
    """Create a blank session state."""
    return SessionState(
        account_context=None,
        current_intent=None,
        target_scope=None,
        active_timeframe=None,
        conversation_history=[],
        last_updated=datetime.now(timezone.utc).isoformat(),
    )
