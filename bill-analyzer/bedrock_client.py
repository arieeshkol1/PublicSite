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
MAX_TOKENS = int(os.environ.get('MAX_TOKENS', '5000'))

# Chunking and retry configuration
MAX_SERVICES_PER_BATCH = int(os.environ.get('MAX_SERVICES_PER_BATCH', '20'))
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', '2'))
RETRY_BASE_DELAY = 1  # seconds (keep short — API Gateway has 29s hard limit)

# Type alias for the AI analysis response structure
AIAnalysis = Dict[str, Any]

# Map bill parser service names → DynamoDB tip service names
# The bill parser extracts full AWS names (e.g. "Amazon EC2"),
# but DynamoDB tips use short names (e.g. "EC2").
SERVICE_NAME_TO_TIP_KEY: Dict[str, str] = {
    "Amazon Elastic Compute Cloud": "EC2",
    "Amazon EC2": "EC2",
    "Amazon Simple Storage Service": "S3",
    "Amazon S3": "S3",
    "Amazon Relational Database Service": "RDS",
    "Amazon RDS": "RDS",
    "AWS Lambda": "Lambda",
    "Amazon CloudFront": "CloudFront",
    "Amazon Virtual Private Cloud": "NAT Gateway",
    "Amazon VPC": "NAT Gateway",
    "Elastic Block Store": "EBS",
    "Amazon EBS": "EBS",
    "Amazon Elastic Block Store": "EBS",
    "Data Transfer": "Data Transfer",
    "AWS Data Transfer": "Data Transfer",
    "Amazon Route 53": "Route 53",
    "Amazon DynamoDB": "DynamoDB",
    "Amazon ElastiCache": "ElastiCache",
    "Amazon OpenSearch Service": "OpenSearch",
    "Amazon Redshift": "Redshift",
    "Amazon CloudWatch": "CloudWatch",
    "AWS Key Management Service": "KMS",
    "Amazon KMS": "KMS",
    "AWS Config": "Config",
    "Amazon Simple Notification Service": "SNS",
    "Amazon SNS": "SNS",
    "Amazon Simple Queue Service": "SQS",
    "Amazon SQS": "SQS",
    "Amazon API Gateway": "API Gateway",
    "AWS WAF": "WAF",
    "Amazon Elastic Container Service": "ECS",
    "Amazon ECS": "ECS",
    "Amazon Elastic Container Registry": "ECR",
    "Amazon ECR": "ECR",
    "AWS Secrets Manager": "Secrets Manager",
    "AWS Cloud Map": "Cloud Map",
    "Elastic Load Balancing": "ELB",
    "Amazon Elastic Load Balancing": "ELB",
}

