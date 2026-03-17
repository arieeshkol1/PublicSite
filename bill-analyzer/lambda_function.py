"""
AWS Bill Analyzer - Lambda Handler

Orchestrates the bill analysis pipeline:
    1. Retrieve bill PDF from S3 using sessionId
    2. Parse bill (pdfplumber)
    3. RAG lookup (DynamoDB tips)
    4. AI analysis (Bedrock Nova Lite)
    5. Generate merged PDF report (ReportLab + PyPDF2)
    6. Upload report to S3
    7. Return pre-signed download URL

Runtime: Python 3.12 | Memory: 512 MB | Timeout: 120s
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

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')

# Environment variables
BILL_STORAGE_BUCKET = os.environ.get(
    'BILL_STORAGE_BUCKET', 'aws-bill-analyzer-storage-991105135552'
)
PRESIGNED_URL_EXPIRY = int(os.environ.get('PRESIGNED_URL_EXPIRY', '86400'))

# CORS headers
CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
}



def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle bill analysis requests from API Gateway.

    Expects a JSON body with:
        - sessionId (str): Session identifier from the upload step.
        - email (str): User's email address.

    Returns:
        API Gateway proxy response with downloadUrl and summary on success,
        or an error response with appropriate HTTP status code.
    """
    logger.info("Received analysis request")

    # 1. Parse and validate request
    try:
        request_data = _parse_request(event)
    except ValueError as e:
        logger.warning("Invalid request: %s", str(e))
        return _create_error_response(400, str(e))

    session_id = request_data['sessionId']
    email = request_data['email']
    logger.info("Processing session %s", session_id)

    # 2. Retrieve bill PDF from S3
    try:
        pdf_bytes, filename = _retrieve_bill_from_s3(session_id)
    except FileNotFoundError:
        logger.warning("Session not found: %s", session_id)
        return _create_error_response(404, "Session not found or expired")
    except RuntimeError:
        logger.error("Failed to retrieve bill for session %s", session_id)
        return _create_error_response(500, "Failed to retrieve bill. Please try again.", retryable=True)

    # 3. Parse bill
    try:
        parsed_bill = parse_bill(pdf_bytes)
    except ValueError as e:
        logger.warning("Bill parsing failed for session %s: %s", session_id, str(e))
        return _create_error_response(
            400,
            "Unable to parse the uploaded bill. Please ensure it is a valid AWS invoice PDF."
        )
    except Exception:
        logger.error("Unexpected bill parsing error for session %s", session_id, exc_info=True)
        return _create_error_response(
            400,
            "Unable to parse the uploaded bill. Please ensure it is a valid AWS invoice PDF."
        )

    # 4. AI analysis via Bedrock
    try:
        analysis = analyze_bill(parsed_bill)
    except RuntimeError as e:
        error_msg = str(e)
        if "Service is busy" in error_msg:
            logger.warning("Bedrock throttled for session %s", session_id)
            return _create_error_response(429, "Service is busy. Please wait a moment and try again.", retryable=True)
        if "AI service temporarily unavailable" in error_msg:
            logger.error("Bedrock unavailable for session %s", session_id)
            return _create_error_response(503, "AI service temporarily unavailable. Please try again later.", retryable=True)
        logger.error("Bedrock error for session %s: %s", session_id, error_msg)
        return _create_error_response(504, "Analysis request timed out. Please try again.", retryable=True)
    except Exception:
        logger.error("Unexpected analysis error for session %s", session_id, exc_info=True)
        return _create_error_response(504, "Analysis request timed out. Please try again.", retryable=True)

    # 5. Generate PDF report
    try:
        report_bytes = generate_report(pdf_bytes, parsed_bill, analysis, session_id, email)
    except Exception:
        logger.error("PDF generation failed for session %s", session_id, exc_info=True)
        return _create_error_response(500, "Failed to generate report. Please try again.", retryable=True)

    # 6. Upload report to S3 and get pre-signed URL
    try:
        download_url = _upload_report_to_s3(session_id, report_bytes)
    except RuntimeError as e:
        error_msg = str(e)
        if "pre-signed" in error_msg.lower() or "presigned" in error_msg.lower():
            logger.error("Pre-signed URL generation failed for session %s", session_id)
            return _create_error_response(
                500,
                "Report was generated but download link creation failed. Please try again.",
                retryable=True,
            )
        logger.error("Report upload failed for session %s", session_id)
        return _create_error_response(500, "Failed to store report. Please try again.", retryable=True)

    # 7. Return success
    summary = analysis.get('summary', '')
    logger.info("Analysis complete for session %s", session_id)
    return _create_success_response(download_url, summary, session_id)




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
    download_url: str, summary: str, session_id: str
) -> Dict[str, Any]:
    """
    Create a success response with download URL and summary.

    Args:
        download_url: Pre-signed S3 URL for the report.
        summary: Brief AI-generated bill summary.
        session_id: Session identifier.

    Returns:
        API Gateway proxy response dict.
    """
    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps({
            'downloadUrl': download_url,
            'summary': summary,
            'sessionId': session_id,
        }),
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
