#!/usr/bin/env python3
"""
Seed script for OpenAI optimization tips in DynamoDB.

Populates the ViewMyBill-CostOptimizationTips table with OpenAI-specific
cost optimization tips covering 8 categories:
  - model-selection
  - prompt-length-reduction
  - caching-strategies
  - batch-api-usage
  - fine-tuning-cost-tradeoffs
  - architectural-optimization
  - subscription-management
  - token-minimization

Usage:
    python scripts/seed_openai_tips.py
    python scripts/seed_openai_tips.py --region us-east-1
"""

import logging
import os
import sys

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = "ViewMyBill-CostOptimizationTips"
REGION = os.environ.get("AWS_REGION", "us-east-1")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

OPENAI_TIPS = [
    # ─── Model Selection (3 tips) ───────────────────────────────────────
    {
        "service": "GPT-4",
        "tipId": "openai-model-selection-001",
        "provider": "openai",
        "category": "model-selection",
        "title": "Use GPT-4o-mini for simple classification tasks",
        "description": (
            "GPT-4o-mini handles classification, summarization, and simple Q&A "
            "at roughly 1/30th the cost of GPT-4. Migrate low-complexity tasks "
            "to GPT-4o-mini to reduce per-request cost significantly without "
            "meaningful quality loss."
        ),
        "estimatedSavings": "$50-500/month depending on volume",
        "difficulty": "easy",
    },
    {
        "service": "GPT-4o",
        "tipId": "openai-model-selection-002",
        "provider": "openai",
        "category": "model-selection",
        "title": "Switch from GPT-4 to GPT-4o for equivalent quality at lower cost",
        "description": (
            "GPT-4o provides comparable quality to GPT-4 at roughly half the "
            "token price. For most production workloads GPT-4o is a drop-in "
            "replacement that delivers faster responses and lower cost per token."
        ),
        "estimatedSavings": "$100-1000/month depending on volume",
        "difficulty": "easy",
    },
    {
        "service": "Embeddings",
        "tipId": "openai-model-selection-003",
        "provider": "openai",
        "category": "model-selection",
        "title": "Use text-embedding-3-small instead of text-embedding-ada-002",
        "description": (
            "The text-embedding-3-small model costs 5x less than ada-002 while "
            "offering comparable retrieval quality for most use cases. Switch "
            "embedding pipelines to the newer model to cut embedding costs."
        ),
        "estimatedSavings": "$20-200/month depending on volume",
        "difficulty": "easy",
    },
    # ─── Prompt Length Reduction (2 tips) ───────────────────────────────
    {
        "service": "Token Optimization",
        "tipId": "openai-prompt-reduction-001",
        "provider": "openai",
        "category": "prompt-length-reduction",
        "title": "Compress system prompts to reduce input token costs",
        "description": (
            "Long system prompts are sent with every request, multiplying cost. "
            "Shorten instructions, remove redundant examples, and use concise "
            "formatting to reduce input tokens by 30-60% without changing behavior."
        ),
        "estimatedSavings": "$30-300/month depending on request volume",
        "difficulty": "medium",
    },
    {
        "service": "Prompt Optimization",
        "tipId": "openai-prompt-reduction-002",
        "provider": "openai",
        "category": "prompt-length-reduction",
        "title": "Limit conversation history to recent messages only",
        "description": (
            "Sending full conversation history grows input tokens linearly. "
            "Truncate to the last 5-10 messages or use summarization of older "
            "context to cap input token growth and reduce cost per turn."
        ),
        "estimatedSavings": "$40-400/month for chat applications",
        "difficulty": "medium",
    },
    # ─── Caching Strategies (2 tips) ───────────────────────────────────
    {
        "service": "Caching",
        "tipId": "openai-caching-001",
        "provider": "openai",
        "category": "caching-strategies",
        "title": "Cache identical prompt responses to eliminate redundant API calls",
        "description": (
            "Many applications send the same or near-identical prompts repeatedly. "
            "Implement a response cache keyed on prompt hash to serve repeat "
            "queries instantly without incurring API costs."
        ),
        "estimatedSavings": "$50-500/month depending on cache hit rate",
        "difficulty": "medium",
    },
    {
        "service": "Caching",
        "tipId": "openai-caching-002",
        "provider": "openai",
        "category": "caching-strategies",
        "title": "Use semantic caching for similar but not identical queries",
        "description": (
            "Semantic caching matches queries by meaning rather than exact text. "
            "Embedding-based similarity lookup can serve cached results for "
            "paraphrased questions, further reducing API call volume and cost."
        ),
        "estimatedSavings": "$30-300/month depending on query diversity",
        "difficulty": "hard",
    },
    # ─── Batch API Usage (2 tips) ──────────────────────────────────────
    {
        "service": "Batch API",
        "tipId": "openai-batch-001",
        "provider": "openai",
        "category": "batch-api-usage",
        "title": "Use the Batch API for non-time-sensitive workloads at 50% discount",
        "description": (
            "OpenAI's Batch API processes requests asynchronously within 24 hours "
            "at half the cost of synchronous calls. Migrate offline tasks like "
            "content generation, data labeling, and bulk summarization to batch."
        ),
        "estimatedSavings": "$100-1000/month for batch-eligible workloads",
        "difficulty": "medium",
    },
    {
        "service": "Batch API",
        "tipId": "openai-batch-002",
        "provider": "openai",
        "category": "batch-api-usage",
        "title": "Consolidate small requests into batch jobs to reduce overhead",
        "description": (
            "Many small synchronous requests incur per-call overhead and higher "
            "pricing. Group related tasks into batch files processed via the "
            "Batch API endpoint to benefit from volume pricing and reduced cost."
        ),
        "estimatedSavings": "$20-200/month depending on request patterns",
        "difficulty": "easy",
    },
    # ─── Fine-Tuning Cost Tradeoffs (2 tips) ───────────────────────────
    {
        "service": "Fine-Tuning",
        "tipId": "openai-finetuning-001",
        "provider": "openai",
        "category": "fine-tuning-cost-tradeoffs",
        "title": "Fine-tune GPT-4o-mini to replace GPT-4 for domain-specific tasks",
        "description": (
            "A fine-tuned GPT-4o-mini can match GPT-4 quality for narrow tasks "
            "at a fraction of the inference cost. The one-time training cost is "
            "recovered within weeks for high-volume workloads."
        ),
        "estimatedSavings": "$200-2000/month after training cost amortization",
        "difficulty": "hard",
    },
    {
        "service": "Fine-Tuning",
        "tipId": "openai-finetuning-002",
        "provider": "openai",
        "category": "fine-tuning-cost-tradeoffs",
        "title": "Reduce prompt length by encoding instructions into a fine-tuned model",
        "description": (
            "Fine-tuning lets you bake repetitive instructions into the model "
            "weights, eliminating long system prompts from every request. This "
            "cuts input tokens per call and reduces inference cost proportionally."
        ),
        "estimatedSavings": "$50-500/month from prompt token savings",
        "difficulty": "hard",
    },
    # ─── Flex Processing (1 tip) ───────────────────────────────────────
    {
        "service": "General",
        "tipId": "openai-flex-processing-001",
        "provider": "openai",
        "category": "architectural-optimization",
        "title": "Use Flex Processing for lower-priority or non-production tasks",
        "description": (
            "Flex Processing trades slower, off-peak response times for massive "
            "cost reductions. Route non-production workloads, staging tests, and "
            "low-priority background jobs through Flex endpoints to cut costs "
            "without impacting user-facing latency."
        ),
        "estimatedSavings": "$50-500/month depending on eligible volume",
        "difficulty": "easy",
    },
    # ─── Token Minimization (2 tips) ───────────────────────────────────
    {
        "service": "Token Optimization",
        "tipId": "openai-token-min-001",
        "provider": "openai",
        "category": "prompt-length-reduction",
        "title": "Minify structured JSON output to save 30-50% on response tokens",
        "description": (
            "Add 'Return minified JSON on a single line without whitespaces or "
            "indentation' to your prompts. Whitespace and line breaks count as "
            "tokens; stripping them from structured responses can reduce output "
            "token costs by 30-50%."
        ),
        "estimatedSavings": "$30-300/month for JSON-heavy workloads",
        "difficulty": "easy",
    },
    {
        "service": "Token Optimization",
        "tipId": "openai-token-min-002",
        "provider": "openai",
        "category": "prompt-length-reduction",
        "title": "Set max_tokens parameter to prevent runaway verbose generation",
        "description": (
            "Always set the max_tokens parameter on API calls to cap output "
            "length. Without limits, models may generate overly verbose responses "
            "that waste tokens. Set hard limits appropriate to your task to "
            "prevent unexpected cost spikes from long outputs."
        ),
        "estimatedSavings": "$20-200/month from prevented overgeneration",
        "difficulty": "easy",
    },
    # ─── Multi-Model Routing (1 tip) ──────────────────────────────────
    {
        "service": "General",
        "tipId": "openai-multimodel-001",
        "provider": "openai",
        "category": "model-selection",
        "title": "Route tasks dynamically across models for optimal cost-quality",
        "description": (
            "Use a hybrid multi-model approach: route standard processing, test "
            "generation, and translation to cheaper alternatives (open-weights or "
            "GPT-4o-mini), and selectively hand off to OpenAI flagship models "
            "only when complex reasoning is required."
        ),
        "estimatedSavings": "$100-1000/month for multi-step pipelines",
        "difficulty": "hard",
    },
    # ─── Subscription & Workspace Management (4 tips) ──────────────────
    {
        "service": "General",
        "tipId": "openai-workspace-001",
        "provider": "openai",
        "category": "subscription-management",
        "title": "Audit inactive ChatGPT Team/Enterprise seats monthly",
        "description": (
            "ChatGPT Team and Enterprise accounts bill per seat monthly. Audit "
            "your workspace regularly to reclaim licenses from users who have not "
            "logged in recently. Each unused seat is wasted spend that adds up "
            "over time."
        ),
        "estimatedSavings": "$25-100/month per reclaimed seat",
        "difficulty": "easy",
    },
    {
        "service": "General",
        "tipId": "openai-workspace-002",
        "provider": "openai",
        "category": "subscription-management",
        "title": "Build internal Custom GPTs instead of paying for third-party wrappers",
        "description": (
            "Instead of paying for external third-party wrapper tools, build "
            "internal Custom GPTs inside your Team workspace. Pre-configure them "
            "with system instructions, documentation, or API actions for your "
            "staff at no extra per-query cost."
        ),
        "estimatedSavings": "$50-500/month from eliminated third-party tools",
        "difficulty": "medium",
    },
    {
        "service": "General",
        "tipId": "openai-workspace-003",
        "provider": "openai",
        "category": "subscription-management",
        "title": "Turn off chat history for free-tier contractors to avoid training",
        "description": (
            "For temporary contractors using free accounts for business tasks, "
            "ensure they disable chat history in settings. This prevents their "
            "data from being used for training while avoiding the need to "
            "immediately provision a paid seat if their volume is low."
        ),
        "estimatedSavings": "$25/month per contractor not upgraded to paid",
        "difficulty": "easy",
    },
    {
        "service": "General",
        "tipId": "openai-workspace-004",
        "provider": "openai",
        "category": "subscription-management",
        "title": "Set hard dollar limits and alert thresholds in OpenAI Billing",
        "description": (
            "Always configure hard dollar spending limits and soft alert "
            "thresholds in the OpenAI Billing Dashboard. Unchecked agent loops "
            "or runaway testing scripts in staging can exhaust an entire month's "
            "budget in minutes if left unmonitored."
        ),
        "estimatedSavings": "Prevents budget overruns (potentially $1000+)",
        "difficulty": "easy",
    },
]


