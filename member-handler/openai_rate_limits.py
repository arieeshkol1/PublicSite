"""OpenAI Rate Limit Utilization — retrieves and analyzes rate limit data.

Extracts RPM (requests-per-minute) and TPM (tokens-per-minute) utilization
from OpenAI API response headers when making a lightweight request to /v1/models.

OpenAI embeds rate limit information in response headers:
  - x-ratelimit-limit-requests: max RPM allowed
  - x-ratelimit-remaining-requests: remaining RPM
  - x-ratelimit-limit-tokens: max TPM allowed
  - x-ratelimit-remaining-tokens: remaining TPM

Since OpenAI doesn't provide a dedicated rate limit endpoint, this module
calls GET /v1/models and inspects the response headers for rate limit info.
"""
import json
import logging

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Constants
OPENAI_BASE_URL = "https://api.openai.com/v1"
REQUEST_TIMEOUT = 30  # seconds
WARNING_THRESHOLD = 80.0  # Percentage — warn if utilization exceeds this


def _calculate_utilization(limit: int, remaining: int) -> float:
    """Calculate utilization percentage from limit and remaining values.

    Args:
        limit: Maximum allowed (RPM or TPM).
        remaining: Remaining capacity.

    Returns:
        Utilization percentage (0.0 to 100.0), rounded to 1 decimal place.
    """
    if limit <= 0:
        return 0.0
    current = limit - remaining
    utilization = (current / limit) * 100
    return round(utilization, 1)


def _should_warn(utilization: float) -> bool:
    """Determine if a warning should be flagged for the given utilization.

    A warning is displayed if and only if utilization exceeds 80%.

    Args:
        utilization: Utilization percentage (0.0 to 100.0).

    Returns:
        True if utilization > 80%, False otherwise.
    """
    return utilization > WARNING_THRESHOLD


def _parse_rate_limit_headers(headers) -> dict:
    """Parse rate limit information from OpenAI API response headers.

    OpenAI returns per-model rate limit headers. When calling /v1/models,
    the headers reflect the account-level limits for the default model tier.

    Args:
        headers: HTTP response headers (dict-like object).

    Returns:
        Dict with parsed rate limit data, or empty dict if headers not present.
        {
            'rpm_limit': int,
            'rpm_remaining': int,
            'tpm_limit': int,
            'tpm_remaining': int,
        }
    """
    rpm_limit = headers.get('x-ratelimit-limit-requests')
    rpm_remaining = headers.get('x-ratelimit-remaining-requests')
    tpm_limit = headers.get('x-ratelimit-limit-tokens')
    tpm_remaining = headers.get('x-ratelimit-remaining-tokens')

    # If none of the rate limit headers are present, data is unavailable
    if rpm_limit is None and tpm_limit is None:
        return {}

    result = {}
    try:
        if rpm_limit is not None:
            result['rpm_limit'] = int(rpm_limit)
            result['rpm_remaining'] = int(rpm_remaining) if rpm_remaining is not None else 0
        if tpm_limit is not None:
            result['tpm_limit'] = int(tpm_limit)
            result['tpm_remaining'] = int(tpm_remaining) if tpm_remaining is not None else 0
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse rate limit headers: {e}")
        return {}

    return result


