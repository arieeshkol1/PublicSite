"""
Unit tests for the upload handler Lambda function.
Tests email extraction from multipart form data and S3 metadata storage.
"""

import json
import base64
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lambda_function import parse_multipart_form_data, extract_file_from_event, lambda_handler


def build_multipart_body(boundary, file_content, filename, email=None):
    """Helper to build a multipart/form-data body."""
    parts = []
    if email is not None:
        parts.append(
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="email"\r\n'
            f'\r\n'
            f'{email}\r\n'
        )
    parts.append(
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: application/pdf\r\n'
        f'\r\n'
    )
    body = ''.join(parts).encode('utf-8') + file_content + f'\r\n--{boundary}--\r\n'.encode('utf-8')
    return body


class TestParseMultipartFormData:
    def test_extracts_email_from_form_data(self):
        boundary = 'testboundary123'
        file_bytes = b'%PDF-1.4 fake content'
        body = build_multipart_body(boundary, file_bytes, 'bill.pdf', email='user@example.com')

        file_content, filename, email = parse_multipart_form_data(body, boundary)

        assert filename == 'bill.pdf'
        assert file_content == file_bytes
        assert email == 'user@example.com'

    def test_email_defaults_to_empty_when_missing(self):
        boundary = 'testboundary123'
        file_bytes = b'%PDF-1.4 fake content'
        body = build_multipart_body(boundary, file_bytes, 'invoice.pdf')

        file_content, filename, email = parse_multipart_form_data(body, boundary)

        assert filename == 'invoice.pdf'
        assert email == ''


class TestExtractFileFromEvent:
    def test_multipart_returns_email(self):
        boundary = 'myboundary'
        file_bytes = b'%PDF-1.4 test'
        body = build_multipart_body(boundary, file_bytes, 'test.pdf', email='a@b.com')
        encoded = base64.b64encode(body).decode('utf-8')

        event = {
            'isBase64Encoded': True,
            'body': encoded,
            'headers': {
                'content-type': f'multipart/form-data; boundary={boundary}'
            }
        }

        file_content, filename, content_type, email = extract_file_from_event(event)

        assert email == 'a@b.com'
        assert filename == 'test.pdf'
        assert file_content == file_bytes

    def test_direct_upload_returns_empty_email(self):
        event = {
            'isBase64Encoded': True,
            'body': base64.b64encode(b'some data').decode('utf-8'),
            'headers': {
                'content-type': 'application/pdf',
                'x-filename': 'bill.pdf'
            }
        }

        file_content, filename, content_type, email = extract_file_from_event(event)

        assert email == ''


class TestLambdaHandlerEmailMetadata:
    @patch('lambda_function.s3_client')
    def test_email_stored_in_s3_metadata(self, mock_s3):
        boundary = 'testbound'
        file_bytes = b'%PDF-1.4 content'
        body = build_multipart_body(boundary, file_bytes, 'bill.pdf', email='test@example.com')
        encoded = base64.b64encode(body).decode('utf-8')

        event = {
            'isBase64Encoded': True,
            'body': encoded,
            'headers': {
                'content-type': f'multipart/form-data; boundary={boundary}'
            }
        }

        mock_s3.put_object.return_value = {}

        response = lambda_handler(event, None)

        assert response['statusCode'] == 200
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs['Metadata']['user-email'] == 'test@example.com'

    @patch('lambda_function.s3_client')
    def test_empty_email_when_not_provided(self, mock_s3):
        boundary = 'testbound'
        file_bytes = b'%PDF-1.4 content'
        body = build_multipart_body(boundary, file_bytes, 'bill.pdf')
        encoded = base64.b64encode(body).decode('utf-8')

        event = {
            'isBase64Encoded': True,
            'body': encoded,
            'headers': {
                'content-type': f'multipart/form-data; boundary={boundary}'
            }
        }

        mock_s3.put_object.return_value = {}

        response = lambda_handler(event, None)

        assert response['statusCode'] == 200
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs['Metadata']['user-email'] == ''
