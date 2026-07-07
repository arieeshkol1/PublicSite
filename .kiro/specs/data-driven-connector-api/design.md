# Design Document: Data-Driven Connector API

## Overview

This feature extends the existing `provider_router.route_tool()` flow to support data-driven drilldown execution. When a tool invocation includes a `tipId` parameter, the Provider Router intercepts the call before standard connector dispatch, queries the Tips table for a Drilldown Plan, and delegates execution to the connector using the structured API definitions found in the plan. This eliminates the need for code deployments when adding new vendor API integrations — operators simply update the Tips DynamoDB table.

## Architecture

The key architectural principle: **the existing route_tool flow remains untouched for regular tool calls**. The drilldown plan lookup is an additional path triggered exclusively by the presence of `tipId` in parameters. No existing connector methods are modified — a new `execute_drilldown_plan()` method is added to the connector interface.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     provider_router.route_tool()                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  1. resolve_provider(account_id, member_email)                        │
│  2. Check: does params contain "tipId"?                               │
│     ├─ NO  → existing flow (cache check → connector dispatch)         │
│     └─ YES → drilldown plan flow:                                     │
│              a. Query Tips_Table(service, tipId)                       │
│              b. Detect format (structured vs legacy)                   │
│              c. Validate entries                                       │
│              d. Execute via connector.execute_drilldown_plan()         │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. Drilldown Plan Resolver (in `provider_router.py`)

A new internal function `_resolve_drilldown_plan(service, tip_id)` handles the Tips table lookup:

```python
TIPS_TABLE_NAME = 'ViewMyBill-CostOptimizationTips'

def _resolve_drilldown_plan(service: str, tip_id: str) -> dict:
    """
    Query Tips_Table for the drilldown plan associated with a tip.
    
    Always queries fresh — no in-memory caching.
    
    Returns:
        dict with keys:
          - 'plan': list of structured objects or legacy strings
          - 'format': 'structured' or 'legacy'
        OR error dict with 'error' key on failure.
    """
    dynamodb = _get_dynamodb_resource()
    table = dynamodb.Table(TIPS_TABLE_NAME)
    
    try:
        response = table.get_item(
            Key={'service': service, 'tipId': tip_id}
        )
    except ClientError as e:
        logger.error(f"DynamoDB error fetching drilldown plan for {service}/{tip_id}: {e}")
        return {'error': 'Unable to fetch drilldown plan', 'retryable': True}
    
    item = response.get('Item')
    if not item:
        return {
            'error': 'Drilldown plan not found',
            'guidance': f'No drilldown configuration exists for tip {tip_id} in service {service}.'
        }
    
    drilldown_apis = item.get('drilldownApis', [])
    if not drilldown_apis:
        return {
            'error': 'Drilldown plan not found',
            'guidance': f'Tip {tip_id} exists but has no drilldownApis defined.'
        }
    
    # Detect format by inspecting first element
    fmt = 'structured' if isinstance(drilldown_apis[0], dict) else 'legacy'
    
    return {'plan': drilldown_apis, 'format': fmt}
```

### 2. Format Detection Logic

The format detection is a simple type check on the first element of the `drilldownApis` list:

| First element type | Detected format | Handling |
|---|---|---|
| `dict` | structured | Parse as `{service, operation, params}` objects |
| `str` | legacy | Pass through to existing connector logic |

### 3. Drilldown Plan Executor (in connector base class)

A new method `execute_drilldown_plan()` is added to the `CloudConnector` base class. The AWS connector overrides it to use boto3 dynamic client creation:

```python
# In connectors/__init__.py (CloudConnector base)
def execute_drilldown_plan(self, account_id: str, member_email: str, 
                           plan: list, params: dict) -> dict:
    """Execute a structured drilldown plan. Subclasses override."""
    raise NotImplementedError(
        f"{self.__class__.__name__} does not implement execute_drilldown_plan"
    )
```

