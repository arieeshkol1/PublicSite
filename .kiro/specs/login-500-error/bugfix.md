# Bugfix Requirements Document

## Introduction

Users receive a 500 Internal Server Error when attempting to log in to the SlashMyBill member portal via `POST /members/login`. The Lambda function (`member-handler/lambda_function.py`) either crashes on cold start due to missing top-level module imports (`provider_registry`, `cost_cache`, `intent_classifier`, `provider_router`, `parallel_executor`) or fails during the Cognito `USER_PASSWORD_AUTH` flow when the auth flow is not enabled on the App Client. This blocks all member authentication.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the Lambda cold-starts and any top-level import (`provider_registry`, `cost_cache`, `intent_classifier`, `provider_router`, `parallel_executor`) is missing from the deployment package THEN the system returns a 500 Internal Server Error before the handler function executes

1.2 WHEN a user submits valid credentials and the Cognito App Client does not have `USER_PASSWORD_AUTH` flow enabled THEN the system returns a 500 Internal Server Error instead of authenticating the user

1.3 WHEN an unexpected exception occurs inside `handle_login()` (e.g., missing environment variable, network timeout, malformed response) THEN the system returns a generic 500 with no actionable diagnostic information in the response

### Expected Behavior (Correct)

2.1 WHEN the Lambda cold-starts THEN the system SHALL gracefully handle missing optional modules by deferring their import or catching import errors, allowing the login endpoint to function independently

2.2 WHEN a user submits valid credentials via Cognito `USER_PASSWORD_AUTH` THEN the system SHALL return a 200 response with an access token, refresh token, email, display name, tier, and tier limit

2.3 WHEN an unexpected exception occurs inside `handle_login()` THEN the system SHALL log the full exception details (type, message, traceback) and return a structured 500 response with an error code and descriptive message

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user submits invalid credentials (wrong password) THEN the system SHALL CONTINUE TO return a 401 response with "Invalid email or password" message

3.2 WHEN a user submits an empty email or empty password THEN the system SHALL CONTINUE TO return a 400 response with "Email and password are required" message

3.3 WHEN a user with an unconfirmed Cognito account attempts login THEN the system SHALL CONTINUE TO return a 401 response with "Please verify your email before logging in" message

3.4 WHEN Cognito is not configured (no COGNITO_CLIENT_ID) THEN the system SHALL CONTINUE TO fall back to legacy DynamoDB+bcrypt authentication successfully

3.5 WHEN a user submits valid credentials via the legacy DynamoDB+bcrypt path THEN the system SHALL CONTINUE TO return a 200 response with a JWT token, email, and display name