def seed_openai_tips():
    """Write OpenAI optimization tips to DynamoDB using batch_writer.

    Returns:
        tuple: (loaded_count, failed_count)
    """
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    # Verify table is reachable
    try:
        table.load()
    except ClientError as e:
        logger.error(
            "Cannot reach table '%s': %s",
            TABLE_NAME,
            e.response["Error"]["Message"],
        )
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error accessing table '%s': %s", TABLE_NAME, e)
        sys.exit(1)

    loaded = 0
    failed = 0

    try:
        with table.batch_writer(overwrite_by_pkeys=["service", "tipId"]) as batch:
            for tip in OPENAI_TIPS:
                try:
                    # Ensure the 'cloud' field is set to 'OpenAI' for proper filtering
                    item = dict(tip)
                    item["cloud"] = "OpenAI"
                    batch.put_item(Item=item)
                    loaded += 1
                except ClientError as e:
                    logger.error(
                        "Failed to write tip '%s': %s",
                        tip["tipId"],
                        e.response["Error"]["Message"],
                    )
                    failed += 1
                except Exception as e:
                    logger.error("Failed to write tip '%s': %s", tip["tipId"], e)
                    failed += 1
    except ClientError as e:
        logger.error(
            "Batch write failed for table '%s': %s",
            TABLE_NAME,
            e.response["Error"]["Message"],
        )
        sys.exit(1)
    except Exception as e:
        logger.error("Batch write failed for table '%s': %s", TABLE_NAME, e)
        sys.exit(1)

    return loaded, failed


def main():
    global REGION

    # Support --region argument
    if "--region" in sys.argv:
        idx = sys.argv.index("--region")
        if idx + 1 < len(sys.argv):
            REGION = sys.argv[idx + 1]

    logger.info("Seeding OpenAI tips to table '%s' in region '%s'", TABLE_NAME, REGION)
    logger.info("Tips to seed: %d", len(OPENAI_TIPS))

    loaded, failed = seed_openai_tips()

    logger.info("Done! Loaded: %d, Failed: %d", loaded, failed)

    if failed > 0:
        logger.error("%d tips failed to write", failed)
        sys.exit(1)

    logger.info("All OpenAI tips seeded successfully.")


if __name__ == "__main__":
    main()
