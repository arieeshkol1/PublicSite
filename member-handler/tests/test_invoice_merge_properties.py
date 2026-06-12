"""Property-based tests for forecast merge/supersede/staleness logic in
invoice_drilldown.

Covers design Properties 11 (real precedence), 12 (issuer derivation),
17 (record-type discriminator + staleness). The DynamoDB cache layer and the
Forecast Engine compute step are mocked so the merge logic is tested in
isolation.
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

from hypothesis import given, settings, strategies as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import invoice_drilldown as idd  # noqa: E402

RUNS = 100
NOW = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)  # in forecast window
CURRENT_MONTH = '2026-06'


def _real(period, issuer='Amazon Web Services'):
    return {'invoiceId': f'{period}-monthly', 'issuer': issuer,
            'period': period, 'paymentStatus': 'paid', 'totalAmount': 100.0}


# ─── Property 12: Forecast issuer derivation ──────────────────────────────────

@given(
    issuers=st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=6),
)
@settings(max_examples=RUNS)
def test_property12_latest_real_issuer(issuers):
    # Build real invoices with increasing periods; last one is most recent.
    items = []
    for i, iss in enumerate(issuers):
        items.append(_real(f'2026-{i + 1:02d}', issuer=iss))
    most_recent = sorted(items, key=lambda x: x['period'], reverse=True)[0]
    assert idd._latest_real_issuer(items) == most_recent['issuer']


def test_property12_no_real_invoice_returns_none():
    assert idd._latest_real_issuer([]) is None


# ─── Property 11: real precedence (supersession) ──────────────────────────────

@settings(max_examples=RUNS)
@given(has_cached=st.booleans())
def test_property11_real_supersedes_forecast(has_cached):
    items = [_real(CURRENT_MONTH), _real('2026-05')]
    cached = {'forecastMonth': CURRENT_MONTH} if has_cached else None
    with patch.object(idd, '_read_forecast_record', return_value=cached), \
         patch.object(idd, '_delete_forecast_record') as mock_del, \
         patch.object(idd, '_write_forecast_record') as mock_write, \
         patch('invoice_forecast.compute_forecast') as mock_compute:
        forecast, unavailable = idd._get_or_refresh_forecast(
            'm@e.com', '123456789012', 'aws', items, now=NOW)
    assert forecast is None
    assert unavailable is False
    mock_compute.assert_not_called()
    mock_write.assert_not_called()
    if has_cached:
        mock_del.assert_called_once()


# ─── Property 17: record-type discriminator + staleness ───────────────────────

def test_property17_fresh_cache_returned_without_recompute():
    items = [_real('2026-05')]
    cached = {'forecastMonth': CURRENT_MONTH, 'recordType': 'forecast',
              'invoiceId': 'Forecast-2026-06', 'paymentStatus': 'Forecast'}
    with patch.object(idd, '_read_forecast_record', return_value=cached), \
         patch.object(idd, '_delete_forecast_record'), \
         patch('invoice_forecast.compute_forecast') as mock_compute:
        forecast, unavailable = idd._get_or_refresh_forecast(
            'm@e.com', '123456789012', 'aws', items, now=NOW)
    assert forecast == cached
    assert unavailable is False
    mock_compute.assert_not_called()


def test_property17_stale_cache_recomputed_and_replaced():
    items = [_real('2026-05')]
    stale = {'forecastMonth': '2026-05', 'recordType': 'forecast'}
    fresh = {'forecastMonth': CURRENT_MONTH, 'invoiceId': 'Forecast-2026-06',
             'period': CURRENT_MONTH, 'paymentStatus': 'Forecast'}
    with patch.object(idd, '_read_forecast_record', return_value=stale), \
         patch.object(idd, '_delete_forecast_record') as mock_del, \
         patch.object(idd, '_write_forecast_record') as mock_write, \
         patch('invoice_forecast.compute_forecast', return_value=fresh):
        forecast, unavailable = idd._get_or_refresh_forecast(
            'm@e.com', '123456789012', 'aws', items, now=NOW)
    assert forecast == fresh
    assert unavailable is False
    mock_del.assert_called_once_with('m@e.com', '123456789012', '2026-05')
    mock_write.assert_called_once()


def test_property17_stale_recompute_failure_signals_unavailable():
    items = [_real('2026-05')]
    stale = {'forecastMonth': '2026-05', 'recordType': 'forecast'}
    with patch.object(idd, '_read_forecast_record', return_value=stale), \
         patch.object(idd, '_delete_forecast_record') as mock_del, \
         patch('invoice_forecast.compute_forecast', side_effect=RuntimeError('CE down')):
        forecast, unavailable = idd._get_or_refresh_forecast(
            'm@e.com', '123456789012', 'aws', items, now=NOW)
    assert forecast is None
    assert unavailable is True
    mock_del.assert_called_once_with('m@e.com', '123456789012', '2026-05')


def test_property17_non_aws_no_forecast():
    items = [_real('2026-05')]
    with patch.object(idd, '_read_forecast_record', return_value=None), \
         patch.object(idd, '_delete_forecast_record'), \
         patch('invoice_forecast.compute_forecast') as mock_compute:
        forecast, unavailable = idd._get_or_refresh_forecast(
            'm@e.com', '123456789012', 'openai', items, now=NOW)
    assert forecast is None
    mock_compute.assert_not_called()
