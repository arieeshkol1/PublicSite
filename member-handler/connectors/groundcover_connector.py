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

        Note: GroundCover's API requires a sessionId for data queries.
        If the API returns an error or no data, returns empty list gracefully.
        """
        token = auth_context.get('api_key', '')
        from datetime import datetime, timezone, timedelta

        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

            url = GROUNDCOVER_API_BASE
            headers = {
                'Authorization': f'Bearer {token}',
                'X-Backend-Id': 'groundcover',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            }

            # Query GroundCover for AI services data with a short timeout
            # to avoid Lambda timeout (GroundCover may hang if sessionId not provided)
            payload = json.dumps({
                "conditions": [],
                "limit": 100,
                "order": "desc",
                "skip": 0,
                "sortBy": "rps",
                "sources": [],
            }).encode('utf-8')

            try:
                req = urllib.request.Request(url, method='POST', headers=headers, data=payload)
                resp = urllib.request.urlopen(req, timeout=8)  # Short timeout
                raw_data = resp.read().decode('utf-8')
                data = json.loads(raw_data)
            except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
                logger.warning(f"GroundCover API call failed: {e}")
                return []
            except Exception as e:
                logger.warning(f"GroundCover API unexpected error: {e}")
                return []

            # Parse the response - GroundCover returns service-level data
            # We look for any AI-related services that have cost/token info
            services = data if isinstance(data, list) else data.get('services', data.get('data', data.get('results', [])))
            if not isinstance(services, list):
                logger.info(f"GroundCover returned non-list data type: {type(data).__name__}")
                return []

            if not services:
                logger.info("GroundCover returned empty services list")
                return []

            # Build buckets from service data
            day_count = max(1, (end_dt - start_dt).days)
            all_results = []

            for svc in services:
                if not isinstance(svc, dict):
                    continue

                # Extract model/service name from various possible fields
                model_name = (
                    svc.get('model') or
                    svc.get('gen_ai.request.model') or
                    svc.get('name') or
                    svc.get('serviceName') or
                    svc.get('service_name') or
                    'anthropic-unknown'
                )

                # Extract cost
                cost = 0.0
                for cost_field in ('cost', 'totalCost', 'total_cost', 'gc.llm_cost'):
                    if svc.get(cost_field):
                        try:
                            cost = float(svc[cost_field])
                            break
                        except (TypeError, ValueError):
                            pass

                # Extract tokens
                input_tokens = 0
                for t_field in ('input_tokens', 'gen_ai.usage.input_tokens', 'inputTokens'):
                    if svc.get(t_field):
                        try:
                            input_tokens = int(svc[t_field])
                            break
                        except (TypeError, ValueError):
                            pass

                output_tokens = 0
                for t_field in ('output_tokens', 'gen_ai.usage.output_tokens', 'outputTokens'):
                    if svc.get(t_field):
                        try:
                            output_tokens = int(svc[t_field])
                            break
                        except (TypeError, ValueError):
                            pass

                if cost > 0 or input_tokens > 0 or output_tokens > 0:
                    daily_cost = cost / day_count
                    daily_input = input_tokens // day_count
                    daily_output = output_tokens // day_count

                    for day_offset in range(day_count):
                        day_ts = int((start_dt + timedelta(days=day_offset)).timestamp())
                        all_results.append({
                            'day_ts': day_ts,
                            'amount': {'value': round(daily_cost, 6), 'currency': 'usd'},
                            'line_item': model_name,
                            'input_tokens': daily_input,
                            'output_tokens': daily_output,
                        })

            if not all_results:
                return []

            # Group by day into buckets
            by_day = {}
            for r in all_results:
                day_ts = r.pop('day_ts')
                by_day.setdefault(day_ts, []).append(r)

            buckets = []
            for day_ts in sorted(by_day.keys()):
                buckets.append({
                    'object': 'bucket',
                    'start_time': day_ts,
                    'end_time': day_ts + 86400,
                    'results': by_day[day_ts],
                })

            return buckets

        except Exception as e:
            logger.warning(f"GroundCover get_cost_data failed: {type(e).__name__}: {e}")
            return []


# Auto-register when module is imported
register_connector('groundcover', GroundcoverConnector, vendor_type='ai_vendor')
