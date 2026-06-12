# Implementation Plan

## Overview

Fix the login 500 error in `member-handler/lambda_function.py` caused by unconditional top-level imports of optional modules and missing Cognito `InvalidParameterException` handling. The fix wraps optional imports in try/except blocks, adds specific error handling for auth flow misconfiguration, and improves traceback logging.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["1", "2"],
      "description": "Write exploration and preservation tests BEFORE fix"
    },
    {
      "wave": 2,
      "tasks": ["3.1", "3.2", "3.3"],
      "description": "Implement the fix (imports, Cognito handling, logging)"
    },
    {
      "wave": 3,
      "tasks": ["3.4", "3.5"],
      "description": "Verify exploration test passes and preservation tests still pass"
    },
    {
      "wave": 4,
      "tasks": ["4"],
      "description": "Final checkpoint - all tests pass"
    }
  ]
}
```

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Import Failure and Cognito Misconfiguration
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope to concrete failing cases: (a) import with a missing optional module, (b) Cognito InvalidParameterException during login
  - Test Case A: Mock `provider_registry` as unavailable (remove from sys.modules, patch import), then attempt to import `lambda_function` — assert it loads WITHOUT raising `ModuleNotFoundError`
  - Test Case B: Mock `cognito_client.initiate_auth` to raise `InvalidParameterException`, call `handle_login()` with valid email/password — assert response has `statusCode=500` AND body contains `"errorCode": "AuthConfigError"`
  - Test Case C: Mock `cognito_client.initiate_auth` to raise a generic `ClientError`, verify the logged output includes a traceback (not just the exception string)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct - proves the bug exists: ModuleNotFoundError crashes Lambda, InvalidParameterException returns generic error without AuthConfigError code, traceback not logged)
  - Document counterexamples: `ModuleNotFoundError: No module named 'provider_registry'`, generic 500 without structured error code
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Existing Login Paths Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe on UNFIXED code: `handle_login()` with wrong password returns `{'statusCode': 401, body: '{"errorCode":"AuthError","message":"Invalid email or password"}'}`
  - Observe on UNFIXED code: `handle_login()` with empty email returns `{'statusCode': 400, body: '{"errorCode":"InvalidRequest","message":"Email and password are required"}'}`
  - Observe on UNFIXED code: `handle_login()` with `UserNotConfirmedException` returns `{'statusCode': 401, body: '{"errorCode":"AuthError","message":"Please verify your email before logging in"}'}`
  - Observe on UNFIXED code: `handle_login()` with no `COGNITO_CLIENT_ID` and valid DynamoDB credentials returns `{'statusCode': 200}` with token, email, displayName
  - Write property-based tests: for all login inputs where modules are present and Cognito auth flow is valid, assert response status code and error code match the observed behavior patterns
  - Use hypothesis to generate random email/password combinations (empty, whitespace, valid format, special chars) and verify the response matches expected patterns (400 for missing fields, 401 for bad creds, 200 for valid)
  - Verify tests pass on UNFIXED code (since these paths are not affected by the bug)
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix login 500 error

  - [x] 3.1 Wrap optional top-level imports in try/except blocks
    - Replace bare `import provider_registry` with `try: import provider_registry / except ImportError: provider_registry = None`
    - Replace `from cost_cache import _get_cost_data_cached` with try/except, fallback to `None`
    - Replace `from intent_classifier import _classify_intent, get_apis_for_intent` with try/except, fallback to `None`
    - Replace `from provider_router import _route_to_connector` with try/except, fallback to `None`
    - Replace `from parallel_executor import _gather_multi_account_parallel` with try/except, fallback to `None`
    - Add `import traceback` to standard library imports at top of file
    - _Bug_Condition: isBugCondition(input) where input.phase="import" AND anyModuleMissing(...)_
    - _Expected_Behavior: Lambda loads successfully, login endpoint functions independently of optional modules_
    - _Preservation: All existing code paths that USE these modules must check for None before calling_
    - _Requirements: 2.1_

  - [x] 3.2 Add specific Cognito InvalidParameterException handling in handle_login()
    - Add `except cognito_client.exceptions.InvalidParameterException as e:` BEFORE the generic `ClientError` handler
    - Log: `logger.error(f"Cognito auth flow misconfiguration: {e}\n{traceback.format_exc()}")`
    - Return: `create_error_response(500, "AuthConfigError", "Authentication service misconfigured. Please contact support.")`
    - _Bug_Condition: isBugCondition(input) where cognitoAuthFlowNotEnabled('USER_PASSWORD_AUTH')_
    - _Expected_Behavior: Structured 500 with errorCode "AuthConfigError" and descriptive message_
    - _Requirements: 2.2_

  - [x] 3.3 Improve generic exception handler with traceback logging
    - Update the existing `except ClientError as e:` to include `traceback.format_exc()` in the log message
    - Add reference string to response: `"An unexpected error occurred. Reference: cognito_client_error"`
    - Add a catch-all `except Exception as e:` after the ClientError handler with full traceback logging
    - Return structured response: `create_error_response(500, "ServerError", "An unexpected error occurred. Reference: unhandled_exception")`
    - _Bug_Condition: isBugCondition(input) where unexpectedException AND NOT hasStructuredErrorResponse_
    - _Expected_Behavior: Full traceback in CloudWatch logs, structured error response to client_
    - _Requirements: 2.3_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Import Failure and Cognito Misconfiguration
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (Lambda loads without crash, InvalidParameterException returns AuthConfigError)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - Existing Login Paths Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm: 401 for wrong password, 400 for missing fields, 401 for unconfirmed, legacy fallback 200 — all unchanged

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the full test suite for member-handler
  - Verify exploration tests (task 1) now PASS
  - Verify preservation tests (task 2) still PASS
  - Verify no other tests in the project are broken
  - Ensure all tests pass, ask the user if questions arise

## Notes

- The exploration test (task 1) is expected to FAIL on unfixed code — this confirms the bug exists
- The preservation tests (task 2) are expected to PASS on unfixed code — they capture existing correct behavior
- After implementing the fix (task 3), both exploration AND preservation tests should PASS
- The 5 optional modules (`provider_registry`, `cost_cache`, `intent_classifier`, `provider_router`, `parallel_executor`) are used by AI/cost features, not by the login path
- Callers of these optional modules elsewhere in the file should check for `None` before invoking
