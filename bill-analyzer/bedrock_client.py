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
from typing import Any, Dict, List

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Environment variables
TIPS_TABLE_NAME = os.environ.get('TIPS_TABLE_NAME', 'ViewMyBill-CostOptimizationTips')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'amazon.nova-lite-v1:0')
MAX_TOKENS = int(os.environ.get('MAX_TOKENS', '4000'))

# Type alias for the AI analysis response structure
AIAnalysis = Dict[str, Any]

# Analysis prompt template
ANALYSIS_PROMPT = """You are an AWS billing expert. Analyze this AWS bill and provide insights.

## Bill Data:
{bill_data}

## Relevant Cost Optimization Tips (from AWS best practices):
{retrieved_tips}

Based on the bill data and the optimization tips above, provide:

1. SUMMARY: A 2-3 sentence overview of the bill highlighting total cost and top spending services
2. EXPLANATIONS: For each service in the bill, explain what the charges represent in plain language. \
Also describe how the service is billed (e.g., per hour, per GB, per request) and provide one specific \
cost-saving tip for that service.
3. RECOMMENDATIONS: 3-5 specific, actionable cost-saving recommendations. Prioritize tips that match \
the services in this bill. Include estimated savings percentages where applicable.

Respond in this exact JSON format:
{{
  "summary": "...",
  "explanations": [
    {{"service": "...", "cost": "...", "explanation": "...", "billing_model": "...", "savings_tip": "..."}}
  ],
  "recommendations": [
    {{"title": "...", "description": "...", "estimated_savings": "...", "difficulty": "..."}}
  ]
}}"""


def analyze_bill(parsed_bill: Dict[str, Any]) -> AIAnalysis:
    """
    Run the full AI analysis pipeline on a parsed bill.

    Steps:
        1. Query DynamoDB for optimization tips matching detected services.
        2. Construct the analysis prompt with bill data and retrieved tips.
        3. Invoke Bedrock Nova Lite model.
        4. Parse and return the structured AIAnalysis response.

    Args:
        parsed_bill: ParsedBill dict from bill_parser.parse_bill().

    Returns:
        AIAnalysis dict with the following structure:
            {
                "summary": str,
                "explanations": [{"service": str, "cost": str, "explanation": str}],
                "recommendations": [
                    {"title": str, "description": str,
                     "estimated_savings": str, "difficulty": str}
                ]
            }

    Raises:
        RuntimeError: If Bedrock is throttled (429) or unavailable (503).
        ValueError: If the Bedrock response cannot be parsed as valid JSON.
    """
    # 1. Extract service names from the parsed bill
    services = list(parsed_bill.get("service_totals", {}).keys())
    logger.info("Detected services: %s", services)

    # 2. Query DynamoDB for optimization tips
    tips = _get_optimization_tips(services)

    # 3. Build the analysis prompt
    prompt = _build_prompt(parsed_bill, tips)

    # 4. Invoke Bedrock
    raw_response = _invoke_bedrock(prompt)

    # 5. Parse and return structured response
    return _parse_analysis_response(raw_response)



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
    # Format bill data as readable text
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

    if parsed_bill.get("line_items"):
        bill_lines.append("")
        bill_lines.append("Line Items:")
        for item in parsed_bill["line_items"]:
            bill_lines.append(
                f"  - {item.get('service', 'Unknown')}: {item.get('cost', 0)} "
                f"({item.get('description', '')})"
            )

    bill_data = "\n".join(bill_lines)

    # Format tips as readable text
    if tips:
        tip_lines = []
        for tip in tips:
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
        AIAnalysis dict.

    Raises:
        ValueError: If the response is not valid JSON or missing required fields.
    """
    # Strip markdown code fences if present (LLMs sometimes wrap JSON in ```json ... ```)
    cleaned = response_text.strip()
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', cleaned)
    if json_match:
        cleaned = json_match.group(1).strip()

    try:
        analysis = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Bedrock response is not valid JSON: {str(e)}") from e

    # Validate required top-level fields
    if not isinstance(analysis, dict):
        raise ValueError("Bedrock response is not a JSON object")

    if "summary" not in analysis or not isinstance(analysis["summary"], str):
        raise ValueError("Bedrock response missing required 'summary' string field")

    if "explanations" not in analysis or not isinstance(analysis["explanations"], list):
        raise ValueError("Bedrock response missing required 'explanations' array field")

    for i, exp in enumerate(analysis["explanations"]):
        for field in ("service", "cost", "explanation"):
            if field not in exp:
                raise ValueError(
                    f"Explanation at index {i} missing required field '{field}'"
                )

    if "recommendations" not in analysis or not isinstance(analysis["recommendations"], list):
        raise ValueError("Bedrock response missing required 'recommendations' array field")

    for i, rec in enumerate(analysis["recommendations"]):
        for field in ("title", "description", "estimated_savings"):
            if field not in rec:
                raise ValueError(
                    f"Recommendation at index {i} missing required field '{field}'"
                )

    return analysis
