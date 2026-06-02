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
        """Retrieve daily cost data grouped by service from Azure Cost Management."""
        try:
            access_token = auth_context['access_token']
            url = f'https://management.azure.com/subscriptions/{account_id}/providers/Microsoft.CostManagement/query?api-version=2023-11-01'
            
            payload = json.dumps({
                'type': 'ActualCost',
                'timeframe': 'Custom',
                'timePeriod': {'from': start_date, 'to': end_date},
                'dataset': {
                    'granularity': 'Daily',
                    'aggregation': {'totalCost': {'name': 'Cost', 'function': 'Sum'}},
                    'grouping': [{'type': 'Dimension', 'name': 'ServiceName'}],
                }
            }).encode('utf-8')
            
            req = urllib.request.Request(url, data=payload, method='POST')
            req.add_header('Authorization', f'Bearer {access_token}')
            req.add_header('Content-Type', 'application/json')
            
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            raise CostRetrievalError(f'Azure cost retrieval failed: {e}', provider='azure')


# Auto-register
register_connector('azure', AzureConnector)