```python
# In connectors/aws_connector.py
def execute_drilldown_plan(self, account_id: str, member_email: str,
                           plan: list, params: dict) -> dict:
    """
    Execute a structured drilldown plan using boto3 dynamic clients.
    
    Each entry: {service: str, operation: str, params: dict}
    Maps to: boto3.client(service).operation(**params)
    """
    credentials = self._assume_role(account_id, member_email)
    results = []
    
    for i, step in enumerate(plan):
        # Validate required fields
        svc = step.get('service')
        op = step.get('operation')
        call_params = step.get('params', {})
        
        if not svc or not op:
            logger.warning(f"Skipping malformed drilldown step {i}: {step}")
            continue
        
        # Substitute <each> placeholders from previous results
        if results and isinstance(call_params, dict):
            call_params = _substitute_placeholders(call_params, results[-1])
        
        try:
            client = self._make_client(svc, credentials)
        except Exception as e:
            logger.warning(f"Unrecognized service '{svc}': {e}")
            return {
                'error': f"Unrecognized service: {svc}",
                'healingRequired': True,
                'tipId': params.get('tipId', ''),
                'service': params.get('service', ''),
            }
        
        method = getattr(client, op, None)
        if not method:
            logger.warning(f"Invalid operation '{op}' on service '{svc}'")
            return {
                'error': f"Invalid operation: {op} on service {svc}",
                'healingRequired': True,
                'tipId': params.get('tipId', ''),
                'service': params.get('service', ''),
            }
        
        try:
            result = method(**call_params)
            results.append(result)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ('AccessDeniedException', 'UnauthorizedOperation',
                              'AccessDenied', 'AuthFailure'):
                logger.error(f"Permission error on step {i} ({svc}.{op}): {e}")
                return {
                    'authError': True,
                    'partialResults': results,
                    'failedStep': i,
                    'guidance': 'Check your account connection in the Configure tab.',
                }
            raise
    
    return {'drilldownResults': results, 'stepCount': len(results)}
```

### 4. AI Vendor Drilldown Execution

For AI vendor connectors (OpenAI, Anthropic), the structured object format maps differently:

| Field | AWS meaning | AI vendor meaning |
|---|---|---|
| `service` | boto3 service name (e.g., `ec2`, `ce`) | Base URL domain (e.g., `api.openai.com`) |
| `operation` | API method name (e.g., `describe_instances`) | HTTP path (e.g., `/v1/usage`) |
| `params` | Keyword arguments for boto3 call | Headers, query params, body |

```python
# In connectors/ai_vendor_connector.py
def execute_drilldown_plan(self, account_id: str, member_email: str,
                           plan: list, params: dict) -> dict:
    """Execute drilldown plan using HTTP requests to AI vendor APIs."""
    import requests
    
    api_key = self._get_api_key(account_id, member_email)
    results = []
    
    for i, step in enumerate(plan):
        svc = step.get('service')  # base URL domain
        op = step.get('operation')   # HTTP path
        call_params = step.get('params', {})
        
        if not svc or not op:
            logger.warning(f"Skipping malformed AI drilldown step {i}: {step}")
            continue
        
        headers = call_params.get('headers', {})
        headers['Authorization'] = f'Bearer {api_key}'
        query = call_params.get('query', {})
        
        url = f"https://{svc}{op}"
        
        try:
            resp = requests.get(url, headers=headers, params=query, timeout=10)
            resp.raise_for_status()
            results.append(resp.json())
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in (401, 403):
                return {
                    'authError': True,
                    'partialResults': results,
                    'failedStep': i,
                    'guidance': 'Check your API key in the Configure tab.',
                }
            raise
    
    return {'drilldownResults': results, 'stepCount': len(results)}
```

### 5. Placeholder Substitution

The `<each>` placeholder enables multi-step plans where step N+1 iterates over results from step N:

```python
def _substitute_placeholders(call_params: dict, previous_result: dict) -> dict:
    """
    Replace <each> placeholders in params with values from previous result.
    
    Example:
      params: {"InstanceIds": "<each>"}
      previous_result: {"Reservations": [{"Instances": [{"InstanceId": "i-123"}]}]}
      
    The connector extracts the iterable from previous_result and substitutes.
    """
    substituted = {}
    for key, value in call_params.items():
        if value == '<each>':
            # Extract list values from previous result
            # The previous result is a raw API response; extract the primary list
            substituted[key] = _extract_iterable(previous_result)
        else:
            substituted[key] = value
    return substituted


def _extract_iterable(result: dict) -> list:
    """Extract the primary list from an API response for <each> substitution."""
    # Common AWS response patterns: Items, Reservations, etc.
    for key in result:
        if isinstance(result[key], list) and result[key]:
            return result[key]
    return []
```

