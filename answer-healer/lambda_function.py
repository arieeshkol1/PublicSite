"""
Answer Healer Lambda — self-healing mechanism for low-quality chat answers.

Triggered asynchronously by the audit-evaluator Lambda when audit_score < threshold.
Flow:
  1. Receive the original question, answer, improvement hints, and transaction_id
  2. Search the Tips table for matching optimisation tips (grounding context)
  3. Re-invoke Nova with the original data + tips + improvement hints to produce a better answer
  4. Score the improved answer (inline audit)
  5. Write healed_answer, healed_score, healed_at back to Audit_Transaction_Log

This is a pure background operation — it NEVER blocks the user-facing response.
The improved answer is stored in the audit log and can be surfaced by the admin panel
or as a "view improved answer" UX hint in a future front-end iteration.
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AUDIT_TABLE_NAME  = os.environ.get('AUDIT_TABLE_NAME',  'Audit_Transaction_Log')
TIPS_TABLE_NAME   = os.environ.get('TIPS_TABLE_NAME',   'ViewMyBill-CostOptimizationTips')
BEDROCK_MODEL_ID  = os.environ.get('BEDROCK_MODEL_ID',  'us.amazon.nova-2-lite-v1:0')
REGION            = os.environ.get('AWS_REGION',        'us-east-1')
HEAL_THRESHOLD    = int(os.environ.get('AUDIT_QUALITY_THRESHOLD', '70'))

dynamodb = boto3.resource('dynamodb')


def lambda_handler(event, context):
    """Entry point — invoked asynchronously by audit-evaluator."""
    transaction_id  = event.get('transaction_id', '')
    question        = (event.get('question') or '').strip()
    original_answer = (event.get('answer') or '').strip()
    improvement     = (event.get('improvement_suggestions') or '').strip()
    provider        = (event.get('provider') or 'aws').lower()

    if not transaction_id or not question or not original_answer:
        logger.warning('answer-healer: missing required fields — skipping')
        return {'statusCode': 400, 'body': 'missing fields'}

    logger.info(json.dumps({
        'action': 'heal_start',
        'transaction_id': transaction_id,
        'provider': provider,
    }))

    # 1. Fetch relevant tips (provider-aware, best-effort)
    tips_context = _fetch_tips(question, provider)

    # 2. Produce an improved answer via Nova
    healed_answer = _heal(question, original_answer, improvement, tips_context)

    # 3. Score the healed answer
    healed_score = _score(question, healed_answer)

    # 4. Write back to Audit_Transaction_Log
    _write_healed(transaction_id, healed_answer, healed_score)

    logger.info(json.dumps({
        'action': 'heal_complete',
        'transaction_id': transaction_id,
        'healed_score': healed_score,
    }))
    return {'statusCode': 200, 'body': json.dumps({'healed_score': healed_score})}


# ── helpers ───────────────────────────────────────────────────────────────────

def _fetch_tips(question: str, provider: str) -> str:
    """Query ViewMyBill-CostOptimizationTips for tips relevant to this question."""
    try:
        from boto3.dynamodb.conditions import Key as _Key
        table = dynamodb.Table(TIPS_TABLE_NAME)
        # Use the provider-cloud-index GSI (added by C5) for an efficient targeted query.
        for prov in (provider, 'all'):
            try:
                resp = table.query(
                    IndexName='provider-cloud-index',
                    KeyConditionExpression=_Key('provider').eq(prov),
                )
                items = resp.get('Items', [])
                if items:
                    snippets = [
                        f"- {t.get('title','')}: {t.get('description','')}"
                        for t in items[:5] if t.get('title')
                    ]
                    return '\n'.join(snippets)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f'answer-healer: tips fetch failed: {e}')
    return ''


def _heal(question: str, original: str, improvement: str, tips: str) -> str:
    """Call Nova to produce a better answer, grounded in the original data + tips + hints."""
    try:
        bedrock = boto3.client(
            'bedrock-runtime', region_name=REGION,
            config=BotoConfig(read_timeout=12, connect_timeout=3, retries={'max_attempts': 1}),
        )
        tips_block = f'\nRELEVANT TIPS:\n{tips}' if tips else ''
        improvement_block = f'\nIMPROVEMENT HINTS FROM AUDIT:\n{improvement}' if improvement else ''
        prompt = (
            'You are a FinOps assistant. The answer below was scored as low quality. '
            'Using the improvement hints and any relevant tips provided, rewrite the answer '
            'to be more accurate, complete, and useful. Keep numbers and data unchanged. '
            'Return ONLY the improved answer — no preamble, no meta-commentary.\n\n'
            f'ORIGINAL QUESTION:\n{question[:500]}\n\n'
            f'ORIGINAL ANSWER:\n{original[:1500]}'
            f'{improvement_block}'
            f'{tips_block}\n'
        )
        body = {
            'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
            'inferenceConfig': {'maxTokens': 800},
        }
        resp = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType='application/json',
            accept='application/json',
            body=json.dumps(body),
        )
        text = json.loads(resp['body'].read())['output']['message']['content'][0]['text'].strip()
        return text or original
    except Exception as e:
        logger.warning(f'answer-healer: nova call failed: {e}')
        return original


def _score(question: str, answer: str) -> int:
    """Re-score the healed answer using the same Nova inline audit approach."""
    try:
        bedrock = boto3.client(
            'bedrock-runtime', region_name=REGION,
            config=BotoConfig(read_timeout=8, connect_timeout=2, retries={'max_attempts': 1}),
        )
        prompt = (
            'Rate the quality of this FinOps chat answer (0-100). '
            'Reply with ONLY a JSON object: {"score": <integer 0-100>}\n\n'
            f'QUESTION: {question[:300]}\n\nANSWER: {answer[:1000]}'
        )
        body = {
            'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
            'inferenceConfig': {'maxTokens': 60},
        }
        resp = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType='application/json',
            accept='application/json',
            body=json.dumps(body),
        )
        text = json.loads(resp['body'].read())['output']['message']['content'][0]['text']
        return int(json.loads(text).get('score', 0))
    except Exception:
        return 0


def _write_healed(transaction_id: str, healed_answer: str, healed_score: int):
    """Write healed answer fields back to the audit log record."""
    try:
        table = dynamodb.Table(AUDIT_TABLE_NAME)
        table.update_item(
            Key={'transaction_id': transaction_id},
            UpdateExpression=(
                'SET healed_answer = :a, healed_score = :s, healed_at = :t'
            ),
            ExpressionAttributeValues={
                ':a': healed_answer,
                ':s': healed_score,
                ':t': datetime.now(timezone.utc).isoformat(),
            },
        )
    except ClientError as e:
        logger.warning(f'answer-healer: DDB write failed: {e}')