def _build_model_utilization(rate_data: dict, model_name: str = 'default') -> dict:
    """Build a model utilization entry from parsed rate limit data.

    Args:
        rate_data: Parsed rate limit headers from _parse_rate_limit_headers().
        model_name: The model tier name to associate with this data.

    Returns:
        Dict with utilization metrics and warning flag.
    """
    entry = {'model': model_name, 'warning': False}

    if 'rpm_limit' in rate_data:
        rpm_limit = rate_data['rpm_limit']
        rpm_remaining = rate_data.get('rpm_remaining', 0)
        rpm_current = rpm_limit - rpm_remaining
        rpm_utilization = _calculate_utilization(rpm_limit, rpm_remaining)
        entry['rpm_limit'] = rpm_limit
        entry['rpm_current'] = rpm_current
        entry['rpm_utilization'] = rpm_utilization
    else:
        entry['rpm_limit'] = 0
        entry['rpm_current'] = 0
        entry['rpm_utilization'] = 0.0

    if 'tpm_limit' in rate_data:
        tpm_limit = rate_data['tpm_limit']
        tpm_remaining = rate_data.get('tpm_remaining', 0)
        tpm_current = tpm_limit - tpm_remaining
        tpm_utilization = _calculate_utilization(tpm_limit, tpm_remaining)
        entry['tpm_limit'] = tpm_limit
        entry['tpm_current'] = tpm_current
        entry['tpm_utilization'] = tpm_utilization
    else:
        entry['tpm_limit'] = 0
        entry['tpm_current'] = 0
        entry['tpm_utilization'] = 0.0

    # Flag warning if either utilization exceeds 80%
    if _should_warn(entry['rpm_utilization']) or _should_warn(entry['tpm_utilization']):
        entry['warning'] = True

    return entry


def get_rate_limit_utilization(api_key: str) -> dict:
    """Get rate limit utilization for the connected OpenAI account.

    Calls GET /v1/models with the API key and inspects response headers
    for rate limit information (x-ratelimit-limit-requests,
    x-ratelimit-remaining-requests, x-ratelimit-limit-tokens,
    x-ratelimit-remaining-tokens).

    If headers are present: calculates utilization percentages per model tier.
    If headers are NOT present: returns unavailable message.

    Args:
        api_key: Decrypted OpenAI API key (Bearer token).

    Returns:
        Dict with structure:
        {
            'available': True/False,
            'message': '...',  # Only if available=False
            'models': [        # Only if available=True
                {
                    'model': 'gpt-4',
                    'rpm_limit': 500,
                    'rpm_current': 450,
                    'rpm_utilization': 90.0,
                    'tpm_limit': 40000,
                    'tpm_current': 35000,
                    'tpm_utilization': 87.5,
                    'warning': True,  # True if either utilization > 80%
                },
                ...
            ]
        }
    """
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

        # Extract rate limit headers from the response
        rate_data = _parse_rate_limit_headers(response.headers)

        if not rate_data:
            return {
                'available': False,
                'message': 'Rate limit information is unavailable for this account key type.',
            }

        # Parse the models list to determine model tiers if available
        body = json.loads(response.read().decode('utf-8'))
        model_ids = [m.get('id', '') for m in body.get('data', [])]

        # Build utilization entry from the headers
        # Note: /v1/models returns account-level rate limits in headers.
        # We label this by the tier visible in the response.
        # If model-specific rate limits are returned per header, we use
        # the model name from the x-ratelimit-limit-requests-model header if present.
        model_header = response.headers.get('x-ratelimit-limit-requests-model')
        model_tier = model_header if model_header else 'account-level'

        model_entry = _build_model_utilization(rate_data, model_name=model_tier)
        models = [model_entry]

        return {
            'available': True,
            'models': models,
        }

    except urllib.error.HTTPError as e:
        status_code = e.code
        # Try to extract rate limit info from error response headers too
        rate_data = _parse_rate_limit_headers(e.headers) if hasattr(e, 'headers') else {}

        if rate_data:
            model_entry = _build_model_utilization(rate_data, model_name='account-level')
            return {
                'available': True,
                'models': [model_entry],
            }

        if status_code == 401:
            return {
                'available': False,
                'message': 'API key is invalid or revoked. Cannot retrieve rate limit data.',
            }
        elif status_code == 429:
            # Ironically, a 429 itself signals rate limiting — extract info if available
            return {
                'available': False,
                'message': 'Rate limited by OpenAI. Rate limit data temporarily unavailable.',
            }
        else:
            return {
                'available': False,
                'message': 'Rate limit information is unavailable for this account key type.',
            }

    except (urllib.error.URLError, OSError, Exception) as e:
        logger.warning(f"Failed to retrieve rate limit data: {e}")
        return {
            'available': False,
            'message': 'Rate limit information is unavailable for this account key type.',
        }
