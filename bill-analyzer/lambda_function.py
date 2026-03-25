"""
AWS Bill Analyzer - Lambda Handler

Orchestrates the bill analysis pipeline with async polling:
    Phase 1 (sync, <2s): Receive request, invoke self async, return "processing"
    Phase 2 (async, up to 300s): Parse bill, AI analysis, generate PDF, upload to S3
    Poll: Frontend polls /analyze, Lambda checks S3 for result

Runtime: Python 3.12 | Memory: 512 MB | Timeout: 300s
"""

import json
import logging
import os
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

from bill_parser import parse_bill
from bedrock_client import analyze_bill
from pdf_generator import generate_report

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
lambda_client = boto3.client('lambda')

BILL_STORAGE_BUCKET = os.environ.get(
    'BILL_STORAGE_BUCKET', 'aws-bill-analyzer-storage-991105135552'
)
PRESIGNED_URL_EXPIRY = int(os.environ.get('PRESIGNED_URL_EXPIRY', '86400'))
FUNCTION_NAME = os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'aws-bill-analyzer-viewmybill')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle bill analysis requests — supports async processing with polling."""
    logger.info("Received analysis request")

    # Check if this is an async background invocation
    if event.get('_async_process'):
        return _process_bill(event)

    # Parse request
    try:
        request_data = _parse_request(event)
    except ValueError as e:
        logger.warning("Invalid request: %s", str(e))
        return _create_error_response(400, str(e))

    session_id = request_data['sessionId']
    email = request_data['email']

    # Check if result already exists (polling)
    result = _check_result(session_id)
    if result:
        return result

    # Check if already processing
    if _is_processing(session_id):
        return _create_response(202, {'status': 'processing', 'sessionId': session_id})

    # Mark as processing
    _set_processing(session_id)

    # Invoke self asynchronously for the heavy work
    try:
        lambda_client.invoke(
            FunctionName=FUNCTION_NAME,
            InvocationType='Event',
            Payload=json.dumps({
                '_async_process': True,
                'sessionId': session_id,
                'email': email,
            }),
        )
        logger.info("Async invocation started for session %s", session_id)
    except Exception:
        logger.error("Failed to invoke async for session %s", session_id, exc_info=True)
        _clear_processing(session_id)
        return _create_error_response(500, "Failed to start analysis. Please try again.", retryable=True)

    return _create_response(202, {'status': 'processing', 'sessionId': session_id})


def _process_bill(event: Dict[str, Any]) -> Dict[str, Any]:
    """Background async processing — parse, analyze, generate PDF, upload."""
    session_id = event['sessionId']
    email = event['email']
    logger.info("Async processing session %s", session_id)

    try:
        # Retrieve bill
        pdf_bytes, filename = _retrieve_bill_from_s3(session_id)

        # Parse bill
        parsed_bill = parse_bill(pdf_bytes)

        # AI analysis
        analysis = analyze_bill(parsed_bill)

        # Generate PDF
        report_bytes = generate_report(pdf_bytes, parsed_bill, analysis, session_id, email)

        # Upload report
        download_url = _upload_report_to_s3(session_id, report_bytes)

        # Save result metadata
        summary = analysis.get('summary', '')
        _save_result(session_id, download_url, summary, filename)
        _clear_processing(session_id)

        logger.info("Async processing complete for session %s", session_id)
        return {'status': 'complete'}

    except Exception as e:
        logger.error("Async processing failed for session %s: %s", session_id, str(e), exc_info=True)
        _save_error(session_id, str(e))
        _clear_processing(session_id)
        return {'status': 'error'}


def _check_result(session_id: str):
    """Check if analysis result exists in S3. Returns response or None."""
    result_key = f"reports/{session_id}/result.json"
    try:
        obj = s3_client.get_object(Bucket=BILL_STORAGE_BUCKET, Key=result_key)
        data = json.loads(obj['Body'].read().decode('utf-8'))
        if data.get('error'):
            _cleanup_status(session_id)
            return _create_error_response(503, "Analysis failed. Please try again.", retryable=True)
        return _create_response(200, {
            'status': 'complete',
            'downloadUrl': data['downloadUrl'],
            'summary': data['summary'],
            'sessionId': session_id,
            'originalFilename': data.get('originalFilename', ''),
        })
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return None
        return None


def _is_processing(session_id: str) -> bool:
    """Check if a processing marker exists."""
    try:
        s3_client.head_object(Bucket=BILL_STORAGE_BUCKET, Key=f"reports/{session_id}/processing")
        return True
    except ClientError:
        return False


def _set_processing(session_id: str):
    """Create a processing marker in S3."""
    try:
        s3_client.put_object(Bucket=BILL_STORAGE_BUCKET, Key=f"reports/{session_id}/processing", Body=b'1')
    except ClientError:
        pass


def _clear_processing(session_id: str):
    """Remove the processing marker."""
    try:
        s3_client.delete_object(Bucket=BILL_STORAGE_BUCKET, Key=f"reports/{session_id}/processing")
    except ClientError:
        pass


def _save_result(session_id: str, download_url: str, summary: str, filename: str):
    """Save analysis result metadata to S3."""
    result_key = f"reports/{session_id}/result.json"
    s3_client.put_object(
        Bucket=BILL_STORAGE_BUCKET,
        Key=result_key,
        Body=json.dumps({'downloadUrl': download_url, 'summary': summary, 'originalFilename': filename}),
        ContentType='application/json',
    )


def _save_error(session_id: str, error_msg: str):
    """Save error result to S3."""
    result_key = f"reports/{session_id}/result.json"
    s3_client.put_object(
        Bucket=BILL_STORAGE_BUCKET,
        Key=result_key,
        Body=json.dumps({'error': True, 'message': error_msg}),
        ContentType='application/json',
    )


def _cleanup_status(session_id: str):
    """Remove result.json so user can retry."""
    try:
        s3_client.delete_object(Bucket=BILL_STORAGE_BUCKET, Key=f"reports/{session_id}/result.json")
    except ClientError:
        pass




def _parse_request(event: Dict[str, Any]) -> Dict[str, str]:
    """
    Parse and validate the request body.

    Args:
        event: API Gateway proxy event.

    Returns:
        Dict with 'sessionId' and 'email' keys.

    Raises:
        ValueError: If required fields are missing or invalid.
    """
    body = event.get('body', '')
    if not body:
        raise ValueError("Request body is required")

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        raise ValueError("Invalid request format")

    session_id = data.get('sessionId', '').strip()
    email = data.get('email', '').strip()

    if not session_id:
        raise ValueError("sessionId is required")
    if not email:
        raise ValueError("email is required")

    return {'sessionId': session_id, 'email': email}


def _retrieve_bill_from_s3(session_id: str) -> tuple[bytes, str]:
    """
    Retrieve the uploaded bill PDF from S3.

    Args:
        session_id: Session identifier from the upload step.

    Returns:
        Tuple of (pdf_bytes, original_filename).

    Raises:
        FileNotFoundError: If no bill is found for the session.
        RuntimeError: If S3 access fails.
    """
    prefix = f"bills/{session_id}/"

    try:
        response = s3_client.list_objects_v2(
            Bucket=BILL_STORAGE_BUCKET,
            Prefix=prefix,
            MaxKeys=10,
        )
    except ClientError as e:
        logger.error("S3 list failed for prefix %s: %s", prefix, str(e))
        raise RuntimeError("Failed to access storage") from e

    contents = response.get('Contents', [])
    if not contents:
        raise FileNotFoundError(f"No bill found for session {session_id}")

    # Pick the first (and typically only) object under the session prefix
    bill_key = contents[0]['Key']
    filename = bill_key.split('/')[-1] if '/' in bill_key else bill_key

    try:
        obj = s3_client.get_object(Bucket=BILL_STORAGE_BUCKET, Key=bill_key)
        pdf_bytes = obj['Body'].read()
    except ClientError as e:
        logger.error("S3 get failed for key %s: %s", bill_key, str(e))
        raise RuntimeError("Failed to retrieve bill from storage") from e

    return pdf_bytes, filename


def _upload_report_to_s3(session_id: str, report_bytes: bytes) -> str:
    """
    Upload the generated PDF report to S3 and return a pre-signed URL.

    Args:
        session_id: Session identifier.
        report_bytes: Generated PDF report as bytes.

    Returns:
        Pre-signed URL for downloading the report (24-hour expiry).

    Raises:
        RuntimeError: If S3 upload or URL generation fails.
    """
    report_key = f"reports/{session_id}/report.pdf"

    # Upload the report
    try:
        s3_client.put_object(
            Bucket=BILL_STORAGE_BUCKET,
            Key=report_key,
            Body=report_bytes,
            ContentType='application/pdf',
            Metadata={
                'session-id': session_id,
            },
        )
    except ClientError as e:
        logger.error("S3 upload failed for key %s: %s", report_key, str(e))
        raise RuntimeError("Failed to store report") from e

    # Generate pre-signed URL
    try:
        download_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': BILL_STORAGE_BUCKET,
                'Key': report_key,
            },
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )
    except ClientError as e:
        logger.error("Pre-signed URL generation failed for key %s: %s", report_key, str(e))
        raise RuntimeError("Failed to generate pre-signed download URL") from e

    return download_url


def _create_success_response(
    download_url: str, summary: str, session_id: str, original_filename: str = ""
) -> Dict[str, Any]:
    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps({
            'downloadUrl': download_url,
            'summary': summary,
            'sessionId': session_id,
            'originalFilename': original_filename,
        }),
    }


def _create_response(status_code: int, body: dict) -> Dict[str, Any]:
    return {
        'statusCode': status_code,
        'headers': CORS_HEADERS,
        'body': json.dumps(body),
    }


def _create_error_response(
    status_code: int, message: str, retryable: bool = False
) -> Dict[str, Any]:
    """
    Create a standardized error response.

    Error messages are user-friendly and do not expose internal details
    (stack traces, file paths, ARNs, or exception class names).

    Args:
        status_code: HTTP status code.
        message: User-facing error message.
        retryable: Whether the client should retry the request.

    Returns:
        API Gateway proxy response dict.
    """
    error_type_map = {
        400: 'BadRequest',
        404: 'NotFound',
        429: 'TooManyRequests',
        500: 'ServerError',
        503: 'ServiceUnavailable',
        504: 'Timeout',
    }

    return {
        'statusCode': status_code,
        'headers': CORS_HEADERS,
        'body': json.dumps({
            'error': error_type_map.get(status_code, 'Error'),
            'message': message,
            'code': status_code,
            'retryable': retryable,
        }),
    }
