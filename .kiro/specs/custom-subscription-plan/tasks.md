# Implementation Plan: Custom Subscription Plan

## Overview

This implementation adds a 4th commitment-based plan option to the existing Free/Growth/Scale tier system. The work spans infrastructure (DynamoDB table), backend (member-handler and admin-handler Lambdas), and frontend (members.js modal, admin.js panel). PayPal recurring billing, commitment lock enforcement, discount calculation, expiry notifications, and admin visibility are all covered.

## Tasks

- [x] 1. Infrastructure and Discount Engine foundation
  - [x] 1.1 Create the CustomPlan-DiscountConfig DynamoDB table and seed default data
    - Add CloudFormation resource for `CustomPlan-DiscountConfig` table (PK: `configId`, PAY_PER_REQUEST billing)
    - Create a seed script or inline Lambda initializer that inserts the default configuration item (`configId: "ACTIVE"`, baseMonthlyPrice: 250, baseTokenCount: 2000, discount tiers)
    - _Requirements: 8.1, 8.2_

  - [x] 1.2 Implement the Discount Engine module (`member-handler/discount_engine.py`)
    - Create `discount_engine.py` with `calculate_discount(commitment_months, config)` function
    - Implement tier lookup logic: find tier where `minMonths <= commitment_months <= maxMonths`
    - Calculate `monthlyPrice = baseMonthlyPrice * (1 - discountPercent/100)`
    - Calculate `tokenAllocation = round(baseTokenCount * (1 + discountPercent/100))`
    - Validate bounds: price > 0, tokens >= baseTokenCount
    - Add input validation: commitment_months must be int between 3 and 24
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 1.3 Write property tests for Discount Engine monotonicity (Property 1)
    - **Property 1: Discount calculation monotonicity**
    - **Validates: Requirements 2.2, 2.3**
    - File: `member-handler/tests/test_discount_engine.py`
    - Use `hypothesis` with `st.integers(3, 24)` pairs where a < b
    - Verify: discount% for longer period >= discount% for shorter period
    - Verify: monthly price for longer period <= price for shorter period
    - Verify: token allocation for longer period >= allocation for shorter period

  - [ ]* 1.4 Write property tests for price bounds (Property 2) and token bounds (Property 3)
    - **Property 2: Price bounded above zero and below base**
    - **Property 3: Token allocation bounded above base**
    - **Validates: Requirements 2.3, 2.4**
    - File: `member-handler/tests/test_discount_engine.py`
    - Generate commitment months (3-24) and valid configs (discount 1-50%)
    - Verify: 0 < monthlyPrice <= baseMonthlyPrice for all inputs
    - Verify: tokenAllocation >= baseTokenCount for all inputs

- [x] 2. Custom Plan API endpoints in member-handler
  - [x] 2.1 Implement `POST /members/custom-plan/calculate` endpoint
    - Add route handling in `member-handler/lambda_function.py`
    - Read `CustomPlan-DiscountConfig` from DynamoDB
    - Call `calculate_discount()` with request body `commitmentMonths`
    - Return calculated price, tokens, discount%, total value, and comparison to Scale plan
    - Return 400 if commitment months outside 3-24 range
    - _Requirements: 1.3, 2.1, 2.5_

  - [x] 2.2 Implement `POST /members/custom-plan/subscribe` endpoint (PayPal integration)
    - Add route handling for subscribe flow (two-step: create and activate)
    - Step 1 (create): Call PayPal Subscriptions API to create a billing plan with exact N billing cycles matching commitment months, then create a subscription and return approval URL
    - Step 2 (activate): After PayPal approval redirect, activate subscription, update Member_Record with `tier: "custom"`, `customTokenAllocation`, `customMonthlyPrice`, `commitmentStartDate`, `commitmentEndDate`, `commitmentMonths`, `commitmentDiscountPercent`, `paypalCustomPlanSubId`, `commitmentStatus: "active"`
    - Return 409 if member already has an active commitment
    - Return 502 if PayPal API call fails
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 2.3 Schedule EventBridge expiry notifications on commitment activation
    - After successful activation, create two EventBridge Scheduler one-time schedules:
      - 14-day warning: `commitmentEndDate - 14 days` → invoke member-handler with `_commitmentNotification` event
      - 3-day warning: `commitmentEndDate - 3 days` → invoke member-handler with `_commitmentNotification` event
    - If commitment is <= 14 days, skip the 14-day notification
    - _Requirements: 7.1, 7.4_

  - [x] 2.4 Implement `GET /members/custom-plan/status` endpoint
    - Read member record and return commitment status (dates, remaining months, price, tokens, canRenew flag)
    - Return `hasCommitment: false` if no active commitment
    - Calculate `remainingMonths` from current date and `commitmentEndDate`
    - Set `canRenew: true` when 30 days or fewer remain
    - _Requirements: 1.5, 7.5_

  - [x] 2.5 Implement `POST /members/custom-plan/renew` endpoint
    - Allow member to select a new commitment period starting after current one ends
    - Only available when current commitment has 30 days or fewer remaining
    - Create new PayPal subscription starting on current commitment's end date
    - _Requirements: 7.5_

  - [ ]* 2.6 Write property test for PayPal billing cycles match commitment (Property 8)
    - **Property 8: PayPal billing cycles match commitment**
    - **Validates: Requirements 4.2**
    - File: `member-handler/tests/test_custom_plan_api.py`
    - Generate commitment months (3-24), verify PayPal plan creation specifies exactly N cycles
    - Mock PayPal API calls, assert `billing_cycles` count equals commitment months

