# Technical Design: Multi-Tag Cost Cache

## Overview

This design enhances the cost data cache to query and store cost breakdowns for **all** active cost allocation tag keys per daily cost item, replacing the current single-tag-key approach. The cache stores a nested structure keyed by tag key name, enabling instant dashboard tag filtering from cache without live Cost Explorer calls.

## Architecture

The enhancement touches four layers of the existing cache system:

```
┌─────────────────────────────────────────────────────────────────┐
│  Dashboard Handler (lambda_function.py)                         │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ Read Cache   │→ │ Read Normalizer  │→ │ Tag Key Lookup   │  │
│  │ (DynamoDB)   │  │ (flat→nested)    │  │ (extract values) │  │
│  └──────────────┘  └──────────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↑ reads
┌─────────────────────────────────────────────────────────────────┐
│  Cost Cache Table (DynamoDB)                                    │
│  pk: {member}#{account}  sk: DAILY#{date}                       │
│  tag_breakdown: { "Environment": {"Prod": 45.2, ...}, ... }    │
└─────────────────────────────────────────────────────────────────┘
                              ↑ writes
┌─────────────────────────────────────────────────────────────────┐
│  Incremental Fetch Engine (incremental_fetch_engine.py)         │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ Tag Key      │→ │ Sequential Tag   │→ │ Top-N Cap +      │  │
│  │ Discovery    │  │ Key Querying     │  │ Size Guard       │  │
│  └──────────────┘  └──────────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. Tag Key Discovery (`_discover_active_tag_keys`)

New method replacing `_get_primary_tag_key`. Returns **all** active tag keys instead of just the first one.

```python
def _discover_active_tag_keys(self, ce_client, date_range: DateRange) -> list[str]:
    """Discover all active cost allocation tag keys for the date range.

    Calls CE get_tags API. On failure, logs warning and returns empty list
    (graceful degradation — tag breakdown is skipped, service data unaffected).

    Returns:
        List of active tag key strings. Empty list on failure or no tags.
    """
    try:
        response = ce_client.get_tags(
            TimePeriod={'Start': date_range.start, 'End': date_range.end}
        )
        tags = response.get('Tags', [])
        if tags:
            logger.info(f"Discovered {len(tags)} active tag keys: {tags}")
            return tags
        logger.info("No active tag keys found, skipping tag breakdown")
        return []
    except Exception as e:
        logger.warning(f"Failed to discover tag keys, skipping tag breakdown: {e}")
        return []
```

### 2. Sequential Tag Key Querying (`_call_ce_by_tag` refactored)

The existing `_call_ce_by_tag` is refactored to accept a single tag key parameter and is called in a loop for each discovered tag key. Error isolation ensures one tag key failure doesn't block others.

```python
def _call_ce_for_single_tag(
    self,
    ce_client,
    date_range: DateRange,
    tag_key: str,
    max_retries: int = 3,
    base_delay: float = 0.1,
) -> dict | None:
    """Query CE GetCostAndUsage for a single tag key with retry.

    Returns None on failure (after retry exhaustion) to allow caller
    to continue with remaining tag keys.
    """
    for attempt in range(max_retries + 1):
        try:
            response = ce_client.get_cost_and_usage(
                TimePeriod={'Start': date_range.start, 'End': date_range.end},
                Granularity='DAILY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'TAG', 'Key': tag_key}],
            )
            return response
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in RETRYABLE_ERROR_CODES and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Transient CE error '%s' for tag '%s' attempt %d/%d, retry in %.2fs",
                    error_code, tag_key, attempt + 1, max_retries, delay,
                )
                time.sleep(delay)
                continue
            logger.warning(
                "Tag key query failed for '%s': %s (code: %s)",
                tag_key, e, error_code,
            )
            return None
    return None


