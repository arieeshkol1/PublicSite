"""Intent Classifier v2 - keyword matching + LLM few-shot disambiguation."""
from __future__ import annotations

import json
import logging
import re

import boto3

from .models import ClassificationResult, SessionState
from .constants import CLASSIFICATION_SCHEMA, VALID_INTENT_TYPES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword definitions mapping to new intent types
# ---------------------------------------------------------------------------
INTENT_KEYWORDS: dict[str, list[str]] = {
    "Cost_Analysis_General": [
        "total cost", "overall cost", "monthly bill", "bill", "spending",
        "spend", "budget", "trend", "cost breakdown", "how much",
        "expensive", "cheapest", "billing", "invoice", "charge", "pricing",
        "cost", "what am i paying", "what did i pay",
    ],
    "Cost_Analysis_Specific": [
        "ec2", "rds", "s3", "lambda", "serverless", "database",
        "virtual machine", "vm", "bucket", "nat gateway", "ebs",
        "volume", "snapshot", "aurora", "neptune", "elasticache",
        "cloudfront", "load balancer", "specific service",
    ],
    "Optimization_Tips": [
        "optimize", "optimization", "save money", "reduce cost", "cut cost",
        "savings", "tip", "tips", "recommendation", "recommendations",
        "rightsizing", "right-sizing", "underutilized", "over-provisioned",
        "waste", "unused", "idle",
    ],
    "Forecasting": [
        "forecast", "predict", "projection", "next month", "next quarter",
        "future cost", "will cost", "expected cost", "estimate future",
        "what if", "scenario", "plan budget", "budget planning",
    ],
}

# Precompile patterns
_INTENT_PATTERNS: dict[str, re.Pattern] = {}
for _intent, _keywords in INTENT_KEYWORDS.items():
    escaped = [re.escape(kw) for kw in _keywords]
    _INTENT_PATTERNS[_intent] = re.compile(
        r"(?:" + "|".join(escaped) + r")", re.IGNORECASE
    )

# Few-shot examples for disambiguation
FEW_SHOT_EXAMPLES = [
    {"question": "How much am I spending on EC2 this month?", "intent_type": "Cost_Analysis_Specific", "target_scope": "ec2", "timeframe": "last-30d"},
    {"question": "What's my total AWS bill?", "intent_type": "Cost_Analysis_General", "target_scope": "account-wide", "timeframe": "last-30d"},
    {"question": "How can I reduce my RDS costs?", "intent_type": "Optimization_Tips", "target_scope": "rds", "timeframe": "last-30d"},
    {"question": "What will my costs be next quarter?", "intent_type": "Forecasting", "target_scope": "account-wide", "timeframe": "next-3m"},
    {"question": "Show me cost breakdown by service", "intent_type": "Cost_Analysis_General", "target_scope": "account-wide", "timeframe": "last-30d"},
    {"question": "Are there any unused EC2 instances I can terminate?", "intent_type": "Optimization_Tips", "target_scope": "ec2", "timeframe": "last-30d"},
    {"question": "What if I add 5 more t3.large instances?", "intent_type": "Forecasting", "target_scope": "ec2", "timeframe": "next-1m"},
    {"question": "How much is S3 costing me specifically?", "intent_type": "Cost_Analysis_Specific", "target_scope": "s3", "timeframe": "last-30d"},
]


def classify_intent(
    question: str,
    session: SessionState | None = None,
    model_client=None,
) -> ClassificationResult:
    """Classify user question into intent type.

    Primary path: keyword matching.
    If 3+ categories match (ambiguous): use LLM few-shot disambiguation.
    Falls back to Cost_Analysis_General on any error.
    """
    if not question or not question.strip():
        return ClassificationResult(
            intent_type="Cost_Analysis_General",
            target_scope="account-wide",
            timeframe="last-30d",
            confidence_score=0.5,
        )

    # Step 1: Keyword matching
    matched_intents = _keyword_match(question)

    # Single clear match → high confidence
    if len(matched_intents) == 1:
        intent = matched_intents[0]
        scope = _extract_scope(question)
        timeframe = _extract_timeframe(question, session)
        return ClassificationResult(
            intent_type=intent,
            target_scope=scope,
            timeframe=timeframe,
            confidence_score=0.9,
        )

    # Two matches → pick the more specific one
    if len(matched_intents) == 2:
        intent = _pick_more_specific(matched_intents, question)
        scope = _extract_scope(question)
        timeframe = _extract_timeframe(question, session)
        return ClassificationResult(
            intent_type=intent,
            target_scope=scope,
            timeframe=timeframe,
            confidence_score=0.75,
        )

    # 3+ matches or no matches → LLM disambiguation
    if len(matched_intents) >= 3 or len(matched_intents) == 0:
        result = _llm_disambiguate(question, matched_intents, model_client)
        if result:
            return result

    # Final fallback
    return ClassificationResult(
        intent_type="Cost_Analysis_General",
        target_scope=_extract_scope(question),
        timeframe=_extract_timeframe(question, session),
        confidence_score=0.5,
    )


def _keyword_match(question: str) -> list[str]:
    """Match question against keyword patterns, return matched intent types."""
    question_lower = question.lower()
    matches = []
    for intent_type, pattern in _INTENT_PATTERNS.items():
        if pattern.search(question_lower):
            matches.append(intent_type)
    return matches


