"""Cost Normalizer — transforms provider-specific cost responses into a unified schema.

Common schema: {date, service_name, cost_amount, currency, cloud_provider, account_id}
"""
import logging
from datetime import datetime, timezone, timedelta
import calendar
from collections import defaultdict

logger = logging.getLogger(__name__)


def normalize_openai(raw_records: list, account_id: str) -> list:
    """Transform OpenAI Usage API response into common cost schema.

    OpenAI format (per bucket):
    {
        'object': 'bucket',
        'start_time': 1704067200,  # Unix timestamp
        'end_time': 1704153600,
        'results': [
            {
                'object': 'organization.costs.result',
                'amount': {'value': 0.45, 'currency': 'usd'},
                'line_item': 'GPT-4',
                'project_id': 'proj_abc123',
                'input_tokens': 150000,
                'output_tokens': 45000
            }
        ]
    }

    Returns: list of dicts matching common schema:
    {date, service_name, cost_amount, currency, cloud_provider, account_id,
     input_tokens, output_tokens, project_id}
    """
    normalized = []
    for bucket in raw_records:
        try:
            # Parse Unix timestamp to ISO date (YYYY-MM-DD)
            start_time = bucket.get('start_time')
            if start_time is None:
                logger.warning("Skipping OpenAI bucket with missing start_time")
                continue
            date = datetime.fromtimestamp(int(start_time), tz=timezone.utc).strftime('%Y-%m-%d')

            results = bucket.get('results', [])
            for result in results:
                try:
                    amount_obj = result.get('amount', {})
                    cost_value = float(amount_obj.get('value', 0))
                    currency = amount_obj.get('currency', 'usd').upper()

                    # Extract model name as service_name (lowercase for consistency)
                    line_item = result.get('line_item', 'Unknown')
                    service_name = line_item.lower() if line_item else 'unknown'

                    # Token counts (may not be present in all responses)
                    input_tokens = result.get('input_tokens', 0)
                    output_tokens = result.get('output_tokens', 0)

                    # Project ID (optional, present for per-project breakdowns)
                    project_id = result.get('project_id', None)

                    record = {
                        'date': date,
                        'service_name': service_name,
                        'cost_amount': round(cost_value, 4),
                        'currency': currency,
                        'cloud_provider': 'openai',
                        'account_id': account_id,
                        'input_tokens': int(input_tokens) if input_tokens else 0,
                        'output_tokens': int(output_tokens) if output_tokens else 0,
                    }
                    if project_id:
                        record['project_id'] = project_id

                    normalized.append(record)
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Skipping malformed OpenAI result: {e}")
                    continue
        except (ValueError, TypeError, OSError) as e:
            logger.warning(f"Skipping malformed OpenAI bucket: {e}")
            continue
    return normalized


def format_normalized_to_openai(normalized_records: list) -> list:
    """Reverse normalization — convert common schema records back to OpenAI Usage API format.

    This enables round-trip validation: normalize → format back → re-normalize
    should produce equivalent records.

    Args:
        normalized_records: list of dicts in common schema format

    Returns:
        list of OpenAI bucket dicts matching the Usage API response structure
    """
    from collections import defaultdict

    # Group records by date to reconstruct buckets
    buckets_by_date = defaultdict(list)
    for record in normalized_records:
        date_str = record.get('date', '')
        buckets_by_date[date_str].append(record)

    buckets = []
    for date_str, records in sorted(buckets_by_date.items()):
        try:
            # Parse ISO date to Unix timestamp (start of day UTC)
            dt = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            start_time = int(dt.timestamp())
            # End time is start of next day (24 hours later)
            end_time = start_time + 86400
        except (ValueError, TypeError):
            logger.warning(f"Skipping invalid date in format_normalized_to_openai: {date_str}")
            continue

        results = []
        for record in records:
            result = {
                'object': 'organization.costs.result',
                'amount': {
                    'value': record.get('cost_amount', 0),
                    'currency': record.get('currency', 'USD').lower(),
                },
                'line_item': record.get('service_name', 'unknown'),
            }
            # Include token counts
            input_tokens = record.get('input_tokens', 0)
            output_tokens = record.get('output_tokens', 0)
            if input_tokens:
                result['input_tokens'] = input_tokens
            if output_tokens:
                result['output_tokens'] = output_tokens

            # Include project_id if present
            project_id = record.get('project_id')
            if project_id:
                result['project_id'] = project_id

            results.append(result)

        buckets.append({
            'object': 'bucket',
            'start_time': start_time,
            'end_time': end_time,
            'results': results,
        })

    return buckets

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


def aggregate_cost_by_model(normalized_records: list) -> list:
    """Aggregate costs by model name from normalized OpenAI records.

    Groups costs by model (service_name), sorts by cost descending,
    returns up to 20 models with formatted cost and percentage.

    Args:
        normalized_records: list of dicts from normalize_openai(), each containing
            at minimum 'service_name' and 'cost_amount' fields.

    Returns:
        List of dicts sorted by cost descending, max 20 entries:
        [
            {'model': 'gpt-4', 'cost': 8.20, 'percentage': 65.2},
            {'model': 'gpt-4o-mini', 'cost': 2.15, 'percentage': 17.1},
            ...
        ]
        Costs formatted to 2 decimal places, percentages to 1 decimal place.
    """
    from collections import defaultdict

    # Group costs by model name
    model_costs = defaultdict(float)
    for record in normalized_records:
        model = record.get('service_name', 'unknown')
        cost = float(record.get('cost_amount', 0))
        model_costs[model] += cost

    # Calculate total spend
    total_cost = sum(model_costs.values())

    # Build result list with percentages
    results = []
    for model, cost in model_costs.items():
        percentage = (cost / total_cost * 100) if total_cost > 0 else 0.0
        results.append({
            'model': model,
            'cost': round(cost, 2),
            'percentage': round(percentage, 1),
        })

    # Sort by cost descending, limit to top 20
    results.sort(key=lambda x: x['cost'], reverse=True)
    results = results[:20]

    return results


