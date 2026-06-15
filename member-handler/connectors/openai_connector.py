"""OpenAI connector — API key authentication + Usage API."""
import json
import logging
import time

from .base_connector import ProviderConnector, AuthenticationError, CostRetrievalError
from .kms_helpers import decrypt_credential
from .openai_kms import encrypt_openai_key, decrypt_openai_key, EncryptionError, DecryptionError
from . import register_connector

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Constants
OPENAI_BASE_URL = "https://api.openai.com/v1"
REQUEST_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 1.0  # seconds — used for on-demand calls
NIGHTLY_SYNC_BACKOFF_BASE = 2.0  # seconds — used for nightly sync (per design)

# Valid API key prefix — any key starting with 'sk-' is accepted
VALID_KEY_PREFIXES = ('sk-',)
MIN_KEY_LENGTH = 20
MAX_KEY_LENGTH = 200


def validate_openai_key_format(api_key: str) -> dict:
    """Validate OpenAI API key format without making an external API call.

    Valid keys must start with 'sk-' and have a total length between 20
    and 200 characters inclusive.

    Args:
        api_key: The API key string to validate.

    Returns:
        dict: {'valid': True} if format is correct, or
              {'valid': False, 'error': '<reason>'} if format is invalid.
    """
    if not isinstance(api_key, str):
        return {'valid': False, 'error': 'API key must be a string.'}

    if not api_key:
        return {'valid': False, 'error': 'API key must not be empty.'}

    if not api_key.startswith(VALID_KEY_PREFIXES):
        return {
            'valid': False,
            'error': 'Invalid API key format. Key must start with "sk-".'
        }

    key_length = len(api_key)
    if key_length < MIN_KEY_LENGTH or key_length > MAX_KEY_LENGTH:
        return {
            'valid': False,
            'error': (
                f'Invalid API key length ({key_length} characters). '
                f'Key must be between {MIN_KEY_LENGTH} and {MAX_KEY_LENGTH} characters.'
            )
        }

    return {'valid': True}


