"""
AWS Bill Analyzer - Upload Handler Lambda Function

Handles bill file uploads, validates input, stores files in S3,
and saves lead contact information to DynamoDB.
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

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

BILL_STORAGE_BUCKET = os.environ.get('BILL_STORAGE_BUCKET', 'aws-bill-analyzer-storage-991105135552')
LEADS_TABLE_NAME = os.environ.get('LEADS_TABLE_NAME', 'ViewMyBill-Leads')
MAX_FILE_SIZE_MB = int(os.environ.get('MAX_FILE_SIZE_MB', '10'))
ALLOWED_EXTENSIONS = os.environ.get('ALLOWED_EXTENSIONS', '.csv,.pdf').split(',')
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        print("Received upload request")
        file_content, filename, content_type, contact = extract_file_from_event(event)

        validation_error = validate_file(file_content, filename)
        if validation_error:
            return create_error_response(validation_error['code'], validation_error['message'])

        session_id = str(uuid.uuid4())
        upload_timestamp = datetime.utcnow().isoformat() + 'Z'
        print(f"Session: {session_id}")

        # Store file in S3
        s3_key = f"bills/{session_id}/{filename}"
        try:
            s3_client.put_object(
                Bucket=BILL_STORAGE_BUCKET,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type,
                Metadata={
                    'session-id': session_id,
                    'upload-timestamp': upload_timestamp,
                    'original-filename': filename,
                    'user-email': contact.get('email', '')
                }
            )
            print(f"File uploaded to s3://{BILL_STORAGE_BUCKET}/{s3_key}")
        except ClientError as e:
            print(f"S3 upload error: {e.response['Error']['Code']} - {e.response['Error']['Message']}")
            return create_error_response(500, "Failed to store file. Please try again.")

        # Save lead to DynamoDB
        try:
            table = dynamodb.Table(LEADS_TABLE_NAME)
            table.put_item(Item={
                'email': contact.get('email', ''),
                'timestamp': upload_timestamp,
                'sessionId': session_id,
                'name': contact.get('name', ''),
                'company': contact.get('company', ''),
                'phone': contact.get('phone', ''),
                'fileName': filename,
                'fileSize': len(file_content)
            })
            print(f"Lead saved for {contact.get('email', '')}")
        except ClientError as e:
            # Log but don't fail the upload if lead save fails
            print(f"DynamoDB lead save error: {e.response['Error']['Code']} - {e.response['Error']['Message']}")

        return {
            'statusCode': 200,
            'headers': cors_headers(),
            'body': json.dumps({
                'sessionId': session_id,
                'message': 'File uploaded successfully',
                'fileName': filename,
                'timestamp': upload_timestamp
            })
        }
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return create_error_response(500, "An unexpected error occurred. Please try again.")


def extract_file_from_event(event: Dict[str, Any]) -> Tuple[bytes, str, str, dict]:
    is_base64 = event.get('isBase64Encoded', False)
    body = event.get('body', '')
    if not body:
        raise ValueError("No file data in request")

    content_type_header = event.get('headers', {}).get('content-type', '') or \
                         event.get('headers', {}).get('Content-Type', '')

    if 'multipart/form-data' in content_type_header:
        if is_base64:
            body = base64.b64decode(body)
        else:
            body = body.encode('utf-8') if isinstance(body, str) else body
        boundary = content_type_header.split('boundary=')[-1].strip()
        file_content, filename, contact = parse_multipart_form_data(body, boundary)
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        return file_content, filename, content_type, contact
    else:
        if is_base64:
            file_content = base64.b64decode(body)
        else:
            file_content = body.encode('utf-8') if isinstance(body, str) else body
        filename = event.get('headers', {}).get('x-filename', 'uploaded-bill.csv')
        ct = event.get('headers', {}).get('content-type', 'application/octet-stream')
        return file_content, filename, ct, {}


def parse_multipart_form_data(body: bytes, boundary: str) -> Tuple[bytes, str, dict]:
    boundary_bytes = f'--{boundary}'.encode('utf-8')
    parts = body.split(boundary_bytes)
    file_content = None
    filename = None
    contact = {}

    for part in parts:
        if b'Content-Disposition' not in part:
            continue
        disposition_line = part.split(b'\r\n')[1].decode('utf-8')

        if 'filename=' in disposition_line:
            filename_start = disposition_line.find('filename="') + 10
            filename_end = disposition_line.find('"', filename_start)
            filename = disposition_line[filename_start:filename_end]
            content_start = part.find(b'\r\n\r\n') + 4
            content_end = part.rfind(b'\r\n')
            file_content = part[content_start:content_end]
        else:
            # Extract form field name and value
            for field in ['name', 'company', 'email', 'phone']:
                if f'name="{field}"' in disposition_line:
                    content_start = part.find(b'\r\n\r\n') + 4
                    content_end = part.rfind(b'\r\n')
                    contact[field] = part[content_start:content_end].decode('utf-8').strip()

    if file_content is None or filename is None:
        raise ValueError("No file found in multipart data")
    return file_content, filename, contact


def validate_file(file_content: bytes, filename: str) -> Dict[str, Any] | None:
    file_size = len(file_content)
    if file_size > MAX_FILE_SIZE_BYTES:
        return {'code': 413, 'message': f'File size ({file_size / (1024*1024):.1f} MB) exceeds {MAX_FILE_SIZE_MB} MB limit.'}
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return {'code': 400, 'message': f'Invalid file type. Only {", ".join(ALLOWED_EXTENSIONS)} files are supported.'}
    if file_size == 0:
        return {'code': 400, 'message': 'File is empty. Please upload a valid AWS bill file.'}
    return None


def cors_headers():
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'POST, OPTIONS'
    }


def create_error_response(status_code: int, message: str) -> Dict[str, Any]:
    error_type_map = {400: 'InvalidFileType', 413: 'FileTooLarge', 500: 'ServerError'}
    return {
        'statusCode': status_code,
        'headers': cors_headers(),
        'body': json.dumps({
            'error': error_type_map.get(status_code, 'Error'),
            'message': message,
            'code': status_code,
            'retryable': status_code >= 500
        })
    }
