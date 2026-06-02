"""AWS connector — STS AssumeRole + Cost Explorer."""
from .base_connector import ProviderConnector, AuthenticationError, CostRetrievalError
from . import register_connector
import boto3
import hashlib
from datetime import datetime, timezone, timedelta


class AWSConnector(ProviderConnector):
    """AWS cloud provider connector using STS AssumeRole and Cost Explorer."""

    def authenticate(self, credentials: dict) -> dict:
        """Assume cross-account IAM role.

        credentials should contain:
          - account_id: 12-digit AWS account ID
          - member_email: for external ID derivation
          - session_name: optional session name
        """
        account_id = credentials['account_id']
        member_email = credentials['member_email']
        session_name = credentials.get('session_name', 'SlashMyBill')

        external_id = hashlib.sha256(member_email.encode('utf-8')).hexdigest()
        role_arn = f'arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}'

        try:
            sts = boto3.client('sts')
            response = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=session_name,
                ExternalId=external_id,
                DurationSeconds=3600
            )
            return response['Credentials']
        except Exception as e:
            raise AuthenticationError(f'Cannot assume role: {e}', provider='aws')

    def test_connection(self, auth_context: dict, account_id: str) -> dict:
        """Test connection by reading a small cost data sample."""
        try:
            ce = boto3.client('ce',
                aws_access_key_id=auth_context['AccessKeyId'],
                aws_secret_access_key=auth_context['SecretAccessKey'],
                aws_session_token=auth_context['SessionToken'])

            end = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d')

            resp = ce.get_cost_and_usage(
                TimePeriod={'Start': start, 'End': end},
                Granularity='DAILY',
                Metrics=['UnblendedCost']
            )
            return {
                'success': True,
                'message': 'AWS connection successful',
                'details': {'days': len(resp.get('ResultsByTime', []))}
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'AWS connection test failed: {e}',
                'details': {}
            }

    def get_cost_data(self, auth_context: dict, account_id: str, start_date: str, end_date: str) -> list:
        """Retrieve daily cost data from AWS Cost Explorer."""
        try:
            ce = boto3.client('ce',
                aws_access_key_id=auth_context['AccessKeyId'],
                aws_secret_access_key=auth_context['SecretAccessKey'],
                aws_session_token=auth_context['SessionToken'])

            resp = ce.get_cost_and_usage(
                TimePeriod={'Start': start_date, 'End': end_date},
                Granularity='DAILY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
            )
            return resp.get('ResultsByTime', [])
        except Exception as e:
            raise CostRetrievalError(f'AWS cost retrieval failed: {e}', provider='aws')


# Auto-register when module is imported
register_connector('aws', AWSConnector)
