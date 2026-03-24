# Implementation Plan: Admin Panel

## Overview

Build a login-protected admin dashboard for the "Slash My Bill" tool. The implementation adds a single Python Lambda with route-based dispatch for authentication and CRUD operations, a vanilla HTML/CSS/JS frontend, CloudFormation infrastructure additions, and GitHub Actions deployment updates. Tasks are ordered so each step builds on the previous, with no orphaned code.

## Tasks

- [x] 1. Create Admin Handler Lambda with authentication
  - [x] 1.1 Create `admin-handler/lambda_function.py` with route dispatcher, CORS helpers, and login handler
    - Implement `lambda_handler` that reads `event['routeKey']` and dispatches to handler functions
    - Implement `handle_login(event)`: parse JSON body for username/password, compare username against `ADMIN_USERNAME` env var, verify password with `bcrypt.checkpw()` against `ADMIN_PASSWORD_HASH` env var, return JWT (HS256, 24h expiry) signed with `JWT_SECRET` env var
    - Implement `validate_token(event)` helper: extract `Authorization: Bearer <token>` header, decode with PyJWT, check expiration, return decoded payload or raise
    - Implement `cors_headers()` and `create_error_response(status_code, message)` following existing Lambda patterns
    - Return 401 with "Invalid credentials" for wrong username/password (Req 1.3)
    - Return 401 with "Authentication required" for missing Authorization header
    - Return 401 with "Invalid or expired token" for bad/expired JWT
    - Return 404 for unknown routes
    - Return 400 for malformed JSON body
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 1.2 Create `admin-handler/requirements.txt`
    - Add `PyJWT>=2.8` and `bcrypt>=4.0`
    - _Requirements: 7.1_

  - [ ]* 1.3 Write property tests for authentication (`admin-handler/tests/test_auth_properties.py`)
    - Create `admin-handler/tests/__init__.py` and `admin-handler/tests/conftest.py` with shared fixtures (mock env vars for ADMIN_USERNAME, ADMIN_PASSWORD_HASH, JWT_SECRET, table names; mock boto3 DynamoDB)
    - **Property 1: JWT token structure and expiration** — For any valid credentials, login returns a JWT with `sub` == username, `iat`, and `exp` == `iat + 86400`
    - **Validates: Requirements 1.2**
    - **Property 2: Invalid credentials rejection** — For any wrong username/password pair, login returns 401
    - **Validates: Requirements 1.3**
    - **Property 3: Protected endpoint auth enforcement** — For any protected route with missing/malformed/expired token, endpoint returns 401
    - **Validates: Requirements 1.4, 1.5, 2.5, 3.5, 4.7, 5.6, 6.5**

- [x] 2. Implement Leads and Tips API endpoints
  - [x] 2.1 Add `handle_get_leads(event)` to `admin-handler/lambda_function.py`
    - Validate JWT token
    - DynamoDB Scan on `ViewMyBill-Leads` table
    - Sort results by timestamp descending
    - Return `{ "leads": [...] }` with all lead fields (email, name, company, phone, fileName, fileSize, sessionId, timestamp)
    - Return empty array when no leads exist
    - _Requirements: 2.1, 2.3, 2.4, 2.5_

  - [x] 2.2 Add tips CRUD handlers to `admin-handler/lambda_function.py`
    - `handle_get_tips(event)`: Scan Tips table, sort by service then tipId, return `{ "tips": [...] }`
    - `handle_create_tip(event)`: Parse body, validate all 7 fields non-empty, PutItem with `ConditionExpression: attribute_not_exists(service) AND attribute_not_exists(tipId)`, return 409 on ConditionalCheckFailedException
    - `handle_update_tip(event)`: Parse body, validate fields, unconditional PutItem, return updated tip
    - `handle_delete_tip(event)`: Parse body for service+tipId, DeleteItem with `ConditionExpression: attribute_exists(service)`, return 404 on ConditionalCheckFailedException
    - _Requirements: 3.1, 3.3, 3.4, 3.5, 4.2, 4.4, 4.5, 4.7, 5.2, 5.3, 5.6, 6.2, 6.4, 6.5_

  - [ ]* 2.3 Write property tests for leads (`admin-handler/tests/test_leads_properties.py`)
    - **Property 4: Leads sorted by timestamp descending** — For any set of leads, the response array has timestamps in non-increasing order
    - **Validates: Requirements 2.3**

  - [ ]* 2.4 Write property tests for tips CRUD (`admin-handler/tests/test_tips_properties.py`)
    - **Property 6: Tips grouped by service** — Tips with the same service appear consecutively
    - **Validates: Requirements 3.3**
    - **Property 9: Tip creation round-trip** — After POST, GET returns the created tip with matching fields
    - **Validates: Requirements 4.4**
    - **Property 10: Duplicate tip conflict detection** — Creating a tip with existing service+tipId returns 409
    - **Validates: Requirements 4.5**
    - **Property 11: Tip update round-trip** — After PUT, GET returns the updated field values
    - **Validates: Requirements 5.3**
    - **Property 12: Tip deletion removes from table** — After DELETE, GET no longer contains that tip
    - **Validates: Requirements 6.2**
    - **Property 13: Delete non-existent tip returns 404** — DELETE with unknown service+tipId returns 404
    - **Validates: Requirements 6.4**

  - [ ]* 2.5 Write unit tests for all routes (`admin-handler/tests/test_handler_unit.py`)
    - Login with correct credentials returns 200 + token (Req 1.2)
    - Login with wrong password returns 401 (Req 1.3)
    - GET /admin/leads with no data returns empty array (Req 2.4)
    - GET /admin/tips with no data returns empty array (Req 3.4)
    - Create tip with valid fields succeeds (Req 4.4)
    - Update tip preserves service/tipId (Req 5.3)
    - Delete existing tip succeeds (Req 6.2)
    - Unknown route returns 404
    - Malformed JSON body returns 400