- [x] 3. Commitment Lock Enforcement
  - [x] 3.1 Modify `handle_update_tier` to check commitment lock before allowing tier changes
    - In `member-handler/lambda_function.py`, read member's `commitmentEndDate` before processing tier change
    - If `commitmentEndDate` exists and is in the future, return 403 with `CommitmentLocked` error including end date and remaining months
    - Ensure the lock applies to all downgrade/upgrade attempts (free, growth, scale)
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 3.2 Implement lazy commitment expiry check in `_check_and_consume_credits`
    - When tier is `custom` and `commitmentEndDate < now`, transition member to Scale tier
    - Clear commitment fields: set `commitmentStatus: "expired"`, remove lock dates
    - Set `customTokenAllocation` to null, tier to `scale`
    - _Requirements: 3.5, 5.5, 7.2_

  - [ ]* 3.3 Write property test for commitment lock rejects all tier changes (Property 4)
    - **Property 4: Commitment lock rejects all tier changes**
    - **Validates: Requirements 3.1, 3.2, 3.3**
    - File: `member-handler/tests/test_commitment_lock.py`
    - Generate members with future end dates, attempt tier changes to free/growth/scale
    - Verify all return 403 with correct error structure

  - [ ]* 3.4 Write property test for commitment lock expires correctly (Property 5)
    - **Property 5: Commitment lock expires correctly**
    - **Validates: Requirements 3.5**
    - File: `member-handler/tests/test_commitment_lock.py`
    - Generate members with past end dates, verify tier changes are allowed

  - [ ]* 3.5 Write property test for expiry transitions to Scale tier (Property 10)
    - **Property 10: Expiry transitions to Scale tier**
    - **Validates: Requirements 5.5, 7.2**
    - File: `member-handler/tests/test_commitment_lock.py`
    - Generate expired commitments, verify tier becomes "scale", tokenAllocation becomes 1500, commitment fields cleared

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Credit System and Token Allocation
  - [x] 5.1 Modify `_check_and_consume_credits` to use member-specific `customTokenAllocation`
    - When `tier == 'custom'`, read `customTokenAllocation` from member record instead of `AI_CREDITS` dict
    - Fall back to Scale tier value (1500) if `customTokenAllocation` is missing
    - Ensure monthly usage counter reset logic works with custom plan billing cycle anniversary
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 5.2 Write property test for custom token allocation override (Property 6)
    - **Property 6: Custom token allocation override**
    - **Validates: Requirements 5.1, 5.3**
    - File: `member-handler/tests/test_discount_engine.py`
    - Generate custom allocation values (100-10000), verify `_check_and_consume_credits` uses member-specific value instead of AI_CREDITS lookup

- [x] 6. Payment Failure and Grace Period Handling
  - [x] 6.1 Implement PayPal webhook handler for payment events
    - Add webhook endpoint in member-handler for PayPal events
    - Handle `PAYMENT.SALE.COMPLETED`: clear grace period, reset to `active`
    - Handle `PAYMENT.SALE.DENIED`: set `commitmentStatus: "grace_period"`, set `commitmentGraceDeadline = now + 7 days`
    - Handle `BILLING.SUBSCRIPTION.EXPIRED`: trigger expiry transition to Scale tier
    - Verify PayPal webhook signature on all incoming events
    - _Requirements: 4.5_

  - [x] 6.2 Implement grace period enforcement logic
    - On API calls for grace_period members, check if `commitmentGraceDeadline` has passed
    - If past deadline: revert to `tier: "free"`, clear all commitment fields
    - If within deadline: allow continued access at custom tier
    - Send email notification when entering grace period
    - _Requirements: 4.5_

  - [ ]* 6.3 Write property test for grace period timing (Property 9)
    - **Property 9: Grace period timing**
    - **Validates: Requirements 4.5**
    - File: `member-handler/tests/test_custom_plan_api.py`
    - Generate payment failure timestamps, verify 7-day window enforcement
    - Verify member retains access during 7 days, reverts to free tier after

- [x] 7. Expiry Notification System
  - [x] 7.1 Implement `_commitmentNotification` event handler in member-handler
    - Detect `_commitmentNotification` key in event (same pattern as `_asyncScan`)
    - For `type: "14day"`: send styled HTML email via SES with upcoming expiry info and options
    - For `type: "3day"`: send final reminder email via SES
    - Include member's current plan details and link to Plan Modal
    - _Requirements: 7.1, 7.4_

  - [ ]* 7.2 Write property test for notification scheduling correctness (Property 12)
    - **Property 12: Notification scheduling correctness**
    - **Validates: Requirements 7.1, 7.4**
    - File: `member-handler/tests/test_custom_plan_api.py`
    - Generate end dates, verify exactly two notifications scheduled at correct times
    - Verify short commitments (<=14 days) only schedule the 3-day notification