## Integration with route_tool()

The modification to `route_tool()` is minimal — a single branch check inserted after provider resolution:

```python
def route_tool(tool_name: str, account_id: str, member_email: str, params: dict) -> dict:
    # Resolve provider (unchanged)
    try:
        provider = resolve_provider(account_id, member_email)
    except AccountNotFoundError:
        return {"error": "Account not connected", "guidance": "..."}
    except ClientError as e:
        return {"error": "Unable to look up account information", "retryable": True, ...}

    # === NEW: Drilldown plan path (triggered by tipId presence) ===
    tip_id = params.get('tipId')
    if tip_id:
        service = params.get('service', '')
        plan_result = _resolve_drilldown_plan(service, tip_id)
        
        if 'error' in plan_result:
            return plan_result
        
        connector = _get_connector(provider)
        plan = plan_result['plan']
        fmt = plan_result['format']
        
        if fmt == 'structured':
            # Validate and filter malformed entries
            valid_steps = [s for s in plan if s.get('service') and s.get('operation')]
            skipped = len(plan) - len(valid_steps)
            if skipped > 0:
                logger.warning(f"Skipped {skipped} malformed entries in plan for {tip_id}")
            
            if not valid_steps:
                return {
                    'error': 'All drilldown plan entries are malformed',
                    'healingRequired': True,
                    'tipId': tip_id,
                    'service': service,
                }
            
            return connector.execute_drilldown_plan(
                account_id, member_email, valid_steps, params
            )
        else:
            # Legacy string-array format — pass to existing connector logic
            return connector.execute_legacy_drilldown(
                account_id, member_email, plan, params
            )

    # === Existing flow (unchanged) ===
    connector = _get_connector(provider)
    # ... cache check, SUPPORTED_OPERATIONS check, dispatch ...
```

## Data Models

### Tips Table Record (DynamoDB)

```json
{
  "service": "EC2",
  "tipId": "ec2-idle-instances",
  "title": "Terminate idle EC2 instances",
  "description": "...",
  "drilldownApis": [
    {
      "service": "ec2",
      "operation": "describe_instances",
      "params": {
        "Filters": [
          {"Name": "instance-state-name", "Values": ["running"]}
        ]
      }
    },
    {
      "service": "cloudwatch",
      "operation": "get_metric_statistics",
      "params": {
        "Namespace": "AWS/EC2",
        "MetricName": "CPUUtilization",
        "Dimensions": "<each>"
      }
    }
  ]
}
```

### Structured Object Schema

```python
StructuredObject = {
    "service": str,      # Required. AWS: boto3 service name. AI: base URL domain.
    "operation": str,    # Required. AWS: method name. AI: HTTP path.
    "params": dict       # Optional. AWS: kwargs. AI: headers/query/body.
}
```

### Response Shapes

**Successful drilldown:**
```json
{
  "drilldownResults": [{...}, {...}],
  "stepCount": 2
}
```

**Permission error (partial results):**
```json
{
  "authError": true,
  "partialResults": [{...}],
  "failedStep": 1,
  "guidance": "Check your account connection in the Configure tab."
}
```

**Healing required:**
```json
{
  "error": "Unrecognized service: fakeservice",
  "healingRequired": true,
  "tipId": "ec2-idle-instances",
  "service": "EC2"
}
```

**Plan not found:**
```json
{
  "error": "Drilldown plan not found",
  "guidance": "No drilldown configuration exists for tip xyz in service EC2."
}
```

## Error Handling

| Error condition | Response shape | Retryable? |
|---|---|---|
| Tip not found in Tips_Table | `{error: "Drilldown plan not found", guidance: ...}` | No |
| DynamoDB ClientError on lookup | `{error: ..., retryable: true}` | Yes |
| Permission error during execution | `{authError: true, partialResults: [...], guidance: ...}` | No (needs config fix) |
| Unrecognized service name | `{error: ..., healingRequired: true, tipId, service}` | No (needs plan fix) |
| Invalid operation on valid service | `{error: ..., healingRequired: true, tipId, service}` | No (needs plan fix) |
| Malformed entry (missing fields) | Skipped, remaining entries processed | N/A |

