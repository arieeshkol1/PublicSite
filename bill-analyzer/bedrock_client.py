"""
AWS Bill Analyzer - Bedrock AI Analysis Client Module

Queries DynamoDB for cost optimization tips matching detected services,
constructs an analysis prompt, invokes Amazon Bedrock Nova Lite model,
and returns a structured AIAnalysis dict.
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Environment variables
TIPS_TABLE_NAME = os.environ.get('TIPS_TABLE_NAME', 'ViewMyBill-CostOptimizationTips')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'amazon.nova-lite-v1:0')
MAX_TOKENS = int(os.environ.get('MAX_TOKENS', '4000'))

# Chunking and retry configuration
MAX_SERVICES_PER_BATCH = int(os.environ.get('MAX_SERVICES_PER_BATCH', '8'))
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', '2'))
RETRY_BASE_DELAY = 1  # seconds (keep short — API Gateway has 29s hard limit)

# Type alias for the AI analysis response structure
AIAnalysis = Dict[str, Any]

# Analysis prompt template
ANALYSIS_PROMPT = """You are an AWS billing expert. Analyze this AWS bill and provide insights.

## Bill Data:
{bill_data}

## Relevant Cost Optimization Tips (from AWS best practices):
{retrieved_tips}

Based on the bill data and the optimization tips above, provide:

1. SUMMARY: A 2-3 sentence overview of the bill highlighting total cost and top spending services.

2. SERVICE_ANALYSIS: For EACH service in the bill, provide a unified analysis containing:
   - explanation: The AWS pricing model for this service. Do NOT start with "This represents the cost for" \
or "Charges for". Instead, describe the actual pricing dimensions and how the service bills \
(e.g., "EC2 bills per instance-hour based on instance type and region. On-Demand t3.medium costs $0.0416/hr in us-east-1. \
Additional charges apply for EBS volumes, data transfer, and Elastic IPs."). \
If calculation parameters are available from the bill, include them \
(e.g., "6,784 hours x $0.0416/hr = $282.34 for compute, plus $43.40 for 500 GB gp3 storage").
   - billing_details: A concise one-line formula showing the actual calculation if quantities are available \
(e.g., "6,784 hrs x $0.0416/hr + 500 GB x $0.08/GB/mo"). If exact quantities are not in the bill, \
describe the typical billing units (e.g., "Billed per instance-hour + GB of storage + GB of data transfer").
   - recommendations: 1-3 specific cost-saving recommendations for THIS service, each with estimated savings percentage.

