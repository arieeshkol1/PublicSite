"""
AWS Bill Analyzer - Question Processor Lambda Function

This Lambda function processes user questions about uploaded bills using AI.
It retrieves bills from S3, parses them, and uses Amazon Bedrock for analysis.
"""

import json
import os
import boto3
from botocore.exceptions import ClientError
from typing import Dict, Any
from bill_parser import get_parser
from response_formatter import ResponseFormatter

# Initialize AWS clients
s3_client = boto3.client('s3')
bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')

# Environment variables
BILL_STORAGE_BUCKET = os.environ.get('BILL_STORAGE_BUCKET', 'aws-bill-analyzer-storage-991105135552')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'amazon.nova-lite-v1:0')
MAX_TOKENS = int(os.environ.get('MAX_TOKENS', '2000'))

# Initialize response formatter
formatter = ResponseFormatter()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process user questions about uploaded bills using AI.
    
    Args:
        event: API Gateway proxy event with sessionId and question
        context: Lambda context object
        
    Returns:
        API Gateway proxy response with AI-generated answer
    """
    try:
        print("Received question processing request")
        
        # Extract parameters from event
        body = json.loads(event.get('body', '{}'))
        session_id = body.get('sessionId')
        question = body.get('question')
        
        # Validate required parameters
        if not session_id:
            return create_error_response(400, "Missing required parameter: sessionId")
        
        if not question or not question.strip():
            return create_error_response(400, "Missing required parameter: question")
        
        print(f"Session ID: {session_id}")
        print(f"Question: {question}")
        
        # Retrieve bill file from S3
        try:
            bill_content, filename = retrieve_bill_from_s3(session_id)
        except FileNotFoundError:
            return create_error_response(
                404,
                "Session not found or expired. Please upload your bill again."
            )
        except Exception as e:
            print(f"Error retrieving bill: {str(e)}")
            return create_error_response(
                500,
                "Failed to retrieve bill file. Please try again."
            )
        
        # Parse bill
        try:
            file_extension = os.path.splitext(filename)[1].lower()
            parser = get_parser(file_extension)
            parsed_bill = parser.parse(bill_content)
            print(f"Bill parsed successfully. Total cost: {parsed_bill['total_cost']}")
        except ValueError as e:
            return create_error_response(
                400,
                f"Failed to parse bill file: {str(e)}"
            )
        except Exception as e:
            print(f"Parsing error: {str(e)}")
            return create_error_response(
                500,
                "Failed to parse bill file. The file may be corrupted or in an unsupported format."
            )
        
        # Construct prompt for Bedrock
        prompt = construct_prompt(parsed_bill, question)
        
        # Invoke Bedrock
        try:
            bedrock_response = invoke_bedrock(prompt)
            print("Bedrock invocation successful")
        except Exception as e:
            print(f"Bedrock error: {str(e)}")
            error_message = handle_bedrock_error(e)
            return create_error_response(error_message['code'], error_message['message'])
        
        # Format response
        formatted_response = formatter.format_response(bedrock_response)
        
        # Return success response
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': json.dumps({
                'answer': formatted_response['answer'],
                'timestamp': formatted_response['timestamp'],
                'sessionId': session_id
            })
        }
        
    except json.JSONDecodeError:
        return create_error_response(400, "Invalid JSON in request body")
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return create_error_response(
            500,
            "An unexpected error occurred. Please try again."
        )


def retrieve_bill_from_s3(session_id: str) -> tuple:
    """
    Retrieve bill file from S3 using session ID.
    
    Args:
        session_id: Session identifier
        
    Returns:
        Tuple of (file_content, filename)
        
    Raises:
        FileNotFoundError: If session not found
        Exception: For other S3 errors
    """
    # List objects with session ID prefix
    try:
        response = s3_client.list_objects_v2(
            Bucket=BILL_STORAGE_BUCKET,
            Prefix=f'bills/{session_id}/'
        )
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            raise FileNotFoundError(f"No bill found for session {session_id}")
        
        # Get the first (and should be only) file
        s3_key = response['Contents'][0]['Key']
        filename = os.path.basename(s3_key)
        
        # Retrieve file content
        file_response = s3_client.get_object(
            Bucket=BILL_STORAGE_BUCKET,
            Key=s3_key
        )
        
        file_content = file_response['Body'].read()
        
        return file_content, filename
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'NoSuchKey':
            raise FileNotFoundError(f"Bill not found for session {session_id}")
        raise


def construct_prompt(parsed_bill: Dict[str, Any], question: str) -> str:
    """
    Construct prompt for Bedrock with bill data and user question.
    
    Args:
        parsed_bill: Parsed bill data
        question: User's question
        
    Returns:
        Formatted prompt string
    """
    # Format bill data for prompt
    bill_summary = f"""
