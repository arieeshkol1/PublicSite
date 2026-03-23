# Implementation Plan: OTP Email Verification

## Overview

Add OTP email verification to the Slash My Bill page. Implementation proceeds in layers: infrastructure first (CloudFormation), then the OTP Lambda backend, then frontend UI changes, and finally CI/CD pipeline updates. Each step builds on the previous and is wired together incrementally.

## Tasks

- [x] 1. Add OTP infrastructure to CloudFormation stack
  - [x] 1.1 Add OTP DynamoDB table, OTP Lambda role, OTP Lambda function, API Gateway integration and routes, Lambda invoke permission, and SES email identity to `infrastructure/viewmybill-stack.yaml`
    - Add `OTPHandlerCodeKey` parameter (default: `lambda-packages/otp-handler.zip`)
    - Add `OTPTable` DynamoDB table: partition key `email` (String), PAY_PER_REQUEST billing, SSE enabled, TTL attribute `ttl`
    - Add `OTPHandlerRole` IAM role with DynamoDB read/write on OTPTable and `ses:SendEmail` permission
    - Add `OTPHandlerFunction` Lambda: Python 3.12, 128MB, 30s timeout, handler `lambda_function.lambda_handler`, env vars `OTP_TABLE_NAME` and `SES_SENDER_EMAIL` (`noreply@eshkolai.com`)
    - Add `OTPIntegration` (AWS_PROXY, payload format 2.0)
    - Add `SendOTPRoute` (`POST /send-otp`) and `VerifyOTPRoute` (`POST /verify-otp`)
    - Add `OTPHandlerInvokePermission` allowing API Gateway to invoke the OTP Lambda
    - Add `SESEmailIdentity` resource for `eshkolai.com` domain with `DkimSigningAttributes` and `ConfigurationSetAttributes` if needed
    - Add outputs for OTPTable name/ARN and OTPHandlerFunction ARN
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ]* 1.2 Write unit test to validate CloudFormation template structure
    - Validate the template YAML is parseable and contains expected resource logical IDs
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 2. Implement OTP Lambda handler
  - [x] 2.1 Create `otp-handler/lambda_function.py` with send-otp and verify-otp route handling
    - Implement `lambda_handler` that routes on `event['routeKey']`
    - Implement `handle_send_otp`: validate email format, check rate limit (60s cooldown via `createdAt`), generate 6-digit OTP with `secrets.randbelow`, store in DynamoDB with TTL (createdAt + 300s), send email via SES with HTML body containing OTP code, 5-minute validity notice, and Eshkol AI branding
    - Implement `handle_verify_otp`: look up OTP record by email, compare codes, check expiry, delete record on success
    - Implement `cors_headers()` helper returning `Access-Control-Allow-Origin`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Methods`
    - Implement `error_response()` helper matching existing upload-handler pattern (include `retryAfter` for 429)
    - Return CORS headers in all responses (success and error)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.2, 4.3, 4.4, 4.5, 4.6, 6.1, 10.3_

  - [x] 2.2 Create `otp-handler/requirements.txt`
    - Add `boto3` (for local testing; Lambda runtime includes it)
    - _Requirements: 3.1_


  - [ ]* 2.3 Write property tests for OTP Lambda (`otp-handler/tests/test_otp_properties.py`)
    - **Property 1: OTP generation and storage correctness**
    - **Validates: Requirements 3.1, 3.2**

  - [ ]* 2.4 Write property test for email body content
    - **Property 2: OTP email body contains required content**
    - **Validates: Requirements 3.4**

  - [ ]* 2.5 Write property test for invalid email rejection
    - **Property 3: Invalid email rejection**
    - **Validates: Requirements 3.5**

  - [ ]* 2.6 Write property test for OTP overwrite semantics
    - **Property 4: OTP overwrite semantics**
    - **Validates: Requirements 3.7**

  - [ ]* 2.7 Write property test for verification round trip
    - **Property 5: OTP verification round trip**
    - **Validates: Requirements 4.3, 4.6**

  - [ ]* 2.8 Write property test for wrong OTP rejection
    - **Property 6: Wrong OTP rejection**
    - **Validates: Requirements 4.4**

  - [ ]* 2.9 Write property test for rate limiting
    - **Property 7: Rate limiting within cooldown window**
    - **Validates: Requirements 6.1**

  - [ ]* 2.10 Write property test for CORS headers
    - **Property 8: CORS headers in all responses**
    - **Validates: Requirements 10.3**

  - [ ]* 2.11 Write unit tests for OTP Lambda (`otp-handler/tests/test_otp_unit.py`)
    - Test send-otp happy path, verify-otp happy path, SES failure, expired OTP, no record, rate limiting, CORS on errors, unknown route
    - Use `moto` to mock DynamoDB and SES
    - _Requirements: 3.1, 3.5, 3.6, 4.3, 4.4, 4.5, 6.1, 10.3_

- [x] 3. Checkpoint - Verify backend implementation
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Update frontend HTML with OTP UI elements
  - [x] 4.1 Modify `viewMyBill/index.html` to add OTP verification UI
    - Add "Verify my email" button (`id="vmb-verify-email"`) below the contact fields grid, above the file picker
    - Add OTP input section (`id="vmb-otp-section"`, initially hidden) with a 6-digit text input (`id="vmb-otp-input"`), a "Verify code" submit button (`id="vmb-otp-submit"`), and a "Resend code" link (`id="vmb-resend-otp"`) with countdown span
    - Add verification status message area (`id="vmb-verify-status"`)
    - Add a visual overlay/message on the file picker area indicating "Verify your email to upload"
    - Add `aria-describedby` and `role="alert"` attributes for accessibility on status messages
    - Set the file picker input and submit button to `disabled` by default in the HTML
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.5, 4.1, 5.4, 5.5, 9.1_

- [x] 5. Update frontend CSS for OTP styles
  - [x] 5.1 Add OTP-related styles to `viewMyBill/viewMyBill.css`
    - Style the verify button, OTP input section, resend link, countdown timer, verification status messages, disabled file picker overlay, and success/error states
    - Style the disabled file picker with reduced opacity and `pointer-events: none`
    - Style the countdown timer on the verify/resend buttons
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.4, 6.2, 6.3, 9.2_

- [x] 6. Implement frontend OTP JavaScript logic
  - [x] 6.1 Update `viewMyBill/viewMyBill.js` with OTP verification state machine and API calls
    - Add OTP state management (UNVERIFIED → SENDING → CODE_SENT → VERIFYING → VERIFIED)
    - Add `verifiedEmail` variable to track which email was verified
    - Modify existing `updateSubmitState` to require `emailVerified === true && fileValid` for submit button
    - Add `validateVerifyButton()` that enables the verify button only when name, email, and phone are valid
    - Add `sendOTP()` function: POST to `/send-otp` with email, handle loading state, show OTP input on success, show error on failure
    - Add `verifyOTP()` function: POST to `/verify-otp` with email and OTP code, enable file picker on success, show error on failure
    - Add `resendOTP()` function: call sendOTP again, show confirmation message
    - Add 60-second cooldown timer logic: disable verify/resend buttons, show countdown, re-enable after cooldown
    - Add email change listener: if email value changes after verification, reset to UNVERIFIED state, disable file picker and submit button
    - Disable drag-and-drop on file picker while unverified (prevent `dragover`, `drop` events)
    - Hide OTP section and verify button after successful verification, show confirmation message
    - Handle 429 responses: parse `retryAfter`, start countdown from that value
    - Wire up event listeners for verify button, OTP submit, resend link
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 4.1, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.2, 6.3, 9.1, 9.2, 9.3, 9.4_

  - [ ]* 6.2 Write property test for verify button disabled state (frontend)
    - **Property 9: Verify button disabled for invalid inputs**
    - **Validates: Requirements 2.2**

  - [ ]* 6.3 Write property test for email change resets verification
    - **Property 10: Email change resets verification state**
    - **Validates: Requirements 5.7**

  - [ ]* 6.4 Write property test for submit button enabled conditions
    - **Property 11: Submit button enabled only when verified with file**
    - **Validates: Requirements 5.6**

- [x] 7. Checkpoint - Verify frontend implementation
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Update CI/CD pipeline for OTP Lambda deployment
  - [x] 8.1 Update `.github/workflows/deploy.yml` to package and deploy the OTP Lambda
    - Add `otp-handler/**` to the `paths` trigger list
    - Add "Package OTP Handler Lambda" step: copy `otp-handler/lambda_function.py` into a build directory, zip it, upload to S3 as `lambda-packages/otp-handler.zip`
    - Add `aws lambda update-function-code` command for the OTP Lambda function after CloudFormation deploy (same pattern as upload-handler)
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The OTP Lambda follows the same single-file pattern as the existing upload-handler
- All infrastructure is added to the existing CloudFormation stack — no new stacks
- Frontend changes are additive to the existing form flow