- [x] 8. Admin Panel Backend and Config Management
  - [x] 8.1 Implement `GET /admin/custom-plans` endpoint in admin-handler
    - Scan MemberPortal-Members table for members with `tier: "custom"` or `commitmentStatus` present
    - Return list with email, monthlyPrice, tokenAllocation, dates, remaining months, status
    - Calculate and return summary: total active commitments, total monthly revenue, grace period count
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 8.2 Implement `GET /admin/custom-plans/config` and `PUT /admin/custom-plans/config` endpoints
    - GET: Read and return current `CustomPlan-DiscountConfig` item
    - PUT: Validate incoming config (discount 1-50%, base price > 200, tier ranges cover 3-24 without gaps/overlaps)
    - Store `updatedAt` timestamp and `updatedBy` admin email on update
    - Return 400 with `InvalidConfig` error for validation failures
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 8.3 Write property test for discount configuration validation (Property 7)
    - **Property 7: Discount configuration validation**
    - **Validates: Requirements 8.4, 8.5**
    - File: `member-handler/tests/test_discount_engine.py`
    - Generate invalid configs (discount outside [1,50], base price <=200, gap/overlap in tier ranges)
    - Verify all are rejected with appropriate error messages

  - [ ]* 8.4 Write property test for existing commitments unaffected by config changes (Property 11)
    - **Property 11: Existing commitments unaffected by config changes**
    - **Validates: Requirements 8.3**
    - File: `member-handler/tests/test_custom_plan_api.py`
    - Create member with active commitment, update discount config, verify member's price/tokens/dates unchanged

- [x] 9. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Frontend - Custom Plan Card in Members Portal
  - [x] 10.1 Add Custom Plan card to `_showUpgradeModal()` in `members/members.js`
    - Render 4th plan card to the right of Scale card
    - Include month-selection dropdown (3-24 months, 1-month increments)
    - Add placeholder divs for price, tokens, and discount display
    - Add conditional rendering: if member has active commitment, show status instead of dropdown (remaining months, end date)
    - Style card consistently with existing plan cards in `members/members.css`
    - _Requirements: 1.1, 1.2, 1.5_

  - [x] 10.2 Implement `calculateCustomPrice()` function and PayPal subscribe button
    - On dropdown change, call `POST /members/custom-plan/calculate` and display results
    - Update price, tokens, and discount% within 500ms of selection
    - Render PayPal subscribe button using returned subscription data
    - Handle subscribe flow: redirect to PayPal approval URL, then call activate on return
    - Disable plan change buttons while commitment is active (show lock message)
    - _Requirements: 1.3, 1.4, 3.1, 4.1_

  - [x] 10.3 Add renewal prompt display when commitment has 30 days or fewer remaining
    - Check `canRenew` flag from `/custom-plan/status` endpoint
    - Display renewal section with new month selector starting after current commitment ends
    - Wire renewal button to `POST /members/custom-plan/renew`
    - _Requirements: 7.3, 7.5_

- [x] 11. Frontend - Admin Panel Custom Plans Section
  - [x] 11.1 Add Custom Plans tab/section to `admin/admin.js` and `admin/admin.css`
    - Add "Custom Plans" navigation item in admin panel
    - Implement `loadCustomPlans()` function calling `GET /admin/custom-plans`
    - Render table with columns: email, monthly price, tokens, start date, end date, remaining months, status
    - Display summary card with total MRR, active count, grace period count
    - Highlight members with `grace_period` status
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 11.2 Add Discount Configuration editor to admin panel
    - Implement `loadDiscountConfig()` calling `GET /admin/custom-plans/config`
    - Render editable form for base price, base tokens, and discount tiers
    - Add save button calling `PUT /admin/custom-plans/config`
    - Display validation errors inline on save failure
    - Show `updatedAt` and `updatedBy` info
    - _Requirements: 6.5, 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 12. Final checkpoint - Ensure all tests pass and integration is complete
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python for backend (Lambda handlers) and vanilla JavaScript for frontend
- PayPal integration uses the Subscriptions API (not Orders API) with fixed billing cycles
- The `CustomPlan-DiscountConfig` table is a single-item table accessed by key `configId: "ACTIVE"`
- Expiry notifications use EventBridge Scheduler one-time schedules (not polling)
- Commitment expiry processing uses lazy evaluation on API calls (no separate cron)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "2.4", "3.2", "5.1"] },
    { "id": 3, "tasks": ["2.3", "2.5", "2.6", "3.3", "3.4", "3.5", "5.2"] },
    { "id": 4, "tasks": ["6.1", "6.2", "7.1"] },
    { "id": 5, "tasks": ["6.3", "7.2", "8.1", "8.2"] },
    { "id": 6, "tasks": ["8.3", "8.4"] },
    { "id": 7, "tasks": ["10.1", "11.1"] },
    { "id": 8, "tasks": ["10.2", "10.3", "11.2"] }
  ]
}
```