def _fetch_all_tag_breakdowns(
    self,
    ce_client,
    date_range: DateRange,
) -> dict[str, dict[str, dict[str, float]]]:
    """Fetch tag breakdowns for all active tag keys sequentially.

    Returns:
        Nested dict: {tag_key: {date: {tag_value: cost}}}
        Only includes successfully queried tag keys.
    """
    tag_keys = self._discover_active_tag_keys(ce_client, date_range)
    if not tag_keys:
        return {}

    all_tag_data: dict[str, dict[str, dict[str, float]]] = {}
    failed_count = 0

    for tag_key in tag_keys:
        response = self._call_ce_for_single_tag(ce_client, date_range, tag_key)
        if response is None:
            failed_count += 1
            continue
        # Parse response into {date: {value: cost}} for this tag key
        parsed = self._parse_single_tag_response(response, tag_key)
        if parsed:
            all_tag_data[tag_key] = parsed

    if failed_count == len(tag_keys):
        logger.error(f"All {failed_count} tag key queries failed")
    elif failed_count > 0:
        logger.warning(f"{failed_count}/{len(tag_keys)} tag key queries failed")

    return all_tag_data
```

### 3. Tag Response Parser (`_parse_single_tag_response`)

New method that parses a CE response for a single tag key into the nested format. Replaces the flat-format `_parse_tag_response`.

```python
def _parse_single_tag_response(
    self, response: dict, tag_key: str
) -> dict[str, dict[str, float]]:
    """Parse CE tag response for a single tag key into {date: {value: cost}}.

    Rules:
    - Zero-cost values are excluded
    - Empty/missing tag values are stored as "(untagged)"
    - The dollar-sign separator in CE keys ("key$value") is handled

    Returns:
        Dict mapping date to {tag_value: cost_amount}.
    """
    date_data: dict[str, dict[str, float]] = {}

    for period in response.get('ResultsByTime', []):
        period_start = period['TimePeriod']['Start']
        values: dict[str, float] = {}

        for group in period.get('Groups', []):
            raw_key = group['Keys'][0]
            amount = float(group['Metrics']['UnblendedCost']['Amount'])

            if amount == 0.0:
                continue

            # Extract tag value from CE key format
            if raw_key == '' or raw_key == '$' or raw_key == f'{tag_key}$':
                tag_value = '(untagged)'
            elif '$' in raw_key:
                # Format: "tagKey$tagValue" — extract value after $
                tag_value = raw_key.split('$', 1)[1] or '(untagged)'
            else:
                tag_value = raw_key

            values[tag_value] = values.get(tag_value, 0.0) + amount

        if values:
            date_data[period_start] = values

    return date_data
```

### 4. Top-N Cap (`_apply_top_n_cap`)

Limits each tag key to the top 50 values by cost, aggregating discarded values into "(other)".

```python
TOP_N_CAP_DEFAULT = 50


def _apply_top_n_cap(
    self,
    tag_data: dict[str, dict[str, dict[str, float]]],
    top_n: int = TOP_N_CAP_DEFAULT,
) -> dict[str, dict[str, dict[str, float]]]:
    """Retain only top N tag values per tag key by total cost across all dates.

    Discarded values are aggregated into a single "(other)" entry per day.

    Args:
        tag_data: {tag_key: {date: {value: cost}}}
        top_n: Maximum values to retain per tag key.

    Returns:
        Modified tag_data with capped values.
    """
    for tag_key, date_values in tag_data.items():
        # Sum costs across all dates per value
        value_totals: dict[str, float] = {}
        for date_dict in date_values.values():
            for value, cost in date_dict.items():
                if value == '(other)':
                    continue
                value_totals[value] = value_totals.get(value, 0.0) + cost

        if len(value_totals) <= top_n:
            continue

        # Determine top N values
        sorted_values = sorted(value_totals.items(), key=lambda x: x[1], reverse=True)
        top_values = {v[0] for v in sorted_values[:top_n]}

        # Aggregate discarded values into "(other)" per day
        for date_str, day_values in date_values.items():
            other_sum = 0.0
            keys_to_remove = []
            for value, cost in day_values.items():
                if value not in top_values and value != '(untagged)':
                    other_sum += cost
                    keys_to_remove.append(value)
            for k in keys_to_remove:
                del day_values[k]
            if other_sum > 0:
                day_values['(other)'] = day_values.get('(other)', 0.0) + other_sum

    return tag_data
```

### 5. Size Guard (`_apply_size_guard`)

Ensures the serialized tag breakdown fits within DynamoDB's 400KB item limit (using 350KB as a safe threshold).

```python
import json

