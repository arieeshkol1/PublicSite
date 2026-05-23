"""
Unit tests for invoice_sync module.

Tests the cross-account Cost Explorer data fetching, normalization,
and error handling logic.
"""

import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

import pytest
from botocore.exceptions import ClientError

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from invoice_sync import (
    sync_invoice_data,
    _assume_role,
    _fetch_month_data,
    _call_cost_explorer_with_retry,
    _normalize_records,
    _get_next_month_first_day,
    _write_records_to_dynamodb,
    InvoiceSyncError,
)


class TestGetNextMonthFirstDay:
    """Tests for _get_next_month_first_day helper."""

    def test_regular_month(self):
        assert _get_next_month_first_day(2024, 1) == '2024-02-01'
        assert _get_next_month_first_day(2024, 6) == '2024-07-01'
        assert _get_next_month_first_day(2024, 11) == '2024-12-01'

    def test_december_wraps_to_next_year(self):
        assert _get_next_month_first_day(2024, 12) == '2025-01-01'
        assert _get_next_month_first_day(2023, 12) == '2024-01-01'

    def test_single_digit_months_padded(self):
        result = _get_next_month_first_day(2024, 3)
        assert result == '2024-04-01'


class TestAssumeRole:
    """Tests for _assume_role function."""

    @patch('invoice_sync.boto3.client')
    def test_assume_role_uses_correct_arn_pattern(self, mock_boto_client):
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            'Credentials': {
                'AccessKeyId': 'AKIA...',
                'SecretAccessKey': 'secret',
                'SessionToken': 'token',
            }
        }

        creds = _assume_role('user@example.com', '123456789012')

        mock_sts.assume_role.assert_called_once()
        call_kwargs = mock_sts.assume_role.call_args[1]
        assert call_kwargs['RoleArn'] == 'arn:aws:iam::123456789012:role/SlashMyBill-123456789012'
        assert call_kwargs['RoleSessionName'] == 'SlashMyBillInvoiceSync'
        # ExternalId is SHA-256 of email
        import hashlib
        expected_ext_id = hashlib.sha256('user@example.com'.encode('utf-8')).hexdigest()
        assert call_kwargs['ExternalId'] == expected_ext_id

    @patch('invoice_sync.boto3.client')
    def test_assume_role_returns_credentials(self, mock_boto_client):
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        expected_creds = {
            'AccessKeyId': 'AKIATEST',
            'SecretAccessKey': 'secrettest',
            'SessionToken': 'tokentest',
        }
        mock_sts.assume_role.return_value = {'Credentials': expected_creds}

        result = _assume_role('test@test.com', '111222333444')
        assert result == expected_creds

    @patch('invoice_sync.boto3.client')
    def test_assume_role_raises_on_access_denied(self, mock_boto_client):
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Not authorized'}},
            'AssumeRole'
        )

        with pytest.raises(ClientError):
            _assume_role('user@example.com', '123456789012')


class TestCallCostExplorerWithRetry:
    """Tests for _call_cost_explorer_with_retry with exponential backoff."""

    def test_success_on_first_attempt(self):
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.return_value = {'ResultsByTime': []}

        result = _call_cost_explorer_with_retry(
            mock_ce,
            TimePeriod={'Start': '2024-01-01', 'End': '2024-02-01'},
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
        )

        assert result == {'ResultsByTime': []}
        assert mock_ce.get_cost_and_usage.call_count == 1

    @patch('invoice_sync.time.sleep')
    def test_retries_on_throttling(self, mock_sleep):
        mock_ce = MagicMock()
        throttle_error = ClientError(
            {'Error': {'Code': 'LimitExceededException', 'Message': 'Rate exceeded'}},
            'GetCostAndUsage'
        )
        mock_ce.get_cost_and_usage.side_effect = [
            throttle_error,
            throttle_error,
            {'ResultsByTime': [{'Groups': []}]},
        ]

        result = _call_cost_explorer_with_retry(
            mock_ce,
            TimePeriod={'Start': '2024-01-01', 'End': '2024-02-01'},
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
        )

        assert result == {'ResultsByTime': [{'Groups': []}]}
        assert mock_ce.get_cost_and_usage.call_count == 3
        # Verify exponential backoff: 1s, 2s
        assert mock_sleep.call_args_list == [call(1.0), call(2.0)]

    @patch('invoice_sync.time.sleep')
    def test_raises_after_max_retries(self, mock_sleep):
        mock_ce = MagicMock()
        throttle_error = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
            'GetCostAndUsage'
        )
        mock_ce.get_cost_and_usage.side_effect = throttle_error

        with pytest.raises(ClientError):
            _call_cost_explorer_with_retry(
                mock_ce,
                TimePeriod={'Start': '2024-01-01', 'End': '2024-02-01'},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
            )

        # 1 initial + 3 retries = 4 total attempts
        assert mock_ce.get_cost_and_usage.call_count == 4

    def test_non_throttling_error_not_retried(self):
        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.side_effect = ClientError(
            {'Error': {'Code': 'ValidationException', 'Message': 'Invalid params'}},
            'GetCostAndUsage'
        )

        with pytest.raises(ClientError):
            _call_cost_explorer_with_retry(
                mock_ce,
                TimePeriod={'Start': '2024-01-01', 'End': '2024-02-01'},
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
            )

        assert mock_ce.get_cost_and_usage.call_count == 1


