"""GroundCover connector — Anthropic AI usage monitoring via GroundCover."""
import json
import logging

from .base_connector import ProviderConnector
from . import register_connector

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Constants
GROUNDCOVER_API_BASE = "https://api.groundcover.com"
REQUEST_TIMEOUT = 10  # seconds
VALID_TOKEN_PREFIX = 'gcsa_'
MIN_TOKEN_LENGTH = 20
MAX_TOKEN_LENGTH = 200


def validate_groundcover_token_format(token: str) -> dict:
    """Validate GroundCover token format without making an external API call.

    Valid tokens must start with 'gcsa_' and have a total length between 20
    and 200 characters inclusive.

    Args:
        token: The API token string to validate.

    Returns:
        dict: {'valid': True} if format is correct, or
              {'valid': False, 'error': '<reason>'} if format is invalid.
    """
    if not isinstance(token, str):
        return {'valid': False, 'error': 'Token must be a string.'}

    if not token:
        return {'valid': False, 'error': 'Token must not be empty.'}

    if not token.startswith(VALID_TOKEN_PREFIX):
        return {
            'valid': False,
            'error': 'Invalid token format. Token must start with "gcsa_".'
        }

    token_length = len(token)
    if token_length < MIN_TOKEN_LENGTH or token_length > MAX_TOKEN_LENGTH:
        return {
            'valid': False,
            'error': (
                f'Invalid token length ({token_length} characters). '
                f'Must be between {MIN_TOKEN_LENGTH} and {MAX_TOKEN_LENGTH}.'
            )
        }

    return {'valid': True}


