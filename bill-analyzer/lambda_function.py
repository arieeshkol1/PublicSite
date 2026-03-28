"""
AWS Bill Analyzer - Lambda Handler

Orchestrates the bill analysis pipeline with async self-invoke:
    1. First /analyze call: Sets processing marker, invokes self async, returns 202
    2. Async invocation: Processes bill (parse/Bedrock/PDF), saves result to S3
    3. Poll /analyze calls: Check S3 for result.json, return 202 or 200

Runtime: Python 3.12 | Memory: 512 MB | Timeout: 900s
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
dynamodb = boto3.resource('dynamodb')

BILL_STORAGE_BUCKET = os.environ.get(
    'BILL_STORAGE_BUCKET', 'aws-bill-analyzer-storage-991105135552'
)
PRESIGNED_URL_EXPIRY = int(os.environ.get('PRESIGNED_URL_EXPIRY', '86400'))
FUNCTION_NAME = os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'aws-bill-analyzer-viewmybill')
LEADS_TABLE_NAME = os.environ.get('LEADS_TABLE_NAME', 'ViewMyBill-Leads')

CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle bill analysis requests with async self-invoke and polling."""
    # Async background invocation — do the actual work
    if event.get('_async'):
        return _process_bill(event['sessionId'], event['email'])

    logger.info("Received analysis request")

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

    # Quick validation: check size, format, text extractability, and AWS bill content
    logger.info("STEP 4.0: Validating PDF for session %s", session_id)
    try:
        pdf_bytes, filename = _retrieve_bill_from_s3(session_id)
        file_size_mb = len(pdf_bytes) / (1024 * 1024)
        logger.info("STEP 4.0: Retrieved %.1f MB, filename=%s", file_size_mb, filename)

        # 4.0.1: Size check
        if len(pdf_bytes) == 0:
            return _create_error_response(400, "The uploaded file is empty. Please upload a valid AWS invoice PDF.")
        if len(pdf_bytes) > 10 * 1024 * 1024:
            return _create_error_response(400, f"File size ({file_size_mb:.1f} MB) exceeds the 10 MB limit.")

        # 4.0.2: Format check — verify it's a real PDF
        if not pdf_bytes[:5] == b'%PDF-':
            return _create_error_response(400, "The uploaded file is not a valid PDF. Please upload a PDF file.")

        # 4.0.3: Text extractability check with PyPDF2
        import io
        from PyPDF2 import PdfReader
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
        except Exception:
            return _create_error_response(400, "The PDF file is corrupted or password-protected. Please upload a valid, unprotected AWS invoice PDF.")

        num_pages = len(reader.pages)
        if num_pages == 0:
            return _create_error_response(400, "The PDF file has no pages. Please upload a valid AWS invoice PDF.")
        logger.info("STEP 4.0: PDF has %d pages", num_pages)

        # Extract text from first page (fast with PyPDF2)
        first_page_text = (reader.pages[0].extract_text() or "").strip()
        logger.info("STEP 4.0: PyPDF2 first page: %d chars", len(first_page_text))

        # If PyPDF2 got nothing, try pdfplumber on first page only
        if len(first_page_text) < 50:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf_check:
                first_page_text = (pdf_check.pages[0].extract_text() or "").strip()
                logger.info("STEP 4.0: pdfplumber fallback first page: %d chars", len(first_page_text))

        if len(first_page_text) < 50:
            return _create_error_response(400,
                "This PDF appears to be a scanned image and cannot be processed. "
                "Please download your AWS bill directly from the AWS Billing Console "
                "(Billing → Bills → Download CSV or PDF) as a native digital PDF."
            )

        # 4.0.4: Content check — verify it looks like an AWS bill
        text_lower = first_page_text.lower()
        aws_keywords = ['amazon web services', 'aws', 'invoice', 'billing', 'total', 'account']
        matches = sum(1 for kw in aws_keywords if kw in text_lower)
        logger.info("STEP 4.0: AWS keyword matches: %d/6 (%s)", matches, [kw for kw in aws_keywords if kw in text_lower])

        if matches < 2:
            return _create_error_response(400,
                "This PDF does not appear to be an AWS invoice. "
                "Please upload an AWS billing PDF downloaded from the AWS Billing Console."
            )

        logger.info("STEP 4.0: Validation PASSED — %d pages, %.1f MB, %d AWS keywords", num_pages, file_size_mb, matches)

    except FileNotFoundError:
        return _create_error_response(404, "Session not found or expired")
    except Exception as e:
        if hasattr(e, 'statusCode'):
            raise  # Re-raise our own error responses
        logger.error("STEP 4.0: Validation error: %s", str(e))
        return _create_error_response(400, "Unable to read the PDF. Please ensure it is a valid AWS invoice PDF.")

    # Start async processing: set marker, invoke self, return 202
    _set_processing(session_id)
    logger.info("STEP 4.1: Processing marker set, invoking self async for session %s", session_id)

    try:
        invoke_response = lambda_client.invoke(
            FunctionName=FUNCTION_NAME,
            InvocationType='Event',
            Payload=json.dumps({'_async': True, 'sessionId': session_id, 'email': email}),
        )
        logger.info("STEP 4.1 DONE: Self-invoke returned StatusCode=%s for session %s", invoke_response.get('StatusCode'), session_id)
    except Exception:
        logger.error("Failed to invoke async for session %s", session_id, exc_info=True)
        _clear_processing(session_id)
        return _create_error_response(500, "Failed to start analysis. Please try again.", retryable=True)

    return _create_response(202, {'status': 'processing', 'sessionId': session_id})


