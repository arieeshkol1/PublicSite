"""Unit tests for the /members/terraform/generate API endpoint.

Tests cover:
- Missing actionType returns 400
- Missing accountId for account-specific actions returns 400
- Invalid accountId format returns 400
- Unsupported action type returns 400 with descriptive message
- Unauthenticated request returns 401
- Successful dispatch to cross-account-role generator
- Successful dispatch to cross-account-module generator
- Successful dispatch to optimization action generators
- Successful dispatch to waste action generators
- Successful dispatch to ri-sp-commitment generator
- Account ownership enforcement returns 403 for unauthorized accounts
"""

import sys
import os
import json
import base64
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def _make_event(body=None, token='valid-token', route_key='POST /members/terraform/generate'):
    """Build a mock API Gateway event for the terraform generate endpoint."""
    event = {
        'routeKey': route_key,
        'headers': {
            'authorization': f'Bearer {token}' if token else '',
        },
        'body': json.dumps(body) if body is not None else '{}',
    }
    return event


def _mock_auth_success(email='test@example.com'):
    """Return a successful auth dict."""
    return {'sub': email, 'role': 'member', 'displayName': 'Test User'}


def _mock_auth_failure():
    """Return an auth failure response."""
    return {
        'statusCode': 401,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        },
        'body': json.dumps({'error': 'AuthError', 'message': 'Authentication required', 'code': 401}),
    }


class TestTerraformGenerateAuthentication:
    """Tests for authentication enforcement."""

    @patch('lambda_function.validate_token')
    def test_unauthenticated_request_returns_401(self, mock_validate):
        """Unauthenticated request should return 401."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_failure()
        event = _make_event(body={'actionType': 'cross-account-role'}, token='')
        result = handle_terraform_generate(event)
        assert result['statusCode'] == 401

    @patch('lambda_function.validate_token')
    def test_expired_token_returns_401(self, mock_validate):
        """Expired token should return 401."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_failure()
        event = _make_event(body={'actionType': 'cross-account-role'}, token='expired-token')
        result = handle_terraform_generate(event)
        assert result['statusCode'] == 401


class TestTerraformGenerateValidation:
    """Tests for request validation."""

    @patch('lambda_function.validate_token')
    def test_missing_action_type_returns_400(self, mock_validate):
        """Missing actionType should return 400."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={})
        result = handle_terraform_generate(event)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidRequest'
        assert 'actionType is required' in body['message']

    @patch('lambda_function.validate_token')
    def test_empty_action_type_returns_400(self, mock_validate):
        """Empty actionType should return 400."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={'actionType': ''})
        result = handle_terraform_generate(event)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidRequest'
        assert 'actionType is required' in body['message']

    @patch('lambda_function.validate_token')
    def test_missing_account_id_for_optimization_action_returns_400(self, mock_validate):
        """Missing accountId for account-specific actions should return 400."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={'actionType': 'resize-ec2'})
        result = handle_terraform_generate(event)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidRequest'
        assert 'accountId is required' in body['message']

    @patch('lambda_function.validate_token')
    def test_missing_account_id_for_waste_action_returns_400(self, mock_validate):
        """Missing accountId for waste actions should return 400."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={'actionType': 'waste-ebs'})
        result = handle_terraform_generate(event)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidRequest'
        assert 'accountId is required' in body['message']

    @patch('lambda_function.validate_token')
    def test_missing_account_id_for_commitment_returns_400(self, mock_validate):
        """Missing accountId for ri-sp-commitment should return 400."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={'actionType': 'ri-sp-commitment'})
        result = handle_terraform_generate(event)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidRequest'
        assert 'accountId is required' in body['message']

    @patch('lambda_function.validate_token')
    def test_cross_account_role_does_not_require_account_id(self, mock_validate):
        """cross-account-role should not require accountId."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={'actionType': 'cross-account-role'})
        result = handle_terraform_generate(event)
        # Should succeed (200) since no accountId is required
        assert result['statusCode'] == 200

    @patch('lambda_function.validate_token')
    def test_cross_account_module_does_not_require_account_id(self, mock_validate):
        """cross-account-module should not require accountId."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={'actionType': 'cross-account-module'})
        result = handle_terraform_generate(event)
        # Should succeed (200) since no accountId is required
        assert result['statusCode'] == 200

    @patch('lambda_function.validate_token')
    def test_invalid_account_id_format_returns_400(self, mock_validate):
        """Invalid accountId format should return 400."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={'actionType': 'resize-ec2', 'accountId': '12345'})
        result = handle_terraform_generate(event)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidAccountId'
        assert '12 digits' in body['message']

    @patch('lambda_function.validate_token')
    def test_account_id_with_letters_returns_400(self, mock_validate):
        """AccountId with letters should return 400."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={'actionType': 'resize-ec2', 'accountId': '12345678abcd'})
        result = handle_terraform_generate(event)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidAccountId'

    @patch('lambda_function.validate_token')
    def test_unsupported_action_type_returns_400(self, mock_validate):
        """Unsupported actionType should return 400 with UnsupportedActionType error."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={'actionType': 'custom-unknown-action', 'accountId': '123456789012'})

        with patch('lambda_function._verify_account_ownership', return_value=True):
            result = handle_terraform_generate(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'UnsupportedActionType'
        assert 'custom-unknown-action' in body['message']

    @patch('lambda_function.validate_token')
    def test_invalid_json_body_returns_400(self, mock_validate):
        """Invalid JSON body should return 400."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = {
            'routeKey': 'POST /members/terraform/generate',
            'headers': {'authorization': 'Bearer valid-token'},
            'body': 'not-valid-json{{{',
        }
        result = handle_terraform_generate(event)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert body['error'] == 'InvalidRequest'


class TestTerraformGenerateAccountOwnership:
    """Tests for account ownership enforcement."""

    @patch('lambda_function._verify_account_ownership')
    @patch('lambda_function.validate_token')
    def test_unauthorized_account_returns_403(self, mock_validate, mock_ownership):
        """Account not owned by member should return 403."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        mock_ownership.return_value = {
            'statusCode': 403,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            },
            'body': json.dumps({
                'error': 'Forbidden',
                'message': 'Account 123456789012 does not belong to you',
                'code': 403,
            }),
        }

        event = _make_event(body={'actionType': 'resize-ec2', 'accountId': '123456789012'})
        result = handle_terraform_generate(event)
        assert result['statusCode'] == 403
        body = json.loads(result['body'])
        assert body['error'] == 'Forbidden'


