"""
Audit Evaluator Lambda.
Triggered by DynamoDB Streams on the Transaction_Log_Table.
Evaluates each new transaction entry using Amazon Bedrock (Claude Opus)
and updates the entry with audit results.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get('TABLE_NAME', 'Audit_Transaction_Log')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'us.amazon.nova-lite-v1:0')

MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')


def lambda_handler(event, context):
    """Process DynamoDB Stream records. Only handles INSERT events."""
    logger.info(f"Received {len(event.get('Records', []))} records")

    for record in event.get('Records', []):
        if record['eventName'] != 'INSERT':
            continue

        try:
            image = record['dynamodb']['NewImage']
            entry = _unmarshall(image)
            logger.info(f"Processing transaction: {entry.get('transaction_id')}")

            evaluation = _evaluate_with_bedrock(entry)
            _update_entry_with_evaluation(
                entry['transaction_id'],
                entry['start_timestamp'],
                evaluation
            )
        except Exception as e:
            logger.error(f"Error processing record: {e}")
            # Try to mark as failed if we have the keys
            try:
                image = record['dynamodb']['NewImage']
                entry = _unmarshall(image)
                _update_entry_with_evaluation(
                    entry['transaction_id'],
                    entry['start_timestamp'],
                    {
                        'audit_status': 'failed',
                        'audit_score': None,
                        'audit_accuracy_assessment': None,
                        'audit_timing_assessment': None,
                        'audit_improvement_suggestions': None,
                        'error': str(e)
                    }
                )
            except Exception as inner_e:
                logger.error(f"Failed to mark entry as failed: {inner_e}")


def _unmarshall(image):
    """Convert DynamoDB Stream NewImage format to plain dict.

    DynamoDB Stream records use the low-level format with type descriptors:
    {'field': {'S': 'value'}, 'num': {'N': '123'}, 'map': {'M': {...}}}
    """
    result = {}
    for key, value in image.items():
        result[key] = _unmarshall_value(value)
    return result


def _unmarshall_value(value):
    """Recursively convert a single DynamoDB typed value to a Python value."""
    if 'S' in value:
        return value['S']
    elif 'N' in value:
        num_str = value['N']
        if '.' in num_str:
            return float(num_str)
        return int(num_str)
    elif 'BOOL' in value:
        return value['BOOL']
    elif 'NULL' in value:
        return None
    elif 'M' in value:
        return {k: _unmarshall_value(v) for k, v in value['M'].items()}
    elif 'L' in value:
        return [_unmarshall_value(item) for item in value['L']]
    elif 'SS' in value:
        return set(value['SS'])
    elif 'NS' in value:
        return set(int(n) if '.' not in n else float(n) for n in value['NS'])
    else:
        # Fallback: return the raw value
        return value


def _evaluate_with_bedrock(entry):
    """Invoke Bedrock Claude Opus to evaluate the transaction.

    Retries up to 3 times with exponential backoff (2s, 4s, 8s) on failure.
    Returns a dict with audit fields.
    """
    prompt = _build_prompt(entry)
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            # Build request body based on model type
            if 'amazon.nova' in BEDROCK_MODEL_ID:
                # Amazon Nova format
                request_body = {
                    'messages': [
                        {
                            'role': 'user',
                            'content': [{'text': prompt}]
                        }
                    ],
                    'inferenceConfig': {
                        'maxTokens': 1024
                    }
                }
            else:
                # Anthropic Claude format
                request_body = {
                    'anthropic_version': 'bedrock-2023-05-31',
                    'max_tokens': 1024,
                    'messages': [
                        {
                            'role': 'user',
                            'content': prompt
                        }
                    ]
                }

            response = bedrock_runtime.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                contentType='application/json',
                accept='application/json',
                body=json.dumps(request_body)
            )

            response_body = json.loads(response['body'].read())

            # Parse response based on model type
            if 'amazon.nova' in BEDROCK_MODEL_ID:
                content_text = response_body['output']['message']['content'][0]['text']
            else:
                content_text = response_body['content'][0]['text']

            evaluation = _parse_bedrock_response(content_text)
            evaluation['audit_status'] = 'completed'
            return evaluation

        except Exception as e:
            last_error = e
            logger.warning(
                f"Bedrock invocation failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}"
            )
            if attempt < MAX_RETRIES - 1:
                backoff = BACKOFF_BASE * (2 ** attempt)  # 2s, 4s, 8s
                time.sleep(backoff)

    # All retries exhausted
    logger.error(f"Bedrock evaluation failed after {MAX_RETRIES} attempts: {last_error}")
    return {
        'audit_status': 'failed',
        'audit_score': None,
        'audit_accuracy_assessment': None,
        'audit_timing_assessment': None,
        'audit_improvement_suggestions': None,
        'error': f"Bedrock invocation failed after {MAX_RETRIES} retries: {str(last_error)}"
    }


def _build_prompt(entry):
    """Build the evaluation prompt from a transaction entry."""
    function_name = entry.get('function_name', 'unknown')
    duration_ms = entry.get('duration_ms', 0)
    request_payload = entry.get('request_payload', {})
    response_payload = entry.get('response_payload', {})

    # Convert payloads to readable strings
    if isinstance(request_payload, dict):
        request_str = json.dumps(request_payload, default=str, indent=2)
    else:
        request_str = str(request_payload)

    if isinstance(response_payload, dict):
        response_str = json.dumps(response_payload, default=str, indent=2)
    else:
        response_str = str(response_payload)

    return f"""You are an audit agent evaluating API transaction quality.

