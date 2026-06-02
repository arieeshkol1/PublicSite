"""Cost Normalizer — transforms provider-specific cost responses into a unified schema.

Common schema: {date, service_name, cost_amount, currency, cloud_provider, account_id}
"""
import logging

logger = logging.getLogger(__name__)


def normalize_aws(raw_records: list, account_id: str) -> list:
    """Transform AWS Cost Explorer ResultsByTime into common schema.

    AWS format (per time period):
    {
        'TimePeriod': {'Start': '2024-01-15', 'End': '2024-01-16'},
        'Groups': [
            {'Keys': ['Amazon EC2'], 'Metrics': {'UnblendedCost': {'Amount': '45.23', 'Unit': 'USD'}}}
        ]
    }
    """
    normalized = []
    for period in raw_records:
        date = period.get('TimePeriod', {}).get('Start', '')
        for group in period.get('Groups', []):
            service_name = group['Keys'][0] if group.get('Keys') else 'Unknown'
            amount = float(group.get('Metrics', {}).get('UnblendedCost', {}).get('Amount', 0))
            currency = group.get('Metrics', {}).get('UnblendedCost', {}).get('Unit', 'USD')
            if amount > 0.001:
                normalized.append({
                    'date': date,
                    'service_name': service_name,
                    'cost_amount': round(amount, 4),
                    'currency': currency,
                    'cloud_provider': 'aws',
                    'account_id': account_id,
                })
        # Handle ungrouped total (when no Groups key)
        if not period.get('Groups') and period.get('Total'):
            total = period['Total'].get('UnblendedCost', {})
            amount = float(total.get('Amount', 0))
            if amount > 0.001:
                normalized.append({
                    'date': date,
                    'service_name': 'Total',
                    'cost_amount': round(amount, 4),
                    'currency': total.get('Unit', 'USD'),
                    'cloud_provider': 'aws',
                    'account_id': account_id,
                })
    return normalized


def normalize_azure(raw_response: dict, account_id: str) -> list:
    """Transform Azure Cost Management query response into common schema.

    Azure format:
    {
        'properties': {
            'columns': [{'name': 'Cost', 'type': 'Number'}, {'name': 'UsageDate', 'type': 'Number'}, {'name': 'ServiceName', 'type': 'String'}, {'name': 'Currency', 'type': 'String'}],
            'rows': [[45.23, 20240115, 'Virtual Machines', 'USD'], ...]
        }
    }
    """
    normalized = []
    properties = raw_response.get('properties', raw_response)
    columns = properties.get('columns', [])
    rows = properties.get('rows', [])

    # Build column index map
    col_map = {col['name'].lower(): i for i, col in enumerate(columns)}
    cost_idx = col_map.get('cost', col_map.get('pretaxcost', 0))
    date_idx = col_map.get('usagedate', 1)
    service_idx = col_map.get('servicename', col_map.get('metercategory', 2))
    currency_idx = col_map.get('currency', 3)

    for row in rows:
        try:
            amount = float(row[cost_idx])
            if amount <= 0.001:
                continue
            # Azure returns date as integer YYYYMMDD
            raw_date = str(int(row[date_idx]))
            date = f'{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}'
            service_name = str(row[service_idx]) if service_idx < len(row) else 'Unknown'
            currency = str(row[currency_idx]) if currency_idx < len(row) else 'USD'
            normalized.append({
                'date': date,
                'service_name': service_name,
                'cost_amount': round(amount, 4),
                'currency': currency,
                'cloud_provider': 'azure',
                'account_id': account_id,
            })
        except (IndexError, ValueError, TypeError) as e:
            logger.warning(f"Skipping malformed Azure row: {e}")
            continue
    return normalized


def normalize_gcp(raw_response: list, account_id: str) -> list:
    """Transform GCP Cloud Billing / BigQuery response into common schema.

    GCP format (BigQuery billing export rows):
    [
        {'usage_start_time': '2024-01-15T00:00:00Z', 'service': {'description': 'Compute Engine'}, 'cost': 45.23, 'currency': 'USD'},
        ...
    ]

    Or from Cloud Billing API:
    [
        {'date': '2024-01-15', 'service_name': 'Compute Engine', 'cost': 45.23, 'currency': 'USD'}
    ]
    """
    normalized = []
    for record in raw_response:
        try:
            # Support both BigQuery export format and simplified format
            if 'usage_start_time' in record:
                date = record['usage_start_time'][:10]
                service_name = record.get('service', {}).get('description', 'Unknown')
            else:
                date = record.get('date', '')[:10]
                service_name = record.get('service_name', record.get('service', 'Unknown'))

            amount = float(record.get('cost', 0))
            if amount <= 0.001:
                continue
            currency = record.get('currency', 'USD')
            normalized.append({
                'date': date,
                'service_name': service_name,
                'cost_amount': round(amount, 4),
                'currency': currency,
                'cloud_provider': 'gcp',
                'account_id': account_id,
            })
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Skipping malformed GCP record: {e}")
            continue
    return normalized


def aggregate_costs(account_results: list) -> dict:
    """Aggregate normalized cost records from multiple accounts.

    Args:
        account_results: List of dicts, each with:
            - account_id: str
            - cloud_provider: str
            - records: list of normalized cost records
            - error: str or None (if retrieval failed)

    Returns:
        Dict with:
            - all_records: combined list of all successful records
            - by_provider: {provider: {'total': float, 'records': list}}
            - total_cost: float
            - provider_breakdown: [{'provider': str, 'amount': float, 'percentage': float}]
            - failed_accounts: [{'account_id': str, 'cloud_provider': str, 'error': str}]
    """
    all_records = []
    by_provider = {}
    failed_accounts = []

    for result in account_results:
        if result.get('error'):
            failed_accounts.append({
                'account_id': result['account_id'],
                'cloud_provider': result['cloud_provider'],
                'error': result['error'],
            })
            continue

        records = result.get('records', [])
        provider = result['cloud_provider']
        all_records.extend(records)

        if provider not in by_provider:
            by_provider[provider] = {'total': 0, 'records': []}
        by_provider[provider]['records'].extend(records)
        by_provider[provider]['total'] += sum(r['cost_amount'] for r in records)

    total_cost = sum(p['total'] for p in by_provider.values())

    provider_breakdown = []
    for provider, data in sorted(by_provider.items()):
        pct = (data['total'] / total_cost * 100) if total_cost > 0 else 0
        provider_breakdown.append({
            'provider': provider,
            'amount': round(data['total'], 2),
            'percentage': round(pct, 1),
        })

    return {
        'all_records': all_records,
        'by_provider': {p: {'total': round(d['total'], 2), 'records': d['records']} for p, d in by_provider.items()},
        'total_cost': round(total_cost, 2),
        'provider_breakdown': provider_breakdown,
        'failed_accounts': failed_accounts,
    }