class TestNormalizeRecords:
    """Tests for _normalize_records function."""

    def _make_service_data(self, services):
        """Helper to create mock service-level CE response."""
        groups = []
        for name, cost in services.items():
            groups.append({
                'Keys': [name],
                'Metrics': {
                    'UnblendedCost': {'Amount': str(cost), 'Unit': 'USD'},
                    'UsageQuantity': {'Amount': '100', 'Unit': 'N/A'},
                }
            })
        return {'ResultsByTime': [{'TimePeriod': {'Start': '2024-01-01', 'End': '2024-02-01'}, 'Groups': groups}]}

    def _make_daily_data(self, daily_by_service):
        """Helper to create mock daily CE response."""
        results = []
        for day, services in daily_by_service.items():
            groups = []
            for name, cost in services.items():
                groups.append({
                    'Keys': [name],
                    'Metrics': {'UnblendedCost': {'Amount': str(cost), 'Unit': 'USD'}},
                })
            results.append({
                'TimePeriod': {'Start': f'2024-01-{day:02d}', 'End': f'2024-01-{day + 1:02d}'},
                'Groups': groups,
            })
        return {'ResultsByTime': results}

    def _make_usage_type_data(self, usage_by_service):
        """Helper to create mock usage type CE response."""
        groups = []
        for service, usages in usage_by_service.items():
            for usage_type, cost in usages.items():
                groups.append({
                    'Keys': [service, usage_type],
                    'Metrics': {
                        'UnblendedCost': {'Amount': str(cost), 'Unit': 'USD'},
                        'UsageQuantity': {'Amount': '50', 'Unit': 'Hrs'},
                    }
                })
        return {'ResultsByTime': [{'TimePeriod': {'Start': '2024-01-01', 'End': '2024-02-01'}, 'Groups': groups}]}

    def test_basic_normalization(self):
        service_data = self._make_service_data({'Amazon EC2': 150.50, 'Amazon S3': 25.75})
        daily_data = self._make_daily_data({
            1: {'Amazon EC2': 5.0, 'Amazon S3': 0.85},
            2: {'Amazon EC2': 4.5, 'Amazon S3': 0.90},
        })
        usage_type_data = self._make_usage_type_data({
            'Amazon EC2': {'BoxUsage:t3.medium': 100.0, 'EBS:VolumeUsage': 50.50},
            'Amazon S3': {'TimedStorage-ByteHrs': 25.75},
        })

        records = _normalize_records(
            service_data=service_data,
            daily_data=daily_data,
            usage_type_data=usage_type_data,
            member_email='user@example.com',
            account_id='123456789012',
            month='2024-01',
            synced_at='2024-01-15T10:00:00+00:00',
            ttl=1700000000,
        )

        assert len(records) == 2

        ec2_record = next(r for r in records if r['service'] == 'Amazon EC2')
        assert ec2_record['pk'] == 'user@example.com#123456789012'
        assert ec2_record['sk'] == '2024-01#Amazon EC2'
        assert ec2_record['cost'] == Decimal('150.50')
        assert ec2_record['month'] == '2024-01'
        assert ec2_record['currency'] == 'USD'
        assert ec2_record['lastSyncedAt'] == '2024-01-15T10:00:00+00:00'
        assert ec2_record['ttl'] == 1700000000
        assert '01' in ec2_record['dailyCosts']
        assert len(ec2_record['usageTypes']) == 2

    def test_skips_zero_cost_services(self):
        service_data = self._make_service_data({'Amazon EC2': 100.0, 'AWS Tax': 0.0})
        daily_data = {'ResultsByTime': []}
        usage_type_data = {'ResultsByTime': []}

        records = _normalize_records(
            service_data=service_data,
            daily_data=daily_data,
            usage_type_data=usage_type_data,
            member_email='user@example.com',
            account_id='123456789012',
            month='2024-01',
            synced_at='2024-01-15T10:00:00+00:00',
            ttl=1700000000,
        )

        assert len(records) == 1
        assert records[0]['service'] == 'Amazon EC2'

    def test_empty_response_returns_no_records(self):
        service_data = {'ResultsByTime': [{'TimePeriod': {'Start': '2024-01-01', 'End': '2024-02-01'}, 'Groups': []}]}
        daily_data = {'ResultsByTime': []}
        usage_type_data = {'ResultsByTime': []}

        records = _normalize_records(
            service_data=service_data,
            daily_data=daily_data,
            usage_type_data=usage_type_data,
            member_email='user@example.com',
            account_id='123456789012',
            month='2024-01',
            synced_at='2024-01-15T10:00:00+00:00',
            ttl=1700000000,
        )

        assert records == []


