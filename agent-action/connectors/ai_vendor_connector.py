"""
AI Vendor Cloud Connector.

Implements vendor-neutral tool operations for AI vendor accounts (OpenAI,
Anthropic, etc.) using their respective APIs. Extends the base CloudConnector
and supports only cost/usage-related operations — compute, database, and
storage tools return notSupported responses via the Provider Router.

All methods return raw dicts — response normalization is applied upstream
by the Provider Router / Response Normalizer layer.
"""

import json
import logging
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

import boto3

from . import CloudConnector
from provider_router import _substitute_placeholders

logger = logging.getLogger(__name__)


class AIVendorConnector(CloudConnector):
    """
    AI Vendor-specific implementation of the CloudConnector interface.

    Supports OpenAI and similar AI vendor APIs for cost and usage tracking.
    Uses API key from the account's encrypted credentials map in
    MemberPortal-Accounts DynamoDB table.

    Only cost/usage operations are supported. Compute, database, storage,
    network, and serverless tools are not applicable for AI vendor accounts.
    """

    SUPPORTED_OPERATIONS: list[str] = [
        "getCostBreakdown",
        "getAIUsage",
        "getMonthlyTrend",
    ]

    # Default resolution window when no period is supplied (Req 3.6).
    DEFAULT_WINDOW_DAYS = 30

    # ─── Credential Helpers ───────────────────────────────────────────────

    def _get_credentials(self, account_id: str, member_email: str) -> dict:
        """
        Retrieve and decrypt the API key for the AI vendor account
        from MemberPortal-Accounts DynamoDB table.

        Returns:
            dict with 'api_key' and optionally 'organization_id', 'vendor' fields.

        Raises:
            PermissionError: If credentials are missing or invalid.
        """
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("MemberPortal-Accounts")

        try:
            response = table.get_item(
                Key={"memberEmail": member_email, "accountId": account_id}
            )
        except Exception as e:
            logger.error(f"Failed to retrieve AI vendor credentials: {e}")
            raise PermissionError(
                f"Unable to retrieve credentials for account {account_id}"
            )

        item = response.get("Item")
        if not item:
            raise PermissionError(
                f"Account {account_id} not found for {member_email}"
            )

        credentials = item.get("credentials", {})
        encrypted_key = credentials.get("encryptedApiKey", "")
        api_key = credentials.get("api_key", "")

        # If we have an encrypted key, decrypt it via KMS
        if encrypted_key and not api_key:
            try:
                import base64
                kms_client = boto3.client("kms")
                decrypted = kms_client.decrypt(
                    CiphertextBlob=base64.b64decode(encrypted_key),
                    EncryptionContext={
                        "memberEmail": member_email,
                        "accountId": account_id,
                    },
                )
                api_key = decrypted["Plaintext"].decode("utf-8")
            except Exception as e:
                logger.error(f"KMS decryption failed for AI vendor {account_id}: {e}")
                raise PermissionError(
                    "AI vendor API key decryption failed. Please re-add your connection "
                    "in the Configure tab."
                )

        if not api_key:
            raise PermissionError(
                "AI vendor API key is missing. Please update your credentials "
                "in the Configure tab."
            )

        return {
            "api_key": api_key,
            "organization_id": credentials.get("organization_id", ""),
            "vendor": item.get("cloudProvider", "openai"),
        }

    def _make_openai_request(self, endpoint: str, api_key: str, organization_id: str = "") -> dict:
        """
        Make an authenticated GET request to the OpenAI API.

        Args:
            endpoint: The API endpoint path (e.g., '/v1/usage').
            api_key: The OpenAI API key.
            organization_id: Optional organization ID for org-scoped requests.

        Returns:
            Parsed JSON response dict.

        Raises:
            PermissionError: If authentication fails (401/403).
            RuntimeError: For other API errors.
        """
        url = f"https://api.openai.com{endpoint}"

        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Content-Type", "application/json")
        if organization_id:
            req.add_header("OpenAI-Organization", organization_id)

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"OpenAI API error: {e.code} - {error_body[:500]}")
            if e.code in (401, 403):
                raise PermissionError(
                    "AI vendor authentication failed. Please verify your API key "
                    "in the Configure tab."
                )
            raise RuntimeError(f"AI vendor API error: HTTP {e.code}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"AI vendor API unreachable: {e.reason}")
        except Exception as e:
            raise RuntimeError(f"AI vendor API request failed: {e}")

    # ─── Cost Analysis ────────────────────────────────────────────────────

    def get_cost_breakdown(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get cost breakdown for the AI vendor account.

        Returns normalized cost data including total spend, service/model
        breakdown, and daily cost trend. Uses the OpenAI billing/usage API
        to retrieve spend data for the requested period.

        Returns:
            dict with totalCost, currency, period, serviceBreakdown, dailyCosts,
            and providerMetadata fields.
        """
        try:
            creds = self._get_credentials(account_id, member_email)
            api_key = creds["api_key"]
            organization_id = creds.get("organization_id", "")
            vendor = creds.get("vendor", "openai")

            # Determine date range from params or default to last 30 days
            now = datetime.now(timezone.utc)
            start_date = params.get("startDate", (now - timedelta(days=30)).strftime("%Y-%m-%d"))
            end_date = params.get("endDate", now.strftime("%Y-%m-%d"))

            # Query the AI vendor's usage/billing API
            usage_data = self._fetch_usage_data(
                api_key, organization_id, vendor, start_date, end_date
            )

            # Build normalized cost breakdown
            service_breakdown = usage_data.get("model_costs", [])
            daily_costs = usage_data.get("daily_costs", [])
            total_cost = usage_data.get("total_cost", 0.0)

            return {
                "totalCost30Days": round(total_cost, 2),
                "currency": "USD",
                "period": f"{start_date} to {end_date}",
                "topServices": [
                    {"service": item["model"], "cost": round(item["cost"], 4)}
                    for item in service_breakdown
                ],
                "dailyCosts": daily_costs,
                "providerMetadata": {
                    "provider": vendor,
                    "source": "live",
                    "totalTokens": usage_data.get("total_tokens", 0),
                },
            }
        except (PermissionError, RuntimeError) as e:
            raise
        except Exception as e:
            logger.error(f"AI vendor get_cost_breakdown failed: {e}")
            return {"error": str(e)}

    # ─── Knowledge / AI Usage ─────────────────────────────────────────────

    def get_ai_vendor_usage(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get AI vendor usage data including token usage, model-level costs,
        and total spend.

        Returns:
            dict with totalSpend, tokenUsage (prompt/completion/total),
            modelBreakdown (per-model cost and token usage), period,
            and providerMetadata.
        """
        try:
            creds = self._get_credentials(account_id, member_email)
            api_key = creds["api_key"]
            organization_id = creds.get("organization_id", "")
            vendor = creds.get("vendor", "openai")

            # Determine date range from params or default to last 30 days
            now = datetime.now(timezone.utc)
            start_date = params.get("startDate", (now - timedelta(days=30)).strftime("%Y-%m-%d"))
            end_date = params.get("endDate", now.strftime("%Y-%m-%d"))

            # Fetch usage data from the vendor API
            usage_data = self._fetch_usage_data(
                api_key, organization_id, vendor, start_date, end_date
            )

            # Build model breakdown with token details
            model_breakdown = []
            for model_entry in usage_data.get("model_costs", []):
                model_breakdown.append({
                    "model": model_entry["model"],
                    "cost": round(model_entry["cost"], 4),
                    "promptTokens": model_entry.get("prompt_tokens", 0),
                    "completionTokens": model_entry.get("completion_tokens", 0),
                    "totalTokens": model_entry.get("total_tokens", 0),
                    "requests": model_entry.get("requests", 0),
                })

            return {
                "totalSpend": round(usage_data.get("total_cost", 0.0), 2),
                "currency": "USD",
                "tokenUsage": {
                    "promptTokens": usage_data.get("total_prompt_tokens", 0),
                    "completionTokens": usage_data.get("total_completion_tokens", 0),
                    "totalTokens": usage_data.get("total_tokens", 0),
                },
                "modelBreakdown": model_breakdown,
                "period": f"{start_date} to {end_date}",
                "providerMetadata": {
                    "provider": vendor,
                    "organizationId": organization_id,
                    "source": "live",
                },
            }
        except (PermissionError, RuntimeError) as e:
            raise
        except Exception as e:
            logger.error(f"AI vendor get_ai_vendor_usage failed: {e}")
            return {"error": str(e)}

    # ─── Vendor-Neutral AI Usage (getAIUsage) ─────────────────────────────

    def get_ai_usage(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Vendor-neutral AI cost/usage retrieval.

        Reuses the existing OpenAI fetch path and maps raw vendor fields onto
        the neutral schema (tokens -> units, user_id -> actor, model -> service)
        before projecting by ``dimension``:

          - ``cost``  -> daily Cost_Rollup_Item list (rollups), plus detail usage.
          - ``units`` -> usage_quantity totals grouped by service.
          - ``actor`` -> usage detail grouped by actor.

        params:
          dimension: "cost" | "units" | "actor"   (defaults to "cost")
          service:   optional str  - scope to a single AI service/model
          period:    optional {start, end} or "start/end" string
                     (defaults to the last 30 days, Req 3.6)

        Returns a neutral-shaped dict:
            {dimension, period, currency, rollups[], usage[], truncated,
             providerMetadata}
        """
        try:
            creds = self._get_credentials(account_id, member_email)
            api_key = creds["api_key"]
            organization_id = creds.get("organization_id", "")
            vendor = creds.get("vendor", "openai")

            dimension = (params.get("dimension") or "cost").lower()
            if dimension not in ("cost", "units", "actor"):
                dimension = "cost"
            service_filter = params.get("service") or None

            # Default window is the most recent 30 days (Req 3.6).
            period = self._resolve_period(params.get("period"))
            start_date = period["start"]
            end_date = period["end"]

            # Raw per-actor / per-model usage buckets (nulls preserved, Req 2.6).
            raw_buckets = self._fetch_raw_usage_buckets(
                api_key, organization_id, vendor, start_date, end_date
            )
            usage_items = self._map_usage_buckets_to_neutral(raw_buckets)

            # Daily cost rollups from the org costs endpoint.
            cost_data = self._fetch_usage_data(
                api_key, organization_id, vendor, start_date, end_date
            )
            currency = self._resolve_currency(usage_items)
            rollup_items = self._map_daily_costs_to_rollups(cost_data, currency)

            # Optional single-service scoping (Req 3.4 / 5.3).
            if service_filter:
                usage_items = [
                    u for u in usage_items if u.get("service") == service_filter
                ]

            rollups, usage = self._project_by_dimension(
                dimension, rollup_items, usage_items
            )

            return {
                "dimension": dimension,
                "period": period,
                "currency": currency,
                "rollups": rollups,
                "usage": usage,
                "truncated": False,
                "providerMetadata": {
                    "provider": vendor,
                    "organizationId": organization_id,
                    "source": "live",
                },
            }
        except (PermissionError, RuntimeError):
            raise
        except Exception as e:
            logger.error(f"AI vendor get_ai_usage failed: {e}")
            return {"error": str(e)}

    def _resolve_period(self, period) -> dict:
        """
        Resolve the requested window, defaulting to the most recent 30 days
        when no ``period`` is supplied (Req 3.6).

        Accepts a ``{start, end}`` dict, a ``"start/end"`` / ``"start to end"``
        / ``"start,end"`` string, or ``None``. Returns ``{start, end}`` as
        ISO-8601 ``YYYY-MM-DD`` strings.
        """
        now = datetime.now(timezone.utc)
        default_end = now.strftime("%Y-%m-%d")
        default_start = (
            now - timedelta(days=self.DEFAULT_WINDOW_DAYS)
        ).strftime("%Y-%m-%d")

        if not period:
            return {"start": default_start, "end": default_end}

        if isinstance(period, dict):
            return {
                "start": period.get("start") or default_start,
                "end": period.get("end") or default_end,
            }

        if isinstance(period, str):
            for sep in ("/", " to ", ","):
                if sep in period:
                    parts = [p.strip() for p in period.split(sep, 1)]
                    if len(parts) == 2 and parts[0] and parts[1]:
                        return {"start": parts[0], "end": parts[1]}
                    break

        return {"start": default_start, "end": default_end}

    def _fetch_raw_usage_buckets(
        self, api_key: str, organization_id: str, vendor: str,
        start_date: str, end_date: str
    ) -> list[dict]:
        """
        Fetch raw per-actor / per-model usage buckets from the AI vendor.

        Returns the raw bucket list unchanged (so the neutral mapper can
        preserve missing fields as null). Returns [] for unsupported vendors
        or on any API error (never raises).
        """
        if vendor != "openai":
            return []

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
        except (ValueError, TypeError):
            return []

        endpoint = (
            f"/v1/organization/usage/completions"
            f"?group_by=user_id&group_by=model&bucket_width=1d"
            f"&start_time={start_ts}&end_time={end_ts}"
        )

        try:
            data = self._make_openai_request(endpoint, api_key, organization_id)
        except (PermissionError, RuntimeError):
            return []

        buckets = list(data.get("data", []))

        page_count = 1
        while data.get("has_more") and data.get("next_page") and page_count < 2:
            try:
                data = self._make_openai_request(
                    endpoint + f"&page={data['next_page']}",
                    api_key,
                    organization_id,
                )
                buckets.extend(data.get("data", []))
                page_count += 1
            except Exception:
                break

        return buckets

    def _map_usage_buckets_to_neutral(self, buckets: list) -> list[dict]:
        """
        Map raw vendor usage buckets onto neutral Usage_Detail fields
        (Req 2.5, 2.6). Direction:

            tokens (input + output) -> usage_quantity ("tokens")
            user_id -> actor          (falls back to project_id, then api_key_id)
            model   -> service        (falls back to line_item)
            amount.value -> cost_amount
            amount.currency -> currency (uppercased, default USD)

        A neutral field with no corresponding source is set to ``None`` (null)
        rather than omitted.
        """
        items: list[dict] = []
        for bucket in buckets or []:
            date = None
            start_time = bucket.get("start_time")
            if start_time is not None:
                try:
                    date = datetime.fromtimestamp(
                        int(start_time), tz=timezone.utc
                    ).strftime("%Y-%m-%d")
                except (ValueError, TypeError, OSError):
                    date = None

            for result in bucket.get("results", []):
                # actor: user_id -> project_id -> api_key_id -> null
                actor = (
                    result.get("user_id")
                    or result.get("project_id")
                    or result.get("api_key_id")
                    or None
                )
                # service: model -> line_item -> null
                service = result.get("model") or result.get("line_item") or None

                # usage_quantity: input + output tokens; null if neither present
                input_tokens = result.get("input_tokens")
                output_tokens = result.get("output_tokens")
                if input_tokens is None and output_tokens is None:
                    usage_quantity = None
                    unit = None
                else:
                    usage_quantity = int(input_tokens or 0) + int(output_tokens or 0)
                    unit = "tokens"

                amount_obj = result.get("amount") or {}
                cost_value = amount_obj.get("value")
                cost_amount = (
                    round(float(cost_value), 4) if cost_value is not None else None
                )
                currency = (amount_obj.get("currency") or "USD").upper()

                items.append({
                    "date": date,
                    "actor": actor,
                    "service": service,
                    "usage_quantity": usage_quantity,
                    "unit": unit,
                    "cost_amount": cost_amount,
                    "currency": currency,
                })
        return items

    def _map_daily_costs_to_rollups(self, cost_data: dict, currency: str) -> list[dict]:
        """
        Map the daily cost series produced by ``_fetch_usage_data`` onto
        neutral Cost_Rollup fields ({date, cost_amount, currency}).
        """
        rollups: list[dict] = []
        for entry in cost_data.get("daily_costs", []):
            date = entry.get("date")
            cost = entry.get("cost")
            rollups.append({
                "date": date,
                "cost_amount": round(float(cost), 4) if cost is not None else None,
                "currency": currency,
            })
        return rollups

    @staticmethod
    def _resolve_currency(usage_items: list) -> str:
        """Use the first non-null currency from usage detail, default USD."""
        for item in usage_items:
            currency = item.get("currency")
            if currency:
                return currency.upper()
        return "USD"

    @staticmethod
    def _project_by_dimension(
        dimension: str, rollup_items: list, usage_items: list
    ) -> tuple[list, list]:
        """
        Project the neutral records according to the requested dimension.

          - ``cost``  -> rollups primary; usage is the full detail list.
          - ``units`` -> usage grouped by service (summed usage_quantity).
          - ``actor`` -> usage grouped by actor (summed quantity and cost).
        """
        if dimension == "units":
            grouped: dict = {}
            for u in usage_items:
                svc = u.get("service")
                qty = u.get("usage_quantity") or 0
                grouped[svc] = grouped.get(svc, 0) + qty
            usage = [
                {"service": svc, "usage_quantity": qty, "unit": "tokens"}
                for svc, qty in sorted(
                    grouped.items(), key=lambda kv: kv[1], reverse=True
                )
            ]
            return rollup_items, usage

        if dimension == "actor":
            grouped_actor: dict = {}
            for u in usage_items:
                actor = u.get("actor")
                bucket = grouped_actor.setdefault(
                    actor, {"actor": actor, "usage_quantity": 0, "cost_amount": 0.0}
                )
                bucket["usage_quantity"] += u.get("usage_quantity") or 0
                bucket["cost_amount"] += u.get("cost_amount") or 0.0
            usage = sorted(
                (
                    {
                        "actor": v["actor"],
                        "usage_quantity": v["usage_quantity"],
                        "cost_amount": round(v["cost_amount"], 4),
                        "unit": "tokens",
                    }
                    for v in grouped_actor.values()
                ),
                key=lambda x: x["cost_amount"],
                reverse=True,
            )
            return rollup_items, usage

        # dimension == "cost": rollups primary, full usage detail retained.
        return rollup_items, usage_items

    # ─── Internal Helpers ─────────────────────────────────────────────────

    def _fetch_usage_data(
        self, api_key: str, organization_id: str, vendor: str,
        start_date: str, end_date: str
    ) -> dict:
        """
        Fetch usage and cost data from the AI vendor API.

        Currently supports OpenAI. For unsupported vendors, returns a
        structured response indicating limited data availability.

        Returns:
            dict with keys: total_cost, total_tokens, total_prompt_tokens,
            total_completion_tokens, model_costs (list), daily_costs (list).
        """
        if vendor == "openai":
            return self._fetch_openai_usage(api_key, organization_id, start_date, end_date)
        else:
            # Generic fallback for other AI vendors (Anthropic, etc.)
            # Returns empty structure — can be extended per vendor
            logger.warning(f"AI vendor '{vendor}' usage API not yet implemented, returning empty data")
            return {
                "total_cost": 0.0,
                "total_tokens": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "model_costs": [],
                "daily_costs": [],
            }

    def _fetch_openai_usage(
        self, api_key: str, organization_id: str,
        start_date: str, end_date: str
    ) -> dict:
        """
        Fetch usage data from OpenAI's Organization Costs API.

        Uses /v1/organization/costs?start_time=EPOCH&end_time=EPOCH&group_by=line_item
        to retrieve cost data grouped by model and day.

        Returns:
            Normalized usage dict with total_cost, model_costs, daily_costs, etc.
        """
        # Convert dates to Unix timestamps for the OpenAI API
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        ).timestamp())
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        ).timestamp())

        # Use Organization Costs API (works with admin keys)
        endpoint = f"/v1/organization/costs?start_time={start_ts}&end_time={end_ts}&group_by=line_item"

        try:
            data = self._make_openai_request(endpoint, api_key, organization_id)
        except (PermissionError, RuntimeError):
            logger.warning("OpenAI org costs endpoint failed, attempting fallback")
            return self._fetch_openai_usage_fallback(
                api_key, organization_id, start_date, end_date
            )

        # Parse the Organization Costs API response (paginated buckets)
        return self._parse_org_costs_response(data, api_key, organization_id, start_ts, end_ts)

    def _parse_org_costs_response(self, data: dict, api_key: str, organization_id: str, start_ts: int, end_ts: int) -> dict:
        """Parse OpenAI Organization Costs API response into normalized format.
        
        Response format: {"object": "page", "data": [{"start_time": N, "end_time": N, "results": [...]}], "has_more": bool}
        """
        total_cost = 0.0
        model_costs_map = {}
        daily_costs_map = {}

        all_buckets = data.get("data", [])

        # Fetch additional pages (max 2 to stay within Bedrock Agent timeout)
        page_count = 1
        while data.get("has_more") and data.get("next_page") and page_count < 2:
            next_endpoint = f"/v1/organization/costs?start_time={start_ts}&end_time={end_ts}&group_by=line_item&page={data['next_page']}"
            try:
                data = self._make_openai_request(next_endpoint, api_key, organization_id)
                all_buckets.extend(data.get("data", []))
                page_count += 1
            except Exception:
                break

        for bucket in all_buckets:
            start_time = bucket.get("start_time")
            if start_time is None:
                continue
            date_str = datetime.fromtimestamp(int(start_time), tz=timezone.utc).strftime("%Y-%m-%d")

            bucket_cost = 0.0
            for result in bucket.get("results", []):
                amount_obj = result.get("amount", {})
                cost = float(amount_obj.get("value", 0))
                model = result.get("line_item") or "unknown"

                if model not in model_costs_map:
                    model_costs_map[model] = {"model": model, "cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests": 0}
                model_costs_map[model]["cost"] += cost

                total_cost += cost
                bucket_cost += cost

            if date_str:
                daily_costs_map[date_str] = daily_costs_map.get(date_str, 0.0) + bucket_cost

        # Sort model costs descending
        model_costs = sorted(model_costs_map.values(), key=lambda x: x["cost"], reverse=True)

        # Build daily costs list sorted by date
        daily_costs = [{"date": d, "cost": round(c, 4)} for d, c in sorted(daily_costs_map.items())]

        return {
            "total_cost": total_cost,
            "total_tokens": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "model_costs": model_costs,
            "daily_costs": daily_costs,
        }

    def fetch_per_user_daily_usage(
        self,
        api_key: str,
        organization_id: str,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """
        Fetch per-user, per-model daily token consumption from the OpenAI
        Organization Usage API.

        Calls GET /v1/organization/usage/completions with group_by=user_id,
        group_by=model, and bucket_width=1d. Handles pagination up to 100 pages.

        Args:
            api_key: OpenAI admin API key.
            organization_id: OpenAI organization ID.
            start_date: Start date as YYYY-MM-DD string (inclusive).
            end_date: End date as YYYY-MM-DD string (exclusive).

        Returns:
            List of flat dicts with keys: date, user_id, model, input_tokens,
            output_tokens, input_cached_tokens, num_model_requests.
            Returns [] on any error (never raises).
        """
        try:
            # Convert date strings to Unix timestamps (midnight UTC)
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

            all_records: list[dict] = []
            page_token: str | None = None
            max_pages = 100

            for page_num in range(max_pages):
                # Build endpoint with pagination
                endpoint = (
                    f"/v1/organization/usage/completions"
                    f"?group_by=user_id&group_by=model&bucket_width=1d"
                    f"&start_time={start_ts}&end_time={end_ts}"
                )
                if page_token:
                    endpoint += f"&page={page_token}"

                try:
                    response = self._make_openai_request(
                        endpoint, api_key, organization_id
                    )
                except PermissionError:
                    logger.warning(
                        "OpenAI Usage API auth failed (401/403) during "
                        "fetch_per_user_daily_usage"
                    )
                    return []
                except RuntimeError as e:
                    logger.warning(
                        f"OpenAI Usage API error during fetch_per_user_daily_usage "
                        f"(page {page_num}): {e}"
                    )
                    # On 5xx mid-pagination, return records collected so far
                    return all_records

                # Parse buckets from this page
                for bucket in response.get("data", []):
                    bucket_start = bucket.get("start_time")
                    if bucket_start is None:
                        continue
                    # Convert epoch back to YYYY-MM-DD (UTC)
                    date_str = datetime.fromtimestamp(
                        int(bucket_start), tz=timezone.utc
                    ).strftime("%Y-%m-%d")

                    for result in bucket.get("results", []):
                        record = {
                            "date": date_str,
                            "user_id": result.get("user_id") or "unknown",
                            "model": result.get("model") or "unknown",
                            "input_tokens": max(
                                0, int(result.get("input_tokens") or 0)
                            ),
                            "output_tokens": max(
                                0, int(result.get("output_tokens") or 0)
                            ),
                            "input_cached_tokens": max(
                                0, int(result.get("input_cached_tokens") or 0)
                            ),
                            "num_model_requests": max(
                                0, int(result.get("num_model_requests") or 0)
                            ),
                        }
                        all_records.append(record)

                # Check pagination
                if not response.get("has_more"):
                    break
                page_token = response.get("next_page")
                if not page_token:
                    break
            else:
                # Reached max_pages cap
                logger.warning(
                    f"fetch_per_user_daily_usage hit pagination cap of {max_pages} pages"
                )

            return all_records

        except Exception as e:
            logger.warning(
                f"fetch_per_user_daily_usage failed unexpectedly: {e}"
            )
            return []

    def _fetch_openai_usage_fallback(
        self, api_key: str, organization_id: str,
        start_date: str, end_date: str
    ) -> dict:
        """
        Fallback method to fetch usage data when the primary endpoint is unavailable.

        Uses the /v1/models endpoint to verify API access, then returns
        a structure indicating that detailed usage requires admin API access.
        """
        # Verify the key works by listing models
        try:
            self._make_openai_request("/v1/models", api_key, organization_id)
        except PermissionError:
            raise
        except RuntimeError:
            pass  # Models endpoint might not be critical

        # Return empty structure with guidance
        return {
            "total_cost": 0.0,
            "total_tokens": 0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "model_costs": [],
            "daily_costs": [],
            "note": (
                "Detailed usage data requires an admin API key with organization "
                "billing access. Please update your API key in the Configure tab."
            ),
        }

    def _parse_openai_usage_response(self, data: dict, start_date: str, end_date: str) -> dict:
        """
        Parse the OpenAI usage API response into a normalized format.

        The OpenAI usage API returns data grouped by snapshot/bucket with
        per-model token counts and costs.
        """
        total_cost = 0.0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tokens = 0
        model_costs_map = {}
        daily_costs_map = {}

        # Handle different response formats from OpenAI
        buckets = data.get("data", data.get("daily_costs", []))

        for bucket in buckets:
            # Each bucket may represent a day or a snapshot
            date_str = ""
            timestamp = bucket.get("timestamp", bucket.get("date"))
            if isinstance(timestamp, (int, float)):
                date_str = datetime.fromtimestamp(
                    timestamp, tz=timezone.utc
                ).strftime("%Y-%m-%d")
            elif isinstance(timestamp, str):
                date_str = timestamp[:10]

            line_items = bucket.get("line_items", bucket.get("models", []))

            bucket_cost = 0.0
            for item in line_items:
                model = item.get("name", item.get("model", "unknown"))
                cost = float(item.get("cost", item.get("amount", 0.0)))
                prompt_toks = int(item.get("prompt_tokens", item.get("n_context_tokens_total", 0)))
                completion_toks = int(item.get("completion_tokens", item.get("n_generated_tokens_total", 0)))
                item_tokens = prompt_toks + completion_toks
                requests = int(item.get("num_requests", item.get("requests", 0)))

                # Accumulate per-model
                if model not in model_costs_map:
                    model_costs_map[model] = {
                        "model": model,
                        "cost": 0.0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "requests": 0,
                    }
                model_costs_map[model]["cost"] += cost
                model_costs_map[model]["prompt_tokens"] += prompt_toks
                model_costs_map[model]["completion_tokens"] += completion_toks
                model_costs_map[model]["total_tokens"] += item_tokens
                model_costs_map[model]["requests"] += requests

                total_cost += cost
                total_prompt_tokens += prompt_toks
                total_completion_tokens += completion_toks
                total_tokens += item_tokens
                bucket_cost += cost

            # Accumulate daily cost
            if date_str:
                daily_costs_map[date_str] = daily_costs_map.get(date_str, 0.0) + bucket_cost

        # Sort model costs by cost descending
        model_costs = sorted(
            model_costs_map.values(), key=lambda x: x["cost"], reverse=True
        )

        # Build daily costs list sorted by date
        daily_costs = [
            {"date": date, "cost": round(cost, 4)}
            for date, cost in sorted(daily_costs_map.items())
        ]

        return {
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "model_costs": model_costs,
            "daily_costs": daily_costs,
        }

    # ─── Drilldown Execution ─────────────────────────────────────────────

    def execute_drilldown_plan(self, account_id: str, member_email: str,
                               plan: list, params: dict) -> dict:
        """
        Execute a structured drilldown plan using HTTP requests to AI vendor APIs.

        Each plan step contains:
          - service: base URL domain (e.g. "api.openai.com")
          - operation: HTTP path (e.g. "/v1/models")
          - params: dict with optional headers, query, and body fields

        Builds the full URL as https://{service}{operation}, injects an
        Authorization Bearer header with the account's API key, and issues
        a GET request via urllib.

        On 401/403: returns authError response with partial results.
        On success: returns {drilldownResults: [...], stepCount: N}.

        Args:
            account_id: The cloud account identifier for credential resolution.
            member_email: The member requesting the drilldown.
            plan: A list of Structured Objects from the Tips table drilldownApis field.
            params: Additional context parameters from the original tool invocation.

        Returns:
            A dict with drilldown results or error information.
        """
        creds = self._get_credentials(account_id, member_email)
        api_key = creds['api_key']
        results = []

        for i, step in enumerate(plan):
            svc = step.get('service')    # base URL domain
            op = step.get('operation')   # HTTP path
            call_params = step.get('params', {})

            if not svc or not op:
                logger.warning(f"Skipping malformed AI drilldown step {i}: {step}")
                continue

            # Substitute <each> placeholders from previous results
            if results and isinstance(call_params, dict):
                call_params = _substitute_placeholders(call_params, results[-1])

            headers = call_params.get('headers', {})
            headers['Authorization'] = f'Bearer {api_key}'
            query = call_params.get('query', {})

            url = f"https://{svc}{op}"
            if query:
                query_string = urllib.parse.urlencode(query)
                url = f"{url}?{query_string}"

            req = urllib.request.Request(url, method="GET")
            for hdr_key, hdr_val in headers.items():
                req.add_header(hdr_key, hdr_val)

            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    results.append(json.loads(resp.read().decode("utf-8")))
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    logger.error(f"Auth error on AI drilldown step {i} ({svc}{op}): {e.code}")
                    return {
                        'authError': True,
                        'partialResults': results,
                        'failedStep': i,
                        'guidance': 'Check your API key in the Configure tab.',
                    }
                raise

        return {'drilldownResults': results, 'stepCount': len(results)}