SIZE_LIMIT_BYTES = 350 * 1024  # 350 KB safe threshold


def _apply_size_guard(
    self,
    tag_data: dict[str, dict[str, dict[str, float]]],
    account_id: str,
) -> dict[str, dict[str, dict[str, float]]]:
    """Remove tag keys with fewest values until serialized size <= 350KB.

    Removal order: tag key with fewest total distinct values first.
    Logs a warning for each removed tag key.

    Args:
        tag_data: {tag_key: {date: {value: cost}}} — already Top-N capped.
        account_id: For logging context.

    Returns:
        Potentially reduced tag_data within size limit.
    """
    while True:
        serialized = json.dumps(tag_data, default=str)
        if len(serialized.encode('utf-8')) <= SIZE_LIMIT_BYTES:
            break
        if not tag_data:
            break

        # Find tag key with fewest total distinct values
        key_value_counts = {
            tk: len(set(v for day in dates.values() for v in day.keys()))
            for tk, dates in tag_data.items()
        }
        smallest_key = min(key_value_counts, key=key_value_counts.get)
        logger.warning(
            "Size guard: removing tag key '%s' (account: %s) — "
            "%d values, breakdown exceeds 350KB",
            smallest_key, account_id, key_value_counts[smallest_key],
        )
        del tag_data[smallest_key]

    return tag_data
```

### 6. Updated `CostDataItem` Data Model

```python
@dataclass
class CostDataItem:
    """Represents a single day's cost data for one account.

    Attributes:
        date: The date in YYYY-MM-DD format.
        cost_amount: Total cost amount for this date.
        currency: Currency code (e.g., "USD").
        service_breakdown: {service_name: cost_amount}
        tag_breakdown: Nested format — {tag_key: {tag_value: cost_amount}}
        fetched_at: ISO 8601 timestamp of when data was fetched.
    """
    date: str
    cost_amount: float
    currency: str
    service_breakdown: dict[str, float] = field(default_factory=dict)
    tag_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    fetched_at: str = ""
```

### 7. Updated `write_cost_data` Serialization

The `write_cost_data` method in `CacheService` is updated to serialize the nested tag_breakdown structure:

```python
# In write_cost_data, the tag_breakdown serialization changes from:
#   {k: str(v) for k, v in item.tag_breakdown.items()}
# To nested format:
if item.tag_breakdown:
    dynamo_item['tag_breakdown'] = {
        tag_key: {tag_val: str(cost) for tag_val, cost in values.items()}
        for tag_key, values in item.tag_breakdown.items()
    }
```

### 8. Read Normalizer (`normalize_tag_breakdown`)

Handles backward compatibility by detecting and converting flat-format cache items.

```python
def normalize_tag_breakdown(
    raw_breakdown: dict,
) -> dict[str, dict[str, float]]:
    """Normalize tag_breakdown to nested format regardless of stored format.

    Detection logic:
    - If first value is a number/string-number → Flat_Format
    - If first value is a dict → Nested_Format (pass through)
    - Empty dict → return empty

    Flat format conversion:
    - "tagKey=tagValue" → grouped under tag_key
    - Keys without "=" → grouped under "unknown"

    Returns:
        Nested format: {tag_key: {tag_value: cost_float}}
    """
    if not raw_breakdown:
        return {}

    # Detect format by inspecting first value
    first_value = next(iter(raw_breakdown.values()))

    if isinstance(first_value, dict):
        # Already nested format — convert string costs to float
        return {
            tag_key: {
                tag_val: float(cost) for tag_val, cost in values.items()
            }
            for tag_key, values in raw_breakdown.items()
        }

    # Flat format: keys are "tagKey=tagValue", values are cost strings/numbers
    nested: dict[str, dict[str, float]] = {}
    for key, cost in raw_breakdown.items():
        cost_float = float(cost)
        if '=' in key:
            tag_key, tag_value = key.split('=', 1)
            nested.setdefault(tag_key, {})[tag_value] = cost_float
        else:
            nested.setdefault('unknown', {})[key] = cost_float

    return nested