class OpenAIConnector(ProviderConnector):
    """OpenAI AI vendor connector using API key and Usage API."""

    def authenticate(self, credentials: dict) -> dict:
        """Decrypt API key via KMS and validate format.

        credentials should contain:
          - encrypted_api_key: KMS-encrypted base64 API key
          - member_email: member's email (for KMS encryption context)
          - account_id: OpenAI account identifier (for KMS encryption context)
          - org_name: optional organization name

        Returns:
            Auth context dict with 'api_key' and 'org_name'

        Raises:
            AuthenticationError: If key format is invalid or decryption fails
        """
        encrypted_key = credentials.get('encrypted_api_key', '')
        member_email = credentials.get('member_email', '')
        account_id = credentials.get('account_id', '')
        org_name = credentials.get('org_name', '')

        if not encrypted_key:
            raise AuthenticationError(
                'No API key provided', provider='openai'
            )

        # Decrypt the stored API key using encryption context
        try:
            if member_email and account_id:
                # Use context-aware decryption (preferred path)
                api_key = decrypt_openai_key(encrypted_key, member_email, account_id)
            else:
                # Fallback for legacy records without context
                api_key = decrypt_credential(encrypted_key)
        except (DecryptionError, RuntimeError):
            raise AuthenticationError(
                'Credentials inaccessible. Please re-add your OpenAI connection.',
                provider='openai'
            )

        # Validate key format: must start with sk- and be 20-200 chars
        validation = validate_openai_key_format(api_key)
        if not validation['valid']:
            raise AuthenticationError(
                validation['error'],
                provider='openai'
            )

        return {
            'api_key': api_key,
            'org_name': org_name,
        }

    def test_connection(self, auth_context: dict, account_id: str) -> dict:
        """Test connectivity by calling GET /v1/models with Bearer token.

        Args:
            auth_context: Result from authenticate() containing 'api_key'
            account_id: OpenAI org/project identifier

        Returns:
            Dict with keys: success (bool), message (str), details (dict)
        """
        api_key = auth_context.get('api_key', '')
        url = f"{OPENAI_BASE_URL}/models"

        try:
            req = urllib.request.Request(
                url,
                method='GET',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                }
            )
            response = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
            data = json.loads(response.read().decode('utf-8'))

            models = [m.get('id', '') for m in data.get('data', [])]
            return {
                'success': True,
                'message': 'OpenAI connection successful',
                'details': {'models': models}
            }
        except urllib.error.HTTPError as e:
            status_code = e.code
            if status_code == 401:
                return {
                    'success': False,
                    'message': 'API key is invalid or has been revoked.',
                    'details': {'status_code': 401}
                }
            elif status_code == 403:
                # 403 from /v1/models may just mean the key doesn't have model-listing
                # permission. Admin keys only have billing/org access. Try the org costs
                # endpoint (what admin keys are designed for), then chat completions.
                import time as _time
                _start_ts = int(_time.time()) - (30 * 86400)  # 30 days ago
                _fallback_endpoints = [
                    f"{OPENAI_BASE_URL.replace('/v1', '')}/v1/organization/costs?start_time={_start_ts}",
                    f"{OPENAI_BASE_URL}/chat/completions",
                ]
                for _fb_url in _fallback_endpoints:
                    try:
                        if 'chat/completions' in _fb_url:
                            _fb_body = json.dumps({
                                'model': 'gpt-4o-mini',
                                'messages': [{'role': 'user', 'content': 'ping'}],
                                'max_tokens': 1,
                            }).encode('utf-8')
                            _fb_req = urllib.request.Request(
                                _fb_url, method='POST',
                                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                                data=_fb_body,
                            )
                        else:
                            _fb_req = urllib.request.Request(
                                _fb_url, method='GET',
                                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                            )
                        urllib.request.urlopen(_fb_req, timeout=REQUEST_TIMEOUT)
                        return {
                            'success': True,
                            'message': 'OpenAI connection successful',
                            'details': {'models': [], 'note': 'Key verified via organization API'}
                        }
                    except urllib.error.HTTPError as _fb_err:
                        if _fb_err.code in (401, 403):
                            continue  # Try next fallback
                        # Other errors (429, 500) mean the key IS valid but rate-limited/server error
                        return {
                            'success': True,
                            'message': 'OpenAI connection successful (key accepted)',
                            'details': {'models': []}
                        }
                    except Exception:
                        continue
                # All fallbacks failed
                return {
                    'success': False,
                    'message': 'API key does not have access to OpenAI APIs. Please check key permissions.',
                    'details': {'status_code': 403}
                }
            elif status_code == 429:
                return {
                    'success': False,
                    'message': 'OpenAI API rate limited. Please retry after 60 seconds.',
                    'details': {'status_code': 429}
                }
            else:
                return {
                    'success': False,
                    'message': f'OpenAI API returned error (HTTP {status_code}). Please retry.',
                    'details': {'status_code': status_code}
                }
        except (urllib.error.URLError, OSError) as e:
            return {
                'success': False,
                'message': 'OpenAI API is temporarily unavailable. Please retry.',
                'details': {'error': str(e)}
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Connection test failed: {str(e)[:150]}',
                'details': {'error': str(e)[:200]}
            }

    def get_cost_data(self, auth_context: dict, account_id: str,
                      start_date: str, end_date: str,
                      retry_base_delay: float = DEFAULT_BACKOFF_BASE) -> list:
        """Retrieve usage/cost data from OpenAI Usage API with retry logic.

        Retry behaviour (per Requirements 14.3–14.7):
        - HTTP 429 with Retry-After header: wait specified duration, retry up to 3 times
        - HTTP 429 without Retry-After: exponential backoff from retry_base_delay, up to 3 attempts
        - HTTP 5xx: retry up to 3 times with exponential backoff
        - HTTP 401: do NOT retry, raise error indicating key may be revoked
          (caller should update connection status to 'failed')
        - Other HTTP errors: do NOT retry, raise error with status code,
          connection status left unchanged
        - After exhausting retries: raise error indicating API is temporarily unavailable
          (caller should update connection status to 'failed')

        Args:
            auth_context: Result from authenticate() containing 'api_key'
            account_id: OpenAI org/project identifier
            start_date: ISO date string (YYYY-MM-DD)
            end_date: ISO date string (YYYY-MM-DD)
            retry_base_delay: Base delay in seconds for exponential backoff.
                Defaults to 1s for on-demand calls. Nightly sync should pass
                NIGHTLY_SYNC_BACKOFF_BASE (2s) per design.

        Returns:
            List of raw usage records from OpenAI API

        Raises:
            CostRetrievalError: If retrieval fails after retries.
                The error's `mark_connection_failed` attribute indicates whether
                the caller should update the connection status to 'failed'.
        """
        api_key = auth_context.get('api_key', '')

        # Convert date strings to epoch timestamps for the Organization Costs API
        # Format: /v1/organization/costs?start_time=EPOCH&end_time=EPOCH
        import calendar
        from datetime import datetime as _dt
        _start_epoch = int(calendar.timegm(_dt.strptime(start_date, '%Y-%m-%d').timetuple()))
        _end_epoch = int(calendar.timegm(_dt.strptime(end_date, '%Y-%m-%d').timetuple()))

        # Primary: Organization Costs API with line_item and project breakdown (works with admin keys)
        url = f"{OPENAI_BASE_URL}/organization/costs?start_time={_start_epoch}&end_time={_end_epoch}&group_by=line_item&group_by=project_id"
        # Fallback: Legacy usage API (works with project keys)
        legacy_url = f"{OPENAI_BASE_URL}/usage?start_date={start_date}&end_date={end_date}"

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(
                    url,
                    method='GET',
                    headers={
                        'Authorization': f'Bearer {api_key}',
                        'Content-Type': 'application/json',
                    }
                )
                response = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
                data = json.loads(response.read().decode('utf-8'))

                # Handle Organization Costs API response format:
                # {"object": "page", "data": [{"start_time": N, "end_time": N, "results": [{"amount": {"value": X, "currency": "usd"}, "line_item": "model-name"}]}]}
                if data.get('object') == 'page' and 'data' in data:
                    # Paginated organization costs response — flatten all pages
                    all_results = data.get('data', [])
                    # Fetch additional pages (max 5 to support 30d range)
                    _page_count = 1
                    _max_pages = 5
                    while data.get('has_more') and data.get('next_page') and _page_count < _max_pages:
                        _next_url = f"{OPENAI_BASE_URL}/organization/costs?start_time={_start_epoch}&end_time={_end_epoch}&group_by=line_item&group_by=project_id&page={data['next_page']}"
                        _next_req = urllib.request.Request(
                            _next_url, method='GET',
                            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
                        )
                        _next_resp = urllib.request.urlopen(_next_req, timeout=REQUEST_TIMEOUT)
                        data = json.loads(_next_resp.read().decode('utf-8'))
                        all_results.extend(data.get('data', []))
                        _page_count += 1

                    # Also fetch token usage from /v1/organization/usage/completions (provides input/output token counts)
                    try:
                        _usage_url = f"{OPENAI_BASE_URL}/organization/usage/completions?start_time={_start_epoch}&end_time={_end_epoch}&group_by=model&bucket_width=1d"
                        _usage_req = urllib.request.Request(
                            _usage_url, method='GET',
                            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
                        )
                        _usage_resp = urllib.request.urlopen(_usage_req, timeout=REQUEST_TIMEOUT)
                        _usage_data = json.loads(_usage_resp.read().decode('utf-8'))
                        # Paginate usage endpoint (max 5 pages to cover 30 days)
                        _all_usage_buckets = _usage_data.get('data', []) if _usage_data.get('object') == 'page' else []
                        _usage_page = 1
                        while _usage_data.get('has_more') and _usage_data.get('next_page') and _usage_page < 5:
                            _next_usage_url = f"{OPENAI_BASE_URL}/organization/usage/completions?start_time={_start_epoch}&end_time={_end_epoch}&group_by=model&bucket_width=1d&page={_usage_data['next_page']}"
                            _next_usage_req = urllib.request.Request(
                                _next_usage_url, method='GET',
                                headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
                            )
                            _next_usage_resp = urllib.request.urlopen(_next_usage_req, timeout=REQUEST_TIMEOUT)
                            _usage_data = json.loads(_next_usage_resp.read().decode('utf-8'))
                            _all_usage_buckets.extend(_usage_data.get('data', []))
                            _usage_page += 1

                        # Merge token data into cost buckets by matching start_time
                        if _all_usage_buckets:
                            _token_map = {}  # start_time -> {model -> {input_tokens, output_tokens}}
                            for bucket in _all_usage_buckets:
                                st = bucket.get('start_time')
                                for result in bucket.get('results', []):
                                    model = result.get('model') or result.get('line_item') or 'unknown'
                                    input_t = result.get('input_tokens', 0) or 0
                                    output_t = result.get('output_tokens', 0) or 0
                                    if st not in _token_map:
                                        _token_map[st] = {}
                                    if model not in _token_map[st]:
                                        _token_map[st][model] = {'input_tokens': 0, 'output_tokens': 0}
                                    _token_map[st][model]['input_tokens'] += input_t
                                    _token_map[st][model]['output_tokens'] += output_t
                            # Enrich cost buckets with token counts
                            for bucket in all_results:
                                st = bucket.get('start_time')
                                if st in _token_map:
                                    for result in bucket.get('results', []):
                                        line = result.get('line_item') or 'unknown'
                                        # Try exact match first, then partial match (costs use short names, usage uses full model IDs)
                                        matched = False
                                        if line in _token_map[st]:
                                            result['input_tokens'] = _token_map[st][line]['input_tokens']
                                            result['output_tokens'] = _token_map[st][line]['output_tokens']
                                            matched = True
                                        if not matched:
                                            # Try matching: model_key is prefix of cost line_item
                                            # e.g., model_key="gpt-5.1-2025-11-13" matches line="gpt-5.1-2025-11-13, input"
                                            for model_key, tokens in _token_map[st].items():
                                                if line and (model_key.lower() in line.lower() or line.lower().startswith(model_key.lower())):
                                                    result['input_tokens'] = tokens['input_tokens']
                                                    result['output_tokens'] = tokens['output_tokens']
                                                    break
                                # Also inject token-only records for models that appear in usage but not in costs
                                if st in _token_map:
                                    existing_lines = {(r.get('line_item') or '').lower() for r in bucket.get('results', [])}
                                    for model_key, tokens in _token_map[st].items():
                                        # Check if this model already matched any cost line_item
                                        already_matched = any(model_key.lower() in el for el in existing_lines if el)
                                        if not already_matched and (tokens['input_tokens'] > 0 or tokens['output_tokens'] > 0):
                                            bucket.get('results', []).append({
                                                'object': 'organization.usage.result',
                                                'amount': {'value': 0, 'currency': 'usd'},
                                                'line_item': model_key,
                                                'input_tokens': tokens['input_tokens'],
                                                'output_tokens': tokens['output_tokens'],
                                            })
                    except Exception as _usage_err:
                        logger.warning(f"Token usage fetch failed (non-fatal): {_usage_err}")

                    return all_results

                # Legacy /v1/usage response format
                return data.get('data', data.get('results', [data] if 'object' in data else []))

            except urllib.error.HTTPError as e:
                status_code = e.code
                last_error = e

                if status_code == 401:
                    # Invalid/revoked key — do NOT retry (Req 14.6)
                    err = CostRetrievalError(
                        'API key may have been revoked. Please re-add your OpenAI connection.',
                        provider='openai'
                    )
                    err.mark_connection_failed = True
                    raise err

                if status_code == 429:
                    # Rate limited — check Retry-After header (Req 14.3, 14.4)
                    retry_after = e.headers.get('Retry-After') if hasattr(e, 'headers') else None
                    if retry_after:
                        try:
                            wait_time = int(retry_after)
                        except (ValueError, TypeError):
                            wait_time = self._backoff_delay(attempt, base=retry_base_delay)
                    else:
                        # Exponential backoff (Req 14.4)
                        wait_time = self._backoff_delay(attempt, base=retry_base_delay)

                    if attempt < MAX_RETRIES - 1:
                        logger.info(
                            'OpenAI 429 on attempt %d/%d, waiting %.1fs before retry',
                            attempt + 1, MAX_RETRIES, wait_time
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        # Retries exhausted (Req 14.5)
                        err = CostRetrievalError(
                            'OpenAI Usage API is temporarily unavailable (rate limited). Please retry later.',
                            provider='openai'
                        )
                        err.mark_connection_failed = True
                        raise err

                if 500 <= status_code < 600:
                    # Server error — retry with backoff
                    if attempt < MAX_RETRIES - 1:
                        wait_time = self._backoff_delay(attempt, base=retry_base_delay)
                        logger.info(
                            'OpenAI %d on attempt %d/%d, waiting %.1fs before retry',
                            status_code, attempt + 1, MAX_RETRIES, wait_time
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        # Retries exhausted (Req 14.5)
                        err = CostRetrievalError(
                            f'OpenAI API server error (HTTP {status_code}). Please retry later.',
                            provider='openai'
                        )
                        err.mark_connection_failed = True
                        raise err

                # Other HTTP errors — for 403, try legacy endpoint before failing
                if status_code == 403 and url != legacy_url:
                    # Admin key might not have org costs access, try legacy usage API
                    logger.info('Organization Costs API returned 403, trying legacy /v1/usage endpoint')
                    url = legacy_url
                    continue

                # Other HTTP errors — do NOT retry, connection status unchanged (Req 14.7)
                err = CostRetrievalError(
                    f'OpenAI API returned HTTP {status_code}.',
                    provider='openai'
                )
                err.mark_connection_failed = False
                raise err

            except (urllib.error.URLError, OSError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait_time = self._backoff_delay(attempt, base=retry_base_delay)
                    logger.info(
                        'OpenAI network error on attempt %d/%d, waiting %.1fs before retry',
                        attempt + 1, MAX_RETRIES, wait_time
                    )
                    time.sleep(wait_time)
                    continue

        # Exhausted all retries (Req 14.5)
        err = CostRetrievalError(
            f'OpenAI Usage API is temporarily unavailable after {MAX_RETRIES} attempts.',
            provider='openai'
        )
        err.mark_connection_failed = True
        raise err

    @staticmethod
    def _validate_key_format(api_key: str) -> bool:
        """Validate OpenAI API key format.

        Valid keys start with 'sk-org-' or 'sk-proj-' and are between
        40 and 200 characters.
        """
        result = validate_openai_key_format(api_key)
        return result['valid']

    @staticmethod
    def _backoff_delay(attempt: int, base: float = 1.0) -> float:
        """Calculate exponential backoff delay.

        Args:
            attempt: Zero-based attempt number
            base: Base delay in seconds (default 1s)

        Returns:
            Delay in seconds: base * 2^attempt
        """
        return base * (2 ** attempt)

    def fetch_per_user_daily_usage(self, api_key, organization_id, start_date, end_date):
        """Fetch per-user, per-model daily token consumption from OpenAI Usage API.

        Calls GET /v1/organization/usage/completions with group_by=user_id,
        group_by=model, bucket_width=1d. Handles pagination up to 100 pages.

        Args:
            api_key: Decrypted OpenAI admin API key.
            organization_id: OpenAI organization ID (may be empty).
            start_date: Start date as YYYY-MM-DD string (inclusive).
            end_date: End date as YYYY-MM-DD string (exclusive).

        Returns:
            List of dicts with keys: date, user_id, model, api_key_id,
            input_tokens, output_tokens, input_cached_tokens, num_model_requests.
            Returns [] on any error (never raises).
        """
        from datetime import datetime, timezone

        try:
            start_ts = int(
                datetime.strptime(start_date, "%Y-%m-%d")
                .replace(tzinfo=timezone.utc)
                .timestamp()
            )
            end_ts = int(
                datetime.strptime(end_date, "%Y-%m-%d")
                .replace(tzinfo=timezone.utc)
                .timestamp()
            )

            all_records = []
            page_token = None
            max_pages = 100
            base_url = OPENAI_BASE_URL.replace('/v1', '')

            for page_num in range(max_pages):
                url = (
                    f"{base_url}/v1/organization/usage/completions"
                    f"?group_by=user_id&group_by=model&group_by=api_key_id&bucket_width=1d"
                    f"&start_time={start_ts}&end_time={end_ts}"
                )
                if page_token:
                    url += f"&page={page_token}"

                headers = {
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                }
                if organization_id:
                    headers['OpenAI-Organization'] = organization_id

                try:
                    req = urllib.request.Request(url, method='GET', headers=headers)
                    resp = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
                    response = json.loads(resp.read().decode('utf-8'))
                except urllib.error.HTTPError as e:
                    if e.code in (401, 403):
                        logger.warning(
                            "OpenAI Usage API auth failed (%d) during "
                            "fetch_per_user_daily_usage", e.code
                        )
                        return []
                    logger.warning(
                        "OpenAI Usage API error (%d) during "
                        "fetch_per_user_daily_usage page %d", e.code, page_num
                    )
                    return all_records
                except (urllib.error.URLError, OSError) as e:
                    logger.warning(
                        "OpenAI Usage API network error during "
                        "fetch_per_user_daily_usage: %s", e
                    )
                    return all_records

                for bucket in response.get("data", []):
                    bucket_start = bucket.get("start_time")
                    if bucket_start is None:
                        continue
                    date_str = datetime.fromtimestamp(
                        int(bucket_start), tz=timezone.utc
                    ).strftime("%Y-%m-%d")

                    for result in bucket.get("results", []):
                        record = {
                            "date": date_str,
                            "user_id": result.get("user_id") or "unknown",
                            "model": result.get("model") or "unknown",
                            "api_key_id": result.get("api_key_id") or "unknown",
                            "input_tokens": max(0, int(result.get("input_tokens") or 0)),
                            "output_tokens": max(0, int(result.get("output_tokens") or 0)),
                            "input_cached_tokens": max(0, int(result.get("input_cached_tokens") or 0)),
                            "num_model_requests": max(0, int(result.get("num_model_requests") or 0)),
                        }
                        all_records.append(record)

                if not response.get("has_more"):
                    break
                page_token = response.get("next_page")
                if not page_token:
                    break
            else:
                logger.warning(
                    "fetch_per_user_daily_usage hit pagination cap of %d pages", max_pages
                )

            return all_records

        except Exception as e:
            logger.warning("fetch_per_user_daily_usage failed: %s", e)
            return []


# Auto-register when module is imported
register_connector('openai', OpenAIConnector, vendor_type='ai_vendor')
