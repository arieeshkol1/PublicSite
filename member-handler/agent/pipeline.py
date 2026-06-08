"""Pipeline orchestrator - wires all agent stages together."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from .models import AccountContext, SessionState, ClassificationResult, ContextBudget
from .account_resolver import resolve_account, validate_account_format
from .session_state import load_session, update_session, persist_session
from .intent_classifier_v2 import classify_intent
from .context_budget import allocate_budget, estimate_tokens
from .payload_assembler import assemble_payload
from .behavioral_router import execute_by_intent
from .ai_model_router import get_model_config, invoke_model
from .output_validator import validate_classification_output
from .response_builder import build_response, build_error_response
from .prompt_defense import detect_injection_patterns
from .constants import DEFAULT_BUDGET_CONFIG

logger = logging.getLogger(__name__)


def execute_pipeline(event: dict) -> dict:
    """Orchestrate the full agent pipeline.

    Stages:
    1. Account Resolver
    2. Session State Manager
    3. Intent Classifier
    4. Payload Assembler
    5. Behavioral Router
    6. AI Model Invocation
    7. Output Validator
    8. Response Builder

    Graceful degradation chain:
    Full pipeline → keyword-only classifier → no session → fallback template → partial data response
    """
    start_time = time.time()
    interaction_id = event.get("interaction_id", "")

    # Extract input parameters
    question = event.get("question", "").strip()
    account_id = event.get("account_id", "").strip()
    member_email = event.get("member_email", "").strip()

    if not question:
        return build_error_response("Question is required.", interaction_id)

    if not account_id or not member_email:
        return build_error_response("Account ID and member email are required.", interaction_id)

    # Security: detect injection patterns (log only, don't block)
    injection_patterns = detect_injection_patterns(question)
    if injection_patterns:
        logger.warning(f"Injection patterns detected in query: {injection_patterns}")

    # Stage 1: Account Resolution
    try:
        account_context = resolve_account(account_id, member_email)
    except ValueError as e:
        return build_error_response(str(e), interaction_id)
    except Exception as e:
        logger.error(f"Account resolution failed: {e}")
        # Graceful degradation: create minimal context
        try:
            provider = validate_account_format(account_id)
        except ValueError:
            return build_error_response(
                "Invalid account ID format. Expected: AWS (12 digits), Azure (UUID), or GCP (project ID).",
                interaction_id,
            )
        account_context = AccountContext(
            account_id=account_id,
            account_name=account_id,
            cloud_provider=provider,
            member_email=member_email,
            supported_services=[],
            provider_config={},
        )

    # Stage 2: Session State
    try:
        session = load_session(member_email, account_id)
        session.account_context = account_context
    except Exception as e:
        logger.warning(f"Session load failed, using fresh session: {e}")
        session = SessionState(
            account_context=account_context,
            last_updated="",
        )

    # Stage 3: Intent Classification
    try:
        intent = classify_intent(question, session)
    except Exception as e:
        logger.warning(f"Intent classification failed, using general: {e}")
        intent = ClassificationResult(
            intent_type="Cost_Analysis_General",
            target_scope="account-wide",
            timeframe="last-30d",
            confidence_score=0.5,
        )

    # Update session with classification result
    try:
        session = update_session(session, {
            "intent_type": intent.intent_type,
            "target_scope": intent.target_scope,
            "timeframe": intent.timeframe,
        })
    except Exception as e:
        logger.warning(f"Session update failed: {e}")

    # Stage 4: Behavioral Router (data gathering)
    try:
        gathered_data = execute_by_intent(intent, account_context, session)
    except Exception as e:
        logger.error(f"Behavioral router failed: {e}")
        gathered_data = {"data": {}, "sources": [], "error": str(e)}

    # Stage 5: Payload Assembly
    try:
        model_config = get_model_config(member_email)
        budget = allocate_budget(model_config)
        payload = assemble_payload(
            "system-prefix-v3.2.txt",
            account_context,
            gathered_data.get("data", {}),
            question,
            budget,
        )
    except Exception as e:
        logger.error(f"Payload assembly failed: {e}")
        return build_error_response(
            "Unable to process your question at this time. Please try again.",
            interaction_id,
        )

    # Stage 6: AI Model Invocation
    try:
        ai_response = invoke_model(model_config, payload)
    except Exception as e:
        logger.error(f"Model invocation failed: {e}")
        # Return partial data response without AI answer
        return build_response(
            "I'm experiencing issues generating a response, but here's the data I gathered.",
            gathered_data,
            payload.template_version,
            interaction_id,
        )

    # Stage 7: Response Builder
    response = build_response(
        ai_response,
        gathered_data,
        payload.template_version,
        interaction_id,
    )

    # Persist session
    try:
        session.conversation_history.append({"role": "user", "content": question})
        session.conversation_history.append({"role": "assistant", "content": ai_response[:200]})
        persist_session(member_email, account_id, session)
    except Exception as e:
        logger.warning(f"Session persist failed: {e}")

    # Log token distribution and timing
    elapsed = time.time() - start_time
    logger.info(
        f"Pipeline completed in {elapsed:.2f}s | "
        f"Intent: {intent.intent_type} | "
        f"Tokens: {payload.token_distribution}"
    )

    return response