- [x] 3. Checkpoint - Backend Lambda complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Build Admin Panel frontend
  - [x] 4.1 Create `admin/index.html` with login form and dashboard structure
    - Login view: username/password fields, submit button, error display area
    - Dashboard view (hidden by default): header with username display + logout button, tab navigation (Leads / Tips)
    - Leads tab: search input, leads table with columns (email, name, company, phone, fileName, timestamp), empty-state message
    - Tips tab: search input, "Add Tip" button, tips table with columns (service, tipId, category, title, description, estimatedSavings, difficulty) + edit/delete action buttons, empty-state message
    - Tip modal form: fields for all 7 tip attributes, difficulty as dropdown (easy/medium/hard), service+tipId disabled in edit mode, submit/cancel buttons
    - Confirmation dialog for delete
    - Loading spinner overlay
    - Error/success notification banner
    - Link `admin.css` and `admin.js`
    - _Requirements: 1.1, 2.2, 3.2, 4.1, 4.3, 5.1, 5.4, 6.1, 8.2, 8.3, 8.5, 8.6_

  - [x] 4.2 Create `admin/admin.css` with eshkolai.com theme
    - Use CSS variables: --primary: #0066ff, --primary-dark: #0052cc, --secondary: #00d4ff, --dark: #0a0e27, --accent: #ff6b35
    - Style login form centered on dark background
    - Style dashboard layout with header, tabs, content area
    - Style data tables with alternating row colors, hover effects
    - Style modal form overlay
    - Style notification banners (success green, error red)
    - Style loading spinner
    - Responsive layout for desktop and tablet
    - _Requirements: 8.1, 8.4_

  - [x] 4.3 Create `admin/admin.js` with all client-side logic
    - `API_BASE_URL` constant pointing to `https://l2fd4h481h.execute-api.us-east-1.amazonaws.com`
    - `login(username, password)`: POST /admin/login, store token + username in sessionStorage, show dashboard
    - `logout()`: clear sessionStorage, show login form (Req 1.8)
    - `apiRequest(method, path, body)`: wrapper that adds `Authorization: Bearer` header, handles 401 → redirect to login
    - `loadLeads()`: GET /admin/leads, render table sorted by timestamp desc
    - `filterLeads(query)`: client-side filter by email/name/company (case-insensitive) (Req 2.6)
    - `loadTips()`: GET /admin/tips, render table grouped by service
    - `filterTips(query)`: client-side filter by service/title/category (case-insensitive) (Req 3.6)
    - `createTip(tipData)`: POST /admin/tips, handle 409 conflict
    - `updateTip(tipData)`: PUT /admin/tips
    - `deleteTip(service, tipId)`: DELETE /admin/tips, handle 404
    - `showNotification(message, type)`: display success/error banner
    - `showLoading()` / `hideLoading()`: toggle loading spinner
    - Form validation: all fields non-empty before submit (Req 4.2, 5.2)
    - On page load: check sessionStorage for token, show dashboard or login accordingly (Req 1.7)
    - Tab switching between leads and tips views (Req 8.2)
    - _Requirements: 1.7, 1.8, 2.1, 2.6, 3.1, 3.6, 4.2, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.5, 6.1, 6.2, 6.3, 8.2, 8.5, 8.6_

- [x] 5. Checkpoint - Frontend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Update CloudFormation stack for admin infrastructure
  - [x] 6.1 Add admin resources to `infrastructure/viewmybill-stack.yaml`
    - Add parameters: `AdminHandlerCodeKey` (default: `lambda-packages/admin-handler.zip`), `AdminUsername` (NoEcho), `AdminPasswordHash` (NoEcho), `JWTSecret` (NoEcho)
    - Add `AdminHandlerRole` IAM role: Lambda basic execution + DynamoDB Scan on LeadsTable + DynamoDB Scan/PutItem/UpdateItem/DeleteItem on CostOptimizationTipsTable
    - Add `AdminHandlerFunction` Lambda: Python 3.12, 128MB, 30s timeout, env vars for ADMIN_USERNAME, ADMIN_PASSWORD_HASH, JWT_SECRET, LEADS_TABLE_NAME, TIPS_TABLE_NAME
    - Add `AdminIntegration` API Gateway integration pointing to AdminHandlerFunction
    - Add 6 routes: POST /admin/login, GET /admin/leads, GET /admin/tips, POST /admin/tips, PUT /admin/tips, DELETE /admin/tips
    - Add `AdminHandlerInvokePermission` Lambda permission for API Gateway
    - Update CORS AllowMethods to include GET, PUT, DELETE and AllowHeaders to include Authorization
    - Add outputs for AdminHandlerFunctionArn
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.7_

- [x] 7. Update GitHub Actions deployment workflow
  - [x] 7.1 Update `.github/workflows/deploy.yml` for admin Lambda and frontend
    - Add `admin-handler/**` and `admin/**` to trigger paths
    - Add "Package Admin Handler Lambda" step: install PyJWT + bcrypt into build dir, copy lambda_function.py, zip, upload to S3
    - Add `aws lambda update-function-code` for `aws-bill-analyzer-admin-api`
    - Add "Deploy Admin frontend" step: inject API_URL into admin.js, sync `admin/` directory to `s3://www.eshkolai.com/admin/`
    - _Requirements: 7.5, 7.6_

- [-] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Backend Lambda uses Python 3.12 with PyJWT and bcrypt
- Frontend uses vanilla HTML/CSS/JS (no build step)
- Property tests use Hypothesis (Python) for backend
- Checkpoints ensure incremental validation
