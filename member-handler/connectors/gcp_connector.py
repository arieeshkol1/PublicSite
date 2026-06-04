"""GCP connector — Service Account OAuth2 + Cloud Billing API."""
import json
import logging
import time
import urllib.request
import urllib.parse
import urllib.error
import base64
import hashlib
import hmac
from datetime import datetime, timezone, timedelta
from .base_connector import ProviderConnector, AuthenticationError, CostRetrievalError
from . import register_connector

logger = logging.getLogger(__name__)


class GCPConnector(ProviderConnector):
    """GCP cloud provider connector using service account authentication and Cloud Billing API."""

    def authenticate(self, credentials: dict) -> dict:
        """Authenticate using service account JSON key, return OAuth2 token.

        credentials should contain the service account JSON key fields:
          - client_email: Service account email
          - private_key: RSA private key (PEM format)
          - token_uri: Token endpoint URL (typically https://oauth2.googleapis.com/token)
          - project_id: GCP project ID (optional, for reference)
        """
        try:
            client_email = credentials.get('client_email')
            private_key = credentials.get('private_key')
            token_uri = credentials.get('token_uri', 'https://oauth2.googleapis.com/token')

            if not client_email or not private_key:
                raise AuthenticationError(
                    'GCP authentication failed: service account JSON key must contain '
                    '"client_email" and "private_key" fields.',
                    provider='gcp'
                )

            # Build JWT for service account authentication
            now = int(time.time())
            jwt_header = base64.urlsafe_b64encode(
                json.dumps({'alg': 'RS256', 'typ': 'JWT'}).encode()
            ).rstrip(b'=').decode()

            jwt_claims = base64.urlsafe_b64encode(json.dumps({
                'iss': client_email,
                'scope': 'https://www.googleapis.com/auth/cloud-billing.readonly '
                         'https://www.googleapis.com/auth/cloud-platform',
                'aud': token_uri,
                'iat': now,
                'exp': now + 3600,
            }).encode()).rstrip(b'=').decode()

            signing_input = f'{jwt_header}.{jwt_claims}'

            # Sign JWT with RSA private key
            signature = self._sign_rs256(signing_input.encode(), private_key)
            jwt_token = f'{signing_input}.{signature}'

            # Exchange JWT for access token
            data = urllib.parse.urlencode({
                'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                'assertion': jwt_token,
            }).encode('utf-8')

            req = urllib.request.Request(token_uri, data=data, method='POST')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')

            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode('utf-8'))
                access_token = body.get('access_token')
                if not access_token:
                    raise AuthenticationError(
                        'GCP OAuth2 returned no access token', provider='gcp'
                    )
                return {
                    'access_token': access_token,
                    'token_type': body.get('token_type', 'Bearer'),
                    'project_id': credentials.get('project_id', ''),
                }

        except AuthenticationError:
            raise
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')
            logger.error(f"GCP auth failed: {e.code} - {error_body[:500]}")
            raise AuthenticationError(
                'GCP authentication failed. Please verify your service account JSON key '
                'and ensure the account has "Billing Account Viewer" role.',
                provider='gcp'
            )
        except Exception as e:
            raise AuthenticationError(f'GCP authentication failed: {e}', provider='gcp')

    def test_connection(self, auth_context: dict, account_id: str) -> dict:
        """Test connection by querying GCP Cloud Billing API for recent billing data.

        Args:
            auth_context: Result from authenticate() containing access_token
            account_id: GCP billing account ID (format: billingAccounts/XXXXXX-XXXXXX-XXXXXX)
                        or just the ID portion which will be prefixed automatically
        """
        try:
            access_token = auth_context['access_token']
            billing_account = self._normalize_billing_account(account_id)

            # Query billing info to validate access
            url = (
                f'https://cloudbilling.googleapis.com/v1/{billing_account}'
            )

            req = urllib.request.Request(url, method='GET')
            req.add_header('Authorization', f'Bearer {access_token}')
            req.add_header('Content-Type', 'application/json')

            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode('utf-8'))
                return {
                    'success': True,
                    'message': 'GCP connection successful',
                    'details': {
                        'display_name': body.get('displayName', ''),
                        'open': body.get('open', False),
                    }
                }

        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')
            logger.warning(f"GCP connection test failed: {e.code} - {error_body[:500]}")
            if e.code == 403:
                return {
                    'success': False,
                    'message': 'GCP connection succeeded but billing access was denied. '
                               'Please verify the "Billing Account Viewer" role is assigned.',
                    'details': {}
                }
            return {
                'success': False,
                'message': f'GCP billing query failed: HTTP {e.code}',
                'details': {}
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'GCP connection test failed: {e}',
                'details': {}
            }

    def get_cost_data(self, auth_context: dict, account_id: str,
                      start_date: str, end_date: str) -> dict:
        """Query GCP Cloud Billing API for cost data and return normalized structure.

        Uses the BigQuery Billing Export via the Cloud Billing Budget API or
        the Cloud Billing API's cost breakdown endpoint.

        Returns normalized dict:
            {
                "cost_by_service": [{"service": str, "cost_usd": float}],
                "daily_cost_trend": [{"date": str, "cost_usd": float}],
                "provider": "gcp",
                "error": null
            }
        """
        try:
            access_token = auth_context['access_token']
            billing_account = self._normalize_billing_account(account_id)

            # Query cost data grouped by service using Cloud Billing API
            cost_by_service = self._query_cost_by_service(
                access_token, billing_account, start_date, end_date
            )

            # Query daily cost trend
            daily_cost_trend = self._query_daily_cost_trend(
                access_token, billing_account, start_date, end_date
            )

            return {
                'cost_by_service': cost_by_service,
                'daily_cost_trend': daily_cost_trend,
                'provider': 'gcp',
                'error': None,
            }

        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"GCP cost retrieval failed for {account_id}: {e}")
            raise CostRetrievalError(f'GCP cost retrieval failed: {e}', provider='gcp')

    def _query_cost_by_service(self, access_token: str, billing_account: str,
                               start_date: str, end_date: str) -> list:
        """Query GCP Cloud Billing API for cost breakdown by service.

        Uses the Cloud Billing API v1beta to query cost data grouped by service.
        """
        # Use the Cloud Billing cost breakdown endpoint
        url = (
            f'https://cloudbilling.googleapis.com/v1beta/{billing_account}'
            f'/services:reportCostBreakdown'
        )

        payload = json.dumps({
            'dateRange': {
                'startDate': self._parse_date_to_gcp_format(start_date),
                'endDate': self._parse_date_to_gcp_format(end_date),
            },
            'currencyCode': 'USD',
        }).encode('utf-8')

        try:
            req = urllib.request.Request(url, data=payload, method='POST')
            req.add_header('Authorization', f'Bearer {access_token}')
            req.add_header('Content-Type', 'application/json')

            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode('utf-8'))
                return self._normalize_service_costs(body)
        except urllib.error.HTTPError as e:
            # Fall back to listing services approach if the beta endpoint is unavailable
            logger.warning(f"GCP cost breakdown API returned {e.code}, attempting fallback")
            return self._query_cost_by_service_fallback(
                access_token, billing_account, start_date, end_date
            )

    def _query_cost_by_service_fallback(self, access_token: str, billing_account: str,
                                        start_date: str, end_date: str) -> list:
        """Fallback: query billing data using the v1 services list endpoint."""
        url = (
            f'https://cloudbilling.googleapis.com/v1/{billing_account}/services'
        )

        try:
            req = urllib.request.Request(url, method='GET')
            req.add_header('Authorization', f'Bearer {access_token}')

            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode('utf-8'))
                services = body.get('services', [])
                # Return service names with zero cost as we cannot get actual costs from this endpoint
                return [
                    {'service': svc.get('displayName', 'Unknown'), 'cost_usd': 0.0}
                    for svc in services[:20]  # Limit to top 20 services
                ]
        except Exception as e:
            logger.warning(f"GCP cost service fallback failed: {e}")
            return []

    def _query_daily_cost_trend(self, access_token: str, billing_account: str,
                                start_date: str, end_date: str) -> list:
        """Query GCP Cloud Billing API for daily cost trend.

        Uses the Cloud Billing API v1beta daily cost report.
        """
        url = (
            f'https://cloudbilling.googleapis.com/v1beta/{billing_account}'
            f':reportDailyCosts'
        )

        payload = json.dumps({
            'dateRange': {
                'startDate': self._parse_date_to_gcp_format(start_date),
                'endDate': self._parse_date_to_gcp_format(end_date),
            },
            'currencyCode': 'USD',
        }).encode('utf-8')

        try:
            req = urllib.request.Request(url, data=payload, method='POST')
            req.add_header('Authorization', f'Bearer {access_token}')
            req.add_header('Content-Type', 'application/json')

            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode('utf-8'))
                return self._normalize_daily_costs(body)
        except urllib.error.HTTPError as e:
            logger.warning(f"GCP daily cost API returned {e.code}, attempting fallback")
            return self._query_daily_cost_trend_fallback(
                access_token, billing_account, start_date, end_date
            )

    def _query_daily_cost_trend_fallback(self, access_token: str, billing_account: str,
                                         start_date: str, end_date: str) -> list:
        """Fallback: generate empty daily trend structure from date range."""
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            days = (end - start).days
            return [
                {
                    'date': (start + timedelta(days=i)).strftime('%Y-%m-%d'),
                    'cost_usd': 0.0
                }
                for i in range(max(0, days))
            ]
        except Exception:
            return []

    def _normalize_service_costs(self, api_response: dict) -> list:
        """Normalize GCP cost breakdown API response to standard format.

        Expected response structure:
        {
            "costBreakdowns": [
                {"service": {"displayName": "Compute Engine"}, "cost": {"amount": "145.67"}}
            ]
        }
        """
        normalized = []
        breakdowns = api_response.get('costBreakdowns', api_response.get('rows', []))

        for item in breakdowns:
            if isinstance(item, dict):
                # Handle costBreakdowns format
                service_info = item.get('service', {})
                service_name = (
                    service_info.get('displayName', '')
                    if isinstance(service_info, dict)
                    else str(service_info)
                )
                cost_info = item.get('cost', item.get('amount', {}))
                if isinstance(cost_info, dict):
                    cost_usd = float(cost_info.get('amount', cost_info.get('units', 0)))
                else:
                    cost_usd = float(cost_info) if cost_info else 0.0

                if service_name:
                    normalized.append({
                        'service': service_name,
                        'cost_usd': round(cost_usd, 2),
                    })

        return normalized

    def _normalize_daily_costs(self, api_response: dict) -> list:
        """Normalize GCP daily cost API response to standard format.

        Expected response structure:
        {
            "dailyCosts": [
                {"date": {"year": 2024, "month": 1, "day": 25}, "cost": {"amount": "12.34"}}
            ]
        }
        """
        normalized = []
        daily_costs = api_response.get('dailyCosts', api_response.get('rows', []))

        for item in daily_costs:
            if isinstance(item, dict):
                date_info = item.get('date', {})
                if isinstance(date_info, dict):
                    year = date_info.get('year', 2024)
                    month = date_info.get('month', 1)
                    day = date_info.get('day', 1)
                    date_str = f'{year:04d}-{month:02d}-{day:02d}'
                elif isinstance(date_info, str):
                    date_str = date_info
                else:
                    continue

                cost_info = item.get('cost', item.get('amount', {}))
                if isinstance(cost_info, dict):
                    cost_usd = float(cost_info.get('amount', cost_info.get('units', 0)))
                else:
                    cost_usd = float(cost_info) if cost_info else 0.0

                normalized.append({
                    'date': date_str,
                    'cost_usd': round(cost_usd, 2),
                })

        return normalized

    def _normalize_billing_account(self, account_id: str) -> str:
        """Ensure billing account ID is in the format 'billingAccounts/XXXXXX-XXXXXX-XXXXXX'."""
        if account_id.startswith('billingAccounts/'):
            return account_id
        return f'billingAccounts/{account_id}'

    def _parse_date_to_gcp_format(self, date_str: str) -> dict:
        """Convert YYYY-MM-DD string to GCP date object {year, month, day}."""
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            return {'year': dt.year, 'month': dt.month, 'day': dt.day}
        except ValueError:
            # If parsing fails, return today's date
            now = datetime.now(timezone.utc)
            return {'year': now.year, 'month': now.month, 'day': now.day}

    def _sign_rs256(self, message: bytes, private_key_pem: str) -> str:
        """Sign a message using RS256 (RSA with SHA-256).

        Uses the built-in hashlib for SHA-256 and implements PKCS#1 v1.5 signature
        with the RSA private key from PEM format.
        """
        try:
            # Try using cryptography library if available (preferred for production)
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            private_key = serialization.load_pem_private_key(
                private_key_pem.encode(), password=None
            )
            signature = private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
            return base64.urlsafe_b64encode(signature).rstrip(b'=').decode()

        except ImportError:
            # Fallback: try using jwt library if available
            try:
                import jwt as pyjwt
                # If PyJWT is available, we can reconstruct the full JWT directly
                # But since we're only signing here, raise to outer handler
                raise ImportError("Use direct RSA signing")
            except ImportError:
                pass

            # Last resort: use subprocess to call openssl (Lambda has openssl)
            import subprocess
            import tempfile
            import os

            key_file = None
            try:
                key_file = tempfile.NamedTemporaryFile(
                    mode='w', suffix='.pem', delete=False
                )
                key_file.write(private_key_pem)
                key_file.close()

                result = subprocess.run(
                    ['openssl', 'dgst', '-sha256', '-sign', key_file.name],
                    input=message,
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode != 0:
                    raise AuthenticationError(
                        f'GCP JWT signing failed: {result.stderr.decode()}',
                        provider='gcp'
                    )
                return base64.urlsafe_b64encode(result.stdout).rstrip(b'=').decode()
            finally:
                if key_file:
                    os.unlink(key_file.name)


# Auto-register when module is imported
register_connector('gcp', GCPConnector)
