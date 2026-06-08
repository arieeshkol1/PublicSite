# Login 500 Error Bugfix Design

## Overview

The member-handler Lambda (`member-handler/lambda_function.py`) returns a 500 Internal Server Error on the `POST /members/login` route due to two root causes: (1) top-level imports of optional modules (`provider_registry`, `cost_cache`, `intent_classifier`, `provider_router`, `parallel_executor`) crash the Lambda on cold start when those modules are not present in the deployment package, and (2) the Cognito `USER_PASSWORD_AUTH` flow raises an unhandled `InvalidParameterException` when the auth flow is not enabled on the App Client. The fix wraps optional imports in try/except blocks and adds specific Cognito error handling.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — either a missing optional module at import time OR Cognito raising `InvalidParameterException` during `initiate_auth`
- **Property (P)**: The desired behavior — login endpoint responds successfully (200 with tokens) or with a structured error (4xx/5xx with error code and message), never an unhandled crash
- **Preservation**: Existing login behavior for invalid credentials (401), missing fields (400), unconfirmed accounts (401), legacy DynamoDB+bcrypt fallback (200), all must remain unchanged
- **handle_login()**: The function in `member-handler/lambda_function.py` (line ~448) that authenticates members via Cognito or legacy DynamoDB+bcrypt
- **Optional modules**: `provider_registry`, `cost_cache`, `intent_classifier`, `provider_router`, `parallel_executor` — used by AI/cost features, not required for login

## Bug Details

### Bug Condition

The bug manifests in two scenarios: (A) on Lambda cold start when any of the 5 optional modules is missing from the deployment package, causing an `ImportError` that prevents the entire Lambda from loading, and (B) during Cognito authentication when `USER_PASSWORD_AUTH` is not enabled on the App Client, causing an `InvalidParameterException` that is caught only by the generic `ClientError` handler which logs minimally and returns an opaque 500.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type LambdaInvocation
  OUTPUT: boolean
  
  RETURN (input.phase = "import" 
          AND anyModuleMissing(['provider_registry', 'cost_cache', 
              'intent_classifier', 'provider_router', 'parallel_executor']))
         OR (input.phase = "execution"
             AND input.route = "POST /members/login"
             AND cognitoAuthFlowNotEnabled('USER_PASSWORD_AUTH'))
         OR (input.phase = "execution"
             AND input.route = "POST /members/login"
             AND unexpectedException(input)
             AND NOT hasStructuredErrorResponse(input))
END FUNCTION
```

### Examples

- **Import crash**: Lambda cold-starts, `provider_registry` module is not in the ZIP → entire Lambda fails with `ModuleNotFoundError`, 500 returned by API Gateway
- **Cognito InvalidParameterException**: User POSTs valid credentials, `USER_PASSWORD_AUTH` not enabled → `InvalidParameterException` raised → caught by generic `ClientError except` → 500 with "An unexpected error occurred."
- **Missing traceback info**: Network timeout in Cognito call → generic 500 returned, CloudWatch logs show only `Cognito login error: <exception>` with no traceback
- **Non-bug case**: User POSTs wrong password → `NotAuthorizedException` → 401 "Invalid email or password" (correct behavior, unchanged)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Invalid credentials (wrong password) must continue to return 401 with "Invalid email or password"
- Empty email or password must continue to return 400 with "Email and password are required"
- Unconfirmed Cognito accounts must continue to return 401 with "Please verify your email before logging in"
- Missing COGNITO_CLIENT_ID must continue to fall back to legacy DynamoDB+bcrypt authentication
- Valid legacy login must continue to return 200 with JWT token, email, and display name

**Scope:**
All inputs that do NOT involve missing imports or Cognito auth-flow misconfiguration should be completely unaffected by this fix. This includes:
- Normal successful Cognito logins (USER_PASSWORD_AUTH enabled, valid credentials)
- All 401/400 error paths already handled by specific except clauses
- Legacy DynamoDB+bcrypt authentication flow
- All non-login routes (register, accounts, AI agent, etc.)

## Hypothesized Root Cause

Based on the bug analysis, the root causes are:

1. **Unconditional top-level imports**: Lines 26-30 of `lambda_function.py` import `provider_registry`, `cost_cache`, `intent_classifier`, `provider_router`, and `parallel_executor` at module level. If any module is missing (e.g., not included in the Lambda ZIP), Python raises `ModuleNotFoundError` before the handler function can execute.

2. **Missing `InvalidParameterException` handling**: The Cognito `initiate_auth` call can raise `InvalidParameterException` when `USER_PASSWORD_AUTH` is not enabled on the App Client. This is caught only by the generic `ClientError` handler, which doesn't distinguish it from truly unexpected errors.

3. **Insufficient error logging**: The generic `ClientError` handler logs only `f"Cognito login error: {e}"` without a full traceback, making it difficult to diagnose issues in CloudWatch.

4. **No structured error body for unexpected errors**: The generic handler returns `"An unexpected error occurred."` without an error code or traceback reference, giving the frontend no actionable information.

## Correctness Properties

Property 1: Bug Condition - Lambda Cold Start and Login Resilience

_For any_ Lambda invocation where optional modules are missing from the deployment package OR where Cognito raises `InvalidParameterException` due to auth flow misconfiguration, the fixed Lambda SHALL load successfully (no import crash) and `handle_login()` SHALL return a structured JSON response with an appropriate HTTP status code, error code, and descriptive message — never an unhandled 500.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Existing Login Behavior Unchanged

_For any_ login request where all modules are present and no auth flow misconfiguration exists (isBugCondition returns false), the fixed `handle_login()` SHALL produce exactly the same HTTP status code and response body as the original code, preserving all existing error handling (401 for bad credentials, 400 for missing fields, 401 for unconfirmed accounts) and success paths (200 with tokens via Cognito, 200 with JWT via legacy).

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

**File**: `member-handler/lambda_function.py`

**Change 1: Wrap optional imports in try/except blocks (lines 26-30)**

Replace:
```python
import provider_registry
from cost_cache import _get_cost_data_cached
from intent_classifier import _classify_intent, get_apis_for_intent
from provider_router import _route_to_connector
from parallel_executor import _gather_multi_account_parallel
```

With:
```python
try:
    import provider_registry
