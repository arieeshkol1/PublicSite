# Query Handler Lambda
# API Gateway integration and request routing

import json
import boto3
import os
from typing import Dict, Any
from langdetect import detect, LangDetectException

lambda_client = boto3.client('lambda')

def detect_language(text: str) -> str:
    """
    Detect language of text (Hebrew or English).
    Returns 'he' for Hebrew, 'en' for English.
    Defaults to 'en' if detection fails.
    """
    try:
        lang = detect(text)
        # Map detected language to supported languages
        if lang == 'he' or lang == 'iw':  # Hebrew (iw is old code)
            return 'he'
        else:
            return 'en'  # Default to English
    except (LangDetectException, Exception):
        return 'en'  # Default to English on error

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for API Gateway integration.
    Validates requests, detects language, and routes to answer retrieval.
    """
    try:
        # Parse API Gateway proxy event
        if 'body' not in event:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Missing request body'})
            }
        
        # Parse request body
        try:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        except json.JSONDecodeError:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Invalid JSON in request body'})
            }
        
        # Validate required fields
        question = body.get('question')
        mode = body.get('mode')
        format_type = body.get('format')
        
        if not question:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Missing required field: question'})
            }
        
        if not mode or mode not in ['multiple_choice', 'conversation']:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Invalid or missing mode. Must be "multiple_choice" or "conversation"'})
            }
        
        if not format_type or format_type not in ['short', 'long']:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Invalid or missing format. Must be "short" or "long"'})
            }
        
        # Detect language
        language = detect_language(question)
        
        # Log request metadata (no full question content for privacy)
        print(f"Request metadata: mode={mode}, format={format_type}, language={language}, question_length={len(question)}")
        
        # Invoke Answer Retrieval Lambda
        answer_retrieval_function = os.environ.get('ANSWER_RETRIEVAL_FUNCTION_NAME', 'mobile-ka-answer-retrieval')
        
        payload = {
            'question': question,
            'language': language,
            'mode': mode,
            'format': format_type
        }
        
        try:
            response = lambda_client.invoke(
                FunctionName=answer_retrieval_function,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            # Parse response
            response_payload = json.loads(response['Payload'].read())
            
            # Check for Lambda errors
            if 'FunctionError' in response:
                print(f"Answer Retrieval Lambda error: {response_payload}")
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({'error': 'Internal server error processing query'})
                }
            
            # Return successful response
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(response_payload)
            }
            
        except lambda_client.exceptions.ResourceNotFoundException:
            print(f"Answer Retrieval Lambda not found: {answer_retrieval_function}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Service configuration error'})
            }
        except lambda_client.exceptions.TooManyRequestsException:
            print("Lambda throttling - too many requests")
            return {
                'statusCode': 429,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Retry-After': '60'
                },
                'body': json.dumps({'error': 'Too many requests. Please try again later.'})
            }
        except Exception as e:
            print(f"Error invoking Answer Retrieval Lambda: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Internal server error'})
            }
    
    except Exception as e:
        # Catch-all error handler
        print(f"Unexpected error in Query Handler: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'Internal server error'})
        }
