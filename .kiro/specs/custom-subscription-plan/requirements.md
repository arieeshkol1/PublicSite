# Requirements Document

## Introduction

The Custom Subscription Plan feature adds a 4th self-service plan option to the existing "Manage Your Plan" modal. Unlike the fixed Free/Growth/Scale tiers, the Custom plan allows members to select a commitment period (in months) and receive a dynamically calculated discount on price and token allocation. The commitment period locks the member in — they cannot downgrade or cancel until the commitment expires. Payments are handled through the existing PayPal integration with recurring billing for the committed duration.

## Glossary

- **Plan_Modal**: The existing "Manage Your Plan" overlay (upgrade-modal) that displays Free, Growth, and Scale plan cards
- **Custom_Plan_Card**: The 4th plan card rendered to the right of the Scale card within the Plan_Modal
- **Commitment_Period**: The number of months a member selects for their Custom plan lock-in (minimum 3 months, maximum 24 months)
- **Discount_Engine**: The backend calculation module that determines the discounted monthly price and token allocation based on Commitment_Period length
- **Discount_Configuration**: Admin-configurable parameters including base monthly price, base token count, and discount tiers mapped to Commitment_Period ranges
- **Commitment_Lock**: The enforcement mechanism that prevents tier downgrade or subscription cancellation during an active Commitment_Period
- **Member_Record**: The DynamoDB item in MemberPortal-Members table storing a member's email, tier, tokens, and subscription metadata
- **PayPal_Billing_Agreement**: A PayPal recurring payment plan created for the Custom plan duration
- **Admin_Panel**: The existing admin interface at /admin/ for platform management
- **Token_Allocation**: The monthly AI credit token count assigned to a member based on their plan

## Requirements

### Requirement 1: Custom Plan Card Display

**User Story:** As a member, I want to see a Custom plan option in the Plan Modal, so that I can explore commitment-based pricing beyond the fixed tiers.

#### Acceptance Criteria

1. WHEN the Plan_Modal is opened, THE Custom_Plan_Card SHALL render as the 4th card positioned to the right of the Scale card
2. THE Custom_Plan_Card SHALL display a month-selection dropdown with options ranging from 3 months to 24 months in 1-month increments
3. WHEN the member selects a Commitment_Period from the dropdown, THE Custom_Plan_Card SHALL display the calculated monthly price and Token_Allocation within 500ms
4. THE Custom_Plan_Card SHALL display the discount percentage applied relative to the Scale plan base rate
5. WHILE the member has an active Commitment_Lock, THE Custom_Plan_Card SHALL display the remaining months and end date of the commitment instead of the selection dropdown

### Requirement 2: Discount Calculation

**User Story:** As a member, I want to see better rates for longer commitments, so that I can save money by committing for a longer period.

#### Acceptance Criteria

1. WHEN the Discount_Engine receives a Commitment_Period, THE Discount_Engine SHALL calculate the monthly price by applying a discount percentage to the base monthly price from the Discount_Configuration
2. THE Discount_Engine SHALL increase the discount percentage as the Commitment_Period length increases (longer commitment produces a larger discount)
3. THE Discount_Engine SHALL calculate the Token_Allocation by applying the same proportional increase to the base token count from the Discount_Configuration
4. THE Discount_Engine SHALL return a monthly price that is greater than 0 and less than or equal to the base monthly price for all valid Commitment_Period values
5. WHEN the Discount_Configuration is updated by an administrator, THE Discount_Engine SHALL use the updated configuration for all new subscription calculations without requiring a deployment

### Requirement 3: Commitment Lock Enforcement

**User Story:** As a platform operator, I want members locked into their commitment period, so that revenue is predictable and discounts are justified by guaranteed duration.

#### Acceptance Criteria

1. WHILE a member has an active Commitment_Lock, THE Plan_Modal SHALL disable the ability to downgrade to Free, Growth, or Scale plans
2. WHILE a member has an active Commitment_Lock, THE Member_Record SHALL retain the custom tier designation regardless of any attempted tier change API calls
3. IF a member attempts to cancel or downgrade during an active Commitment_Lock via the API, THEN THE member-handler SHALL return a 403 error with the commitment end date and remaining months
4. THE Commitment_Lock SHALL store the start date, end date, and original Commitment_Period length in the Member_Record
5. WHEN the current date passes the Commitment_Lock end date, THE Commitment_Lock SHALL expire and the member SHALL regain the ability to change plans