def _process_bill(session_id: str, email: str) -> Dict[str, Any]:
    """Async background processing — runs in a separate Lambda invocation."""
    logger.info("===== STEP 4.2 ASYNC START ===== session=%s email=%s", session_id, email)

    try:
        # STEP 4.2.1: Retrieve PDF from S3
        logger.info("STEP 4.2.1: Retrieving PDF from S3 for session %s", session_id)
        pdf_bytes, filename = _retrieve_bill_from_s3(session_id)
        logger.info("STEP 4.2.1 DONE: Retrieved %d bytes, filename=%s", len(pdf_bytes), filename)

        # STEP 4.2.2: Parse bill with pdfplumber
        logger.info("STEP 4.2.2: Parsing bill with pdfplumber")
        parsed_bill = parse_bill(pdf_bytes)
        num_services = len(parsed_bill.get('service_totals', {}))
        num_items = len(parsed_bill.get('line_items', []))
        logger.info("STEP 4.2.2 DONE: Parsed %d services, %d line items", num_services, num_items)

        # STEP 4.2.3: Query DynamoDB for tips (inside analyze_bill)
        # STEP 4.2.4: Call Bedrock AI
        logger.info("STEP 4.2.3-4: Calling analyze_bill (DynamoDB tips + Bedrock AI)")
        analysis = analyze_bill(parsed_bill)
        logger.info("STEP 4.2.3-4 DONE: Bedrock returned summary length=%d", len(analysis.get('summary', '')))

        # STEP 4.2.5: Generate PDF report
        logger.info("STEP 4.2.5: Generating PDF report")
        report_bytes = generate_report(pdf_bytes, parsed_bill, analysis, session_id, email)
        logger.info("STEP 4.2.5 DONE: PDF generated, %d bytes", len(report_bytes))

        # STEP 4.2.6: Upload report to S3
        logger.info("STEP 4.2.6: Uploading report to S3")
        download_url = _upload_report_to_s3(session_id, report_bytes)
        logger.info("STEP 4.2.6 DONE: Report uploaded, URL generated")

        # STEP 4.2.7: Save result metadata
        logger.info("STEP 4.2.7: Saving result.json to S3")
        _save_result(session_id, download_url, analysis.get('summary', ''), filename)
        logger.info("STEP 4.2.7 DONE: result.json saved")

        # STEP 4.2.8: Update lead with savings data
        logger.info("STEP 4.2.8: Updating lead with bill optimization numbers")
        _update_lead_with_savings(email, session_id, parsed_bill, analysis)
        logger.info("STEP 4.2.8 DONE: Lead updated")

        # STEP 4.2.9: Clear processing marker
        logger.info("STEP 4.2.9: Clearing processing marker")
        _clear_processing(session_id)
        logger.info("===== STEP 4.2 ASYNC COMPLETE ===== session=%s", session_id)
        return {'status': 'complete'}

    except Exception as e:
        logger.error("===== STEP 4.2 ASYNC FAILED ===== session=%s error=%s", session_id, str(e), exc_info=True)
        try:
            _save_error(session_id, str(e))
            _clear_processing(session_id)
            logger.info("Error saved to result.json and processing marker cleared")
        except Exception as cleanup_err:
            logger.error("Failed to save error state: %s", str(cleanup_err))
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