# Analysis prompt template
ANALYSIS_PROMPT = """You are an AWS billing expert. Analyze this AWS bill and provide insights.

## Bill Data:
{bill_data}

## Cost Optimization Tips:
{retrieved_tips}

## CRITICAL RULES — Savings Plans & Reserved Instances eligibility:
Only recommend Savings Plans or Reserved Instances for services that actually support them.

Compute Savings Plans (up to 66% off) apply ONLY to: Amazon EC2, AWS Lambda, AWS Fargate.
EC2 Instance Savings Plans (up to 72% off) apply ONLY to: Amazon EC2.
Database Savings Plans (up to 35% off) apply ONLY to: Amazon RDS, Amazon Aurora, Amazon DynamoDB, Amazon ElastiCache, Amazon DocumentDB, Amazon Neptune, Amazon Keyspaces, Amazon Timestream, AWS DMS. Note: Only Gen7+ instance families (r7g, m7i, etc.) are eligible; older families (r5, m5, t3) require Reserved Instances instead.
Reserved Instances apply ONLY to: Amazon EC2, Amazon RDS, Amazon Redshift, Amazon ElastiCache, Amazon OpenSearch, Amazon DynamoDB, AWS Elemental MediaLive, Amazon MemoryDB.
EC2 Reserved Instance Marketplace: Customers can buy discounted "second-hand" RIs from other AWS customers at reduced prices. Since Jan 2024, marketplace-purchased RIs cannot be resold. Standard RIs only (not Convertible).

DO NOT recommend Savings Plans or Reserved Instances for: VPC, Route 53, CloudWatch, S3, KMS, Secrets Manager, Config, Cloud Map, Data Transfer, ECR, ECS (unless Fargate), SNS, SQS, API Gateway, Lambda (RI not available — use Compute SP only), Elastic Load Balancing, or any other service not listed above.
CloudFront Security Savings Bundle (up to 30% off): Available for Amazon CloudFront. Commit to a monthly spend for 1 year. Also includes free AWS WAF usage up to 10% of the committed amount. Recommend this instead of generic Savings Plans for CloudFront and WAF.

## Savings Plans & Reserved Instances overlap rules:
SP and RI CAN coexist on the same account. AWS applies discounts in this order:
1. Reserved Instances are applied FIRST to matching usage (exact instance type/region match).
2. Savings Plans are applied SECOND to remaining eligible usage not already covered by RIs.
3. Any leftover usage is billed at On-Demand rates.
This means RI + SP never double-discount the same hour of usage. Best practice: use RIs for steady-state predictable workloads (specific instance type/region), then layer Compute Savings Plans on top to cover variable/flexible usage across instance families and regions.

## EC2 cost optimization tiers (recommend in this order):
1. Savings Plans / Reserved Instances (for steady-state workloads)
2. EC2 Reserved Instance Marketplace (buy discounted second-hand RIs)
3. Spot Instances (up to 90% off for fault-tolerant/stateless workloads: batch jobs, CI/CD, containers, HPC, dev/test — NOT for stateful production databases or single-instance apps)
4. Serverless migration: Consider AWS Lambda (for event-driven) or AWS Fargate (for containerized workloads) to eliminate idle compute costs entirely

## Rightsizing eligibility:
Services that support rightsizing (can change instance type/size/class): Amazon EC2 (instance type/size), Amazon RDS (instance class), Amazon ElastiCache (node type), Amazon OpenSearch (instance type), Amazon Redshift (node type), Amazon ECS/Fargate (task CPU/memory).
Services that do NOT support rightsizing: Route 53, CloudWatch, S3, KMS, Secrets Manager, AWS Config, Cloud Map, Data Transfer, ECR, SNS, SQS, WAF, CloudFront, API Gateway, VPC (NAT Gateway has fixed per-hour pricing).
For non-rightsizable services, recommend usage optimization instead: reduce unnecessary requests, clean up unused resources, consolidate, or use more efficient pricing tiers.

## Service-specific rules (NEVER leave recommendations empty for these):
Elastic Load Balancing: ALWAYS recommend checking if the load balancer is idle (fewer than 100 requests/day for 7 days = idle). Each idle ELB costs ~$200/year. Check for unused/unregistered backend instances.
VPC / NAT Gateway: ALWAYS recommend checking if VPC resources are idle or oversized. Check for unused NAT Gateways, consider VPC endpoints to reduce NAT Gateway data processing costs, evaluate if downsizing is possible.
AWS KMS: ALWAYS recommend auditing for unused KMS keys. Each key costs $1/month regardless of usage. Disable or schedule deletion of keys no longer in use.
Amazon S3: ALWAYS recommend reviewing retention policies, lifecycle rules, and delete policies. Check for incomplete multipart uploads, old object versions, and objects that can be moved to cheaper storage classes or deleted.

Provide analysis in this JSON format:

1. SUMMARY: 2-3 sentences about total cost and top spenders.

2. SERVICE_ANALYSIS: For each service:
   - explanation: Use actual line item data if available (cite quantities, rates, amounts). If region breakdown data is provided, mention the top regions and instance types. If line items show "NatGateway-Hours: 672", write "You ran a NAT Gateway for 672 hours at $0.045/hr = $30.24". If no line items, briefly describe the pricing model. Do NOT start with "This represents" or "Charges for".
   - billing_details: One-line formula with actual quantities if available (e.g., "672 hrs x $0.045/hr = $30.24"). Use generic units only if no line items exist.
   - recommendations: 1-2 cost-saving tips with estimated savings %. Only suggest Savings Plans or Reserved Instances if the service is eligible per the rules above. If region data shows usage spread across multiple regions, recommend consolidating to fewer regions where possible.

3. SAVINGS_PLAN_ANALYSIS: Based on Commitment Discount Status, recommend Savings Plans and/or Reserved Instances. Only mention services that are eligible per the rules above.

Respond in this exact JSON:
{{
  "summary": "...",
  "service_analysis": [
    {{
      "service": "...",
      "cost": "...",
      "explanation": "...",
      "billing_details": "...",
      "recommendations": [{{"title": "...", "description": "...", "estimated_savings": "..."}}]
    }}
  ],
  "savings_plan_analysis": {{
    "has_savings_plans": true/false,
    "has_reserved_instances": true/false,
    "recommendation": "...",
    "potential_savings_percent": "...",
    "how_to_purchase": "..."
  }}
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
    savings_plan_analysis: Dict[str, Any] | None = None

    for i, batch_services in enumerate(batches):
        logger.info("Processing batch %d/%d: %s", i + 1, len(batches), batch_services)
        batch_bill = _create_batch_bill(parsed_bill, batch_services)
        batch_tips = [t for t in tips if t.get("service") in {SERVICE_NAME_TO_TIP_KEY.get(s, s) for s in batch_services} or t.get("service") == "General"]
        prompt = _build_prompt(batch_bill, batch_tips)
        raw_response = _invoke_bedrock_with_retry(prompt)
        batch_result = _parse_analysis_response(raw_response)

        all_service_analyses.extend(batch_result.get("service_analysis", []))
        batch_summaries.append(batch_result.get("summary", ""))
        # Capture savings_plan_analysis from first batch (it has the full bill context)
        if i == 0 and "savings_plan_analysis" in batch_result:
            savings_plan_analysis = batch_result["savings_plan_analysis"]

    # Merge all batch results into a single response
    return _merge_batch_results(parsed_bill, all_service_analyses, batch_summaries, savings_plan_analysis)

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
    savings_plan_analysis: Dict[str, Any] | None = None,
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

    result = {
        "summary": summary,
        "service_analysis": all_service_analyses,
        "explanations": explanations,
        "recommendations": all_recs,
    }
    if savings_plan_analysis:
        result["savings_plan_analysis"] = savings_plan_analysis
    return result


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
    # Map full bill names to short DynamoDB tip keys
    services_to_query = set()
    for svc in services:
        tip_key = SERVICE_NAME_TO_TIP_KEY.get(svc, svc)
        services_to_query.add(tip_key)
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
    # Format bill data as readable text — include service_totals and line items
    # so Bedrock can explain how charges were calculated from the actual bill data.
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

    # Include line items grouped by service for calculation details
    # Only include if line items have different descriptions than service names
    # (billing console format just repeats service names — skip those)
    line_items = parsed_bill.get("line_items", [])
    if line_items:
        items_by_svc: Dict[str, List[str]] = {}
        for item in line_items:
            svc = item.get("service", "Unknown")
            desc = item.get("description", "")
            cost = item.get("cost", 0)
            # Skip if description is just the service name (no extra detail)
            if desc and desc != svc:
                if svc not in items_by_svc:
                    items_by_svc[svc] = []
                items_by_svc[svc].append(f"{desc}: {cost}")
        if items_by_svc:
            bill_lines.append("")
            bill_lines.append("Line Item Details (from the bill):")
            for svc, details in items_by_svc.items():
                bill_lines.append(f"  {svc}:")
                for d in details[:8]:  # cap per service
                    bill_lines.append(f"    - {d}")

    # Include commitment discount detection results
    discounts = parsed_bill.get("commitment_discounts", {})
    if discounts:
        bill_lines.append("")
        bill_lines.append("Commitment Discount Status:")
        if discounts.get("has_savings_plans"):
            bill_lines.append("  - Savings Plans: ACTIVE (detected in bill)")
            for detail in discounts.get("savings_plan_details", [])[:5]:
                bill_lines.append(f"    > {detail}")
        else:
            bill_lines.append("  - Savings Plans: NOT DETECTED (customer is likely paying On-Demand rates)")
        if discounts.get("has_reserved_instances"):
            bill_lines.append("  - Reserved Instances: ACTIVE (detected in bill)")
            for detail in discounts.get("reserved_instance_details", [])[:5]:
                bill_lines.append(f"    > {detail}")
        else:
            bill_lines.append("  - Reserved Instances: NOT DETECTED")
        if discounts.get("savings_amount"):
            bill_lines.append(f"  - Total savings shown in bill: {discounts['savings_amount']}")

    # Include region breakdown per service (if available)
    region_breakdown = parsed_bill.get("region_breakdown", {})
    if region_breakdown:
        bill_lines.append("")
        bill_lines.append("Region Breakdown by Service:")
        for svc, regions in region_breakdown.items():
            bill_lines.append(f"  {svc}:")
            for region_entry in regions[:6]:  # cap regions per service
                rname = region_entry.get("region", "Unknown")
                rcost = region_entry.get("cost", 0)
                bill_lines.append(f"    - {rname}: {rcost}")
                for detail in region_entry.get("details", [])[:4]:  # cap details per region
                    bill_lines.append(f"      > {detail.get('description', '')}")

    # Include region breakdown per service (if available)
    region_breakdown = parsed_bill.get("region_breakdown", {})
    if region_breakdown:
        bill_lines.append("")
        bill_lines.append("Region Breakdown by Service:")
        for svc, regions in region_breakdown.items():
            bill_lines.append(f"  {svc}:")
            for region_entry in regions[:6]:  # cap regions per service
                rname = region_entry.get("region", "Unknown")
                rcost = region_entry.get("cost", 0)
                bill_lines.append(f"    - {rname}: {rcost}")
                for detail in region_entry.get("details", [])[:4]:  # cap details per region
                    bill_lines.append(f"      > {detail.get('description', '')}")

    bill_data = "\n".join(bill_lines)

    # Format tips as readable text (limit to 3 per service to keep prompt compact)
    if tips:
        tip_lines = []
        for tip in tips[:10]:  # cap total tips to keep prompt compact
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
            "temperature": 0.3,
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
