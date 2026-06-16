# Implementation Plan: Anthropic GroundCover Connection

## Overview

Add GroundCover as an AI vendor connection option, mirroring the existing OpenAI flow. Backend (Python Lambda) gets two new routes; frontend (JavaScript) gets a new wizard option and validation. Implementation language: Python (backend), JavaScript (frontend).

## Tasks

- [ ] 1. Add `handle_add_groundcover` route to member-handler Lambda
  - [ ] 1.1 Implement `handle_add_groundcover(event)` in `member-handler/lambda_function.py`
    - Add `POST /members/accounts/add-groundcover` route to the routes dict
    - Parse body for `apiKey` and optional `connectionName` (max 64 chars)
    - Validate token format: must start with `gcsa_`, length 20-200 chars
    - Return 400 `InvalidKeyFormat` if validation fails
    - Test connection by POSTing to GroundCover API with `Authorization: Bearer <token>` and `X-Backend-Id: groundcover` headers, 10s timeout
    - Return 400 `ConnectionFailed` if API returns non-200 or times out
    - Encrypt token via KMS using `encrypt_openai_key(api_key, member_email, account_id)`
    - Store record in MemberPortal-Accounts with `cloudProvider='groundcover'`, `vendorType='ai_vendor'`, `connectionStatus='connected'`
    - Return 201 with success response (exclude credentials)
    - Follow the same pattern as `handle_add_openai`
    - _Requirements: 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2_

  - [ ]* 1.2 Write property test for GroundCover token validation
    - **Property 2: Valid tokens always have gcsa_ prefix and correct length**
    - For any string, validation accepts iff it starts with `gcsa_` and has length 20-200
    - **Validates: Requirements 2.1, 2.3**

  - [ ]* 1.3 Write property test for failed connections producing no records
    - **Property 4: Failed connections produce no stored records**
    - For any token that fails the GroundCover API test, no DynamoDB record is written
    - **Validates: Requirements 4.3, 5.2**

- [ ] 2. Add `handle_test_groundcover_connection` route to member-handler Lambda
  - [ ] 2.1 Implement `handle_test_groundcover_connection(event)` in `member-handler/lambda_function.py`
    - Add `POST /members/accounts/test-groundcover-connection` route to the routes dict
    - Parse body for `accountId`
    - Verify account ownership and that `cloudProvider` is `groundcover`
    - Decrypt stored token via KMS
    - Re-test against GroundCover API with same headers/body as add flow
    - On success: update `connectionStatus='connected'`, `lastTestedAt`, remove `failureReason`
    - On failure: update `connectionStatus='failed'`, `lastTestedAt`, store `failureReason` (max 200 chars)
    - Follow the same pattern as `handle_test_openai_connection`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 3. Checkpoint - Verify backend routes
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Update frontend wizard in `members/members.js`
  - [ ] 4.1 Add GroundCover vendor option to `_showAddAIVendorModal()`
    - Add a "Anthropic (via GroundCover)" button in the vendor selection grid (alongside existing OpenAI button)
    - Wire up click handler to set `_aiVendorSelectedProvider = 'groundcover'` and show form step
    - Update form labels/placeholder to show `gcsa_...` when GroundCover is selected
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ] 4.2 Add `_validateGroundcoverKey(key)` validation function
    - Validate: non-empty, starts with `gcsa_`, length 20-200 after trim
    - Return `{ valid: boolean, message: string }` matching OpenAI pattern
    - Wire into form's inline validation and submit logic (use groundcover validator when `_aiVendorSelectedProvider === 'groundcover'`)
    - Submit to `/members/accounts/add-groundcover` endpoint
    - _Requirements: 2.1, 2.2_

  - [ ]* 4.3 Write property test for frontend/backend validation consistency
    - **Property 1: Token validation consistency between frontend and backend**
    - For any string, if frontend validation returns valid:true then backend validation must also return valid:True
    - **Validates: Requirements 2.1, 2.3**

- [ ] 5. Update connection list display
  - [ ] 5.1 Update connection list rendering in `members/members.js`
    - Display GroundCover connections with name, status badge, and lastTestedAt
    - Show "Test Connection" button calling `/members/accounts/test-groundcover-connection`
    - Show failure reason when `connectionStatus` is `failed`
    - Use same display pattern as OpenAI connections (just different label/icon)
    - _Requirements: 7.1, 7.2, 7.3_

- [ ] 6. Final checkpoint - Verify end-to-end
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Backend follows the exact same pattern as `handle_add_openai` / `handle_test_openai_connection`
- Frontend follows the exact same pattern as the existing OpenAI wizard flow
- Scope is connection wizard + credential storage only — no data fetching or dashboard integration
- Files to modify: `member-handler/lambda_function.py`, `members/members.js`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1"] },
    { "id": 2, "tasks": ["4.1", "4.2"] },
    { "id": 3, "tasks": ["4.3", "5.1"] }
  ]
}
```
