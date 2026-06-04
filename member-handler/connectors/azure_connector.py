"""Azure connector — OAuth2 Service Principal + Cost Management API."""
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta
from .base_connector import ProviderConnector, AuthenticationError, CostRetrievalError
from . import register_connector

logger = logging.getLogger(__name__)


class AzureConnector(ProviderConnector):
    """Azure cloud provider connector using Service Principal OAuth2 and Cost Management API."""

    def authenticate(self, credentials: dict) -> dict:
        """Authenticate via OAuth2 client credentials flow.
        
        credentials should contain:
          - tenant_id: Azure AD Tenant ID (UUID)
          - client_id: App Registration Client ID (UUID)
          - client_secret: Client Secret value
        """
        tenant_id = credentials['tenant_id']
        client_id = credentials['client_id']
        client_secret = credentials['client_secret']
        
        token_url = f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'
        
        data = urllib.parse.urlencode({
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
            'scope': 'https://management.azure.com/.default'
        }).encode('utf-8')
        
        try:
            req = urllib.request.Request(token_url, data=data, method='POST')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode('utf-8'))
                access_token = body.get('access_token')
                if not access_token:
                    raise AuthenticationError('Azure OAuth2 returned no access token', provider='azure')
                return {'access_token': access_token, 'token_type': body.get('token_type', 'Bearer')}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')
            logger.error(f"Azure auth failed: {e.code} - {error_body[:500]}")
            if e.code == 401 or e.code == 400:
                raise AuthenticationError(
                    'Azure authentication failed. Please verify your Service Principal credentials '
                    '(Tenant ID, Client ID, Client Secret) and ensure the "Cost Management Reader" role is assigned.',
                    provider='azure'
                )
            raise AuthenticationError(f'Azure authentication error: HTTP {e.code}', provider='azure')
        except Exception as e:
            raise AuthenticationError(f'Azure authentication failed: {e}', provider='azure')

    def test_connection(self, auth_context: dict, account_id: str) -> dict:
        """Test connection by querying Azure Cost Management for recent cost data."""
        try:
            access_token = auth_context['access_token']
            # Query last 7 days of cost data
            end_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            start_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d')
            
            url = f'https://management.azure.com/subscriptions/{account_id}/providers/Microsoft.CostManagement/query?api-version=2023-11-01'
            
            payload = json.dumps({
                'type': 'ActualCost',
                'timeframe': 'Custom',
                'timePeriod': {'from': start_date, 'to': end_date},
                'dataset': {
                    'granularity': 'Daily',
                    'aggregation': {'totalCost': {'name': 'Cost', 'function': 'Sum'}},
                }
            }).encode('utf-8')
            
            req = urllib.request.Request(url, data=payload, method='POST')
            req.add_header('Authorization', f'Bearer {access_token}')
            req.add_header('Content-Type', 'application/json')
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode('utf-8'))
                rows = body.get('properties', body).get('rows', [])
                return {
                    'success': True,
                    'message': 'Azure connection successful',
                    'details': {'days_with_data': len(rows)}
                }
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')
            logger.warning(f"Azure connection test failed: {e.code} - {error_body[:500]}")
            if e.code == 403:
                return {'success': False, 'message': 'Azure connection succeeded but cost data access was denied. Please verify the "Cost Management Reader" role is assigned to the subscription.', 'details': {}}
            return {'success': False, 'message': f'Azure Cost Management query failed: HTTP {e.code}', 'details': {}}
        except Exception as e:
            return {'success': False, 'message': f'Azure connection test failed: {e}', 'details': {}}

    def get_cost_data(self, auth_context: dict, account_id: str, start_date: str, end_date: str) -> dict:
        """Retrieve cost data from Azure Cost Management for AI chat integration.

        Queries:
          1. Cost grouped by ServiceName for the full date range (cost_by_service)
          2. Daily cost trend for the last 7 days (daily_cost_trend)

        Returns normalized structure:
          {
              "cost_by_service": [{"service": str, "cost_usd": float}],
              "daily_cost_trend": [{"date": str, "cost_usd": float}],
              "provider": "azure",
              "error": None
          }

        Raises:
            AuthenticationError: If Azure authentication/authorization fails
            CostRetrievalError: If cost data retrieval fails for non-auth reasons
        """
        try:
            access_token = auth_context['access_token']
        except (KeyError, TypeError):
            raise AuthenticationError(
                'Azure authentication context missing access token. '
                'Please verify your Service Principal credentials.',
                provider='azure'
            )

        # Query 1: Cost by service for the full date range
        cost_by_service = self._query_cost_by_service(access_token, account_id, start_date, end_date)

        # Query 2: Daily cost trend for last 7 days
        trend_end = end_date
        trend_start = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=7)).strftime('%Y-%m-%d')
        daily_cost_trend = self._query_daily_cost_trend(access_token, account_id, trend_start, trend_end)

        return {
            'cost_by_service': cost_by_service,
            'daily_cost_trend': daily_cost_trend,
            'provider': 'azure',
            'error': None
        }

    def _query_cost_by_service(self, access_token: str, account_id: str,
                               start_date: str, end_date: str) -> list:
        """Query Azure Cost Management API for cost data grouped by ServiceName.

        Returns list of {"service": str, "cost_usd": float} dicts.
        """
        url = (f'https://management.azure.com/subscriptions/{account_id}'
               f'/providers/Microsoft.CostManagement/query?api-version=2023-11-01')

        payload = json.dumps({
            'type': 'ActualCost',
            'timeframe': 'Custom',
            'timePeriod': {'from': start_date, 'to': end_date},
            'dataset': {
                'granularity': 'None',
                'aggregation': {'totalCost': {'name': 'Cost', 'function': 'Sum'}},
                'grouping': [{'type': 'Dimension', 'name': 'ServiceName'}],
            }
        }).encode('utf-8')

        body = self._execute_cost_query(access_token, url, payload)
        return self._normalize_cost_by_service(body)

    def _query_daily_cost_trend(self, access_token: str, account_id: str,
                                start_date: str, end_date: str) -> list:
        """Query Azure Cost Management API for daily cost trend.

        Returns list of {"date": str, "cost_usd": float} dicts.
        """
        url = (f'https://management.azure.com/subscriptions/{account_id}'
               f'/providers/Microsoft.CostManagement/query?api-version=2023-11-01')

        payload = json.dumps({
            'type': 'ActualCost',
            'timeframe': 'Custom',
            'timePeriod': {'from': start_date, 'to': end_date},
            'dataset': {
                'granularity': 'Daily',
                'aggregation': {'totalCost': {'name': 'Cost', 'function': 'Sum'}},
            }
        }).encode('utf-8')

        body = self._execute_cost_query(access_token, url, payload)
        return self._normalize_daily_trend(body)

    def _execute_cost_query(self, access_token: str, url: str, payload: bytes) -> dict:
        """Execute a Cost Management API query and return parsed JSON response.

        Raises:
            AuthenticationError: For 401/403 HTTP errors
            CostRetrievalError: For other failures
        """
        try:
            req = urllib.request.Request(url, data=payload, method='POST')
            req.add_header('Authorization', f'Bearer {access_token}')
            req.add_header('Content-Type', 'application/json')

            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')
            logger.error(f"Azure Cost Management query failed: {e.code} - {error_body[:500]}")
            if e.code in (401, 403):
                raise AuthenticationError(
                    'Azure authentication failed or access denied. '
                    'Please verify your Service Principal credentials and ensure the '
                    '"Cost Management Reader" role is assigned to the subscription.',
                    provider='azure'
                )
            raise CostRetrievalError(
                f'Azure Cost Management query failed: HTTP {e.code}',
                provider='azure'
            )
        except urllib.error.URLError as e:
            raise CostRetrievalError(
                f'Azure Cost Management API unreachable: {e.reason}',
                provider='azure'
            )
        except Exception as e:
            raise CostRetrievalError(f'Azure cost retrieval failed: {e}', provider='azure')

    def _normalize_cost_by_service(self, response_body: dict) -> list:
        """Normalize Azure Cost Management grouped-by-service response.

        Azure API returns rows like: [cost, date, service_name, currency]
        With granularity 'None', rows are: [cost, service_name, currency]

        Returns list of {"service": str, "cost_usd": float}.
        """
        properties = response_body.get('properties', response_body)
        rows = properties.get('rows', [])
        columns = properties.get('columns', [])

        # Determine column indices dynamically
        cost_idx = self._find_column_index(columns, 'Cost', fallback=0)
        service_idx = self._find_column_index(columns, 'ServiceName', fallback=1)

        # Aggregate cost per service (in case of duplicate rows)
        service_costs = {}
        for row in rows:
            try:
                service_name = str(row[service_idx]) if len(row) > service_idx else 'Unknown'
                cost_value = float(row[cost_idx]) if len(row) > cost_idx else 0.0
                service_costs[service_name] = service_costs.get(service_name, 0.0) + cost_value
            except (ValueError, TypeError, IndexError):
                continue

        return [
            {'service': service, 'cost_usd': round(cost, 2)}
            for service, cost in sorted(service_costs.items(), key=lambda x: x[1], reverse=True)
            if cost > 0
        ]

    def _normalize_daily_trend(self, response_body: dict) -> list:
        """Normalize Azure Cost Management daily granularity response.

        Azure API returns rows like: [cost, date_int, currency]
        Date is in format YYYYMMDD (integer).

        Returns list of {"date": str (YYYY-MM-DD), "cost_usd": float}.
        """
        properties = response_body.get('properties', response_body)
        rows = properties.get('rows', [])
        columns = properties.get('columns', [])

        # Determine column indices dynamically
        cost_idx = self._find_column_index(columns, 'Cost', fallback=0)
        date_idx = self._find_column_index(columns, 'UsageDate', fallback=1)

        # Aggregate cost per day (in case of duplicate rows)
        daily_costs = {}
        for row in rows:
            try:
                date_raw = row[date_idx] if len(row) > date_idx else None
                cost_value = float(row[cost_idx]) if len(row) > cost_idx else 0.0

                # Azure returns date as integer YYYYMMDD
                if isinstance(date_raw, (int, float)):
                    date_str = str(int(date_raw))
                    date_formatted = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'
                elif isinstance(date_raw, str) and len(date_raw) == 8 and date_raw.isdigit():
                    date_formatted = f'{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}'
                elif isinstance(date_raw, str) and '-' in date_raw:
                    date_formatted = date_raw[:10]  # Already ISO format
                else:
                    continue

                daily_costs[date_formatted] = daily_costs.get(date_formatted, 0.0) + cost_value
            except (ValueError, TypeError, IndexError):
                continue

        return [
            {'date': date, 'cost_usd': round(cost, 2)}
            for date, cost in sorted(daily_costs.items())
        ]

    @staticmethod
    def _find_column_index(columns: list, column_name: str, fallback: int = 0) -> int:
        """Find column index by name in Azure Cost Management response columns.

        Args:
            columns: List of column defs like [{"name": "Cost", "type": "Number"}, ...]
            column_name: Name to search for (case-insensitive)
            fallback: Default index if not found

        Returns:
            Column index (int)
        """
        for i, col in enumerate(columns):
            name = col.get('name', '') if isinstance(col, dict) else str(col)
            if name.lower() == column_name.lower():
                return i
        return fallback


# Auto-register
register_connector('azure', AzureConnector)