### Requirement 4: PayPal Recurring Billing Setup

**User Story:** As a member, I want to pay monthly via PayPal for my custom plan, so that I can use my existing payment method without upfront bulk payment.

#### Acceptance Criteria

1. WHEN a member confirms their Custom plan selection, THE system SHALL create a PayPal_Billing_Agreement for the calculated monthly price recurring for the selected Commitment_Period
2. THE PayPal_Billing_Agreement SHALL specify the exact number of billing cycles matching the Commitment_Period (no auto-renewal)
3. WHEN PayPal confirms the subscription activation, THE system SHALL update the Member_Record with the custom tier, Token_Allocation, Commitment_Lock dates, and PayPal subscription identifier
4. IF the PayPal subscription creation fails, THEN THE system SHALL display an error message to the member and retain their current plan without changes
5. WHEN a recurring PayPal payment fails during the Commitment_Period, THE system SHALL retain the member on the custom tier for a 7-day grace period before reverting to the Free tier

### Requirement 5: Backend Credit Allocation

**User Story:** As a member on a Custom plan, I want to receive my committed token allocation each month, so that I can use AI features at the agreed rate.

#### Acceptance Criteria

1. WHEN a member has an active custom tier, THE member-handler SHALL use the Token_Allocation stored in the Member_Record instead of the fixed AI_CREDITS dictionary value
2. THE member-handler SHALL reset the monthly token usage counter on each billing cycle anniversary date for custom plan members
3. WHEN the _check_and_consume_credits function is called for a custom plan member, THE function SHALL validate against the member-specific Token_Allocation rather than the tier-based lookup
4. THE system SHALL store the custom Token_Allocation as a numeric value in the Member_Record alongside the tier designation
5. WHEN a custom plan commitment expires, THE system SHALL revert the member Token_Allocation to the Scale tier value (1500 tokens) until the member selects a new plan

### Requirement 6: Admin Visibility

**User Story:** As an administrator, I want to see which members have custom plans and their commitment status, so that I can monitor revenue and support members.

#### Acceptance Criteria

1. THE Admin_Panel SHALL display a dedicated section listing all members with active custom plans
2. THE Admin_Panel custom plan section SHALL display for each member: email, monthly price, Token_Allocation, commitment start date, commitment end date, and remaining months
3. THE Admin_Panel SHALL display the total monthly recurring revenue from all active custom plans
4. WHEN an administrator views the custom plan section, THE Admin_Panel SHALL indicate members with failed payments or grace period status
5. THE Admin_Panel SHALL provide the ability to update the Discount_Configuration parameters (base price, base tokens, discount tiers per month range)

### Requirement 7: Commitment Expiry Handling

**User Story:** As a member whose commitment is ending, I want a clear transition experience, so that I understand what happens next and can make an informed decision.

#### Acceptance Criteria

1. WHEN a custom plan commitment has 14 days or fewer remaining, THE system SHALL send an email notification to the member informing them of the upcoming expiry and available options
2. WHEN a custom plan commitment expires and no renewal is selected, THE system SHALL transition the member to the Scale tier with standard Scale Token_Allocation (1500 tokens) and pricing ($200/month)
3. WHEN a custom plan commitment expires, THE Plan_Modal SHALL re-enable all plan selection options including a new custom commitment
4. THE system SHALL send a second email notification 3 days before commitment expiry as a final reminder
5. WHILE a commitment has 30 days or fewer remaining, THE Custom_Plan_Card SHALL display a renewal prompt allowing the member to select a new Commitment_Period starting after the current one ends

### Requirement 8: Discount Configuration Management

**User Story:** As an administrator, I want to configure the discount tiers and base pricing, so that I can adjust the business model without code changes.

#### Acceptance Criteria

1. THE Discount_Configuration SHALL be stored in a DynamoDB table accessible to both the Discount_Engine and the Admin_Panel
2. THE Discount_Configuration SHALL include: base monthly price, base token count, and a mapping of Commitment_Period ranges to discount percentages
3. WHEN an administrator updates the Discount_Configuration, THE system SHALL apply the new configuration only to new subscriptions and not modify existing active commitments
4. THE Discount_Configuration SHALL validate that discount percentages are between 1 and 50 percent inclusive
5. THE Discount_Configuration SHALL validate that the base monthly price is greater than the Scale plan price ($200)