## Security Considerations

- **Credential scoping**: Drilldown execution uses the same STS AssumeRole mechanism as existing connector methods. No new IAM permissions are granted beyond what the cross-account role already allows.
- **Error sanitization**: Raw AWS/provider error messages are logged server-side only. Member-facing responses contain sanitized guidance strings.
- **No arbitrary code execution**: The `operation` field maps to a method name on a boto3 client object. Python's `getattr` is used, but the target is always a boto3 service client — not arbitrary module imports.

## Testing Strategy

- **Unit tests**: Verify specific scenarios (plan not found, single-step execution, legacy format detection) using mocked DynamoDB and boto3 clients.
- **Property tests**: Validate universal behaviors (format detection, placeholder substitution, error shape invariants, routing bifurcation) across generated inputs with 100+ iterations.
- **Integration tests**: End-to-end validation against a local DynamoDB table with real Tips records, confirming the full route_tool → lookup → execute flow.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: No-cache freshness guarantee

*For any* tipId requested N times within a single Lambda invocation, the Provider Router SHALL issue exactly N DynamoDB GetItem calls to the Tips Table — never reusing a previously fetched result.

**Validates: Requirements 1.2, 6.1, 6.2**

### Property 2: Missing plan produces structured error

*For any* (service, tipId) pair that does not match a record in Tips_Table, the Provider Router SHALL return a dict containing exactly the key `"error"` with value `"Drilldown plan not found"` and a `"guidance"` key with a non-empty string value.

**Validates: Requirements 1.3**

### Property 3: DynamoDB failure returns retryable error

*For any* DynamoDB ClientError raised during drilldown plan lookup, the Provider Router SHALL return a response containing `"retryable": true` and SHALL NOT expose the raw exception message in the response.

**Validates: Requirements 1.4**

### Property 4: Format detection correctness

*For any* `drilldownApis` list, if the first element is a dict the format SHALL be detected as "structured"; if the first element is a string the format SHALL be detected as "legacy". The detection is purely based on the type of the first element.

**Validates: Requirements 2.4**

### Property 5: Structured object execution maps fields correctly

*For any* valid structured object `{service: S, operation: O, params: P}`, the connector SHALL create a provider client for service `S`, invoke method `O` on that client, and pass `P` as keyword arguments — producing a result in the combined response list.

**Validates: Requirements 2.3, 3.1, 3.2**

### Property 6: Sequential execution preserves order and collects all results

*For any* drilldown plan with N valid structured objects, the connector SHALL execute them in index order 0..N-1 and produce a results list of length N (assuming no errors occur).

**Validates: Requirements 3.3**

### Property 7: Placeholder substitution from previous results

*For any* params dict containing the string value `"<each>"` for a key K, and any non-empty previous API result, the connector SHALL replace the `"<each>"` value with a list extracted from the previous result before invoking the next API call.

**Validates: Requirements 3.4**

### Property 8: Permission error stops execution and returns partial results

*For any* N-step drilldown plan where step K (0 ≤ K < N) raises a permission error, the response SHALL contain `"authError": true`, a `"partialResults"` list of length K, and a `"guidance"` string. Steps K+1..N-1 SHALL NOT be executed.

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 9: Malformed entries are skipped, valid entries execute

*For any* drilldown plan containing a mix of valid entries (with both `service` and `operation`) and invalid entries (missing either field), the connector SHALL skip all invalid entries and execute only valid ones, producing results only for valid entries.

**Validates: Requirements 5.1**

### Property 10: Healing response for unrecognized service or operation

*For any* structured object whose `service` field does not map to a valid provider client, OR whose `operation` field does not exist on the resolved client, the connector SHALL return a response with `"healingRequired": true` and SHALL include both the `tipId` and `service` partition key in the response.

**Validates: Requirements 5.2, 5.3, 5.4**

### Property 11: tipId presence bifurcates routing

*For any* tool invocation parameters dict, if `tipId` is present the Provider Router SHALL attempt the drilldown plan lookup path; if `tipId` is absent the Provider Router SHALL follow the existing route_tool dispatch path (cache check → connector method) without any drilldown logic.

**Validates: Requirements 7.1, 7.2, 7.3**