Total Cost: ${parsed_bill['total_cost']}
Currency: {parsed_bill['currency']}
Billing Period: {parsed_bill['period_start']} to {parsed_bill['period_end']}

Service Breakdown:
"""
    
    for service, cost in parsed_bill['service_totals'].items():
        bill_summary += f"- {service}: ${cost}\n"
    
    # Include sample line items (limit to 10 for context)
    if parsed_bill['line_items']:
        bill_summary += "\nDetailed Line Items (sample):\n"
        for item in parsed_bill['line_items'][:10]:
            bill_summary += f"- {item['service']} ({item['usage_type']}): ${item['cost']} on {item['date']}\n"
    
    # Construct full prompt
    prompt = f"""You are an AWS billing assistant. Analyze the following bill data and answer the user's question accurately.

Bill Data:
{bill_summary}

User Question: {question}

Provide a clear, concise answer based only on the bill data provided. If the question cannot be answered from the bill data, politely explain what information is available."""
    
    return prompt


def invoke_bedrock(prompt: str) -> Dict[str, Any]:
    """
    Invoke Amazon Bedrock Nova Lite model with prompt.
    
    Args:
        prompt: Formatted prompt string
        
    Returns:
        Bedrock response dictionary
        
    Raises:
        Exception: For Bedrock invocation errors
    """
    # Prepare request body for Nova Lite
    request_body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "inferenceConfig": {
            "max_new_tokens": MAX_TOKENS,
            "temperature": 0.7,
            "top_p": 0.9
        }
    }
    
    # Invoke model
    response = bedrock_client.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps(request_body),
        contentType='application/json',
        accept='application/json'
    )
    
    # Parse response
    response_body = json.loads(response['body'].read())
    
    return response_body


def handle_bedrock_error(error: Exception) -> Dict[str, Any]:
    """
    Handle Bedrock invocation errors and return user-friendly messages.
    
    Args:
        error: Exception from Bedrock invocation
        
    Returns:
        Dictionary with error code and message
    """
    error_str = str(error).lower()
    
    if 'throttling' in error_str or 'rate' in error_str:
        return {
            'code': 429,
            'message': 'The service is currently busy. Please try again in a moment.'
        }
    elif 'timeout' in error_str:
        return {
            'code': 504,
            'message': 'The request took too long to process. Please try again.'
        }
    elif 'access' in error_str or 'permission' in error_str:
        return {
            'code': 403,
            'message': 'AI service access is not configured. Please contact support.'
        }
    elif 'unavailable' in error_str or 'service' in error_str:
        return {
            'code': 503,
            'message': 'The AI service is temporarily unavailable. Please try again in a few minutes.'
        }
    else:
        return {
            'code': 500,
            'message': 'Failed to process your question. Please try again.'
        }


def create_error_response(status_code: int, message: str) -> Dict[str, Any]:
    """
    Create a standardized error response.
    
    Args:
        status_code: HTTP status code
        message: Error message
        
    Returns:
        API Gateway proxy response
    """
    error_type_map = {
        400: 'BadRequest',
        403: 'Forbidden',
        404: 'NotFound',
        429: 'TooManyRequests',
        500: 'ServerError',
        503: 'ServiceUnavailable',
        504: 'Timeout'
    }
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'POST, OPTIONS'
        },
        'body': json.dumps({
            'error': error_type_map.get(status_code, 'Error'),
            'message': message,
            'code': status_code,
            'retryable': status_code >= 500 or status_code == 429
        })
    }
