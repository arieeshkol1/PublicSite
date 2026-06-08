"""
Azure Cloud Connector.

Implements vendor-neutral tool operations using Azure Management APIs
(Compute, Cost Management, SQL Database, CosmosDB). Extends the base
CloudConnector and follows the same pattern as the AWS connector.

All methods return raw dicts — response normalization is applied upstream
by the Provider Router / Response Normalizer layer.

Authentication uses OAuth2 client credentials flow with tenant_id, client_id,
and client_secret from the account's encrypted credentials map in DynamoDB.
"""

import logging
from datetime import datetime, timedelta, timezone

import boto3
import requests

from . import CloudConnector

logger = logging.getLogger(__name__)

# Azure management API base URLs
AZURE_MANAGEMENT_URL = "https://management.azure.com"
AZURE_AUTH_URL = "https://login.microsoftonline.com"


class AzureConnector(CloudConnector):
    """
    Azure-specific implementation of the CloudConnector interface.

    Uses OAuth2 client credentials for authentication. Each tool method maps
    to one or more Azure Management REST API calls and returns raw response data.
    """

    SUPPORTED_OPERATIONS: list[str] = [
        "getComputeInstances",
        "getCostBreakdown",
        "getDatabaseInstances",
    ]

    # ─── Auth Helpers ─────────────────────────────────────────────────────

    def _get_credentials(self, account_id: str, member_email: str) -> dict:
        """
        Retrieve Azure OAuth2 credentials from the MemberPortal-Accounts table.

        Returns dict with tenant_id, client_id, client_secret, subscription_id.
        """
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('MemberPortal-Accounts')

        resp = table.get_item(
            Key={'memberEmail': member_email, 'accountId': account_id},
            ProjectionExpression='credentials',
        )
        item = resp.get('Item', {})
        credentials = item.get('credentials', {})

        return {
            'tenant_id': credentials.get('tenant_id', ''),
            'client_id': credentials.get('client_id', ''),
            'client_secret': credentials.get('client_secret', ''),
            'subscription_id': credentials.get('subscription_id', account_id),
        }

    def _get_access_token(self, tenant_id: str, client_id: str, client_secret: str) -> str:
        """
        Obtain an OAuth2 access token using client credentials flow.

        Calls Azure AD token endpoint for the management.azure.com resource.
        """
        token_url = f"{AZURE_AUTH_URL}/{tenant_id}/oauth2/v2.0/token"

        response = requests.post(
            token_url,
            data={
                'grant_type': 'client_credentials',
                'client_id': client_id,
                'client_secret': client_secret,
                'scope': 'https://management.azure.com/.default',
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()['access_token']

    def _make_headers(self, access_token: str) -> dict:
        """Build authorization headers for Azure REST API calls."""
        return {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }

    def _authenticate(self, account_id: str, member_email: str) -> tuple:
        """
        Full authentication flow: get credentials, obtain token, return (headers, subscription_id).

        Raises Exception if authentication fails.
        """
        creds = self._get_credentials(account_id, member_email)

        if not creds['tenant_id'] or not creds['client_id'] or not creds['client_secret']:
            raise PermissionError(
                "Azure credentials are incomplete. Please check your account connection "
                "in the Configure tab."
            )

        access_token = self._get_access_token(
            creds['tenant_id'],
            creds['client_id'],
            creds['client_secret'],
        )
        headers = self._make_headers(access_token)
        subscription_id = creds['subscription_id']

        return headers, subscription_id

    # ─── Cost Analysis ────────────────────────────────────────────────────

    def get_cost_breakdown(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get cost breakdown by service using Azure Cost Management API.

        Calls the Cost Management query API to get costs grouped by service name
        for the previous month.
        """
        try:
            headers, subscription_id = self._authenticate(account_id, member_email)

            # Calculate date range (previous full month)
            now = datetime.now(timezone.utc)
            first_of_this_month = now.replace(day=1)
            last_month_end = first_of_this_month - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)

            start_date = last_month_start.strftime('%Y-%m-%dT00:00:00+00:00')
            end_date = last_month_end.strftime('%Y-%m-%dT23:59:59+00:00')

            # Azure Cost Management query endpoint
            url = (
                f"{AZURE_MANAGEMENT_URL}/subscriptions/{subscription_id}"
                f"/providers/Microsoft.CostManagement/query"
                f"?api-version=2023-11-01"
            )

            # Query cost grouped by ServiceName
            payload = {
                "type": "ActualCost",
                "timeframe": "Custom",
                "timePeriod": {
                    "from": start_date,
                    "to": end_date,
                },
                "dataset": {
                    "granularity": "None",
                    "aggregation": {
                        "totalCost": {
                            "name": "Cost",
                            "function": "Sum",
                        }
                    },
                    "grouping": [
                        {
                            "type": "Dimension",
                            "name": "ServiceName",
                        }
                    ],
                },
            }

            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()

            # Parse Cost Management response
            columns = data.get('properties', {}).get('columns', [])
            rows = data.get('properties', {}).get('rows', [])

            # Identify column indices
            cost_idx = next(
                (i for i, c in enumerate(columns) if c.get('name') == 'Cost'), 0
            )
            service_idx = next(
                (i for i, c in enumerate(columns) if c.get('name') == 'ServiceName'), 1
            )

            services = []
            total_cost = 0.0
            for row in rows:
                cost = float(row[cost_idx]) if len(row) > cost_idx else 0.0
                service_name = row[service_idx] if len(row) > service_idx else 'Unknown'
                if cost > 0.01:
                    services.append({'service': service_name, 'cost': round(cost, 2)})
                    total_cost += cost

            services.sort(key=lambda x: x['cost'], reverse=True)

            # Get daily costs for last 7 days
            daily_start = (now - timedelta(days=7)).strftime('%Y-%m-%dT00:00:00+00:00')
            daily_end = now.strftime('%Y-%m-%dT23:59:59+00:00')

            daily_payload = {
                "type": "ActualCost",
                "timeframe": "Custom",
                "timePeriod": {
                    "from": daily_start,
                    "to": daily_end,
                },
                "dataset": {
                    "granularity": "Daily",
                    "aggregation": {
                        "totalCost": {
                            "name": "Cost",
                            "function": "Sum",
                        }
                    },
                },
            }

            daily_response = requests.post(
                url, headers=headers, json=daily_payload, timeout=60
            )
            daily_costs = []
            if daily_response.status_code == 200:
                daily_data = daily_response.json()
                daily_rows = daily_data.get('properties', {}).get('rows', [])
                daily_columns = daily_data.get('properties', {}).get('columns', [])
                daily_cost_idx = next(
                    (i for i, c in enumerate(daily_columns) if c.get('name') == 'Cost'), 0
                )
                daily_date_idx = next(
                    (i for i, c in enumerate(daily_columns) if c.get('name') == 'UsageDate'), 1
                )
                for row in daily_rows:
                    date_val = str(row[daily_date_idx]) if len(row) > daily_date_idx else ''
                    cost_val = float(row[daily_cost_idx]) if len(row) > daily_cost_idx else 0.0
                    # Azure returns dates as YYYYMMDD integers
                    if len(date_val) == 8:
                        date_val = f"{date_val[:4]}-{date_val[4:6]}-{date_val[6:8]}"
                    daily_costs.append({'date': date_val, 'cost': round(cost_val, 2)})

            period = (
                f"{last_month_start.strftime('%Y-%m-%d')} to "
                f"{last_month_end.strftime('%Y-%m-%d')} (full previous month)"
            )

            return {
                'totalCost30Days': round(total_cost, 2),
                'topServices': services[:10],
                'dailyCosts': daily_costs,
                'period': period,
            }
        except PermissionError:
            raise
        except Exception as e:
            return {'error': str(e)}

    # ─── Compute & Optimize ───────────────────────────────────────────────

    def get_compute_instances(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List Azure Virtual Machines across the subscription.

        Calls the Azure Compute Management API to list all VMs with their
        instance details including size, power state, and location.
        """
        try:
            headers, subscription_id = self._authenticate(account_id, member_email)

            # List all VMs in the subscription
            url = (
                f"{AZURE_MANAGEMENT_URL}/subscriptions/{subscription_id}"
                f"/providers/Microsoft.Compute/virtualMachines"
                f"?api-version=2024-03-01&statusOnly=true"
            )

            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()

            instances = []
            for vm in data.get('value', []):
                properties = vm.get('properties', {})
                hardware = properties.get('hardwareProfile', {})
                instance_view = properties.get('instanceView', {})

                # Extract power state from statuses
                state = 'unknown'
                for status in instance_view.get('statuses', []):
                    code = status.get('code', '')
                    if code.startswith('PowerState/'):
                        state = code.replace('PowerState/', '')
                        break

                # Extract name from resource ID
                resource_id = vm.get('id', '')
                name = vm.get('name', resource_id.split('/')[-1] if resource_id else '')

                # Extract location/region
                location = vm.get('location', '')

                instances.append({
                    'instanceId': resource_id,
                    'type': hardware.get('vmSize', ''),
                    'state': state,
                    'name': name,
                    'region': location,
                    'az': vm.get('zones', [''])[0] if vm.get('zones') else '',
                    'launchTime': properties.get('timeCreated', ''),
                })

            return {'instances': instances, 'count': len(instances)}
        except PermissionError:
            raise
        except Exception as e:
            return {'error': str(e)}

    # ─── Database & Storage ───────────────────────────────────────────────

    def get_database_instances(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List Azure SQL Database servers and CosmosDB accounts.

        Calls both the Azure SQL Management API and CosmosDB Management API
        to return a combined list of database instances.
        """
        try:
            headers, subscription_id = self._authenticate(account_id, member_email)

            instances = []

            # List Azure SQL Servers and their databases
            sql_url = (
                f"{AZURE_MANAGEMENT_URL}/subscriptions/{subscription_id}"
                f"/providers/Microsoft.Sql/servers"
                f"?api-version=2023-05-01-preview"
            )

            sql_response = requests.get(sql_url, headers=headers, timeout=60)
            if sql_response.status_code == 200:
                sql_data = sql_response.json()
                for server in sql_data.get('value', []):
                    server_name = server.get('name', '')
                    server_location = server.get('location', '')
                    server_id = server.get('id', '')

                    # List databases on this server
                    db_url = (
                        f"{AZURE_MANAGEMENT_URL}{server_id}/databases"
                        f"?api-version=2023-05-01-preview"
                    )
                    db_response = requests.get(db_url, headers=headers, timeout=30)
                    if db_response.status_code == 200:
                        db_data = db_response.json()
                        for db in db_data.get('value', []):
                            db_props = db.get('properties', {})
                            sku = db.get('sku', {})

                            instances.append({
                                'dbId': db.get('name', ''),
                                'instanceClass': sku.get('name', ''),
                                'engine': 'Azure SQL',
                                'engineVersion': '',
                                'status': db_props.get('status', ''),
                                'storageGB': round(
                                    db_props.get('maxSizeBytes', 0) / (1024 ** 3), 1
                                ),
                                'multiAZ': db_props.get('zoneRedundant', False),
                                'serverName': server_name,
                                'region': server_location,
                            })

            # List CosmosDB accounts
            cosmos_url = (
                f"{AZURE_MANAGEMENT_URL}/subscriptions/{subscription_id}"
                f"/providers/Microsoft.DocumentDB/databaseAccounts"
                f"?api-version=2024-02-15-preview"
            )

            cosmos_response = requests.get(cosmos_url, headers=headers, timeout=60)
            if cosmos_response.status_code == 200:
                cosmos_data = cosmos_response.json()
                for account in cosmos_data.get('value', []):
                    account_props = account.get('properties', {})
                    locations = account_props.get('locations', [])

                    instances.append({
                        'dbId': account.get('name', ''),
                        'instanceClass': account_props.get('databaseAccountOfferType', ''),
                        'engine': 'CosmosDB',
                        'engineVersion': account_props.get('apiProperties', {}).get(
                            'serverVersion', ''
                        ),
                        'status': account_props.get('provisioningState', ''),
                        'storageGB': None,
                        'multiAZ': len(locations) > 1,
                        'region': locations[0].get('locationName', '') if locations else '',
                    })

            return {'instances': instances, 'count': len(instances)}
        except PermissionError:
            raise
        except Exception as e:
            return {'error': str(e)}

    # ─── Stub Implementations ─────────────────────────────────────────────

    def get_cost_forecast(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get projected cost forecast.
        TODO: Implement using Azure Cost Management Forecast API.
        """
        return {
            'stub': True,
            'message': 'get_cost_forecast is not yet fully implemented for Azure',
            'tool': 'getCostForecast',
        }

    def get_cost_anomalies(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Detect cost anomalies.
        TODO: Implement using Azure Cost Management Alerts/Anomalies API.
        """
        return {
            'stub': True,
            'message': 'get_cost_anomalies is not yet fully implemented for Azure',
            'tool': 'getCostAnomalies',
        }

    def get_rightsizing_recommendations(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get rightsizing recommendations.
        TODO: Implement using Azure Advisor Recommendations API.
        """
        return {
            'stub': True,
            'message': 'get_rightsizing_recommendations is not yet fully implemented for Azure',
            'tool': 'getRightsizingRecommendations',
        }

    def get_spot_candidates(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Identify spot/low-priority VM candidates.
        TODO: Implement using Azure Spot VM pricing and eviction rate APIs.
        """
        return {
            'stub': True,
            'message': 'get_spot_candidates is not yet fully implemented for Azure',
            'tool': 'getSpotCandidates',
        }

    def get_licensing_analysis(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Analyze software licensing costs.
        TODO: Implement using Azure Hybrid Benefit and License Manager APIs.
        """
        return {
            'stub': True,
            'message': 'get_licensing_analysis is not yet fully implemented for Azure',
            'tool': 'getLicensingAnalysis',
        }

    def get_storage_volumes(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: List Azure Managed Disks.
        TODO: Implement using Microsoft.Compute/disks API.
        """
        return {
            'stub': True,
            'message': 'get_storage_volumes is not yet fully implemented for Azure',
            'tool': 'getStorageVolumes',
        }

    def get_object_storage(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: List Azure Blob Storage accounts/containers.
        TODO: Implement using Microsoft.Storage/storageAccounts API.
        """
        return {
            'stub': True,
            'message': 'get_object_storage is not yet fully implemented for Azure',
            'tool': 'getObjectStorage',
        }

    def get_network_resources(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: List Azure network resources (NAT Gateways, Load Balancers, Public IPs).
        TODO: Implement using Microsoft.Network APIs.
        """
        return {
            'stub': True,
            'message': 'get_network_resources is not yet fully implemented for Azure',
            'tool': 'getNetworkResources',
        }

    def get_serverless_functions(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: List Azure Functions.
        TODO: Implement using Microsoft.Web/sites API filtered by kind=functionapp.
        """
        return {
            'stub': True,
            'message': 'get_serverless_functions is not yet fully implemented for Azure',
            'tool': 'getServerlessFunctions',
        }

    def get_container_clusters(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: List AKS clusters.
        TODO: Implement using Microsoft.ContainerService/managedClusters API.
        """
        return {
            'stub': True,
            'message': 'get_container_clusters is not yet fully implemented for Azure',
            'tool': 'getContainerClusters',
        }

    def get_budgets(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: List Azure Budgets.
        TODO: Implement using Microsoft.Consumption/budgets API.
        """
        return {
            'stub': True,
            'message': 'get_budgets is not yet fully implemented for Azure',
            'tool': 'getBudgets',
        }

    def get_finops_settings(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get FinOps settings for Azure account.
        TODO: Implement using cached healthcheck results from DynamoDB.
        """
        return {
            'stub': True,
            'message': 'get_finops_settings is not yet fully implemented for Azure',
            'tool': 'getFinOpsSettings',
        }

    def get_commitment_coverage(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get Azure reservation coverage.
        TODO: Implement using Microsoft.Consumption/reservationSummaries API.
        """
        return {
            'stub': True,
            'message': 'get_commitment_coverage is not yet fully implemented for Azure',
            'tool': 'getCommitmentCoverage',
        }

    def get_tag_compliance(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get Azure tag compliance status.
        TODO: Implement using Azure Policy and Resource Graph APIs.
        """
        return {
            'stub': True,
            'message': 'get_tag_compliance is not yet fully implemented for Azure',
            'tool': 'getTagCompliance',
        }

    def get_business_metrics(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get business metrics.
        TODO: Implement using custom metrics from DynamoDB or Azure Monitor.
        """
        return {
            'stub': True,
            'message': 'get_business_metrics is not yet fully implemented for Azure',
            'tool': 'getBusinessMetrics',
        }

    def get_monthly_trend(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get monthly cost trend.
        TODO: Implement using Azure Cost Management query API with monthly granularity.
        """
        return {
            'stub': True,
            'message': 'get_monthly_trend is not yet fully implemented for Azure',
            'tool': 'getMonthlyTrend',
        }

    def get_pricing_data(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Query Azure Retail Pricing API.
        TODO: Implement using Azure Retail Prices API.
        """
        return {
            'stub': True,
            'message': 'get_pricing_data is not yet fully implemented for Azure',
            'tool': 'getPricingData',
        }