def calculate_period_change(current_total: float, previous_total: float):
    """Calculate period-over-period percentage change.

    Formula: (current - previous) / previous × 100, rounded to 1 decimal place.

    Args:
        current_total: Total spend for the current period.
        previous_total: Total spend for the previous (comparison) period.

    Returns:
        float: Percentage change rounded to 1 decimal place.
        float('inf'): If previous_total is 0 and current_total > 0 (new spend).
        0.0: If both current_total and previous_total are 0.
    """
    if previous_total == 0:
        if current_total > 0:
            return float('inf')
        return 0.0
    change = (current_total - previous_total) / previous_total * 100
    return round(change, 1)


def aggregate_cost_by_project(normalized_records: list) -> dict:
    """Aggregate normalized cost records by project, sorted by cost descending, capped at 50.

    Args:
        normalized_records: list of normalized cost records, each with at least
            'project_id' and 'cost_amount' fields.

    Returns:
        Dict with:
            - projects: list of {'project_id': str, 'cost': float, 'percentage': float}
              sorted by cost descending, limited to top 50
            - truncated: bool, True if more than 50 projects exist
            - total_projects: int, actual total count of distinct projects
    """
    from collections import defaultdict

    # Group costs by project_id
    project_costs = defaultdict(float)
    for record in normalized_records:
        project_id = record.get('project_id')
        if project_id is None:
            continue
        cost = float(record.get('cost_amount', 0))
        project_costs[project_id] += cost

    total_projects = len(project_costs)
    total_cost = sum(project_costs.values())

    # Sort by cost descending
    sorted_projects = sorted(project_costs.items(), key=lambda x: x[1], reverse=True)

    # Cap at 50 entries
    truncated = total_projects > 50
    top_projects = sorted_projects[:50]

    # Build result with formatted values
    projects = []
    for project_id, cost in top_projects:
        percentage = (cost / total_cost * 100) if total_cost > 0 else 0.0
        projects.append({
            'project_id': project_id,
            'cost': round(cost, 2),
            'percentage': round(percentage, 1),
        })

    return {
        'projects': projects,
        'truncated': truncated,
        'total_projects': total_projects,
    }


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


def aggregate_time_buckets(normalized_records: list, granularity: str) -> list:
    """Aggregate daily cost data into time buckets at the specified granularity.

    Parameters:
        normalized_records: list of normalized cost records, each with 'date' (YYYY-MM-DD)
                           and 'cost_amount' (float) fields.
        granularity: one of 'daily', 'weekly', 'monthly'.
            - daily: groups by individual date
            - weekly: 7-day intervals starting Monday
            - monthly: calendar month intervals

    Returns:
        List of dicts sorted by period_start ascending:
        [
            {'period_start': '2025-01-06', 'period_end': '2025-01-12', 'total_cost': 45.50},
            {'period_start': '2025-01-13', 'period_end': '2025-01-19', 'total_cost': 52.30},
            ...
        ]

    The total spend is preserved across aggregation levels:
    sum of daily costs == sum of weekly bucket costs == sum of monthly bucket costs.
    """
    if not normalized_records:
        return []

    if granularity not in ('daily', 'weekly', 'monthly'):
        raise ValueError(f"Invalid granularity '{granularity}'. Must be 'daily', 'weekly', or 'monthly'.")

    # Group costs by their bucket key
    buckets = defaultdict(float)

    for record in normalized_records:
        date_str = record.get('date', '')
        cost = float(record.get('cost_amount', 0))
        if not date_str:
            continue

        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
        except (ValueError, TypeError):
            logger.warning(f"Skipping record with invalid date: {date_str}")
            continue

        if granularity == 'daily':
            # Bucket key is the date itself; period_start == period_end
            bucket_key = date_str
        elif granularity == 'weekly':
            # Find the Monday of this week (weekday 0 = Monday)
            monday = dt - timedelta(days=dt.weekday())
            bucket_key = monday.strftime('%Y-%m-%d')
        elif granularity == 'monthly':
            # Bucket key is the first day of the month
            bucket_key = dt.strftime('%Y-%m-01')

        buckets[bucket_key] += cost

    # Convert bucket keys to period_start/period_end dicts
    result = []
    for bucket_key in sorted(buckets.keys()):
        total_cost = round(buckets[bucket_key], 4)

        if granularity == 'daily':
            period_start = bucket_key
            period_end = bucket_key
        elif granularity == 'weekly':
            period_start = bucket_key
            monday_dt = datetime.strptime(bucket_key, '%Y-%m-%d')
            sunday_dt = monday_dt + timedelta(days=6)
            period_end = sunday_dt.strftime('%Y-%m-%d')
        elif granularity == 'monthly':
            period_start = bucket_key
            month_dt = datetime.strptime(bucket_key, '%Y-%m-%d')
            last_day = calendar.monthrange(month_dt.year, month_dt.month)[1]
            period_end = month_dt.replace(day=last_day).strftime('%Y-%m-%d')

        result.append({
            'period_start': period_start,
            'period_end': period_end,
            'total_cost': total_cost,
        })

    return result
