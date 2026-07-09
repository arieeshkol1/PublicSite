"""
Answer Healer Lambda — "Bedrock Investigator" self-healing mechanism.

Triggered asynchronously by audit-evaluator when audit_score < threshold.

PURPOSE: Fix the KNOWLEDGE BASE (Tips table), not just rewrite the answer.
The system heals itself so future identical questions are correct from the first attempt.

Flow:
  1. Identify the knowledge gap from audit_improvement_suggestions
  2. Research certified internet sources (official vendor docs) via Bedrock KB retrieval
  3. Use Claude (highest quality) to synthesize the correct optimization tip
  4. Upsert the corrected tip into ViewMyBill-CostOptimizationTips
  5. Re-run the original question through the Bedrock Agent (with corrected Tips)
  6. Score the improved answer; write healed_answer + healed_score to audit log

Model: Claude (via Bedrock) for research synthesis and tip generation.
This is background-only — never blocks the user-facing response.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Configuration ─────────────────────────────────────────────────────────────
AUDIT_TABLE_NAME = os.environ.get('AUDIT_TABLE_NAME', 'Audit_Transaction_Log')
TIPS_TABLE_NAME  = os.environ.get('TIPS_TABLE_NAME', 'ViewMyBill-CostOptimizationTips')
REGION           = os.environ.get('AWS_REGION', 'us-east-1')
HEAL_THRESHOLD   = int(os.environ.get('AUDIT_QUALITY_THRESHOLD', '70'))

# Claude model for highest-quality research and tip generation
CLAUDE_MODEL_ID  = os.environ.get('CLAUDE_MODEL_ID', 'us.anthropic.claude-opus-4-0-20250514-v1:0')
# Nova for fast scoring
NOVA_MODEL_ID    = os.environ.get('BEDROCK_MODEL_ID', 'us.amazon.nova-2-lite-v1:0')

# Bedrock Agent for re-answering after Tips correction
BEDROCK_AGENT_ID       = os.environ.get('BEDROCK_AGENT_ID', '')
BEDROCK_AGENT_ALIAS_ID = os.environ.get('BEDROCK_AGENT_ALIAS_ID', '')

# Certified source domains (only these are trusted for tip generation)
CERTIFIED_SOURCES = [
    'docs.aws.amazon.com', 'aws.amazon.com/pricing',
    'learn.microsoft.com', 'azure.microsoft.com/pricing',
    'cloud.google.com/pricing', 'cloud.google.com/docs',
    'platform.openai.com/docs', 'openai.com/pricing',
    'docs.anthropic.com', 'anthropic.com/pricing',
]

dynamodb = boto3.resource('dynamodb')


def lambda_handler(event, context):
    """Entry point — invoked asynchronously by audit-evaluator."""
    transaction_id  = event.get('transaction_id', '')
    question        = (event.get('question') or '').strip()
    original_answer = (event.get('answer') or '').strip()
    improvement     = (event.get('improvement_suggestions') or '').strip()
    provider        = (event.get('provider') or 'aws').lower()

    if not transaction_id or not question:
        logger.warning('answer-healer: missing required fields')
        return {'statusCode': 400, 'body': 'missing fields'}

    logger.info(json.dumps({
        'action': 'investigator_start',
        'transaction_id': transaction_id,
        'provider': provider,
    }))

    # Step 1: Identify the knowledge gap
    gap_analysis = _identify_gap(question, original_answer, improvement)

    # Step 2: Research certified sources (internet)
    research_findings = _research_certified_sources(gap_analysis, provider)

    # Step 3: Generate corrected tip using Claude (highest quality)
    new_tip = _generate_tip_with_claude(question, gap_analysis, research_findings, provider)

    # Step 4: Upsert the tip into the Tips table
    tip_written = _upsert_tip(new_tip, provider)

    # Step 5: Re-run the question through the Bedrock Agent (now with corrected Tips)
    healed_answer = _re_answer_question(question, provider, transaction_id)

    # Step 6: Score and write back
    healed_score = _score(question, healed_answer)
    _write_healed(transaction_id, healed_answer, healed_score, new_tip, tip_written)

    logger.info(json.dumps({
        'action': 'investigator_complete',
        'transaction_id': transaction_id,
        'healed_score': healed_score,
        'tip_written': tip_written,
        'tip_service': new_tip.get('service', '') if new_tip else '',
    }))
    return {'statusCode': 200, 'body': json.dumps({
        'healed_score': healed_score, 'tip_written': tip_written
    })}


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Identify the knowledge gap
# ══════════════════════════════════════════════════════════════════════════════

def _identify_gap(question: str, answer: str, improvement: str) -> str:
    """Use Claude to identify what knowledge was missing."""
    try:
        prompt = (
            "You are a FinOps knowledge-base analyst. A chat answer scored poorly. "
            "Identify what specific knowledge or data was MISSING that caused the low score.\n\n"
            "COMMON GAP PATTERNS (check for these first):\n"
            "- SHALLOW DATA DUMP: The answer lists dollar amounts from tool output but does NOT explain "
            "the pricing model (per-request, per-hour, per-GB), does NOT calculate implied usage "
            "(total / unit_price = volume), and does NOT explain what generates the charges. "
            "A good answer must convert costs into tangible actions (e.g., '$135 / $0.01 = 13,500 API requests').\n"
            "- MISSING DRILL-DOWN: The user asked 'explain' or 'break down' but got only a top-level summary "
            "without sub-service or usage-type detail.\n"
            "- IRRELEVANT DATA INCLUDED: Daily costs or forecast hints shown when not requested.\n\n"
            "Return a concise paragraph describing the knowledge gap and what the correct answer structure should include.\n\n"
            f"QUESTION: {question[:500]}\n"
            f"ANSWER GIVEN: {answer[:800]}\n"
            f"AUDIT FEEDBACK: {improvement[:500]}\n"
        )
        return _call_claude(prompt, max_tokens=400)
    except Exception as e:
        logger.warning(f'Gap analysis failed: {e}')
        return improvement or question


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Research certified internet sources
# ══════════════════════════════════════════════════════════════════════════════

def _research_certified_sources(gap_analysis: str, provider: str) -> str:
    """Search certified vendor documentation for the missing knowledge.

    Uses Bedrock Knowledge Base retrieval (if configured) or falls back to
    Claude's training knowledge restricted to certified sources only.
    """
    try:
        # Attempt Bedrock Knowledge Base retrieval first
        kb_id = os.environ.get('KNOWLEDGE_BASE_ID', '')
        if kb_id:
            return _retrieve_from_kb(kb_id, gap_analysis, provider)

        # Fallback: ask Claude to provide information ONLY from certified sources
        certified_list = ', '.join(CERTIFIED_SOURCES)
        prompt = (
            "You are a FinOps research agent. Based on the knowledge gap below, "
            "provide FACTUAL information that would be found on these official documentation sites:\n"
            f"{certified_list}\n\n"
            "Rules:\n"
            "- Only state facts from official vendor documentation\n"
            "- Include specific pricing numbers, API names, or configuration steps\n"
            "- If you cannot provide certified facts, say 'INSUFFICIENT_DATA'\n"
            "- Be concise and structured\n\n"
            f"KNOWLEDGE GAP: {gap_analysis[:600]}\n"
            f"PROVIDER: {provider}\n"
        )
        return _call_claude(prompt, max_tokens=800)
    except Exception as e:
        logger.warning(f'Research failed: {e}')
        return 'INSUFFICIENT_DATA'


def _retrieve_from_kb(kb_id: str, query: str, provider: str) -> str:
    """Retrieve from Bedrock Knowledge Base (certified docs indexed)."""
    try:
        client = boto3.client('bedrock-agent-runtime', region_name=REGION)
        resp = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={'text': f"{provider} {query}"[:300]},
            retrievalConfiguration={
                'vectorSearchConfiguration': {'numberOfResults': 5}
            },
        )
        results = resp.get('retrievalResults', [])
        if not results:
            return 'INSUFFICIENT_DATA'
        snippets = [r.get('content', {}).get('text', '') for r in results[:5]]
        return '\n---\n'.join(s for s in snippets if s)
    except Exception as e:
        logger.warning(f'KB retrieval failed: {e}')
        return 'INSUFFICIENT_DATA'


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Generate corrected tip using Claude
# ══════════════════════════════════════════════════════════════════════════════

def _generate_tip_with_claude(question: str, gap: str, research: str, provider: str) -> dict:
    """Use Claude to synthesize a correct optimization tip from research."""
    if 'INSUFFICIENT_DATA' in research:
        logger.info('Research insufficient — skipping tip generation')
        return {}

    try:
        prompt = (
            "You are a FinOps tips-table author. Using the RESEARCH below (from certified "
            "vendor documentation), generate a single optimization tip as a JSON object.\n\n"
            "Required JSON fields:\n"
            '{"service": "<service or model name>", "title": "<short actionable title>", '
            '"description": "<full explanation with specific numbers/steps>", '
            '"estimatedSavings": "<% or $ estimate>", "difficulty": "easy|medium|hard", '
            '"drilldownInstructions": "<step-by-step investigation instructions>", '
            '"drilldownApis": ["<api1>", "<api2>"]}\n\n'
            "Rules:\n"
            "- service: the specific cloud service or AI model name\n"
            "- Include specific pricing or configuration facts from the research\n"
            "- description MUST include: (1) the pricing model (per-request/per-hour/per-GB), "
            "(2) the unit price, (3) the formula: total_cost / unit_price = implied_volume, "
            "(4) what actions/resources generate that usage\n"
            "- drilldownInstructions: actionable steps to investigate and reduce the cost\n"
            "- drilldownApis: relevant AWS API calls for investigation (boto3 format)\n"
            "- Return ONLY the JSON object, no markdown fences\n\n"
            f"ORIGINAL QUESTION: {question[:300]}\n"
            f"KNOWLEDGE GAP: {gap[:300]}\n"
            f"RESEARCH FROM CERTIFIED SOURCES:\n{research[:2000]}\n"
        )
        raw = _call_claude(prompt, max_tokens=600)
        # Parse JSON from response
        match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
        if match:
            tip = json.loads(match.group())
            tip['provider'] = provider
            tip['cloud'] = 'ai_vendor' if provider in ('openai', 'anthropic', 'groundcover') else provider
            tip['source'] = 'bedrock-investigator'
            tip['generated_at'] = datetime.now(timezone.utc).isoformat()
            return tip
    except Exception as e:
        logger.warning(f'Tip generation failed: {e}')
    return {}


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Upsert corrected tip to Tips table
# ══════════════════════════════════════════════════════════════════════════════

def _upsert_tip(tip: dict, provider: str) -> bool:
    """Write the researched tip to ViewMyBill-CostOptimizationTips."""
    if not tip or not tip.get('service') or not tip.get('title'):
        return False
    try:
        table = dynamodb.Table(TIPS_TABLE_NAME)
        service = tip['service']
        tip_id = f"investigator-{provider}-{service.lower().replace(' ', '-')[:30]}"

        table.put_item(Item={
            'service': service,
            'tipId': tip_id,
            'title': tip.get('title', ''),
            'description': tip.get('description', ''),
            'estimatedSavings': tip.get('estimatedSavings', ''),
            'difficulty': tip.get('difficulty', 'medium'),
            'cloud': tip.get('cloud', provider),
            'provider': provider,
            'drilldownApis': tip.get('drilldownApis', []),
            'drilldownInstructions': tip.get('drilldownInstructions', ''),
            'source': 'bedrock-investigator',
            'generated_at': tip.get('generated_at', datetime.now(timezone.utc).isoformat()),
            'actionType': 'optimize',
            'actionLabel': tip.get('title', 'Apply optimization'),
        })
        logger.info(f'Tips table updated: service={service}, tipId={tip_id}')
        return True
    except Exception as e:
        logger.warning(f'Tips table upsert failed: {e}')
        return False


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: Re-answer the question (with corrected Tips table)
# ══════════════════════════════════════════════════════════════════════════════

def _re_answer_question(question: str, provider: str, transaction_id: str) -> str:
    """Re-invoke the Bedrock Agent with the original question.
    The Tips table is now corrected, so the Agent will get better context.
    """
    if not BEDROCK_AGENT_ID or not BEDROCK_AGENT_ALIAS_ID:
        # Fall back to Claude direct if Agent not configured
        return _call_claude(
            f"You are a FinOps assistant. Answer this customer question accurately and concisely:\n{question[:500]}",
            max_tokens=600,
        )

    try:
        agent_rt = boto3.client(
            'bedrock-agent-runtime', region_name=REGION,
            config=BotoConfig(connect_timeout=10, read_timeout=60, retries={'max_attempts': 1}),
        )
        session_id = f"healer-{transaction_id[:20]}"
        response = agent_rt.invoke_agent(
            agentId=BEDROCK_AGENT_ID,
            agentAliasId=BEDROCK_AGENT_ALIAS_ID,
            sessionId=session_id,
            inputText=f"[Provider: {provider}] {question}",
            enableTrace=False,
        )
        parts = []
        for event in response.get('completion', []):
            if 'chunk' in event and 'bytes' in event['chunk']:
                parts.append(event['chunk']['bytes'].decode('utf-8'))
        return ''.join(parts) or ''
    except Exception as e:
        logger.warning(f'Agent re-answer failed: {e}')
        return ''


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6: Score and write back
# ══════════════════════════════════════════════════════════════════════════════

def _score(question: str, answer: str) -> int:
    """Score the healed answer using Nova (fast)."""
    if not answer:
        return 0
    try:
        bedrock = boto3.client(
            'bedrock-runtime', region_name=REGION,
            config=BotoConfig(read_timeout=8, connect_timeout=2, retries={'max_attempts': 1}),
        )
        body = {
            'messages': [{'role': 'user', 'content': [{'text': (
                'Rate the quality of this FinOps chat answer (0-100). '
                'Reply with ONLY a JSON object: {"score": <integer>}\n\n'
                f'QUESTION: {question[:300]}\nANSWER: {answer[:1000]}'
            )}]}],
            'inferenceConfig': {'maxTokens': 50},
        }
        resp = bedrock.invoke_model(
            modelId=NOVA_MODEL_ID, contentType='application/json',
            accept='application/json', body=json.dumps(body),
        )
        text = json.loads(resp['body'].read())['output']['message']['content'][0]['text']
        return int(json.loads(text).get('score', 0))
    except Exception:
        return 0


def _write_healed(transaction_id: str, healed_answer: str, healed_score: int,
                  tip: dict, tip_written: bool):
    """Write healed results back to Audit_Transaction_Log."""
    try:
        table = dynamodb.Table(AUDIT_TABLE_NAME)
        update_expr = 'SET healed_answer = :a, healed_score = :s, healed_at = :t, tip_corrected = :tc'
        expr_values = {
            ':a': healed_answer or '(re-answer failed)',
            ':s': healed_score,
            ':t': datetime.now(timezone.utc).isoformat(),
            ':tc': tip_written,
        }
        if tip and tip.get('service'):
            update_expr += ', healed_tip_service = :ts, healed_tip_id = :ti'
            expr_values[':ts'] = tip.get('service', '')
            expr_values[':ti'] = f"investigator-{tip.get('provider','')}-{tip['service'].lower().replace(' ','-')[:30]}"

        table.update_item(
            Key={'transaction_id': transaction_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
        )
    except ClientError as e:
        logger.warning(f'Audit log write failed: {e}')


# ══════════════════════════════════════════════════════════════════════════════
# Claude API helper (via Bedrock)
# ══════════════════════════════════════════════════════════════════════════════

def _call_claude(prompt: str, max_tokens: int = 500) -> str:
    """Invoke Claude via Bedrock for highest-quality reasoning."""
    bedrock = boto3.client(
        'bedrock-runtime', region_name=REGION,
        config=BotoConfig(read_timeout=30, connect_timeout=5, retries={'max_attempts': 1}),
    )
    body = {
        'anthropic_version': 'bedrock-2023-05-31',
        'max_tokens': max_tokens,
        'messages': [{'role': 'user', 'content': prompt}],
    }
    resp = bedrock.invoke_model(
        modelId=CLAUDE_MODEL_ID, contentType='application/json',
        accept='application/json', body=json.dumps(body),
    )
    resp_body = json.loads(resp['body'].read())
    return resp_body.get('content', [{}])[0].get('text', '').strip()
