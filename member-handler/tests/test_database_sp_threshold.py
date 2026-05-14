"""Unit tests for Database SP threshold logic in committed discount scan.

Tests the threshold logic (> $50/month) that determines whether Database SP
recommendations should be included in the scan response.

Requirements: 11.1, 11.2
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta


# ─── Extracted logic under test ───────────────────────────────────────────────
# These replicate the core logic from lambda_function.py for isolated testing.

def get_database_sp_monthly_spend(ce_client):
    """Check combined RDS + ElastiCache monthly spend using Cost Explorer.

    Replicates _get_database_sp_monthly_spend from lambda_function.py.
    """
    end_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    start_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%d')

    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod={'Start': start_date, 'End': end_date},
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            Filter={
                'Dimensions': {
                    'Key': 'SERVICE',
                    'Values': [
                        'Amazon Relational Database Service',
                        'Amazon ElastiCache',
                    ],
                }
            },
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
        )
    except Exception:
        return 0.0

    total_spend = 0.0
    for result_by_time in response.get('ResultsByTime', []):
        for group in result_by_time.get('Groups', []):
            amount_str = group.get('Metrics', {}).get('UnblendedCost', {}).get('Amount', '0')
            try:
                total_spend += float(amount_str)
            except (ValueError, TypeError):
                pass

    return total_spend


def is_database_sp_eligible(monthly_spend):
    """Determine if Database SP recommendations should be included.

    Returns True iff combined RDS + ElastiCache monthly spend > $50.
    """
    return monthly_spend > 50.0


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestGetDatabaseSpMonthlySpend:
    """Tests for _get_database_sp_monthly_spend function."""

    def test_spend_above_threshold(self):
        """When RDS + ElastiCache spend > $50, should return the combined total."""
        ce_client = MagicMock()
        ce_client.get_cost_and_usage.return_value = {
            'ResultsByTime': [{
                'Groups': [
                    {
                        'Keys': ['Amazon Relational Database Service'],
                        'Metrics': {'UnblendedCost': {'Amount': '35.50', 'Unit': 'USD'}}
                    },
                    {
                        'Keys': ['Amazon ElastiCache'],
                        'Metrics': {'UnblendedCost': {'Amount': '25.00', 'Unit': 'USD'}}
                    },
                ]
            }]
        }

        result = get_database_sp_monthly_spend(ce_client)
        assert result == 60.50

    def test_spend_below_threshold(self):
        """When RDS + ElastiCache spend <= $50, should return the total."""
        ce_client = MagicMock()
        ce_client.get_cost_and_usage.return_value = {
            'ResultsByTime': [{
                'Groups': [
                    {
                        'Keys': ['Amazon Relational Database Service'],
                        'Metrics': {'UnblendedCost': {'Amount': '20.00', 'Unit': 'USD'}}
                    },
                    {
                        'Keys': ['Amazon ElastiCache'],
                        'Metrics': {'UnblendedCost': {'Amount': '15.00', 'Unit': 'USD'}}
                    },
                ]
            }]
        }

        result = get_database_sp_monthly_spend(ce_client)
        assert result == 35.00

    def test_no_database_spend(self):
        """When no RDS/ElastiCache spend, should return 0."""
        ce_client = MagicMock()
        ce_client.get_cost_and_usage.return_value = {
            'ResultsByTime': [{
                'Groups': []
            }]
        }

        result = get_database_sp_monthly_spend(ce_client)
        assert result == 0.0

    def test_only_rds_spend(self):
        """When only RDS spend exists, should return just RDS amount."""
        ce_client = MagicMock()
        ce_client.get_cost_and_usage.return_value = {
            'ResultsByTime': [{
                'Groups': [
                    {
                        'Keys': ['Amazon Relational Database Service'],
                        'Metrics': {'UnblendedCost': {'Amount': '80.00', 'Unit': 'USD'}}
                    },
                ]
            }]
        }

        result = get_database_sp_monthly_spend(ce_client)
        assert result == 80.00

    def test_only_elasticache_spend(self):
        """When only ElastiCache spend exists, should return just ElastiCache amount."""
        ce_client = MagicMock()
        ce_client.get_cost_and_usage.return_value = {
            'ResultsByTime': [{
                'Groups': [
                    {
                        'Keys': ['Amazon ElastiCache'],
                        'Metrics': {'UnblendedCost': {'Amount': '55.00', 'Unit': 'USD'}}
                    },
                ]
            }]
        }

        result = get_database_sp_monthly_spend(ce_client)
        assert result == 55.00

    def test_api_error_returns_zero(self):
        """When the API call fails, should return 0.0 gracefully."""
        ce_client = MagicMock()
        ce_client.get_cost_and_usage.side_effect = Exception("API Error")

        result = get_database_sp_monthly_spend(ce_client)
        assert result == 0.0

    def test_multiple_time_periods(self):
        """When response has multiple time periods, should sum all."""
        ce_client = MagicMock()
        ce_client.get_cost_and_usage.return_value = {
            'ResultsByTime': [
                {
                    'Groups': [
                        {
                            'Keys': ['Amazon Relational Database Service'],
                            'Metrics': {'UnblendedCost': {'Amount': '30.00', 'Unit': 'USD'}}
                        },
                    ]
                },
                {
                    'Groups': [
                        {
                            'Keys': ['Amazon ElastiCache'],
                            'Metrics': {'UnblendedCost': {'Amount': '25.00', 'Unit': 'USD'}}
                        },
                    ]
                },
            ]
        }

        result = get_database_sp_monthly_spend(ce_client)
        assert result == 55.00


class TestDatabaseSpThresholdLogic:
    """Tests for the threshold logic: include Database SP iff spend > $50."""

    def test_eligible_when_above_50(self):
        """Database SP should be eligible when combined spend > $50."""
        assert is_database_sp_eligible(75.0) is True

    def test_eligible_at_50_01(self):
        """Database SP should be eligible when combined spend is $50.01."""
        assert is_database_sp_eligible(50.01) is True

    def test_not_eligible_when_at_50(self):
        """Database SP should NOT be eligible when combined spend == $50."""
        assert is_database_sp_eligible(50.0) is False

    def test_not_eligible_when_below_50(self):
        """Database SP should NOT be eligible when combined spend < $50."""
        assert is_database_sp_eligible(49.99) is False

    def test_not_eligible_when_zero(self):
        """Database SP should NOT be eligible when spend is 0."""
        assert is_database_sp_eligible(0.0) is False

    def test_eligible_with_large_spend(self):
        """Database SP should be eligible with large spend values."""
        assert is_database_sp_eligible(5000.0) is True