class TestSyncInvoiceData:
    """Tests for the main sync_invoice_data function."""

    @patch('invoice_sync._write_records_to_dynamodb')
    @patch('invoice_sync._call_cost_explorer_with_retry')
    @patch('invoice_sync.boto3.client')
    @patch('invoice_sync.time.sleep')
    def test_successful_sync_single_month(self, mock_sleep, mock_boto_client,
                                          mock_ce_call, mock_write):
        # Mock STS
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            'Credentials': {
                'AccessKeyId': 'AKIA',
                'SecretAccessKey': 'secret',
                'SessionToken': 'token',
            }
        }

        # Mock CE responses
        mock_ce_call.side_effect = [
            # Service-level
            {'ResultsByTime': [{'TimePeriod': {'Start': '2024-01-01', 'End': '2024-02-01'}, 'Groups': [
                {'Keys': ['Amazon EC2'], 'Metrics': {'UnblendedCost': {'Amount': '100.50', 'Unit': 'USD'}, 'UsageQuantity': {'Amount': '720', 'Unit': 'Hrs'}}},
            ]}]},
            # Daily
            {'ResultsByTime': [{'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'}, 'Groups': [
                {'Keys': ['Amazon EC2'], 'Metrics': {'UnblendedCost': {'Amount': '3.25', 'Unit': 'USD'}}},
            ]}]},
            # Usage types
            {'ResultsByTime': [{'TimePeriod': {'Start': '2024-01-01', 'End': '2024-02-01'}, 'Groups': [
                {'Keys': ['Amazon EC2', 'BoxUsage:t3.medium'], 'Metrics': {'UnblendedCost': {'Amount': '100.50', 'Unit': 'USD'}, 'UsageQuantity': {'Amount': '720', 'Unit': 'Hrs'}}},
            ]}]},
        ]

        result = sync_invoice_data('user@example.com', '123456789012', ['2024-01'])

        assert result['synced_months'] == ['2024-01']
        assert result['record_count'] == 1
        assert result['total_cost'] == 100.50
        mock_write.assert_called_once()

    @patch('invoice_sync._write_records_to_dynamodb')
    @patch('invoice_sync._call_cost_explorer_with_retry')
    @patch('invoice_sync.boto3.client')
    @patch('invoice_sync.time.sleep')
    def test_empty_months_returns_immediately(self, mock_sleep, mock_boto_client,
                                              mock_ce_call, mock_write):
        result = sync_invoice_data('user@example.com', '123456789012', [])

        assert result == {'synced_months': [], 'record_count': 0, 'total_cost': 0.0}
        mock_boto_client.assert_not_called()

    @patch('invoice_sync.boto3.client')
    def test_sts_access_denied_raises_sync_error(self, mock_boto_client):
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Not authorized'}},
            'AssumeRole'
        )

        with pytest.raises(InvoiceSyncError) as exc_info:
            sync_invoice_data('user@example.com', '123456789012', ['2024-01'])

        assert exc_info.value.status_code == 403
        assert 're-deploy' in exc_info.value.message.lower()

    @patch('invoice_sync._write_records_to_dynamodb')
    @patch('invoice_sync._call_cost_explorer_with_retry')
    @patch('invoice_sync.boto3.client')
    @patch('invoice_sync.time.sleep')
    def test_cost_explorer_not_enabled_raises_error(self, mock_sleep, mock_boto_client,
                                                     mock_ce_call, mock_write):
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            'Credentials': {'AccessKeyId': 'A', 'SecretAccessKey': 'S', 'SessionToken': 'T'}
        }

        mock_ce_call.side_effect = ClientError(
            {'Error': {'Code': 'OptInRequired', 'Message': 'You are not subscribed to this service'}},
            'GetCostAndUsage'
        )

        with pytest.raises(InvoiceSyncError) as exc_info:
            sync_invoice_data('user@example.com', '123456789012', ['2024-01'])

        assert exc_info.value.status_code == 400
        assert 'not enabled' in exc_info.value.message.lower()
        mock_write.assert_not_called()

    @patch('invoice_sync._write_records_to_dynamodb')
    @patch('invoice_sync._call_cost_explorer_with_retry')
    @patch('invoice_sync.boto3.client')
    @patch('invoice_sync.time.sleep')
    def test_partial_failure_stores_successful_months(self, mock_sleep, mock_boto_client,
                                                      mock_ce_call, mock_write):
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            'Credentials': {'AccessKeyId': 'A', 'SecretAccessKey': 'S', 'SessionToken': 'T'}
        }

        # First month succeeds (3 CE calls), second month fails on first CE call
        success_response = {'ResultsByTime': [{'TimePeriod': {'Start': '2024-01-01', 'End': '2024-02-01'}, 'Groups': [
            {'Keys': ['Amazon EC2'], 'Metrics': {'UnblendedCost': {'Amount': '50.00', 'Unit': 'USD'}, 'UsageQuantity': {'Amount': '100', 'Unit': 'Hrs'}}},
        ]}]}
        daily_response = {'ResultsByTime': [{'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'}, 'Groups': [
            {'Keys': ['Amazon EC2'], 'Metrics': {'UnblendedCost': {'Amount': '1.50', 'Unit': 'USD'}}},
        ]}]}
        usage_response = {'ResultsByTime': [{'TimePeriod': {'Start': '2024-01-01', 'End': '2024-02-01'}, 'Groups': [
            {'Keys': ['Amazon EC2', 'BoxUsage'], 'Metrics': {'UnblendedCost': {'Amount': '50.00', 'Unit': 'USD'}, 'UsageQuantity': {'Amount': '100', 'Unit': 'Hrs'}}},
        ]}]}

        generic_error = ClientError(
            {'Error': {'Code': 'InternalError', 'Message': 'Something went wrong'}},
            'GetCostAndUsage'
        )

        mock_ce_call.side_effect = [
            success_response,  # Month 1 - service
            daily_response,    # Month 1 - daily
            usage_response,    # Month 1 - usage types
            generic_error,     # Month 2 - fails
        ]

        result = sync_invoice_data('user@example.com', '123456789012', ['2024-01', '2024-02'])

        assert result['synced_months'] == ['2024-01']
        assert result['record_count'] == 1
        assert 'failed_months' in result
        assert result['failed_months'][0]['month'] == '2024-02'
        mock_write.assert_called_once()

    @patch('invoice_sync._write_records_to_dynamodb')
    @patch('invoice_sync._call_cost_explorer_with_retry')
    @patch('invoice_sync.boto3.client')
    @patch('invoice_sync.time.sleep')
    def test_all_months_fail_raises_error(self, mock_sleep, mock_boto_client,
                                          mock_ce_call, mock_write):
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            'Credentials': {'AccessKeyId': 'A', 'SecretAccessKey': 'S', 'SessionToken': 'T'}
        }

        mock_ce_call.side_effect = ClientError(
            {'Error': {'Code': 'InternalError', 'Message': 'Service unavailable'}},
            'GetCostAndUsage'
        )

        with pytest.raises(InvoiceSyncError) as exc_info:
            sync_invoice_data('user@example.com', '123456789012', ['2024-01'])

        assert exc_info.value.status_code == 502
        mock_write.assert_not_called()

    @patch('invoice_sync._write_records_to_dynamodb')
    @patch('invoice_sync._call_cost_explorer_with_retry')
    @patch('invoice_sync.boto3.client')
    @patch('invoice_sync.time.sleep')
    def test_throttling_after_retries_returns_429(self, mock_sleep, mock_boto_client,
                                                   mock_ce_call, mock_write):
        """After exponential backoff retries are exhausted, returns 429 (Requirement 10.6)."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            'Credentials': {'AccessKeyId': 'A', 'SecretAccessKey': 'S', 'SessionToken': 'T'}
        }

        # Simulate throttling error after retries exhausted in _call_cost_explorer_with_retry
        mock_ce_call.side_effect = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
            'GetCostAndUsage'
        )

        with pytest.raises(InvoiceSyncError) as exc_info:
            sync_invoice_data('user@example.com', '123456789012', ['2024-01'])

        assert exc_info.value.status_code == 429
        assert exc_info.value.error_type == 'Throttled'
        assert 'rate limit' in exc_info.value.message.lower()
        mock_write.assert_not_called()

    @patch('invoice_sync._write_records_to_dynamodb')
    @patch('invoice_sync._call_cost_explorer_with_retry')
    @patch('invoice_sync.boto3.client')
    @patch('invoice_sync.time.sleep')
    def test_limits_to_six_months(self, mock_sleep, mock_boto_client,
                                   mock_ce_call, mock_write):
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            'Credentials': {'AccessKeyId': 'A', 'SecretAccessKey': 'S', 'SessionToken': 'T'}
        }

        # All calls succeed with empty data
        mock_ce_call.return_value = {'ResultsByTime': [{'TimePeriod': {'Start': '2024-01-01', 'End': '2024-02-01'}, 'Groups': []}]}

        months = ['2024-01', '2024-02', '2024-03', '2024-04',
                  '2024-05', '2024-06', '2024-07', '2024-08']

        # This should only process 6 months but since all return empty groups,
        # no records are created and all months "succeed" with 0 records
        # Actually with empty groups, synced_months will be populated but no records
        # Since no records are written, the function still returns success
        result = sync_invoice_data('user@example.com', '123456789012', months)

        # Should only process first 6 months
        assert len(result['synced_months']) <= 6


class TestWriteRecordsToDynamodb:
    """Tests for _write_records_to_dynamodb function."""

    @patch('invoice_sync.boto3.resource')
    @patch('invoice_sync.time.sleep')
    def test_writes_records_in_batches(self, mock_sleep, mock_dynamodb):
        mock_table = MagicMock()
        mock_dynamodb.return_value.Table.return_value = mock_table
        mock_writer = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_writer)
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)

        records = [
            {'pk': 'user@test.com#123456789012', 'sk': '2024-01#EC2', 'cost': Decimal('100.00')},
            {'pk': 'user@test.com#123456789012', 'sk': '2024-01#S3', 'cost': Decimal('25.50')},
        ]

        _write_records_to_dynamodb(records)

        assert mock_writer.put_item.call_count == 2


class TestInvoiceSyncError:
    """Tests for InvoiceSyncError exception class."""

    def test_error_attributes(self):
        err = InvoiceSyncError('Test error', status_code=403, error_type='AccessDenied')
        assert str(err) == 'Test error'
        assert err.message == 'Test error'
        assert err.status_code == 403
        assert err.error_type == 'AccessDenied'

    def test_default_attributes(self):
        err = InvoiceSyncError('Generic error')
        assert err.status_code == 500
        assert err.error_type == 'SyncError'