Transaction Context:
- Function: {function_name}
- Duration: {duration_ms}ms
- Request: {request_str}
- Response: {response_str}

Evaluate and return JSON:
{{
  "score": <0-100>,
  "accuracy_assessment": "<text>",
  "timing_assessment": "<text>",
  "improvement_suggestions": "<text>"
}}"""


def _parse_bedrock_response(content_text):
    """Parse the Bedrock response JSON.

    Handles malformed JSON by extracting what's available and setting
    missing fields to None.
    """
    try:
        # Try to extract JSON from the response (it might be wrapped in markdown)
        json_str = content_text
        if '```json' in content_text:
            json_str = content_text.split('```json')[1].split('```')[0].strip()
        elif '```' in content_text:
            json_str = content_text.split('```')[1].split('```')[0].strip()
        elif '{' in content_text:
            # Find the first { and last }
            start = content_text.index('{')
            end = content_text.rindex('}') + 1
            json_str = content_text[start:end]

        data = json.loads(json_str)

        # Extract and validate fields
        score = data.get('score')
        if score is not None:
            score = int(score)
            score = max(0, min(100, score))  # Clamp to 0-100

        return {
            'audit_score': score,
            'audit_accuracy_assessment': data.get('accuracy_assessment'),
            'audit_timing_assessment': data.get('timing_assessment'),
            'audit_improvement_suggestions': data.get('improvement_suggestions'),
        }

    except (json.JSONDecodeError, ValueError, IndexError) as e:
        logger.error(f"Failed to parse Bedrock response: {e}. Raw: {content_text[:500]}")
        return {
            'audit_status': 'failed',
            'audit_score': None,
            'audit_accuracy_assessment': None,
            'audit_timing_assessment': None,
            'audit_improvement_suggestions': None,
            'error': f"Malformed Bedrock response: {str(e)}"
        }


def _update_entry_with_evaluation(transaction_id, start_timestamp, evaluation):
    """Update the DynamoDB item with audit evaluation fields."""
    update_expr_parts = []
    expr_attr_values = {}
    expr_attr_names = {}

    # Always set audit_status
    audit_status = evaluation.get('audit_status', 'completed')
    update_expr_parts.append('#ast = :ast')
    expr_attr_names['#ast'] = 'audit_status'
    expr_attr_values[':ast'] = audit_status

    # Set evaluated_at timestamp
    update_expr_parts.append('#aet = :aet')
    expr_attr_names['#aet'] = 'audit_evaluated_at'
    expr_attr_values[':aet'] = datetime.now(timezone.utc).isoformat()

    # Set score (can be None)
    score = evaluation.get('audit_score')
    update_expr_parts.append('#asc = :asc')
    expr_attr_names['#asc'] = 'audit_score'
    if score is not None:
        expr_attr_values[':asc'] = score
    else:
        expr_attr_values[':asc'] = None

    # Set accuracy assessment
    accuracy = evaluation.get('audit_accuracy_assessment')
    update_expr_parts.append('#aaa = :aaa')
    expr_attr_names['#aaa'] = 'audit_accuracy_assessment'
    expr_attr_values[':aaa'] = accuracy

    # Set timing assessment
    timing = evaluation.get('audit_timing_assessment')
    update_expr_parts.append('#ata = :ata')
    expr_attr_names['#ata'] = 'audit_timing_assessment'
    expr_attr_values[':ata'] = timing

    # Set improvement suggestions
    suggestions = evaluation.get('audit_improvement_suggestions')
    update_expr_parts.append('#ais = :ais')
    expr_attr_names['#ais'] = 'audit_improvement_suggestions'
    expr_attr_values[':ais'] = suggestions

    # Set error details if present
    error = evaluation.get('error')
    if error:
        update_expr_parts.append('#err = :err')
        expr_attr_names['#err'] = 'audit_error'
        expr_attr_values[':err'] = error

    update_expression = 'SET ' + ', '.join(update_expr_parts)

    try:
        table.update_item(
            Key={
                'transaction_id': transaction_id,
                'start_timestamp': start_timestamp
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expr_attr_names,
            ExpressionAttributeValues=expr_attr_values
        )
        logger.info(
            f"Updated transaction {transaction_id} with audit_status={audit_status}"
        )
    except Exception as e:
        logger.error(f"Failed to update entry {transaction_id}: {e}")
        raise
