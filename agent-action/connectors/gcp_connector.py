"""
GCP Cloud Connector.

Implements vendor-neutral tool operations using GCP APIs (Compute Engine,
BigQuery Billing Export, Cloud SQL). Extends the base CloudConnector and
follows the same pattern as the AWS connector.

All methods return raw dicts — response normalization is applied upstream
by the Provider Router / Response Normalizer layer.

Authentication uses a service account JSON key stored in the account's
encrypted credentials map in MemberPortal-Accounts DynamoDB table.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import boto3

from . import CloudConnector

logger = logging.getLogger(__name__)


class GCPConnector(CloudConnector):
    """
    GCP-specific implementation of the CloudConnector interface.

    Uses service account JSON key credentials for authentication.
    Each tool method maps to one or more GCP API calls and returns raw
    response data.
    """

    SUPPORTED_OPERATIONS: list[str] = [
        "getComputeInstances",
        "getCostBreakdown",
        "getDatabaseInstances",
    ]

    # ─── Auth Helpers ─────────────────────────────────────────────────────

    def _get_credentials(self, account_id: str, member_email: str) -> dict:
        """
        Retrieve the GCP service account JSON key from the MemberPortal-Accounts
        table's encrypted credentials map.

        Returns the parsed service account key as a dict.
        """
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('MemberPortal-Accounts')

        resp = table.get_item(
            Key={
                'memberEmail': member_email,
                'accountId': account_id,
            },
            ProjectionExpression='credentials',
        )

        item = resp.get('Item', {})
        credentials = item.get('credentials', {})

        # The service account key is stored as a JSON string in the credentials map
        service_account_key = credentials.get('serviceAccountKey', '{}')
        if isinstance(service_account_key, str):
            return json.loads(service_account_key)
        return service_account_key

    def _get_access_token(self, service_account_key: dict) -> str:
        """
        Generate an OAuth2 access token from the service account JSON key.

        Uses the Google OAuth2 token endpoint with a signed JWT to obtain
        a short-lived access token for API calls.
        """
        import time
        import hashlib
        import hmac
        import base64
        import urllib.request
        import urllib.parse

        # Extract key components
        client_email = service_account_key.get('client_email', '')
        private_key = service_account_key.get('private_key', '')
        token_uri = service_account_key.get('token_uri', 'https://oauth2.googleapis.com/token')

        if not client_email or not private_key:
            raise ValueError("Invalid service account key: missing client_email or private_key")

        # Build JWT for token exchange
        now = int(time.time())
        header = base64.urlsafe_b64encode(json.dumps({
            "alg": "RS256",
            "typ": "JWT"
        }).encode()).decode().rstrip('=')

        payload = base64.urlsafe_b64encode(json.dumps({
            "iss": client_email,
            "scope": "https://www.googleapis.com/auth/cloud-platform",
            "aud": token_uri,
            "iat": now,
            "exp": now + 3600,
        }).encode()).decode().rstrip('=')

        # Sign the JWT with the private key
        signing_input = f"{header}.{payload}"

        try:
            # Use cryptography library if available for RSA signing
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            private_key_obj = serialization.load_pem_private_key(
                private_key.encode(), password=None
            )
            signature = private_key_obj.sign(
                signing_input.encode(),
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            encoded_signature = base64.urlsafe_b64encode(signature).decode().rstrip('=')
        except ImportError:
            # Fallback: if cryptography is not available, raise clear error
            raise ImportError(
                "The 'cryptography' package is required for GCP authentication. "
                "Install it with: pip install cryptography"
            )

        jwt_token = f"{header}.{payload}.{encoded_signature}"

        # Exchange JWT for access token
        data = urllib.parse.urlencode({
            'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
            'assertion': jwt_token,
        }).encode()

        req = urllib.request.Request(token_uri, data=data, method='POST')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')

        with urllib.request.urlopen(req, timeout=30) as response:
            token_data = json.loads(response.read().decode())

        return token_data.get('access_token', '')

    def _get_project_id(self, service_account_key: dict) -> str:
        """Extract the GCP project ID from the service account key."""
        return service_account_key.get('project_id', '')

    def _make_gcp_request(self, url: str, access_token: str) -> dict:
        """
        Make an authenticated GET request to a GCP REST API endpoint.

        Returns the parsed JSON response.
        """
        import urllib.request

        req = urllib.request.Request(url, method='GET')
        req.add_header('Authorization', f'Bearer {access_token}')
        req.add_header('Content-Type', 'application/json')

        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())

    def _make_gcp_post_request(self, url: str, access_token: str, body: dict) -> dict:
        """
        Make an authenticated POST request to a GCP REST API endpoint.

        Returns the parsed JSON response.
        """
        import urllib.request

        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Authorization', f'Bearer {access_token}')
        req.add_header('Content-Type', 'application/json')

        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode())

    # ─── Cost Analysis ────────────────────────────────────────────────────

    def get_cost_breakdown(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Get cost breakdown using GCP BigQuery Billing Export.

        Queries the billing export dataset in BigQuery to retrieve cost data
        grouped by service for the previous month, plus daily costs for the
        last 7 days.
        """
        try:
            service_account_key = self._get_credentials(account_id, member_email)
            access_token = self._get_access_token(service_account_key)
            project_id = self._get_project_id(service_account_key)

            if not project_id:
                return {'error': 'No project_id found in service account key'}

            now = datetime.now(timezone.utc)
            # Previous month date range
            first_of_this_month = now.replace(day=1)
            first_of_last_month = (first_of_this_month - timedelta(days=1)).replace(day=1)
            start_date = first_of_last_month.strftime('%Y-%m-%d')
            end_date = first_of_this_month.strftime('%Y-%m-%d')

            # Daily trend: last 7 days
            start_7d = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            today = now.strftime('%Y-%m-%d')

            # Query billing export for cost by service (previous month)
            # Assumes standard billing export dataset: billing_export
            billing_dataset = params.get('billingDataset', f'{project_id}.billing_export')
            billing_table = params.get('billingTable', 'gcp_billing_export_v1')

            # Cost by service query
            service_query = f"""
                SELECT
                    service.description AS service_name,
                    SUM(cost) AS total_cost
                FROM `{billing_dataset}.{billing_table}`
                WHERE usage_start_time >= '{start_date}'
                  AND usage_start_time < '{end_date}'
                GROUP BY service_name
                HAVING total_cost > 0.01
                ORDER BY total_cost DESC
                LIMIT 20
            """

            # Daily costs query (last 7 days)
            daily_query = f"""
                SELECT
                    DATE(usage_start_time) AS usage_date,
                    SUM(cost) AS daily_cost
                FROM `{billing_dataset}.{billing_table}`
                WHERE usage_start_time >= '{start_7d}'
                  AND usage_start_time < '{today}'
                GROUP BY usage_date
                ORDER BY usage_date
            """

            # Execute BigQuery queries
            bq_url = f'https://bigquery.googleapis.com/bigquery/v2/projects/{project_id}/queries'

            # Service breakdown query
            service_resp = self._make_gcp_post_request(bq_url, access_token, {
                'query': service_query,
                'useLegacySql': False,
                'timeoutMs': 30000,
            })

            services = []
            for row in service_resp.get('rows', []):
                fields = row.get('f', [])
                if len(fields) >= 2:
                    service_name = fields[0].get('v', 'Unknown')
                    cost = float(fields[1].get('v', 0))
                    services.append({'service': service_name, 'cost': round(cost, 2)})

            # Daily costs query
            daily_resp = self._make_gcp_post_request(bq_url, access_token, {
                'query': daily_query,
                'useLegacySql': False,
                'timeoutMs': 30000,
            })

            daily_costs = []
            for row in daily_resp.get('rows', []):
                fields = row.get('f', [])
                if len(fields) >= 2:
                    date = fields[0].get('v', '')
                    cost = float(fields[1].get('v', 0))
                    daily_costs.append({'date': date, 'cost': round(cost, 2)})

            total = sum(s['cost'] for s in services)

            return {
                'totalCost30Days': round(total, 2),
                'topServices': services[:10],
                'dailyCosts': daily_costs,
                'period': f'{start_date} to {end_date} (full previous month)',
                'source': 'bigquery_billing_export',
            }
        except Exception as e:
            logger.error(f"GCP get_cost_breakdown error: {e}")
            return {'error': str(e)}

    # ─── Compute & Optimize ───────────────────────────────────────────────

    def get_compute_instances(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List GCP Compute Engine instances using the instances.aggregatedList API.

        Returns instances across all zones in the project.
        """
        try:
            service_account_key = self._get_credentials(account_id, member_email)
            access_token = self._get_access_token(service_account_key)
            project_id = self._get_project_id(service_account_key)

            if not project_id:
                return {'error': 'No project_id found in service account key'}

            # Use aggregatedList to get instances across all zones
            url = (
                f'https://compute.googleapis.com/compute/v1/projects/{project_id}'
                f'/aggregated/instances'
                f'?filter=status%3DRUNNING%20OR%20status%3DTERMINATED%20OR%20status%3DSTOPPED'
            )

            response = self._make_gcp_request(url, access_token)

            instances = []
            items = response.get('items', {})
            for zone_key, zone_data in items.items():
                zone_instances = zone_data.get('instances', [])
                for inst in zone_instances:
                    # Extract zone name from the full zone URL
                    zone_url = inst.get('zone', '')
                    zone_name = zone_url.split('/')[-1] if zone_url else ''
                    # Extract region from zone (e.g., us-central1-a → us-central1)
                    region = '-'.join(zone_name.split('-')[:-1]) if zone_name else ''

                    # Machine type is a full URL, extract just the type name
                    machine_type_url = inst.get('machineType', '')
                    machine_type = machine_type_url.split('/')[-1] if machine_type_url else ''

                    instances.append({
                        'instanceId': inst.get('id', ''),
                        'name': inst.get('name', ''),
                        'type': machine_type,
                        'state': inst.get('status', '').lower(),
                        'region': region,
                        'zone': zone_name,
                        'launchTime': inst.get('creationTimestamp', ''),
                        'networkInterfaces': len(inst.get('networkInterfaces', [])),
                    })

            return {'instances': instances, 'count': len(instances)}
        except Exception as e:
            logger.error(f"GCP get_compute_instances error: {e}")
            return {'error': str(e)}

    # ─── Database & Storage ───────────────────────────────────────────────

    def get_database_instances(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        List Cloud SQL instances using the instances.list API.

        Returns all Cloud SQL instances in the project with their configuration.
        """
        try:
            service_account_key = self._get_credentials(account_id, member_email)
            access_token = self._get_access_token(service_account_key)
            project_id = self._get_project_id(service_account_key)

            if not project_id:
                return {'error': 'No project_id found in service account key'}

            url = f'https://sqladmin.googleapis.com/v1/projects/{project_id}/instances'

            response = self._make_gcp_request(url, access_token)

            instances = []
            for db in response.get('items', []):
                settings = db.get('settings', {})
                tier = settings.get('tier', '')
                storage_gb = int(settings.get('dataDiskSizeGb', 0))
                availability_type = settings.get('availabilityType', 'ZONAL')

                instances.append({
                    'dbId': db.get('name', ''),
                    'instanceClass': tier,
                    'engine': db.get('databaseVersion', ''),
                    'engineVersion': db.get('databaseVersion', ''),
                    'status': db.get('state', '').lower(),
                    'storageGB': storage_gb,
                    'multiAZ': availability_type == 'REGIONAL',
                    'region': db.get('region', ''),
                    'connectionName': db.get('connectionName', ''),
                })

            return {'instances': instances, 'count': len(instances)}
        except Exception as e:
            logger.error(f"GCP get_database_instances error: {e}")
            return {'error': str(e)}

    # ─── Stub Implementations ─────────────────────────────────────────────

    def get_cost_forecast(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get projected cost forecast for GCP.
        TODO: Implement using BigQuery billing export with forecasting.
        """
        return {
            'stub': True,
            'message': 'get_cost_forecast is not yet fully implemented for GCP',
            'tool': 'getCostForecast',
        }

    def get_cost_anomalies(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Detect cost anomalies for GCP.
        TODO: Implement using BigQuery billing export analysis.
        """
        return {
            'stub': True,
            'message': 'get_cost_anomalies is not yet fully implemented for GCP',
            'tool': 'getCostAnomalies',
        }

    def get_rightsizing_recommendations(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get rightsizing recommendations for GCP.
        TODO: Implement using GCP Recommender API.
        """
        return {
            'stub': True,
            'message': 'get_rightsizing_recommendations is not yet fully implemented for GCP',
            'tool': 'getRightsizingRecommendations',
        }

    def get_spot_candidates(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get preemptible/spot VM candidates for GCP.
        TODO: Implement using Compute Engine bulk instance API.
        """
        return {
            'stub': True,
            'message': 'get_spot_candidates is not yet fully implemented for GCP',
            'tool': 'getSpotCandidates',
        }

    def get_licensing_analysis(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Analyze licensing costs for GCP.
        TODO: Implement using Compute Engine license tracking.
        """
        return {
            'stub': True,
            'message': 'get_licensing_analysis is not yet fully implemented for GCP',
            'tool': 'getLicensingAnalysis',
        }

    def get_storage_volumes(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: List Persistent Disk volumes for GCP.
        TODO: Implement using Compute Engine disks.aggregatedList API.
        """
        return {
            'stub': True,
            'message': 'get_storage_volumes is not yet fully implemented for GCP',
            'tool': 'getStorageVolumes',
        }

    def get_object_storage(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: List Cloud Storage buckets for GCP.
        TODO: Implement using Cloud Storage JSON API.
        """
        return {
            'stub': True,
            'message': 'get_object_storage is not yet fully implemented for GCP',
            'tool': 'getObjectStorage',
        }

    def get_network_resources(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: List network resources for GCP.
        TODO: Implement using VPC and Cloud NAT APIs.
        """
        return {
            'stub': True,
            'message': 'get_network_resources is not yet fully implemented for GCP',
            'tool': 'getNetworkResources',
        }

    def get_serverless_functions(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: List Cloud Functions for GCP.
        TODO: Implement using Cloud Functions API.
        """
        return {
            'stub': True,
            'message': 'get_serverless_functions is not yet fully implemented for GCP',
            'tool': 'getServerlessFunctions',
        }

    def get_container_clusters(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: List GKE clusters for GCP.
        TODO: Implement using GKE API.
        """
        return {
            'stub': True,
            'message': 'get_container_clusters is not yet fully implemented for GCP',
            'tool': 'getContainerClusters',
        }

    def get_budgets(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: List Cloud Billing budgets for GCP.
        TODO: Implement using Cloud Billing Budget API.
        """
        return {
            'stub': True,
            'message': 'get_budgets is not yet fully implemented for GCP',
            'tool': 'getBudgets',
        }

    def get_finops_settings(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get FinOps settings for GCP account.
        TODO: Implement using DynamoDB healthcheck results.
        """
        return {
            'stub': True,
            'message': 'get_finops_settings is not yet fully implemented for GCP',
            'tool': 'getFinOpsSettings',
        }

    def get_commitment_coverage(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get committed use discount coverage for GCP.
        TODO: Implement using Billing Committed Use Discounts API.
        """
        return {
            'stub': True,
            'message': 'get_commitment_coverage is not yet fully implemented for GCP',
            'tool': 'getCommitmentCoverage',
        }

    def get_tag_compliance(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get label compliance for GCP resources.
        TODO: Implement using Resource Manager API.
        """
        return {
            'stub': True,
            'message': 'get_tag_compliance is not yet fully implemented for GCP',
            'tool': 'getTagCompliance',
        }

    def get_business_metrics(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Get business metrics for GCP account.
        TODO: Implement using custom metrics from DynamoDB.
        """
        return {
            'stub': True,
            'message': 'get_business_metrics is not yet fully implemented for GCP',
            'tool': 'getBusinessMetrics',
        }

    def get_pricing_data(self, account_id: str, member_email: str, params: dict) -> dict:
        """
        Stub: Query GCP pricing data.
        TODO: Implement using Cloud Billing Catalog API.
        """
        return {
            'stub': True,
            'message': 'get_pricing_data is not yet fully implemented for GCP',
            'tool': 'getPricingData',
        }