class TestTerraformGenerateCrossAccountRole:
    """Tests for cross-account-role dispatch."""

    @patch('lambda_function.validate_token')
    def test_cross_account_role_returns_tf_file(self, mock_validate):
        """cross-account-role should return a .tf file with correct headers."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success('user@example.com')
        event = _make_event(body={'actionType': 'cross-account-role', 'accountId': '123456789012'})

        with patch('lambda_function._verify_account_ownership', return_value=True):
            result = handle_terraform_generate(event)

        assert result['statusCode'] == 200
        assert result['headers']['Content-Type'] == 'application/octet-stream'
        assert 'SlashMyBill-123456789012.tf' in result['headers']['Content-Disposition']
        assert result['isBase64Encoded'] is False
        # Body should contain HCL content
        assert 'terraform' in result['body']
        assert 'aws_iam_role' in result['body']

    @patch('lambda_function.validate_token')
    def test_cross_account_role_without_account_id_uses_placeholder(self, mock_validate):
        """cross-account-role without accountId should use placeholder."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success('user@example.com')
        event = _make_event(body={'actionType': 'cross-account-role'})
        result = handle_terraform_generate(event)

        assert result['statusCode'] == 200
        assert '000000000000' in result['headers']['Content-Disposition']


class TestTerraformGenerateCrossAccountModule:
    """Tests for cross-account-module dispatch."""

    @patch('lambda_function.validate_token')
    def test_cross_account_module_returns_zip(self, mock_validate):
        """cross-account-module should return a ZIP file."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success('user@example.com')
        event = _make_event(body={'actionType': 'cross-account-module', 'accountId': '123456789012'})

        with patch('lambda_function._verify_account_ownership', return_value=True):
            result = handle_terraform_generate(event)

        assert result['statusCode'] == 200
        assert result['headers']['Content-Type'] == 'application/zip'
        assert 'slashmybill-cross-account-module.zip' in result['headers']['Content-Disposition']
        assert result['isBase64Encoded'] is True
        # Verify it's valid base64
        zip_bytes = base64.b64decode(result['body'])
        assert len(zip_bytes) > 0


class TestTerraformGenerateOptimizationActions:
    """Tests for optimization action dispatch."""

    @patch('lambda_function._verify_account_ownership', return_value=True)
    @patch('lambda_function.validate_token')
    def test_resize_ec2_returns_tf_file(self, mock_validate, mock_ownership):
        """resize-ec2 should return a .tf file."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={
            'actionType': 'resize-ec2',
            'accountId': '123456789012',
            'actionParams': {'instanceId': 'i-0abc123', 'targetInstanceType': 't3.medium'},
        })
        result = handle_terraform_generate(event)

        assert result['statusCode'] == 200
        assert result['headers']['Content-Type'] == 'application/octet-stream'
        assert 'resize-ec2.tf' in result['headers']['Content-Disposition']
        assert 'aws_instance' in result['body']

    @patch('lambda_function._verify_account_ownership', return_value=True)
    @patch('lambda_function.validate_token')
    def test_delete_ebs_returns_tf_file(self, mock_validate, mock_ownership):
        """delete-ebs should return a .tf file with removed block."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={
            'actionType': 'delete-ebs',
            'accountId': '123456789012',
            'actionParams': {'volumeId': 'vol-0abc123'},
        })
        result = handle_terraform_generate(event)

        assert result['statusCode'] == 200
        assert 'delete-ebs.tf' in result['headers']['Content-Disposition']
        assert 'removed' in result['body']

    @patch('lambda_function._verify_account_ownership', return_value=True)
    @patch('lambda_function.validate_token')
    def test_create_budget_returns_tf_file(self, mock_validate, mock_ownership):
        """create-budget should return a .tf file with budget resource."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={
            'actionType': 'create-budget',
            'accountId': '123456789012',
            'actionParams': {
                'budgetName': 'test-budget',
                'amount': 1000,
                'timeUnit': 'MONTHLY',
                'notificationThresholds': [80, 100],
                'subscriberEmail': 'test@example.com',
            },
        })
        result = handle_terraform_generate(event)

        assert result['statusCode'] == 200
        assert 'create-budget.tf' in result['headers']['Content-Disposition']
        assert 'aws_budgets_budget' in result['body']

    @patch('lambda_function._verify_account_ownership', return_value=True)
    @patch('lambda_function.validate_token')
    def test_region_defaults_to_us_east_1(self, mock_validate, mock_ownership):
        """Region should default to us-east-1 when not specified."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={
            'actionType': 'resize-ec2',
            'accountId': '123456789012',
            'actionParams': {'instanceId': 'i-0abc123', 'targetInstanceType': 't3.medium'},
        })
        result = handle_terraform_generate(event)

        assert result['statusCode'] == 200
        assert 'us-east-1' in result['body']


class TestTerraformGenerateWasteActions:
    """Tests for waste action dispatch."""

    @patch('lambda_function._verify_account_ownership', return_value=True)
    @patch('lambda_function.validate_token')
    def test_waste_ebs_missing_resource_id_returns_400(self, mock_validate, mock_ownership):
        """waste-ebs without resourceId should return 400."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={
            'actionType': 'waste-ebs',
            'accountId': '123456789012',
            'actionParams': {},
        })

        # Mock the AWS client import to avoid actual AWS calls
        with patch('lambda_function.handle_terraform_generate.__module__', 'lambda_function'):
            result = handle_terraform_generate(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'resourceId' in body['message']

    @patch('hcl_generator.aws_client.assume_cross_account_role')
    @patch('lambda_function._verify_account_ownership', return_value=True)
    @patch('lambda_function.validate_token')
    def test_waste_ebs_success(self, mock_validate, mock_ownership, mock_assume):
        """waste-ebs with valid params should return .tf file."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        mock_session = MagicMock()
        mock_assume.return_value = mock_session

        # Mock the EC2 client response
        mock_ec2 = MagicMock()
        mock_session.client.return_value = mock_ec2
        mock_ec2.describe_volumes.return_value = {
            'Volumes': [{
                'VolumeId': 'vol-0abc123',
                'Size': 100,
                'VolumeType': 'gp3',
                'AvailabilityZone': 'us-east-1a',
                'Tags': [{'Key': 'Name', 'Value': 'test-vol'}],
            }]
        }

        event = _make_event(body={
            'actionType': 'waste-ebs',
            'accountId': '123456789012',
            'region': 'us-east-1',
            'actionParams': {'resourceId': 'vol-0abc123'},
        })
        result = handle_terraform_generate(event)

        assert result['statusCode'] == 200
        assert 'waste-ebs.tf' in result['headers']['Content-Disposition']
        assert 'aws_ebs_volume' in result['body']
        assert 'import' in result['body']


class TestTerraformGenerateCommitment:
    """Tests for ri-sp-commitment dispatch."""

    @patch('lambda_function._verify_account_ownership', return_value=True)
    @patch('lambda_function.validate_token')
    def test_commitment_missing_options_returns_400(self, mock_validate, mock_ownership):
        """ri-sp-commitment without options should return 400."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={
            'actionType': 'ri-sp-commitment',
            'accountId': '123456789012',
            'actionParams': {'commitmentType': 'sp'},
        })
        result = handle_terraform_generate(event)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'options' in body['message']

    @patch('lambda_function._verify_account_ownership', return_value=True)
    @patch('lambda_function.validate_token')
    def test_commitment_success(self, mock_validate, mock_ownership):
        """ri-sp-commitment with valid params should return .tf file."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success('user@example.com')
        event = _make_event(body={
            'actionType': 'ri-sp-commitment',
            'accountId': '123456789012',
            'actionParams': {
                'commitmentType': 'sp',
                'options': [{
                    'term': '1-year',
                    'paymentOption': 'no-upfront',
                    'estimatedSavings': 500,
                    'computeType': 'EC2',
                    'monthlyCommitment': 1000,
                }],
            },
        })
        result = handle_terraform_generate(event)

        assert result['statusCode'] == 200
        assert 'sp-commitment.tf' in result['headers']['Content-Disposition']
        assert 'aws_budgets_budget' in result['body']


class TestTerraformGenerateResponseHeaders:
    """Tests for response headers."""

    @patch('lambda_function.validate_token')
    def test_tf_file_has_cors_headers(self, mock_validate):
        """Response should include CORS headers."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={'actionType': 'cross-account-role'})
        result = handle_terraform_generate(event)

        assert result['headers']['Access-Control-Allow-Origin'] == '*'
        assert 'Authorization' in result['headers']['Access-Control-Allow-Headers']

    @patch('lambda_function.validate_token')
    def test_tf_file_has_content_disposition(self, mock_validate):
        """Response should include Content-Disposition attachment header."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={'actionType': 'cross-account-role'})
        result = handle_terraform_generate(event)

        assert 'attachment' in result['headers']['Content-Disposition']
        assert '.tf' in result['headers']['Content-Disposition']

    @patch('lambda_function.validate_token')
    def test_zip_file_has_correct_content_type(self, mock_validate):
        """ZIP response should have application/zip content type."""
        from lambda_function import handle_terraform_generate

        mock_validate.return_value = _mock_auth_success()
        event = _make_event(body={'actionType': 'cross-account-module'})
        result = handle_terraform_generate(event)

        assert result['headers']['Content-Type'] == 'application/zip'


# ============================================================
# Backward Compatibility Tests for handle_generate_template
# (POST /members/accounts/template)
# Validates Requirements 1.6, 1.7
# ============================================================


class TestGenerateTemplateBackwardCompatibility:
    """Tests ensuring handle_generate_template returns CloudFormation YAML
    when format is 'cloudformation' or unspecified (Requirement 1.6),
    and returns Terraform .tf file when format is 'terraform' (Requirement 1.7).
    """

    @patch('lambda_function.boto3.client')
    @patch('lambda_function.validate_token')
    def test_no_format_returns_cloudformation_yaml(self, mock_validate, mock_boto_client):
        """When no format is specified, should return CloudFormation YAML template."""
        from lambda_function import handle_generate_template

        mock_validate.return_value = _mock_auth_success('user@example.com')
        # Mock S3 client to avoid actual AWS calls
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.put_object.return_value = {}
        mock_s3.generate_presigned_url.return_value = 'https://s3.example.com/template'
        # Mock STS assume_role to fail (stack check) — that's fine
        mock_sts = MagicMock()
        mock_boto_client.side_effect = lambda service, **kwargs: mock_s3 if service == 's3' else mock_sts
        mock_sts.assume_role.side_effect = Exception("Role not found")

        event = _make_event(
            body={'accountId': '123456789012'},
            route_key='POST /members/accounts/template',
        )
        result = handle_generate_template(event)

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        # Should contain CloudFormation template YAML
        assert 'template' in body
        assert 'AWSTemplateFormatVersion' in body['template']
        assert 'SlashMyBillRole' in body['template']
        # Should contain CloudFormation-specific fields
        assert 'filename' in body
        assert body['filename'].endswith('.yaml')

    @patch('lambda_function.boto3.client')
    @patch('lambda_function.validate_token')
    def test_format_cloudformation_returns_cloudformation_yaml(self, mock_validate, mock_boto_client):
        """When format is 'cloudformation', should return CloudFormation YAML template."""
        from lambda_function import handle_generate_template

        mock_validate.return_value = _mock_auth_success('user@example.com')
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.put_object.return_value = {}
        mock_s3.generate_presigned_url.return_value = 'https://s3.example.com/template'
        mock_sts = MagicMock()
        mock_boto_client.side_effect = lambda service, **kwargs: mock_s3 if service == 's3' else mock_sts
        mock_sts.assume_role.side_effect = Exception("Role not found")

        event = _make_event(
            body={'accountId': '123456789012', 'format': 'cloudformation'},
            route_key='POST /members/accounts/template',
        )
        result = handle_generate_template(event)

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'template' in body
        assert 'AWSTemplateFormatVersion' in body['template']
        assert body['filename'].endswith('.yaml')

    @patch('lambda_function.validate_token')
    def test_format_terraform_returns_tf_file(self, mock_validate):
        """When format is 'terraform', should return a downloadable .tf file (Requirement 1.7)."""
        from lambda_function import handle_generate_template

        mock_validate.return_value = _mock_auth_success('user@example.com')
        event = _make_event(
            body={'accountId': '123456789012', 'format': 'terraform'},
            route_key='POST /members/accounts/template',
        )
        result = handle_generate_template(event)

        assert result['statusCode'] == 200
        # Should return as downloadable file
        assert result['headers']['Content-Type'] == 'application/octet-stream'
        assert 'SlashMyBill-123456789012.tf' in result['headers']['Content-Disposition']
        assert result['isBase64Encoded'] is False
        # Body should contain Terraform HCL content
        assert 'terraform' in result['body']
        assert 'aws_iam_role' in result['body']

    @patch('lambda_function.validate_token')
    def test_format_terraform_case_insensitive(self, mock_validate):
        """Format parameter should be case-insensitive."""
        from lambda_function import handle_generate_template

        mock_validate.return_value = _mock_auth_success('user@example.com')
        event = _make_event(
            body={'accountId': '123456789012', 'format': 'Terraform'},
            route_key='POST /members/accounts/template',
        )
        result = handle_generate_template(event)

        assert result['statusCode'] == 200
        assert result['headers']['Content-Type'] == 'application/octet-stream'
        assert '.tf' in result['headers']['Content-Disposition']

    @patch('lambda_function.boto3.client')
    @patch('lambda_function.validate_token')
    def test_format_empty_string_returns_cloudformation(self, mock_validate, mock_boto_client):
        """Empty format string should default to CloudFormation."""
        from lambda_function import handle_generate_template

        mock_validate.return_value = _mock_auth_success('user@example.com')
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.put_object.return_value = {}
        mock_s3.generate_presigned_url.return_value = 'https://s3.example.com/template'
        mock_sts = MagicMock()
        mock_boto_client.side_effect = lambda service, **kwargs: mock_s3 if service == 's3' else mock_sts
        mock_sts.assume_role.side_effect = Exception("Role not found")

        event = _make_event(
            body={'accountId': '123456789012', 'format': ''},
            route_key='POST /members/accounts/template',
        )
        result = handle_generate_template(event)

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'template' in body
        assert 'AWSTemplateFormatVersion' in body['template']

    @patch('lambda_function.validate_token')
    def test_terraform_template_contains_external_id(self, mock_validate):
        """Terraform template should contain the SHA-256 ExternalId matching CloudFormation behavior."""
        import hashlib
        from lambda_function import handle_generate_template

        email = 'user@example.com'
        expected_external_id = hashlib.sha256(email.encode('utf-8')).hexdigest()

        mock_validate.return_value = _mock_auth_success(email)
        event = _make_event(
            body={'accountId': '123456789012', 'format': 'terraform'},
            route_key='POST /members/accounts/template',
        )
        result = handle_generate_template(event)

        assert result['statusCode'] == 200
        assert expected_external_id in result['body']
