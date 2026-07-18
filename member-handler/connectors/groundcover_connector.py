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
        """Fetch AI token usage from GroundCover's Prometheus API.

        Queries the GroundCover Prometheus-compatible API for token metrics,
        aggregated by model and day. Returns data in the same bucket format as
        the OpenAI connector so the existing dashboard can consume it.

        Strategy: query raw counter values at daily intervals, then compute
        per-day deltas from consecutive readings. This avoids issues with
        increase()/delta() returning empty on GroundCover's Prometheus.
        """
        token = auth_context.get('api_key', '')
        from datetime import datetime, timezone, timedelta
        try:
            import urllib.parse
        except ImportError:
            return []

        # Anthropic model pricing (USD per 1M tokens) - approximate
        MODEL_PRICING = {
            'claude-opus-4': {'input': 5.0, 'output': 25.0},
            'claude-sonnet-4': {'input': 3.0, 'output': 15.0},
            'claude-sonnet-5': {'input': 3.0, 'output': 15.0},
            'claude-haiku-4': {'input': 1.0, 'output': 5.0},
            'claude-fable-5': {'input': 10.0, 'output': 50.0},
            'gemini-2.5-pro': {'input': 1.25, 'output': 10.0},
            'gemini-2.5-flash': {'input': 0.15, 'output': 0.60},
        }

        def _estimate_cost(model_name, input_tok, output_tok):
            """Estimate cost in USD from token counts using model pricing."""
            model_lower = (model_name or '').lower()
            pricing = None
            for prefix, p in MODEL_PRICING.items():
                if prefix in model_lower:
                    pricing = p
                    break
            if not pricing:
                pricing = {'input': 3.0, 'output': 15.0}
            cost = (input_tok * pricing['input'] + output_tok * pricing['output']) / 1_000_000
            return round(cost, 6)

        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

            prom_url = f"{GROUNDCOVER_API_BASE}/api/prometheus/api/v1/query_range"
            headers = {
                'Authorization': f'Bearer {token}',
                'X-Backend-Id': 'groundcover',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
            }

            # Query raw cumulative counter at daily intervals.
            # We start 1 day earlier so we can compute the delta for start_date.
            query_start_ts = int((start_dt - timedelta(days=1)).timestamp())
            end_ts = int(end_dt.timestamp())
            step = '86400'  # 1 day

            # Raw counter query — no increase()/delta() wrapping
            input_query = 'sum by (model) (claude_code_token_usage_tokens_total{type="input"})'
            output_query = 'sum by (model) (claude_code_token_usage_tokens_total{type="output"})'

            def _prom_range_query(query):
                """Execute a Prometheus range query and return parsed results."""
                params = urllib.parse.urlencode({
                    'query': query,
                    'start': str(query_start_ts),
                    'end': str(end_ts),
                    'step': step,
                })
                data = params.encode('utf-8')
                try:
                    req = urllib.request.Request(prom_url, method='POST', headers=headers, data=data)
                    resp = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
                    raw = json.loads(resp.read().decode('utf-8'))
                    if raw.get('status') != 'success':
                        logger.warning(f"GroundCover Prometheus query failed: {raw.get('error', 'unknown')}")
                        return []
                    return raw.get('data', {}).get('result', [])
                except urllib.error.HTTPError as e:
                    if e.code in (401, 403):
                        raise PermissionError(
                            f"GroundCover API authentication failed (HTTP {e.code}). "
                            "Check your API token in the Configure tab."
                        )
                    logger.warning(f"GroundCover Prometheus API call failed: {e}")
                    return []
                except (urllib.error.URLError, OSError) as e:
                    logger.warning(f"GroundCover Prometheus API call failed: {e}")
                    return []
                except Exception as e:
                    logger.warning(f"GroundCover Prometheus unexpected error: {type(e).__name__}: {e}")
                    return []

            input_results = _prom_range_query(input_query)
            output_results = _prom_range_query(output_query)

            if not input_results and not output_results:
                logger.info("GroundCover Prometheus returned no token data")
                return []

            # Build cumulative readings: {model: [(timestamp, value), ...]}
            # then compute per-day deltas from consecutive readings.
            start_ts_filter = int(start_dt.timestamp())

            def _build_daily_deltas(results):
                """Convert cumulative counter readings into per-day deltas."""
                model_deltas = {}  # {model: {day_ts: delta_tokens}}
                for series in results:
                    model = series.get('metric', {}).get('model', 'unknown')
                    values = series.get('values', [])
                    if len(values) < 2:
                        continue
                    # Sort by timestamp
                    values = sorted(values, key=lambda v: float(v[0]))
                    for i in range(1, len(values)):
                        ts = int(float(values[i][0]))
                        day_ts = ts - (ts % 86400)
                        # Only include days in the requested range
                        if day_ts < start_ts_filter:
                            continue
                        curr = float(values[i][1])
                        prev = float(values[i - 1][1])
                        delta = max(0, int(curr - prev))  # clamp resets to 0
                        if delta > 0:
                            model_deltas.setdefault(model, {}).setdefault(day_ts, 0)
                            model_deltas[model][day_ts] += delta
                return model_deltas

            input_deltas = _build_daily_deltas(input_results)
            output_deltas = _build_daily_deltas(output_results)

            # Merge input + output into model_data
            model_data = {}
            all_models = set(list(input_deltas.keys()) + list(output_deltas.keys()))
            for model in all_models:
                in_days = input_deltas.get(model, {})
                out_days = output_deltas.get(model, {})
                all_days = set(list(in_days.keys()) + list(out_days.keys()))
                for day_ts in all_days:
                    model_data.setdefault(model, {}).setdefault(day_ts, {'input': 0, 'output': 0})
                    model_data[model][day_ts]['input'] += in_days.get(day_ts, 0)
                    model_data[model][day_ts]['output'] += out_days.get(day_ts, 0)

            if not model_data:
                return []

            # Build buckets in the same format as OpenAI connector
            by_day = {}
            for model, days in model_data.items():
                for day_ts, tok in days.items():
                    cost = _estimate_cost(model, tok['input'], tok['output'])
                    by_day.setdefault(day_ts, []).append({
                        'amount': {'value': cost, 'currency': 'usd'},
                        'line_item': model,
                        'input_tokens': tok['input'],
                        'output_tokens': tok['output'],
                    })

            buckets = []
            for day_ts in sorted(by_day.keys()):
                buckets.append({
                    'object': 'bucket',
                    'start_time': day_ts,
                    'end_time': day_ts + 86400,
                    'results': by_day[day_ts],
                })

            logger.info(f"GroundCover: fetched {len(buckets)} daily buckets with {len(model_data)} models")
            return buckets

        except PermissionError:
            raise  # Let auth errors propagate to the resolver
        except Exception as e:
            logger.warning(f"GroundCover get_cost_data failed: {type(e).__name__}: {e}")
            return []

    def get_per_user_data(self, auth_context: dict, account_id: str,
                          start_date: str, end_date: str) -> list:
        """Fetch per-user token usage from GroundCover's Prometheus API.

        Uses a range query on claude_code_token_usage_tokens_total grouped by
        user_email and model, then computes daily deltas from consecutive
        counter readings. Returns actual per-day per-user token consumption.
        """
        token = auth_context.get('api_key', '')
        from datetime import datetime, timezone, timedelta
        try:
            import urllib.parse
        except ImportError:
            return []

        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

            prom_url = f"{GROUNDCOVER_API_BASE}/api/prometheus/api/v1/query_range"
            headers = {
                'Authorization': f'Bearer {token}',
                'X-Backend-Id': 'groundcover',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
            }

            # Query raw cumulative counter at daily intervals (start 1 day early for delta)
            query_start_ts = int((start_dt - timedelta(days=1)).timestamp())
            end_ts = int(end_dt.timestamp())
            step = '86400'

            input_query = 'sum by (user_email, model) (claude_code_token_usage_tokens_total{type="input"})'
            output_query = 'sum by (user_email, model) (claude_code_token_usage_tokens_total{type="output"})'

            def _prom_range_query(query):
                params = urllib.parse.urlencode({
                    'query': query,
                    'start': str(query_start_ts),
                    'end': str(end_ts),
                    'step': step,
                })
                data = params.encode('utf-8')
                try:
                    req = urllib.request.Request(prom_url, method='POST', headers=headers, data=data)
                    resp = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT)
                    raw = json.loads(resp.read().decode('utf-8'))
                    if raw.get('status') != 'success':
                        return []
                    return raw.get('data', {}).get('result', [])
                except urllib.error.HTTPError as e:
                    if e.code in (401, 403):
                        raise PermissionError(
                            f"GroundCover API authentication failed (HTTP {e.code}). "
                            "Check your API token in the Configure tab."
                        )
                    logger.warning(f"GroundCover per-user range query failed: {e}")
                    return []
                except Exception as e:
                    logger.warning(f"GroundCover per-user range query failed: {type(e).__name__}: {e}")
                    return []

            input_results = _prom_range_query(input_query)
            output_results = _prom_range_query(output_query)

            if not input_results and not output_results:
                return []

            # Compute daily deltas from consecutive readings
            start_ts_filter = int(start_dt.timestamp())

            def _extract_user_deltas(results):
                """Build {(user, model): {day_ts: delta}} from range query results."""
                deltas = {}
                for series in results:
                    user = series.get('metric', {}).get('user_email', '')
                    model = series.get('metric', {}).get('model', 'unknown')
                    if not user:
                        continue
                    values = sorted(series.get('values', []), key=lambda v: float(v[0]))
                    if len(values) < 2:
                        continue
                    for i in range(1, len(values)):
                        ts = int(float(values[i][0]))
                        day_ts = ts - (ts % 86400)
                        if day_ts < start_ts_filter:
                            continue
                        curr = float(values[i][1])
                        prev = float(values[i - 1][1])
                        delta = max(0, int(curr - prev))
                        if delta > 0:
                            key = (user, model)
                            deltas.setdefault(key, {}).setdefault(day_ts, 0)
                            deltas[key][day_ts] += delta
                return deltas

            input_deltas = _extract_user_deltas(input_results)
            output_deltas = _extract_user_deltas(output_results)

            # Merge into per-user records
            all_keys = set(list(input_deltas.keys()) + list(output_deltas.keys()))
            per_user_records = []
            for (user_email, model) in all_keys:
                in_days = input_deltas.get((user_email, model), {})
                out_days = output_deltas.get((user_email, model), {})
                all_days = set(list(in_days.keys()) + list(out_days.keys()))
                for day_ts in all_days:
                    day_str = datetime.fromtimestamp(day_ts, tz=timezone.utc).strftime('%Y-%m-%d')
                    inp = in_days.get(day_ts, 0)
                    out = out_days.get(day_ts, 0)
                    per_user_records.append({
                        'date': day_str,
                        'user_id': user_email,
                        'model': model,
                        'input_tokens': inp,
                        'output_tokens': out,
                        'num_model_requests': 1,
                    })

            logger.info(f"GroundCover: fetched {len(per_user_records)} per-user daily records")
            return per_user_records

        except PermissionError:
            raise  # Let auth errors propagate to the resolver
        except Exception as e:
            logger.warning(f"GroundCover get_per_user_data failed: {type(e).__name__}: {e}")
            return []

    def fetch_per_user_daily_usage(self, api_key, organization_id, start_date, end_date):
        """Per-user daily usage in the shared connector signature.

        The Tier-2 Tips drilldown executor calls
        ``connector.fetch_per_user_daily_usage(api_key, organization_id, start,
        end)`` uniformly across AI vendors. GroundCover's native method takes an
        auth_context dict, so this adapts the signature (organization_id is
        unused for GroundCover). Returns ``[]`` on any error (never raises).
        """
        try:
            return self.get_per_user_data(
                {'api_key': api_key}, organization_id or '', start_date, end_date
            )
        except Exception as e:
            logger.warning(
                f"GroundCover fetch_per_user_daily_usage failed: {type(e).__name__}: {e}"
            )
            return []

    # ──────────────────────────────────────────────────────────────────────
    # Vendor-neutral AI cost/usage entrypoint (Tier-3 live call).
    # The shared three-tier resolver (incremental_fetch_engine) calls
    # ``connector.get_ai_usage(account_id, member_email, params)`` for ANY
    # AI-vendor account, selecting the connector purely by the account's
    # ``cloudProvider`` — no vendor-specific branching anywhere upstream
    # (Req 13.4). Implementing this here is what lets GroundCover flow through
    # the exact same cache-first chat + dashboard path as OpenAI, with neutral
    # COST#/USAGE# write-back. Customer-connection-only, single account.
    # ──────────────────────────────────────────────────────────────────────

    def get_ai_usage(self, account_id: str, member_email: str, params: dict) -> dict:
        """Vendor-neutral AI cost/usage retrieval for a GroundCover account.

        Maps GroundCover's token/cost data onto the neutral schema (tokens ->
        units, user_email -> actor, model -> service) and projects by
        ``dimension``:

          - ``cost``  -> daily rollups + per-model cost detail.
          - ``units`` -> per-model token detail.
          - ``actor`` -> per-user token detail.

        params:
          dimension: "cost" | "units" | "actor"   (defaults to "cost")
          service:   optional str  - scope to a single model/service
          period:    optional {start, end} or "start/end" string
                     (defaults to the last 30 days, Req 3.6)

        Returns a neutral-shaped dict
        ``{dimension, period, currency, rollups[], usage[], truncated,
        providerMetadata}`` or ``{'error': ...}`` on failure. Loads the
        CUSTOMER's credentials scoped to (member_email, account_id) — never a
        platform-owned key — and resolves exactly one account.
        """
        import cost_normalizer

        dimension = (params.get('dimension') or 'cost').lower()
        if dimension not in ('cost', 'units', 'actor'):
            dimension = 'cost'
        service_filter = params.get('service') or None
        period = self._resolve_neutral_period(params.get('period'))
        start_date, end_date = period['start'], period['end']

        # Customer credentials only, scoped to (member_email, account_id).
        auth_context = self._load_auth_context(member_email, account_id)

        # Daily cost + per-model tokens (GroundCover returns OpenAI-style buckets,
        # so the shared OpenAI normalizer parses them directly).
        raw_cost = self.get_cost_data(auth_context, account_id, start_date, end_date)
        normalized = cost_normalizer.normalize_openai(raw_cost, account_id)

        # Per-user (actor) token detail.
        per_user = []
        if dimension == 'actor':
            per_user = self.get_per_user_data(
                auth_context, account_id, start_date, end_date
            )

        rollups, usage = self._project_neutral(
            dimension, normalized, per_user, service_filter
        )
        currency = next(
            (r.get('currency') for r in rollups if r.get('currency')), None
        ) or 'USD'

        return {
            'dimension': dimension,
            'period': period,
            'currency': currency,
            'rollups': rollups,
            'usage': usage,
            'truncated': False,
            'providerMetadata': {'provider': 'groundcover', 'source': 'live'},
        }

    @staticmethod
    def _load_auth_context(member_email: str, account_id: str) -> dict:
        """Load + decrypt the customer's GroundCover token, returning the auth
        context expected by get_cost_data / get_per_user_data.

        The token is stored KMS-encrypted under ``credentials.encryptedApiKey``
        with the {memberEmail, accountId} encryption context (same scheme as
        OpenAI). Decrypted secret stays a local variable; it is never returned
        beyond the auth context, logged, or persisted.
        """
        import os
        import boto3
        from .openai_kms import decrypt_openai_key, DecryptionError
        from .base_connector import AuthenticationError

        accounts_table = boto3.resource('dynamodb').Table(
            os.environ.get('ACCOUNTS_TABLE_NAME', 'MemberPortal-Accounts')
        )
        try:
            result = accounts_table.get_item(
                Key={'memberEmail': member_email, 'accountId': account_id}
            )
        except Exception:
            raise AuthenticationError(
                'Unable to read GroundCover account record.', provider='groundcover'
            )
        account = result.get('Item') or {}
        encrypted_key = (account.get('credentials', {}) or {}).get('encryptedApiKey', '')
        if not encrypted_key:
            raise AuthenticationError(
                'No GroundCover token stored for this account.', provider='groundcover'
            )
        try:
            api_key = decrypt_openai_key(encrypted_key, member_email, account_id)
        except DecryptionError:
            raise AuthenticationError(
                'Credentials inaccessible. Please re-add your GroundCover connection.',
                provider='groundcover',
            )
        return {'api_key': api_key}

    @staticmethod
    def _resolve_neutral_period(period) -> dict:
        """Resolve the window, defaulting to the most recent 30 days (Req 3.6)."""
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        now = _dt.now(_tz.utc)
        default_end = now.strftime('%Y-%m-%d')
        default_start = (now - _td(days=30)).strftime('%Y-%m-%d')
        if not period:
            return {'start': default_start, 'end': default_end}
        if isinstance(period, dict):
            return {
                'start': period.get('start') or default_start,
                'end': period.get('end') or default_end,
            }
        if isinstance(period, str):
            for sep in ('/', ' to ', ','):
                if sep in period:
                    parts = [p.strip() for p in period.split(sep, 1)]
                    if len(parts) == 2 and parts[0] and parts[1]:
                        return {'start': parts[0], 'end': parts[1]}
                    break
        return {'start': default_start, 'end': default_end}

    @staticmethod
    def _project_neutral(dimension, normalized, per_user, service_filter):
        """Project normalized records onto neutral rollups + usage detail.

        ``rollups`` carry ``{date, cost_amount, currency}`` (one per day) and
        ``usage`` carry ``{date, actor, service, usage_quantity, unit,
        cost_amount}`` so the resolver's write-back can shape neutral COST#/
        USAGE# items. Mirrors the OpenAI connector's projection so both vendors
        produce identical neutral output.
        """
        rollup_map = {}
        for rec in normalized:
            date = rec.get('date')
            if not date:
                continue
            agg = rollup_map.setdefault(
                date, {'date': date, 'cost_amount': 0.0,
                       'currency': rec.get('currency') or 'USD'}
            )
            agg['cost_amount'] += float(rec.get('cost_amount', 0) or 0)
        rollups = [rollup_map[d] for d in sorted(rollup_map)]

        usage = []
        if dimension == 'actor':
            for rec in per_user:
                date = rec.get('date')
                if not date:
                    continue
                service = rec.get('model')
                if service_filter and service != service_filter:
                    continue
                tokens = (rec.get('input_tokens') or 0) + (rec.get('output_tokens') or 0)
                usage.append({
                    'date': date,
                    'actor': rec.get('user_id'),
                    'service': service,
                    'usage_quantity': tokens if tokens else None,
                    'unit': 'tokens',
                    'cost_amount': None,
                })
        else:
            for rec in normalized:
                date = rec.get('date')
                if not date:
                    continue
                service = rec.get('service_name')
                if service_filter and service != service_filter:
                    continue
                tokens = (rec.get('input_tokens') or 0) + (rec.get('output_tokens') or 0)
                usage.append({
                    'date': date,
                    'actor': rec.get('project_id'),
                    'service': service,
                    'usage_quantity': tokens if tokens else None,
                    'unit': 'tokens',
                    'cost_amount': float(rec.get('cost_amount', 0) or 0),
                })

        return rollups, usage


# Auto-register when module is imported
register_connector('groundcover', GroundcoverConnector, vendor_type='ai_vendor')