except ImportError:
    provider_registry = None

try:
    from cost_cache import _get_cost_data_cached
except ImportError:
    _get_cost_data_cached = None

try:
    from intent_classifier import _classify_intent, get_apis_for_intent
except ImportError:
    _classify_intent = None
    get_apis_for_intent = None

try:
    from provider_router import _route_to_connector
except ImportError:
    _route_to_connector = None

try:
    from parallel_executor import _gather_multi_account_parallel
except ImportError:
    _gather_multi_account_parallel = None
```

**Change 2: Add specific Cognito `InvalidParameterException` handling in `handle_login()`**

Add a new except clause before the generic `ClientError` catch:
```python
except cognito_client.exceptions.InvalidParameterException as e:
    logger.error(f"Cognito auth flow misconfiguration: {e}")
    return create_error_response(500, "AuthConfigError", 
        "Authentication service misconfigured. Please contact support.")
```

**Change 3: Improve generic exception handler with traceback logging**

Replace the generic `ClientError` handler:
```python
except ClientError as e:
    logger.error(f"Cognito login error: {e}")
    return create_error_response(500, "ServerError", "An unexpected error occurred.")
```

With:
```python
except ClientError as e:
    import traceback
    logger.error(f"Cognito login error: {e}\n{traceback.format_exc()}")
    return create_error_response(500, "ServerError", "An unexpected error occurred. Reference: cognito_client_error")
```

**Change 4: Add a catch-all exception handler around the entire Cognito block**

After the `ClientError` handler, add:
```python
except Exception as e:
    import traceback
    logger.error(f"Unexpected login error: {type(e).__name__}: {e}\n{traceback.format_exc()}")
    return create_error_response(500, "ServerError", "An unexpected error occurred. Reference: unhandled_exception")
```

**Change 5: Add `import traceback` to the top-level imports**

Add `traceback` to the standard library imports at the top of the file to avoid repeated inline imports.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm that missing imports crash the Lambda and that `InvalidParameterException` results in a generic 500.

**Test Plan**: Write a property-based test that simulates Lambda loading with missing optional modules and verifies the import fails. Also simulate a Cognito `InvalidParameterException` and verify the current code returns an opaque 500 without structured error information.

**Test Cases**:
1. **Import Failure Test**: Mock one of the 5 optional modules as missing, attempt to import `lambda_function` → expect `ModuleNotFoundError` (will fail on unfixed code)
2. **InvalidParameterException Test**: Mock `cognito_client.initiate_auth` to raise `InvalidParameterException` → verify response lacks structured error code (will fail on unfixed code)
3. **Missing Traceback Test**: Mock a generic `ClientError` → verify CloudWatch log lacks traceback info (will fail on unfixed code)

**Expected Counterexamples**:
- `ModuleNotFoundError: No module named 'provider_registry'` prevents Lambda from loading
- `InvalidParameterException` caught as generic `ClientError`, returns opaque error
- Traceback not logged, making post-mortem debugging impossible

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := handle_login_fixed(input)
  ASSERT result.statusCode IN [200, 400, 401, 500]
  ASSERT result.body HAS 'errorCode' OR result.body HAS 'token'
  ASSERT NOT unhandled_crash(result)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT handle_login_original(input) = handle_login_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many combinations of valid/invalid credentials, empty fields, and legacy paths
- It catches edge cases in the input validation paths
- It provides strong guarantees that all 401/400/200 responses remain unchanged

**Test Plan**: Observe behavior on UNFIXED code first for normal login paths (valid credentials, invalid credentials, missing fields, legacy fallback), then write property-based tests capturing that behavior.

**Test Cases**:
1. **Invalid Credentials Preservation**: Verify wrong password still returns 401 "Invalid email or password"
2. **Missing Fields Preservation**: Verify empty email/password still returns 400 "Email and password are required"
3. **Unconfirmed Account Preservation**: Verify unconfirmed account still returns 401 "Please verify your email before logging in"
4. **Legacy Fallback Preservation**: Verify no COGNITO_CLIENT_ID still falls back to DynamoDB+bcrypt
5. **Successful Login Preservation**: Verify valid Cognito login still returns 200 with tokens

### Unit Tests

- Test each optional import wrapped in try/except individually
- Test `handle_login()` with mocked `InvalidParameterException`
- Test `handle_login()` with mocked generic `ClientError` and verify traceback is logged
- Test `handle_login()` with mocked `Exception` and verify structured response

### Property-Based Tests

- Generate random subsets of the 5 optional modules as missing and verify Lambda loads successfully
- Generate random login payloads (valid email formats, empty strings, special characters) and verify consistent response structure
- Generate random Cognito error types and verify each is handled with appropriate status code

### Integration Tests

- Deploy fixed Lambda and verify cold start succeeds with partial module set
- End-to-end login with valid credentials via Cognito
- End-to-end login with valid credentials via legacy DynamoDB+bcrypt fallback
- Verify CloudWatch logs contain full traceback on errors