def _pick_more_specific(intents: list[str], question: str) -> str:
    """When two intents match, pick the more specific one."""
    # Specificity order: Forecasting > Optimization_Tips > Cost_Analysis_Specific > Cost_Analysis_General
    priority = {
        "Forecasting": 4,
        "Optimization_Tips": 3,
        "Cost_Analysis_Specific": 2,
        "Cost_Analysis_General": 1,
    }
    return max(intents, key=lambda x: priority.get(x, 0))


def _extract_scope(question: str) -> str:
    """Extract target scope (service name or account-wide) from question."""
    question_lower = question.lower()
    services = {
        "ec2": "ec2", "rds": "rds", "s3": "s3", "lambda": "lambda",
        "dynamodb": "dynamodb", "cloudfront": "cloudfront",
        "ebs": "ebs", "nat gateway": "network", "vpc": "network",
        "elasticache": "elasticache", "aurora": "rds",
        "neptune": "neptune", "documentdb": "documentdb",
    }
    for keyword, service in services.items():
        if keyword in question_lower:
            return service
    return "account-wide"


def _extract_timeframe(question: str, session: SessionState | None = None) -> str:
    """Extract timeframe from question or session."""
    question_lower = question.lower()

    # Check for explicit timeframes
    if any(x in question_lower for x in ["next month", "next 1 month", "next-1m"]):
        return "next-1m"
    if any(x in question_lower for x in ["next quarter", "next 3 months", "next-3m"]):
        return "next-3m"
    if any(x in question_lower for x in ["next 6 months", "next-6m"]):
        return "next-6m"
    if any(x in question_lower for x in ["next year", "next 12 months", "next-12m"]):
        return "next-12m"
    if any(x in question_lower for x in ["last week", "last 7 days", "past week"]):
        return "last-7d"
    if any(x in question_lower for x in ["last 90 days", "last 3 months", "past quarter"]):
        return "last-90d"
    if any(x in question_lower for x in ["last month", "last 30 days", "this month", "past month"]):
        return "last-30d"

    # Carry forward from session
    if session and session.active_timeframe:
        return session.active_timeframe

    return "last-30d"


def _llm_disambiguate(
    question: str,
    matched_intents: list[str],
    model_client=None,
) -> ClassificationResult | None:
    """Use LLM few-shot examples to disambiguate when keyword matching is ambiguous."""
    try:
        if model_client is None:
            model_client = boto3.client(
                "bedrock-runtime",
                region_name="us-east-1",
            )

        # Build few-shot prompt
        examples_text = "\n".join(
            f'Question: "{ex["question"]}"\nResult: {{"intent_type": "{ex["intent_type"]}", "target_scope": "{ex["target_scope"]}", "timeframe": "{ex["timeframe"]}"}}'
            for ex in FEW_SHOT_EXAMPLES
        )

        prompt = f"""Classify the following user question into exactly one intent type.
Valid intent types: {', '.join(VALID_INTENT_TYPES)}

Examples:
{examples_text}

Question: "{question}"
Result:"""

        response = model_client.invoke_model(
            modelId="us.amazon.nova-2-lite-v1:0",
            body=json.dumps({
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 150,
                    "temperature": 0.0,
                    "stopSequences": ["\n\n", "Question:"],
                },
            }),
            contentType="application/json",
            accept="application/json",
        )

        response_body = json.loads(response["body"].read())
        output_text = ""
        if "results" in response_body:
            output_text = response_body["results"][0].get("outputText", "")
        elif "outputText" in response_body:
            output_text = response_body["outputText"]

        # Parse JSON from response
        result = _parse_classification_json(output_text)
        if result:
            return result

        # Retry once on parse failure
        logger.warning("First LLM classification parse failed, retrying...")
        response2 = model_client.invoke_model(
            modelId="us.amazon.nova-2-lite-v1:0",
            body=json.dumps({
                "inputText": prompt + " Respond with valid JSON only.",
                "textGenerationConfig": {
                    "maxTokenCount": 150,
                    "temperature": 0.0,
                    "stopSequences": ["\n\n", "Question:"],
                },
            }),
            contentType="application/json",
            accept="application/json",
        )
        response_body2 = json.loads(response2["body"].read())
        output_text2 = ""
        if "results" in response_body2:
            output_text2 = response_body2["results"][0].get("outputText", "")
        elif "outputText" in response_body2:
            output_text2 = response_body2["outputText"]

        result2 = _parse_classification_json(output_text2)
        if result2:
            return result2

    except Exception as e:
        logger.warning(f"LLM disambiguation failed: {e}")

    return None


def _parse_classification_json(text: str) -> ClassificationResult | None:
    """Parse classification JSON from LLM output."""
    if not text:
        return None

    # Try to extract JSON from text
    text = text.strip()

    # Find JSON object in text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None

    try:
        data = json.loads(text[start:end])
    except json.JSONDecodeError:
        return None

    # Validate required fields
    intent_type = data.get("intent_type", "")
    if intent_type not in VALID_INTENT_TYPES:
        return None

    target_scope = data.get("target_scope", "account-wide")
    timeframe = data.get("timeframe", "last-30d")
    confidence = data.get("confidence_score", 0.7)

    # Validate confidence is a number 0-1
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.7

    return ClassificationResult(
        intent_type=intent_type,
        target_scope=target_scope if target_scope else "account-wide",
        timeframe=timeframe if timeframe else "last-30d",
        confidence_score=confidence,
    )