```

### 9. Dashboard Read Path Update

The `handle_dashboard_data` tag filter section is updated to use the nested format:

```python
# TAG FILTER MODE: Use nested tag_breakdown from cache
if tag_key and tag_value:
    tb = normalize_tag_breakdown(item.get('tag_breakdown') or {})
    # Direct lookup by tag key
    tag_key_data = tb.get(tag_key, {})
    tag_cost = float(tag_key_data.get(tag_value, 0.0))
    # ... compute daily trends and service allocations from tag_cost
```

When the selected tag key is **not** present in the cached breakdown, the handler falls back to a live CE query with the tag filter applied (existing `_apply_filter_to_ce_call` logic).

## Data Models

### DynamoDB Item Schema (Updated)

| Attribute | Type | Description |
|-----------|------|-------------|
| `pk` | String | `{member_email}#{account_id}` |
| `sk` | String | `DAILY#{YYYY-MM-DD}` |
| `cost_amount` | String | Total daily cost |
| `currency` | String | Currency code |
| `service_breakdown` | Map | `{service: cost_string}` |
| `tag_breakdown` | Map | Nested: `{tag_key: {tag_value: cost_string}}` |
| `fetched_at` | String | ISO 8601 timestamp |
| `ttl` | Number | Unix epoch expiry (90 days) |

### Nested Format Example

```json
{
  "tag_breakdown": {
    "Environment": {
      "Production": "145.23",
      "Staging": "32.10",
      "(untagged)": "8.50"
    },
    "Team": {
      "Backend": "98.40",
      "Frontend": "55.12",
      "(other)": "32.31"
    }
  }
}
```

### Flat Format (Legacy, read-only)

```json
{
  "tag_breakdown": {
    "Environment=Production": "145.23",
    "Environment=Staging": "32.10",
    "Team=Backend": "98.40"
  }
}
```

### 10. Interface Summary

### Updated `_call_ce_by_tag` → `_fetch_all_tag_breakdowns`

**Input:** `ce_client`, `date_range: DateRange`
**Output:** `dict[str, dict[str, dict[str, float]]]` — `{tag_key: {date: {value: cost}}}`

### `normalize_tag_breakdown`

**Input:** `raw_breakdown: dict` (either flat or nested format from DynamoDB)
**Output:** `dict[str, dict[str, float]]` — always nested format with float costs

### `_apply_top_n_cap`

**Input:** `tag_data: dict[str, dict[str, dict[str, float]]]`, `top_n: int = 50`
**Output:** Same structure with each tag key limited to top N values + "(other)"

### `_apply_size_guard`

**Input:** `tag_data: dict[str, dict[str, dict[str, float]]]`, `account_id: str`
**Output:** Same structure, potentially with tag keys removed to fit under 350KB

## Error Handling

| Scenario | Behavior |
|----------|----------|
| `get_tags` API fails | Log warning, return empty tag keys list, skip tag breakdown |
| Single tag key query fails | Log warning with tag key + error code, continue with remaining keys |
| All tag key queries fail | Log error with failure count, store empty tag_breakdown |
| Tag breakdown exceeds 350KB | Size guard removes smallest tag keys with warning logs |
| DynamoDB write fails | Log error, return False — caller still returns fetched data |
| Flat-format cache item read | Read normalizer converts to nested format transparently |
| Key without "=" in flat format | Placed under "unknown" tag key |

## Execution Flow

```
fetch_cost_data(date_ranges, credentials)
  │
  ├─ For each batch_range:
  │   ├─ _call_ce_with_retry(ce_client, batch_range)  → service data
  │   ├─ _parse_ce_response(response)                 → CostDataItem list
  │   │
  │   ├─ _fetch_all_tag_breakdowns(ce_client, batch_range)
  │   │   ├─ _discover_active_tag_keys(ce_client, batch_range)
  │   │   └─ For each tag_key (sequential):
  │   │       └─ _call_ce_for_single_tag(ce_client, batch_range, tag_key)
  │   │           └─ _parse_single_tag_response(response, tag_key)
  │   │
  │   ├─ _apply_top_n_cap(all_tag_data, top_n=50)
  │   ├─ _apply_size_guard(all_tag_data, account_id)
  │   │
  │   └─ Merge into CostDataItem.tag_breakdown per date:
  │       item.tag_breakdown = {tag_key: date_values[item.date]}
  │
  └─ Return all_items

write_cost_data(member_id, account_id, items)
  │
  └─ Serialize tag_breakdown as nested map to DynamoDB

handle_dashboard_data(event)  [read path]
  │
  ├─ Read cache items from DynamoDB
  ├─ normalize_tag_breakdown(item['tag_breakdown'])
  ├─ If tag_key in normalized → extract costs (cache hit)
  └─ If tag_key NOT in normalized → fall back to live CE query
```

