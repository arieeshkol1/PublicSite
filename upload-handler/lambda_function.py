"""
AWS Bill Analyzer - Upload Handler Lambda Function

This Lambda function handles bill file uploads from the frontend.
It validates file size and type, generates session IDs, and stores files in S3.
"""

import json
import base64
import uuid
import os
import mimetypes
from datetime import datetime
from typing import Dict, Any, Tuple
import boto3
from botocore.exceptions import ClientError

# Initialize S3 client
s3_client = boto3.client('s3')

# Environment variables
BILL_STORAGE_BUCKET = os.environ.get('BILL_STORAGE_BUCKET', 'aws-bill-analyzer-storage-991105135552')
MAX_FILE_SIZE_MB = int(os.environ.get('MAX_FILE_SIZE_MB', '10'))
ALLOWED_EXTENSIONS = os.environ.get('ALLOWED_EXTENSIONS', '.csv,.pdf').split(',')

# Constants
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle bill file uploads from API Gateway.
    
    Args:
        event: API Gateway proxy event with file data
        context: Lambda context object
        
    Returns:
        API Gateway proxy response with session ID
    """
    try:
        print(f"Received upload request")
        
        # Extract file data from event
        file_content, filename, content_type = extract_file_from_event(event)
        
        # Validate file
        validation_error = validate_file(file_content, filename)
        if validation_error:
            return create_error_response(validation_error['code'], validation_error['message'])
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        print(f"Generated session ID: {session_id}")
        
        # Upload to S3
        s3_key = f"bills/{session_id}/{filename}"
        upload_timestamp = datetime.utcnow().isoformat() + 'Z'
        
        try:
            s3_client.put_object(
                Bucket=BILL_STORAGE_BUCKET,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type,
                Metadata={
                    'session-id': session_id,
                    'upload-timestamp': upload_timestamp,
                    'original-filename': filename
                },
                Tagging=f'session-id={session_id}&upload-timestamp={upload_timestamp}&expiration=24h'
            )
            print(f"File uploaded successfully to s3://{BILL_STORAGE_BUCKET}/{s3_key}")
            
        except ClientError as e:
            print(f"S3 upload error: {str(e)}")
            return create_error_response(
                500,
                "Failed to store file. Please try again."
            )
        
        # Return success response
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',  # Will be restricted in API Gateway
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': json.dumps({
                'sessionId': session_id,
                'message': 'File uploaded successfully',
                'fileName': filename,
                'timestamp': upload_timestamp
            })
        }
        
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return create_error_response(
            500,
            "An unexpected error occurred. Please try again."
        )


def extract_file_from_event(event: Dict[str, Any]) -> Tuple[bytes, str, str]:
    """
    Extract file content, filename, and content type from API Gateway event.
    
    Args:
        event: API Gateway proxy event
        
    Returns:
        Tuple of (file_content, filename, content_type)
        
    Raises:
        ValueError: If file data cannot be extracted
    """
    # Check if body is base64 encoded
    is_base64 = event.get('isBase64Encoded', False)
    body = event.get('body', '')
    
    if not body:
        raise ValueError("No file data in request")
    
    # For multipart/form-data, we need to parse the body
    content_type_header = event.get('headers', {}).get('content-type', '') or \
                         event.get('headers', {}).get('Content-Type', '')
    
    if 'multipart/form-data' in content_type_header:
        # Parse multipart form data
        if is_base64:
            body = base64.b64decode(body)
        else:
            body = body.encode('utf-8') if isinstance(body, str) else body
        
        # Extract boundary
        boundary = content_type_header.split('boundary=')[-1].strip()
        
        # Parse multipart data
        file_content, filename = parse_multipart_form_data(body, boundary)
        
        # Detect content type from filename
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        return file_content, filename, content_type
    
    else:
        # Direct binary upload
        if is_base64:
            file_content = base64.b64decode(body)
        else:
            file_content = body.encode('utf-8') if isinstance(body, str) else body
        
        # Try to get filename from headers
        filename = event.get('headers', {}).get('x-filename', 'uploaded-bill.csv')
        content_type = event.get('headers', {}).get('content-type', 'application/octet-stream')
        
        return file_content, filename, content_type


def parse_multipart_form_data(body: bytes, boundary: str) -> Tuple[bytes, str]:
    """
    Parse multipart/form-data to extract file content and filename.
    
    Args:
        body: Raw request body
        boundary: Multipart boundary string
        
    Returns:
        Tuple of (file_content, filename)
    """
    # Split by boundary
    boundary_bytes = f'--{boundary}'.encode('utf-8')
    parts = body.split(boundary_bytes)
    
    for part in parts:
        if b'Content-Disposition' in part and b'filename=' in part:
            # Extract filename
            disposition_line = part.split(b'\r\n')[1].decode('utf-8')
            filename_start = disposition_line.find('filename="') + 10
            filename_end = disposition_line.find('"', filename_start)
            filename = disposition_line[filename_start:filename_end]
            
            # Extract file content (after double CRLF)
            content_start = part.find(b'\r\n\r\n') + 4
            content_end = part.rfind(b'\r\n')
            file_content = part[content_start:content_end]
            
            return file_content, filename
    
    raise ValueError("No file found in multipart data")


def validate_file(file_content: bytes, filename: str) -> Dict[str, Any] | None:
    """
    Validate file size and extension.
    
    Args:
        file_content: File content as bytes
        filename: Original filename
        
    Returns:
        Error dict if validation fails, None if valid
    """
    # Check file size
    file_size = len(file_content)
    if file_size > MAX_FILE_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        return {
            'code': 413,
            'message': f'File size ({size_mb:.1f} MB) exceeds the maximum allowed size of {MAX_FILE_SIZE_MB} MB. Please upload a smaller file.'
        }
    
    # Check file extension
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return {
            'code': 400,
            'message': f'Invalid file type. Only {", ".join(ALLOWED_EXTENSIONS)} files are supported. You uploaded a {file_ext} file.'
        }
    
    # Check if file is empty
    if file_size == 0:
        return {
            'code': 400,
            'message': 'File is empty. Please upload a valid AWS bill file.'
        }
    
    return None


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
        400: 'InvalidFileType',
        413: 'FileTooLarge',
        500: 'ServerError'
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
            'retryable': status_code >= 500
        })
    }
