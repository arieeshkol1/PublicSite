"""Unit tests for the Lambda handler (lambda_function.py)."""
import json
from unittest.mock import MagicMock, patch

import pytest

from lambda_function import (
    _create_error_response,
    _create_success_response,
    _parse_request,
    _retrieve_bill_from_s3,
    _upload_report_to_s3,
    lambda_handler,
)


# ---------------------------------------------------------------------------
# _parse_request
# ---------------------------------------------------------------------------
class TestParseRequest:
    def test_valid_request(self):
        event = {"body": json.dumps({"sessionId": "abc-123", "email": "user@example.com"})}
        result = _parse_request(event)
        assert result == {"sessionId": "abc-123", "email": "user@example.com"}

    def test_missing_body(self):
        with pytest.raises(ValueError, match="Request body is required"):
            _parse_request({})

    def test_empty_body(self):
        with pytest.raises(ValueError, match="Request body is required"):
            _parse_request({"body": ""})

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="Invalid request format"):
            _parse_request({"body": "not-json"})

    def test_missing_session_id(self):
        event = {"body": json.dumps({"email": "user@example.com"})}
        with pytest.raises(ValueError, match="sessionId is required"):
            _parse_request(event)

    def test_missing_email(self):
        event = {"body": json.dumps({"sessionId": "abc-123"})}
        with pytest.raises(ValueError, match="email is required"):
            _parse_request(event)

    def test_whitespace_session_id(self):
        event = {"body": json.dumps({"sessionId": "  ", "email": "user@example.com"})}
        with pytest.raises(ValueError, match="sessionId is required"):
            _parse_request(event)

    def test_whitespace_email(self):
        event = {"body": json.dumps({"sessionId": "abc-123", "email": "  "})}
        with pytest.raises(ValueError, match="email is required"):
            _parse_request(event)


    def test_strips_whitespace(self):
        event = {"body": json.dumps({"sessionId": " abc-123 ", "email": " user@example.com "})}
        result = _parse_request(event)
        assert result == {"sessionId": "abc-123", "email": "user@example.com"}


# ---------------------------------------------------------------------------
# _retrieve_bill_from_s3
# ---------------------------------------------------------------------------
class TestRetrieveBillFromS3:
    @patch("lambda_function.s3_client")
    def test_success(self, mock_s3):
        mock_s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "bills/sess-1/invoice.pdf"}]
        }
        body_mock = MagicMock()
        body_mock.read.return_value = b"%PDF-fake"
        mock_s3.get_object.return_value = {"Body": body_mock}

        pdf_bytes, filename = _retrieve_bill_from_s3("sess-1")
        assert pdf_bytes == b"%PDF-fake"
        assert filename == "invoice.pdf"

    @patch("lambda_function.s3_client")
    def test_session_not_found(self, mock_s3):
        mock_s3.list_objects_v2.return_value = {"Contents": []}
        with pytest.raises(FileNotFoundError):
            _retrieve_bill_from_s3("nonexistent")

    @patch("lambda_function.s3_client")
    def test_no_contents_key(self, mock_s3):
        mock_s3.list_objects_v2.return_value = {}
        with pytest.raises(FileNotFoundError):
            _retrieve_bill_from_s3("nonexistent")

    @patch("lambda_function.s3_client")
    def test_list_client_error(self, mock_s3):
        from botocore.exceptions import ClientError

        mock_s3.list_objects_v2.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "ListObjectsV2"
        )
        with pytest.raises(RuntimeError, match="Failed to access storage"):
            _retrieve_bill_from_s3("sess-1")

    @patch("lambda_function.s3_client")
    def test_get_client_error(self, mock_s3):
        from botocore.exceptions import ClientError

        mock_s3.list_objects_v2.return_value = {
            "Contents": [{"Key": "bills/sess-1/invoice.pdf"}]
        }
        mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject"
        )
        with pytest.raises(RuntimeError, match="Failed to retrieve bill"):
            _retrieve_bill_from_s3("sess-1")