## Testing Strategy

### Unit Tests (Example-Based)
- Tag key discovery: verify get_tags is called, handles failure gracefully, handles empty list
- Sequential querying: verify N calls for N tag keys, correct order, error isolation per key
- Retry logic: verify exponential backoff on transient errors
- Size guard logging: verify warning includes tag key name and account ID
- Top-N cap default: verify default is 50
- Dashboard fallback: verify live CE call when tag key not in cache
- Service breakdown isolation: verify service data cached regardless of tag failures

### Property Tests (100+ iterations each)
- Parsing correctness (Property 1): random CE responses → valid nested format
- Size guard invariant (Property 2): oversized breakdowns → always ≤ 350KB
- Top-N ordering (Property 3): random tag values → only highest retained
- Other aggregation (Property 4): discarded values → sum matches "(other)"
- Dashboard extraction (Property 5): nested format → correct value lookup
- Normalization preservation (Property 6): flat format → nested preserves all data
- Normalization idempotence (Property 7): nested format → normalize is no-op
- Error isolation (Property 8): partial failures → successful keys preserved

### Integration Tests
- End-to-end cache write/read with nested format
- Background refresh with multiple tag keys against mocked CE
- Dashboard read path with both flat and nested cached items

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Tag response parsing produces valid nested format

*For any* valid Cost Explorer GetCostAndUsage response grouped by a tag key, parsing the response SHALL produce a dictionary mapping dates to inner dictionaries where: (a) no inner value is zero, (b) empty/missing tag values are stored under the key "(untagged)", and (c) all cost values are positive floats.

**Validates: Requirements 3.1, 3.3, 3.4**

### Property 2: Size guard ensures output fits within DynamoDB limit

*For any* tag breakdown dictionary (regardless of size), after applying the size guard, the UTF-8 encoded JSON serialization of the result SHALL be less than or equal to 350 kilobytes.

**Validates: Requirements 4.2**

### Property 3: Top-N cap retains only highest-cost values

*For any* tag key with more than N values, after applying the Top-N cap, the retained values (excluding "(untagged)" and "(other)") SHALL all have total cost greater than or equal to any discarded value's total cost.

**Validates: Requirements 5.1, 5.2**

### Property 4: Discarded values aggregate into "(other)"

*For any* tag key where values are discarded by the Top-N cap, the "(other)" entry for each day SHALL equal the sum of the discarded values' costs for that day.

**Validates: Requirements 5.4**

### Property 5: Dashboard correctly extracts tag key costs from nested format

*For any* nested tag breakdown and any tag key present in it, extracting the daily costs for that tag key SHALL produce values that exactly match the inner dictionary values stored under that key.

**Validates: Requirements 6.2**

### Property 6: Flat-to-nested normalization preserves all cost data

*For any* flat-format tag breakdown dictionary, normalizing it to nested format SHALL preserve all cost values — the sum of all costs in the flat format SHALL equal the sum of all costs in the resulting nested format, and every "tagKey=tagValue" entry SHALL appear under the correct tag key with the correct value.

**Validates: Requirements 7.1, 7.4**

### Property 7: Nested format normalization is idempotent

*For any* tag breakdown already in nested format, applying the read normalizer SHALL return a dictionary identical to the input (with string costs converted to floats).

**Validates: Requirements 7.2**

### Property 8: Partial tag key failure preserves successful results

*For any* set of N active tag keys where K keys fail (0 < K < N), the resulting tag breakdown SHALL contain exactly N - K tag keys, and each successful tag key's data SHALL be identical to what it would contain if no failures occurred.

**Validates: Requirements 10.1**