def _update_lead_with_savings(email: str, session_id: str, parsed_bill: Dict[str, Any], ai_analysis: Dict[str, Any]):
    """Update the lead record in DynamoDB with bill optimization summary numbers."""
    try:
        table = dynamodb.Table(LEADS_TABLE_NAME)

        # Find the lead by email + sessionId
        response = table.query(
            KeyConditionExpression='#em = :e',
            FilterExpression='sessionId = :s',
            ExpressionAttributeNames={'#em': 'email'},
            ExpressionAttributeValues={':e': email, ':s': session_id},
            Limit=1,
        )
        items = response.get('Items', [])
        if not items:
            logger.warning("Lead not found for email=%s sessionId=%s, skipping savings update", email, session_id)
            return

        lead = items[0]
        timestamp = lead['timestamp']

        # Compute savings from AI analysis
        total_cost = float(parsed_bill.get('total_cost', 0))
        currency = parsed_bill.get('currency', 'USD')
        service_items = ai_analysis.get('service_analysis', []) or ai_analysis.get('explanations', [])

        monthly_min = 0.0
        monthly_max = 0.0
        for item in service_items:
            cost_str = str(item.get('cost', '0')).replace('$', '').replace(',', '').strip()
            try:
                svc_cost = float(cost_str)
            except ValueError:
                continue
            best_min, best_max = 0.0, 0.0
            for rec in item.get('recommendations', []):
                savings_str = str(rec.get('estimated_savings', ''))
                parsed = _parse_savings_pct(savings_str)
                if parsed and parsed[1] > best_max:
                    best_min, best_max = parsed
            monthly_min += svc_cost * best_min / 100.0
            monthly_max += svc_cost * best_max / 100.0

        monthly_avg = (monthly_min + monthly_max) / 2.0

        from decimal import Decimal
        table.update_item(
            Key={'email': email, 'timestamp': timestamp},
            UpdateExpression='SET billTotalCost = :tc, billCurrency = :cur, '
                           'monthlySavingsMin = :smin, monthlySavingsMax = :smax, monthlySavingsAvg = :savg, '
                           'yearlySavingsMin = :ymin, yearlySavingsMax = :ymax, yearlySavingsAvg = :yavg, '
                           'numServices = :ns',
            ExpressionAttributeValues={
                ':tc': Decimal(str(round(total_cost, 2))),
                ':cur': currency,
                ':smin': Decimal(str(round(monthly_min, 2))),
                ':smax': Decimal(str(round(monthly_max, 2))),
                ':savg': Decimal(str(round(monthly_avg, 2))),
                ':ymin': Decimal(str(round(monthly_min * 12, 2))),
                ':ymax': Decimal(str(round(monthly_max * 12, 2))),
                ':yavg': Decimal(str(round(monthly_avg * 12, 2))),
                ':ns': len(service_items),
            },
        )
        logger.info("Lead updated with savings: email=%s monthly=%.2f-%.2f yearly=%.2f-%.2f",
                     email, monthly_min, monthly_max, monthly_min * 12, monthly_max * 12)
    except Exception as e:
        logger.error("Failed to update lead with savings: %s", str(e), exc_info=True)


def _parse_savings_pct(s: str):
    """Parse savings string like '20-40%' or 'up to 30%' into (min%, max%)."""
    import re
    s = s.strip().lower().replace(',', '')
    m = re.search(r'(\d+(?:\.\d+)?)\s*[%]?\s*[-\u2013to]+\s*(\d+(?:\.\d+)?)\s*%', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'(?:up\s+to|~)\s*(\d+(?:\.\d+)?)\s*%', s)
    if m:
        val = float(m.group(1))
        return val * 0.3, val
    m = re.search(r'(\d+(?:\.\d+)?)\s*%', s)
    if m:
        v = float(m.group(1))
        return v, v
    return None


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

    # Skip 0-byte folder markers — pick the first real file
    bill_key = None
    for obj in contents:
        if obj.get('Size', 0) > 0 and not obj['Key'].endswith('/'):
            bill_key = obj['Key']
            break

    if not bill_key:
        raise FileNotFoundError(f"No bill found for session {session_id}")

    filename = bill_key.split('/')[-1] if '/' in bill_key else bill_key
    logger.info("STEP 4.2.1: Downloading S3 key=%s size=%d", bill_key, next((o['Size'] for o in contents if o['Key'] == bill_key), 0))

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