# ---------------------------------------------------------------------------
# _upload_report_to_s3
# ---------------------------------------------------------------------------
class TestUploadReportToS3:
    @patch("lambda_function.s3_client")
    def test_success(self, mock_s3):
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/report.pdf"
        url = _upload_report_to_s3("sess-1", b"%PDF-report")
        assert url == "https://s3.example.com/report.pdf"
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Key"] == "reports/sess-1/report.pdf"
        assert call_kwargs["ContentType"] == "application/pdf"

    @patch("lambda_function.s3_client")
    def test_upload_failure(self, mock_s3):
        from botocore.exceptions import ClientError

        mock_s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "fail"}}, "PutObject"
        )
        with pytest.raises(RuntimeError, match="Failed to store report"):
            _upload_report_to_s3("sess-1", b"%PDF-report")

    @patch("lambda_function.s3_client")
    def test_presigned_url_failure(self, mock_s3):
        from botocore.exceptions import ClientError

        mock_s3.generate_presigned_url.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "fail"}}, "GeneratePresignedUrl"
        )
        with pytest.raises(RuntimeError, match="pre-signed"):
            _upload_report_to_s3("sess-1", b"%PDF-report")


# ---------------------------------------------------------------------------
# Helper response functions
# ---------------------------------------------------------------------------
class TestResponseHelpers:
    def test_success_response(self):
        resp = _create_success_response("https://url", "Summary text", "sess-1")
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["downloadUrl"] == "https://url"
        assert body["summary"] == "Summary text"
        assert body["sessionId"] == "sess-1"

    def test_error_response_400(self):
        resp = _create_error_response(400, "Bad input")
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"] == "BadRequest"
        assert body["message"] == "Bad input"
        assert body["retryable"] is False

    def test_error_response_retryable(self):
        resp = _create_error_response(500, "Server error", retryable=True)
        body = json.loads(resp["body"])
        assert body["retryable"] is True