Respond in this exact JSON format:
{{
  "summary": "...",
  "service_analysis": [
    {{
      "service": "...",
      "cost": "...",
      "explanation": "...",
      "billing_details": "...",
      "recommendations": [
        {{"title": "...", "description": "...", "estimated_savings": "..."}}
      ]
    }}
  ]
}}"""


def analyze_bill(parsed_bill: Dict[str, Any]) -> AIAnalysis:
    """
    Run the full AI analysis pipeline on a parsed bill.

    For bills with many services, splits into batches of MAX_SERVICES_PER_BATCH
    services each, calls Bedrock per batch, and merges results. This avoids
    hitting Nova Lite's context/token limits on large bills.

    Args:
        parsed_bill: ParsedBill dict from bill_parser.parse_bill().

    Returns:
        AIAnalysis dict with summary, service_analysis, explanations, recommendations.

    Raises:
        RuntimeError: If Bedrock is throttled (429) or unavailable (503).
        ValueError: If the Bedrock response cannot be parsed as valid JSON.
    """
    service_totals = parsed_bill.get("service_totals", {})
    services = list(service_totals.keys())
    logger.info("Detected %d services: %s", len(services), services)

    # Query DynamoDB for optimization tips (once, for all services)
    tips = _get_optimization_tips(services)

    # If small enough, do a single call (original behavior)
    if len(services) <= MAX_SERVICES_PER_BATCH:
        prompt = _build_prompt(parsed_bill, tips)
        raw_response = _invoke_bedrock_with_retry(prompt)
        return _parse_analysis_response(raw_response)

    # --- Chunked analysis for large bills ---
    logger.info(
        "Bill has %d services, splitting into batches of %d",
        len(services), MAX_SERVICES_PER_BATCH,
    )
    batches = _split_services_into_batches(services, MAX_SERVICES_PER_BATCH)
    all_service_analyses: List[Dict[str, Any]] = []
    batch_summaries: List[str] = []

    for i, batch_services in enumerate(batches):
        logger.info("Processing batch %d/%d: %s", i + 1, len(batches), batch_services)
        batch_bill = _create_batch_bill(parsed_bill, batch_services)
        batch_tips = [t for t in tips if t.get("service") in batch_services or t.get("service") == "General"]
        prompt = _build_prompt(batch_bill, batch_tips)
        raw_response = _invoke_bedrock_with_retry(prompt)
        batch_result = _parse_analysis_response(raw_response)

        all_service_analyses.extend(batch_result.get("service_analysis", []))
        batch_summaries.append(batch_result.get("summary", ""))

    # Merge all batch results into a single response
    return _merge_batch_results(parsed_bill, all_service_analyses, batch_summaries)

def _split_services_into_batches(services: List[str], batch_size: int) -> List[List[str]]:
    """Split a list of services into batches of the given size."""
    return [services[i:i + batch_size] for i in range(0, len(services), batch_size)]


def _create_batch_bill(parsed_bill: Dict[str, Any], batch_services: List[str]) -> Dict[str, Any]:
    """Create a subset of the parsed bill containing only the given services."""
    batch_totals = {
        svc: cost for svc, cost in parsed_bill.get("service_totals", {}).items()
        if svc in batch_services
    }
    batch_line_items = [
        item for item in parsed_bill.get("line_items", [])
        if item.get("service") in batch_services
    ]
    return {
        **parsed_bill,
        "service_totals": batch_totals,
        "line_items": batch_line_items,
    }


def _merge_batch_results(
    parsed_bill: Dict[str, Any],
    all_service_analyses: List[Dict[str, Any]],
    batch_summaries: List[str],
) -> AIAnalysis:
    """Merge results from multiple batch calls into a single AIAnalysis."""
    total_cost = parsed_bill.get("total_cost", 0)
    currency = parsed_bill.get("currency", "USD")
    num_services = len(parsed_bill.get("service_totals", {}))

    # Build a combined summary
    top_services = sorted(
        all_service_analyses, key=lambda x: _extract_cost_value(x.get("cost", "0")), reverse=True
    )[:3]
    top_names = ", ".join(s.get("service", "Unknown") for s in top_services)
    summary = (
        f"Your total AWS bill is {currency} {total_cost} across {num_services} services. "
        f"Top spenders: {top_names}."
    )

    # Build legacy fields for backward compatibility
    explanations = [
        {"service": s.get("service", ""), "cost": s.get("cost", ""), "explanation": s.get("explanation", "")}
        for s in all_service_analyses
    ]
    all_recs = []
    for s in all_service_analyses:
        all_recs.extend(s.get("recommendations", []))

    return {
        "summary": summary,
        "service_analysis": all_service_analyses,
        "explanations": explanations,
        "recommendations": all_recs,
    }


def _extract_cost_value(cost_str: str) -> float:
    """Extract numeric cost from a string like '$45.23'."""
    cleaned = str(cost_str).replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _invoke_bedrock_with_retry(prompt: str) -> str:
    """Invoke Bedrock with exponential backoff retry on transient errors."""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            return _invoke_bedrock(prompt)
        except RuntimeError as e:
            last_error = e
            error_msg = str(e)
            if "Service is busy" in error_msg or "temporarily unavailable" in error_msg:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Bedrock transient error (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1, MAX_RETRIES, delay, error_msg,
                )
                time.sleep(delay)
            else:
                raise
    # All retries exhausted
    raise last_error  # type: ignore[misc]




def _get_optimization_tips(services: List[str]) -> List[Dict[str, Any]]:
    """
    Query DynamoDB for cost optimization tips matching the given services.

    Always includes "General" tips in addition to service-specific tips.

    Args:
        services: List of AWS service names detected in the bill.

    Returns:
        List of tip dicts from DynamoDB.
    """
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(TIPS_TABLE_NAME)
    tips: List[Dict[str, Any]] = []

    # Build unique set of services to query, always including "General"
    services_to_query = set(services)
    services_to_query.add("General")

    logger.info("Querying DynamoDB for tips for services: %s", services_to_query)

    for service_name in services_to_query:
        try:
            response = table.query(
                KeyConditionExpression=Key('service').eq(service_name)
            )
            items = response.get('Items', [])
            tips.extend(items)
            logger.info("Retrieved %d tips for service '%s'", len(items), service_name)
        except Exception as e:
            # DynamoDB errors are non-fatal — tips are optional
            logger.warning("Failed to query tips for service '%s': %s", service_name, str(e))

    return tips




def _build_prompt(parsed_bill: Dict[str, Any], tips: List[Dict[str, Any]]) -> str:
    """
    Construct the analysis prompt with bill data and retrieved tips.

    Args:
        parsed_bill: ParsedBill dict.
        tips: List of optimization tip dicts from DynamoDB.

    Returns:
        Formatted prompt string for Bedrock.
    """
    # Format bill data as readable text — use service_totals only to keep prompt compact.
    # Line items are too verbose for large bills and can blow up the prompt size.
    bill_lines = [
        f"Invoice Number: {parsed_bill.get('invoice_number', 'N/A')}",
        f"Account ID: {parsed_bill.get('account_id', 'N/A')}",
        f"Billing Period: {parsed_bill.get('period_start', 'N/A')} to {parsed_bill.get('period_end', 'N/A')}",
        f"Currency: {parsed_bill.get('currency', 'USD')}",
        f"Total Cost: {parsed_bill.get('total_cost', 0)}",
        "",
        "Service Breakdown:",
    ]
    for service, cost in parsed_bill.get("service_totals", {}).items():
        bill_lines.append(f"  - {service}: {cost}")

    bill_data = "\n".join(bill_lines)

    # Format tips as readable text (limit to 3 per service to keep prompt compact)
    if tips:
        tip_lines = []
        for tip in tips[:15]:  # cap total tips to avoid bloating prompt
            tip_lines.append(
                f"- [{tip.get('service', 'General')}] {tip.get('title', '')}: "
                f"{tip.get('description', '')} "
                f"(Estimated savings: {tip.get('estimatedSavings', 'N/A')}, "
                f"Difficulty: {tip.get('difficulty', 'N/A')})"
            )
        retrieved_tips = "\n".join(tip_lines)
    else:
        retrieved_tips = "No specific tips available for the detected services."

    return ANALYSIS_PROMPT.format(bill_data=bill_data, retrieved_tips=retrieved_tips)


def _invoke_bedrock(prompt: str) -> str:
    """
    Invoke Amazon Bedrock Nova Lite model with the given prompt.

    Args:
        prompt: The analysis prompt string.

    Returns:
        Raw response text from Bedrock.

    Raises:
        RuntimeError: If Bedrock returns a throttling (429) or
                      unavailability (503) error.
    """
    bedrock = boto3.client('bedrock-runtime')

    request_body = {
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {
            "max_new_tokens": MAX_TOKENS,
            "temperature": 0.7,
            "top_p": 0.9,
        },
    }

    try:
        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(request_body),
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "ThrottlingException":
            logger.error("Bedrock throttling error: %s", str(e))
            raise RuntimeError("Service is busy, please retry in a moment") from e
        if error_code == "ServiceUnavailableException":
            logger.error("Bedrock unavailable: %s", str(e))
            raise RuntimeError("AI service temporarily unavailable") from e
        logger.error("Bedrock invocation failed: %s", str(e))
        raise

    response_body = json.loads(response["body"].read())

    # Nova Lite returns content in output.message.content[0].text
    try:
        return response_body["output"]["message"]["content"][0]["text"]
    except (KeyError, IndexError) as e:
        logger.error("Unexpected Bedrock response structure: %s", response_body)
        raise ValueError("Failed to extract text from Bedrock response") from e


def _parse_analysis_response(response_text: str) -> AIAnalysis:
    """
    Parse the raw Bedrock response text into a structured AIAnalysis dict.

    Args:
        response_text: Raw JSON string from Bedrock.

    Returns:
        AIAnalysis dict with summary and service_analysis.

    Raises:
        ValueError: If the response is not valid JSON or missing required fields.
    """
    # Strip markdown code fences if present
    cleaned = response_text.strip()
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', cleaned)
    if json_match:
        cleaned = json_match.group(1).strip()

    try:
        analysis = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Bedrock response is not valid JSON: {str(e)}") from e

    if not isinstance(analysis, dict):
        raise ValueError("Bedrock response is not a JSON object")

    if "summary" not in analysis or not isinstance(analysis["summary"], str):
        raise ValueError("Bedrock response missing required 'summary' string field")

    # Support both new format (service_analysis) and legacy (explanations + recommendations)
    if "service_analysis" in analysis and isinstance(analysis["service_analysis"], list):
        for i, svc in enumerate(analysis["service_analysis"]):
            for field in ("service", "cost", "explanation"):
                if field not in svc:
                    raise ValueError(
                        f"service_analysis at index {i} missing required field '{field}'"
                    )
        # Also build legacy fields for backward compatibility
        if "explanations" not in analysis:
            analysis["explanations"] = [
                {
                    "service": s.get("service", ""),
                    "cost": s.get("cost", ""),
                    "explanation": s.get("explanation", ""),
                }
                for s in analysis["service_analysis"]
            ]
        if "recommendations" not in analysis:
            all_recs = []
            for s in analysis["service_analysis"]:
                for r in s.get("recommendations", []):
                    all_recs.append(r)
            analysis["recommendations"] = all_recs
    else:
        # Legacy format validation
        if "explanations" not in analysis or not isinstance(analysis["explanations"], list):
            raise ValueError("Bedrock response missing 'service_analysis' or 'explanations'")
        for i, exp in enumerate(analysis["explanations"]):
            for field in ("service", "cost", "explanation"):
                if field not in exp:
                    raise ValueError(
                        f"Explanation at index {i} missing required field '{field}'"
                    )
        if "recommendations" not in analysis:
            analysis["recommendations"] = []

    return analysis
