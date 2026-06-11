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
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

import boto3

from . import CloudConnector

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
        "getAIVendorUsage",
        "getMonthlyTrend",
    ]

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
            with urllib.request.urlopen(req, timeout=30) as resp:
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

        # Fetch additional pages (max 5)
        page_count = 1
        while data.get("has_more") and data.get("next_page") and page_count < 5:
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