# ---------------------------------------------------------------------------
# lambda_handler integration (mocked dependencies)
# ---------------------------------------------------------------------------
class TestLambdaHandler:
    def _make_event(self, session_id="sess-1", email="user@example.com"):
        return {"body": json.dumps({"sessionId": session_id, "email": email})}

    def test_missing_body_returns_400(self):
        resp = lambda_handler({}, None)
        assert resp["statusCode"] == 400

    def test_missing_session_id_returns_400(self):
        event = {"body": json.dumps({"email": "user@example.com"})}
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert body["error"] == "BadRequest"

    @patch("lambda_function._retrieve_bill_from_s3")
    def test_session_not_found_returns_404(self, mock_retrieve):
        mock_retrieve.side_effect = FileNotFoundError("not found")
        resp = lambda_handler(self._make_event(), None)
        assert resp["statusCode"] == 404
        body = json.loads(resp["body"])
        assert "Session not found" in body["message"]

    @patch("lambda_function._retrieve_bill_from_s3")
    def test_s3_retrieval_error_returns_500(self, mock_retrieve):
        mock_retrieve.side_effect = RuntimeError("storage error")
        resp = lambda_handler(self._make_event(), None)
        assert resp["statusCode"] == 500

    @patch("lambda_function.parse_bill")
    @patch("lambda_function._retrieve_bill_from_s3")
    def test_parse_value_error_returns_400(self, mock_retrieve, mock_parse):
        mock_retrieve.return_value = (b"%PDF-data", "invoice.pdf")
        mock_parse.side_effect = ValueError("bad format")
        resp = lambda_handler(self._make_event(), None)
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert "parse" in body["message"].lower() or "valid AWS invoice" in body["message"]

    @patch("lambda_function.analyze_bill")
    @patch("lambda_function.parse_bill")
    @patch("lambda_function._retrieve_bill_from_s3")
    def test_bedrock_throttling_returns_429(self, mock_retrieve, mock_parse, mock_analyze):
        mock_retrieve.return_value = (b"%PDF-data", "invoice.pdf")
        mock_parse.return_value = {"summary": "test"}
        mock_analyze.side_effect = RuntimeError("Service is busy, please retry in a moment")
        resp = lambda_handler(self._make_event(), None)
        assert resp["statusCode"] == 429
        body = json.loads(resp["body"])
        assert body["retryable"] is True

    @patch("lambda_function.analyze_bill")
    @patch("lambda_function.parse_bill")
    @patch("lambda_function._retrieve_bill_from_s3")
    def test_bedrock_unavailable_returns_503(self, mock_retrieve, mock_parse, mock_analyze):
        mock_retrieve.return_value = (b"%PDF-data", "invoice.pdf")
        mock_parse.return_value = {"summary": "test"}
        mock_analyze.side_effect = RuntimeError("AI service temporarily unavailable")
        resp = lambda_handler(self._make_event(), None)
        assert resp["statusCode"] == 503
        body = json.loads(resp["body"])
        assert body["retryable"] is True

    @patch("lambda_function.analyze_bill")
    @patch("lambda_function.parse_bill")
    @patch("lambda_function._retrieve_bill_from_s3")
    def test_bedrock_timeout_returns_504(self, mock_retrieve, mock_parse, mock_analyze):
        mock_retrieve.return_value = (b"%PDF-data", "invoice.pdf")
        mock_parse.return_value = {"summary": "test"}
        mock_analyze.side_effect = RuntimeError("some other error")
        resp = lambda_handler(self._make_event(), None)
        assert resp["statusCode"] == 504

    @patch("lambda_function.generate_report")
    @patch("lambda_function.analyze_bill")
    @patch("lambda_function.parse_bill")
    @patch("lambda_function._retrieve_bill_from_s3")
    def test_pdf_generation_failure_returns_500(self, mock_retrieve, mock_parse, mock_analyze, mock_gen):
        mock_retrieve.return_value = (b"%PDF-data", "invoice.pdf")
        mock_parse.return_value = {"summary": "test"}
        mock_analyze.return_value = {"summary": "AI summary"}
        mock_gen.side_effect = RuntimeError("PDF error")
        resp = lambda_handler(self._make_event(), None)
        assert resp["statusCode"] == 500
        body = json.loads(resp["body"])
        assert "generate report" in body["message"].lower()

    @patch("lambda_function._upload_report_to_s3")
    @patch("lambda_function.generate_report")
    @patch("lambda_function.analyze_bill")
    @patch("lambda_function.parse_bill")
    @patch("lambda_function._retrieve_bill_from_s3")
    def test_upload_failure_returns_500(self, mock_retrieve, mock_parse, mock_analyze, mock_gen, mock_upload):
        mock_retrieve.return_value = (b"%PDF-data", "invoice.pdf")
        mock_parse.return_value = {"summary": "test"}
        mock_analyze.return_value = {"summary": "AI summary"}
        mock_gen.return_value = b"%PDF-report"
        mock_upload.side_effect = RuntimeError("Failed to store report")
        resp = lambda_handler(self._make_event(), None)
        assert resp["statusCode"] == 500
        body = json.loads(resp["body"])
        assert "store report" in body["message"].lower()

    @patch("lambda_function._upload_report_to_s3")
    @patch("lambda_function.generate_report")
    @patch("lambda_function.analyze_bill")
    @patch("lambda_function.parse_bill")
    @patch("lambda_function._retrieve_bill_from_s3")
    def test_presigned_url_failure_returns_500(self, mock_retrieve, mock_parse, mock_analyze, mock_gen, mock_upload):
        mock_retrieve.return_value = (b"%PDF-data", "invoice.pdf")
        mock_parse.return_value = {"summary": "test"}
        mock_analyze.return_value = {"summary": "AI summary"}
        mock_gen.return_value = b"%PDF-report"
        mock_upload.side_effect = RuntimeError("Failed to generate pre-signed download URL")
        resp = lambda_handler(self._make_event(), None)
        assert resp["statusCode"] == 500
        body = json.loads(resp["body"])
        assert "download link" in body["message"].lower()

    @patch("lambda_function._upload_report_to_s3")
    @patch("lambda_function.generate_report")
    @patch("lambda_function.analyze_bill")
    @patch("lambda_function.parse_bill")
    @patch("lambda_function._retrieve_bill_from_s3")
    def test_success_flow(self, mock_retrieve, mock_parse, mock_analyze, mock_gen, mock_upload):
        mock_retrieve.return_value = (b"%PDF-data", "invoice.pdf")
        mock_parse.return_value = {"summary": "test"}
        mock_analyze.return_value = {"summary": "Your bill totals $150."}
        mock_gen.return_value = b"%PDF-report"
        mock_upload.return_value = "https://s3.example.com/report.pdf"

        resp = lambda_handler(self._make_event(), None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["downloadUrl"] == "https://s3.example.com/report.pdf"
        assert body["summary"] == "Your bill totals $150."
        assert body["sessionId"] == "sess-1"