class GroundcoverConnector(ProviderConnector):
    """GroundCover AI vendor connector using Bearer token auth."""

    def authenticate(self, credentials: dict) -> dict:
        """Validate token format and return auth context.

        credentials should contain:
          - api_key: The gcsa_ token (plaintext, already decrypted)

        Returns:
            Auth context dict with 'api_key'
        """
        api_key = credentials.get('api_key', '')
        validation = validate_groundcover_token_format(api_key)
        if not validation['valid']:
            from .base_connector import AuthenticationError
            raise AuthenticationError(validation['error'], provider='groundcover')
        return {'api_key': api_key}

    def test_connection(self, auth_context: dict, account_id: str) -> dict:
        """Validate GroundCover credentials.

        GroundCover API requires a sessionId for all data endpoints, so we
        cannot perform a lightweight connectivity check without an active
        session. Instead we validate the token format — if the token passes
        format validation, the connection is accepted. Real connectivity is
        verified on first data fetch.

        Args:
            auth_context: Dict containing 'api_key' (gcsa_ token)
            account_id: Account identifier

        Returns:
            Dict with keys: success (bool), message (str)
        """
        token = auth_context.get('api_key', '')
        validation = validate_groundcover_token_format(token)
        if not validation['valid']:
            return {
                'success': False,
                'message': validation['error'],
            }
        return {
            'success': True,
            'message': 'GroundCover token validated and connection saved.',
        }

    def get_cost_data(self, auth_context: dict, account_id: str,
                      start_date: str, end_date: str, **kwargs) -> list:
        """Fetch AI cost data from GroundCover's services API.

        Queries the GroundCover API for services with AI/LLM traffic data.
        Returns data in the same bucket format as OpenAI connector so the
        existing cost_normalizer and dashboard can consume it.

        Args:
            auth_context: Dict containing 'api_key' (gcsa_ token)
            account_id: Account identifier
            start_date: Start date as YYYY-MM-DD (inclusive)
            end_date: End date as YYYY-MM-DD (exclusive)

        Returns:
            List of bucket dicts matching OpenAI format:
            [{'start_time': epoch, 'results': [{'amount': {'value': X, 'currency': 'usd'},
              'line_item': 'model-name', 'input_tokens': N, 'output_tokens': N}]}]
            Returns [] on any error (never raises).
        """
        token = auth_context.get('api_key', '')
        from datetime import datetime, timezone, timedelta

        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

            # GroundCover services endpoint returns AI service data including
            # model usage, tokens, and cost when AI observability is enabled.
            # We query with conditions filtering for gen_ai span type.
            url = GROUNDCOVER_API_BASE
            headers = {
                'Authorization': f'Bearer {token}',
                'X-Backend-Id': 'groundcover',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            }

            # Query GroundCover for AI services data
            # The API returns service-level metrics including AI model calls
            payload = json.dumps({
                "conditions": [
                    {"key": "span_type", "operator": "eq", "value": "gen_ai"}
                ],
                "limit": 500,
                "order": "desc",
                "skip": 0,
                "sortBy": "rps",
                "sources": [],
                "startTime": start_dt.isoformat(),
                "endTime": end_dt.isoformat(),
            }).encode('utf-8')

            try:
                req = urllib.request.Request(url, method='POST', headers=headers, data=payload)
                resp = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
                data = json.loads(resp.read().decode('utf-8'))
            except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
                logger.warning(f"GroundCover services API failed: {e}")
                # Try alternative: query without conditions (get all services)
                payload_all = json.dumps({
                    "conditions": [],
                    "limit": 200,
                    "order": "desc",
                    "skip": 0,
                    "sortBy": "rps",
                    "sources": [],
                    "startTime": start_dt.isoformat(),
                    "endTime": end_dt.isoformat(),
                }).encode('utf-8')
                try:
                    req2 = urllib.request.Request(url, method='POST', headers=headers, data=payload_all)
                    resp2 = urllib.request.urlopen(req2, timeout=REQUEST_TIMEOUT)
                    data = json.loads(resp2.read().decode('utf-8'))
                except Exception as e2:
                    logger.warning(f"GroundCover fallback API also failed: {e2}")
                    return []

            # Parse the GroundCover response into OpenAI-compatible bucket format.
            # GroundCover returns services with AI metrics. We need to transform
            # this into daily buckets with cost and token data.
            all_buckets = []
            services = data if isinstance(data, list) else data.get('services', data.get('data', data.get('results', [])))
            if not isinstance(services, list):
                services = []

            # Group service data into a single bucket per day
            # GroundCover may return aggregated data — we split by day if possible
            day_count = (end_dt - start_dt).days or 1
            bucket_start = int(start_dt.timestamp())

            # Build a single bucket covering the full range (will be normalized later)
            results = []
            for svc in services:
                if not isinstance(svc, dict):
                    continue

                # Extract model/service name
                model_name = (
                    svc.get('model') or
                    svc.get('gen_ai.request.model') or
                    svc.get('name') or
                    svc.get('serviceName') or
                    svc.get('service_name') or
                    'anthropic-unknown'
                )

                # Extract cost (GroundCover calculates cost per span)
                cost = float(
                    svc.get('cost') or
                    svc.get('totalCost') or
                    svc.get('total_cost') or
                    svc.get('gc.llm_cost') or
                    0
                )

                # Extract tokens
                input_tokens = int(
                    svc.get('input_tokens') or
                    svc.get('gen_ai.usage.input_tokens') or
                    svc.get('inputTokens') or
                    0
                )
                output_tokens = int(
                    svc.get('output_tokens') or
                    svc.get('gen_ai.usage.output_tokens') or
                    svc.get('outputTokens') or
                    0
                )

                # Extract request count
                requests = int(
                    svc.get('count') or
                    svc.get('requestCount') or
                    svc.get('rps', 0) * 86400  # rps * seconds in a day as fallback
                    if svc.get('rps') else 0
                )

                if cost > 0 or input_tokens > 0 or output_tokens > 0:
                    # Distribute evenly across days for the date range
                    daily_cost = cost / day_count if day_count > 0 else cost
                    daily_input = input_tokens // day_count if day_count > 0 else input_tokens
                    daily_output = output_tokens // day_count if day_count > 0 else output_tokens

                    for day_offset in range(day_count):
                        day_ts = int((start_dt + timedelta(days=day_offset)).timestamp())
                        results.append({
                            'day_ts': day_ts,
                            'object': 'organization.costs.result',
                            'amount': {'value': round(daily_cost, 6), 'currency': 'usd'},
                            'line_item': model_name,
                            'input_tokens': daily_input,
                            'output_tokens': daily_output,
                        })

            # Group results by day timestamp into buckets
            by_day = {}
            for r in results:
                day_ts = r.pop('day_ts')
                by_day.setdefault(day_ts, []).append(r)

            for day_ts in sorted(by_day.keys()):
                all_buckets.append({
                    'object': 'bucket',
                    'start_time': day_ts,
                    'end_time': day_ts + 86400,
                    'results': by_day[day_ts],
                })

            return all_buckets

        except Exception as e:
            logger.warning(f"GroundCover get_cost_data failed: {type(e).__name__}: {e}")
            return []


# Auto-register when module is imported
register_connector('groundcover', GroundcoverConnector, vendor_type='ai_vendor')
