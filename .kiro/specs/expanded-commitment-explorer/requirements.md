# Requirements Document

## Introduction

The existing Committed Discounts feature in the SlashMyBill member portal provides SP/RI coverage and utilization scanning, purchase recommendations (Compute SP, EC2 Instance SP, EC2/RDS RIs), a laddering strategy, expiring commitments tracking, and an interactive SP/RI Explorer. This enhancement — **Expanded Commitment Explorer** — broadens the feature in five areas:

1. **Expand RI recommendations** to all AWS services that support Reserved Instances (adding ElastiCache, MemoryDB, OpenSearch, and Redshift alongside existing EC2 and RDS).
2. **Expand SP recommendations** by adding the PartialUpfront payment option (currently only NoUpfront and AllUpfront are queried) and adding SageMaker Savings Plans as a distinct SP type.
3. **Remove the Laddering Strategy** entirely — frontend panel, backend generation function, and the `POST /members/committed-discounts/ladder` API route.
4. **Add AWS Free Tier Tracking** — show which free tier benefits are in use, which are unused opportunities, and alert when approaching free tier limits.
5. **Add Free Tier Alternatives in Recommendations** — when showing RI/SP recommendations, check if workloads could be moved to free-tier-eligible resources instead of committing.

## Glossary

- **Member_Handler**: The existing Lambda `aws-bill-analyzer-member-api` that handles all member API routes
- **Cost_Explorer_Client**: A boto3 Cost Explorer client created using temporary credentials from the Cross_Account_Role
- **Cross_Account_Role**: The IAM role `SlashMyBill-{accountId}` deployed in each Customer_Account, assumed by Platform_Account Lambdas using STS with ExternalId = SHA256(memberEmail)
- **Customer_Account**: An AWS account connected to SlashMyBill via a cross-account IAM role
- **Reserved_Instance (RI)**: A capacity reservation providing a billing discount for a 1-year or 3-year term on specific instance types
- **Savings_Plan (SP)**: A flexible pricing model providing savings in exchange for a commitment to consistent usage ($/hr) for a 1-year or 3-year term
- **Compute_Savings_Plan**: An SP applying to any EC2, Fargate, or Lambda usage regardless of instance family, size, AZ, region, OS, or tenancy
- **EC2_Instance_Savings_Plan**: An SP applying to a specific instance family in a specific region, offering deeper discounts than Compute SPs
- **SageMaker_Savings_Plan**: An SP applying to SageMaker instance usage (notebook instances, training, inference endpoints) for a 1-year or 3-year term
- **Standard_RI**: A Reserved Instance that cannot be exchanged; offers the deepest discount
- **Convertible_RI**: A Reserved Instance that can be exchanged for a different configuration; offers a smaller discount
- **RI_Supported_Services**: The set of AWS services supporting Reserved Instances: EC2, RDS, ElastiCache, MemoryDB, OpenSearch, Redshift
- **Free_Tier_Benefit**: An AWS service usage allowance provided at no cost, either for 12 months after account creation (e.g., 750 hrs EC2 t2.micro) or always free (e.g., 1M Lambda requests/month)
- **Free_Tier_Usage_Percentage**: The proportion of a free tier benefit currently consumed in the billing period, expressed as a percentage [0–100]
- **Free_Tier_Alert_Threshold**: The usage percentage (80%) at which the system warns the member they are approaching a free tier limit
- **Free_Tier_Alternative**: A suggestion to move a workload to a free-tier-eligible resource type instead of purchasing a commitment
- **Laddering_Strategy**: (DEPRECATED — to be removed) A purchasing approach where commitments are staggered across multiple purchase dates
- **Act_Tab**: The member portal tab containing actionable optimization features
- **Committed_Discounts_Section**: The section within the Act_Tab displaying SP and RI scan results and the interactive explorer
- **Scan_Response**: The cached response from `POST /members/committed-discounts/scan` containing SP and RI recommendations

## Requirements

### Requirement 1: Expand RI Recommendations to All Supported Services

**User Story:** As a member with ElastiCache, MemoryDB, OpenSearch, or Redshift workloads, I want to receive Reserved Instance recommendations for those services, so that I can lock in savings on all steady-state resources — not just EC2 and RDS.

#### Acceptance Criteria

1. WHEN a member requests RI recommendations, THE Member_Handler SHALL call `ce:GetReservationPurchaseRecommendation` for all six RI_Supported_Services: EC2, RDS, ElastiCache, MemoryDB, OpenSearch, and Redshift.
2. WHEN requesting recommendations for each service, THE Member_Handler SHALL query for both Standard_RI and Convertible_RI offering classes.
3. WHEN requesting recommendations for each service, THE Member_Handler SHALL query for all three payment options (No Upfront, Partial Upfront, All Upfront) for both 1-year and 3-year terms.
4. WHEN returning recommendations, THE Member_Handler SHALL include for each recommendation: the service name, instance type (or node type for cache/search services), region, offering class, term, payment option, recommended instance count, estimated monthly savings, estimated savings percentage versus on-demand, upfront cost, and break-even months.
5. IF no RI recommendations are available from the API for a specific service, THEN THE Member_Handler SHALL return an empty list for that service with a message indicating no steady-state usage patterns detected for that service.
6. WHEN displaying RI recommendations in the RI_Explorer, THE Act_Tab SHALL group recommendations by service and allow the member to filter by service using a service selector dropdown.
7. THE RI_Explorer comparison table SHALL include a "Service" column to distinguish recommendations across the six supported services.

### Requirement 2: Add PartialUpfront Payment Option to SP Recommendations

**User Story:** As a member, I want to see PartialUpfront Savings Plan options alongside NoUpfront and AllUpfront, so that I can evaluate the middle-ground payment option that balances upfront cost with monthly savings.

#### Acceptance Criteria

1. WHEN a member requests Savings Plan recommendations, THE Member_Handler SHALL query `ce:GetSavingsPlansPurchaseRecommendation` for all six term-payment combinations: 1-year NoUpfront, 1-year PartialUpfront, 1-year AllUpfront, 3-year NoUpfront, 3-year PartialUpfront, and 3-year AllUpfront.
2. WHEN returning PartialUpfront recommendations, THE Member_Handler SHALL include the upfront cost, the recurring hourly commitment, the estimated monthly savings, the savings percentage, and the break-even point in months.
3. THE SP_Explorer interactive controls SHALL include PartialUpfront as a selectable payment option alongside NoUpfront and AllUpfront.
4. THE SP_Explorer comparison table SHALL include PartialUpfront rows, showing all six combinations (2 terms × 3 payment options) for each SP type.
5. WHEN calculating break-even for PartialUpfront options, THE Member_Handler SHALL use the formula: `upfrontCost / monthlySavings` where monthlySavings accounts for the reduced hourly rate compared to on-demand.

### Requirement 3: Add SageMaker Savings Plans

**User Story:** As a member with SageMaker workloads (notebook instances, training jobs, inference endpoints), I want to receive SageMaker Savings Plan recommendations, so that I can commit to SageMaker usage at a discounted rate.

#### Acceptance Criteria

1. WHEN a member requests Savings Plan recommendations, THE Member_Handler SHALL additionally query `ce:GetSavingsPlansPurchaseRecommendation` with SavingsPlanType set to "SageMakerSavingsPlans" for all six term-payment combinations.
2. WHEN the account has SageMaker spend detected in the Cost Explorer data, THE Member_Handler SHALL include SageMaker_Savings_Plan recommendations in the scan response alongside Compute SP and EC2 Instance SP recommendations.
3. WHEN displaying SageMaker SP recommendations, THE Act_Tab SHALL clearly label them as "SageMaker Savings Plan" and explain they apply to SageMaker notebook instances, training, and inference endpoint usage.
4. THE SP_Explorer SHALL include SageMaker Savings Plans as a distinct group with independent term and payment option selection controls.
5. THE SP_Explorer comparison table SHALL include SageMaker SP options alongside Compute SP and EC2 Instance SP when SageMaker recommendations are available.
6. IF no SageMaker usage is detected for the account, THEN THE Member_Handler SHALL omit SageMaker SP recommendations from the response rather than returning empty results.

### Requirement 4: Remove Laddering Strategy — Backend

**User Story:** As a developer, I want the laddering strategy backend code removed, so that the codebase is simplified and the deprecated feature no longer consumes maintenance effort.

#### Acceptance Criteria

1. THE Member_Handler SHALL remove the `_generate_laddering_strategy` function and all code that calls it.
2. THE Member_Handler SHALL remove the `POST /members/committed-discounts/ladder` route from the API routing table.
3. THE Member_Handler SHALL remove the laddering strategy object from the `POST /members/committed-discounts/scan` response payload (the `ladderingStrategy` field SHALL no longer be present in the response).
4. WHEN the scan endpoint is called, THE Member_Handler SHALL return the response without any laddering-related data, and the response schema SHALL not include a `ladderingStrategy` key.
5. IF a client sends a request to `POST /members/committed-discounts/ladder`, THEN THE Member_Handler SHALL return HTTP 404 with a message indicating the endpoint has been removed.

### Requirement 5: Remove Laddering Strategy — Frontend

**User Story:** As a member, I want the laddering strategy panel removed from the UI, so that the Committed Discounts section is focused on actionable recommendations without the deprecated staggered purchase plan.

#### Acceptance Criteria

1. THE Act_Tab SHALL remove the Laddering Strategy panel, including the timeline visualization, the summary table, the "Customize" modal, and the preset buttons (Conservative, Moderate, Aggressive).
2. THE Act_Tab SHALL remove the "Laddering Strategy" heading and all associated rendering code from the committed discounts section.
3. WHEN the scan response is received, THE Act_Tab SHALL not attempt to read or render any `ladderingStrategy` field from the response.
4. THE Act_Tab SHALL remove any navigation elements, buttons, or links that reference the laddering strategy (including the horizontal progress bar timeline and milestone markers).
5. WHEN the committed discounts section is displayed, THE Act_Tab SHALL show coverage/utilization, SP recommendations, RI recommendations, expiring commitments, and purchase guidance — without any laddering content.

### Requirement 6: AWS Free Tier Tracking — Usage Monitoring

**User Story:** As a member, I want to see which AWS Free Tier benefits my account is currently using and how much of each allowance has been consumed, so that I can avoid unexpected charges when free tier limits are exceeded.

#### Acceptance Criteria

1. WHEN a member requests a free tier scan, THE Member_Handler SHALL call the AWS Free Tier API (`freetier:GetFreeTierUsage`) via the Cross_Account_Role to retrieve current free tier usage data for the Customer_Account.
2. THE Member_Handler SHALL return for each active free tier benefit: the service name, the usage type description, the free tier limit (amount and unit), the actual usage amount, the Free_Tier_Usage_Percentage, and the forecasted usage for the billing period.
3. THE Member_Handler SHALL categorize each free tier benefit as "in-use" (usage > 0), "unused" (usage = 0 and the benefit is available), or "exceeded" (usage > limit).
4. WHEN a free tier benefit has Free_Tier_Usage_Percentage at or above 80%, THE Member_Handler SHALL flag it with an "approaching-limit" alert status.
5. THE Member_Handler SHALL track the following common free tier items when available: EC2 t2.micro or t3.micro (750 hours/month), S3 standard storage (5 GB), RDS db.t2.micro or db.t3.micro (750 hours/month), Lambda invocations (1 million requests/month), DynamoDB storage (25 GB), CloudWatch alarms (10 alarms), and SNS publishes (1 million/month).
6. IF the Cross_Account_Role lacks `freetier:GetFreeTierUsage` permission, THEN THE Member_Handler SHALL return an error indicating the missing permission and instructions to update the CloudFormation template.

### Requirement 7: AWS Free Tier Tracking — Frontend Display

**User Story:** As a member, I want a clear visual display of my free tier usage with progress bars and alerts, so that I can quickly identify which benefits are being consumed and which represent unused opportunities.

#### Acceptance Criteria

1. THE Act_Tab SHALL display a "Free Tier Tracker" panel within the Committed Discounts section, positioned after the coverage/utilization summary and before the SP/RI recommendations.
2. THE Free Tier Tracker panel SHALL display each tracked free tier benefit as a row with: the service icon, the benefit description, a progress bar showing usage percentage, the actual usage versus the limit (e.g., "580 / 750 hrs"), and the alert status.
3. WHEN a benefit has Free_Tier_Usage_Percentage at or above 80%, THE Free Tier Tracker SHALL display the progress bar in amber/warning color and show an "⚠️ Approaching Limit" badge.
4. WHEN a benefit has been exceeded (usage > limit), THE Free Tier Tracker SHALL display the progress bar in red and show a "🚨 Exceeded" badge with the overage amount.
5. THE Free Tier Tracker SHALL display unused benefits (usage = 0) in a separate "Opportunities" subsection with a message: "You have unused free tier benefits — consider using these before paying for resources."
6. THE Free Tier Tracker SHALL include a summary line at the top showing: total free tier benefits tracked, count in use, count approaching limit, count exceeded, and estimated monthly savings from free tier usage.
7. WHEN no free tier data is available (permission error or new account), THE Free Tier Tracker SHALL display an empty state explaining the requirement and linking to the CloudFormation template update.

### Requirement 8: AWS Free Tier Tracking — API Route

**User Story:** As a developer, I want a dedicated API route for free tier tracking, so that the feature is cleanly separated and can be called independently of the commitment scan.

#### Acceptance Criteria

1. THE Member_Handler SHALL expose a `POST /members/committed-discounts/free-tier` route that accepts `accountId` in the request body and returns free tier usage data.
2. THE Member_Handler SHALL validate the JWT token and verify account ownership before processing the free tier request.
3. WHEN the free tier route is called, THE Member_Handler SHALL return a response containing: the scan timestamp, the list of tracked free tier benefits with usage data, the categorized counts (in-use, unused, approaching-limit, exceeded), and the estimated monthly savings from free tier usage.
4. THE Member_Handler SHALL cache free tier results in the frontend sessionStorage alongside committed discount scan data, keyed as `freeTier_{accountId}`.
5. IF the AWS Free Tier API is unavailable or returns an error, THEN THE Member_Handler SHALL return HTTP 200 with an empty benefits list and an error message explaining the issue.

### Requirement 9: Free Tier Alternatives in Recommendations

**User Story:** As a member, I want to see when a workload could be moved to a free-tier-eligible resource instead of purchasing a commitment, so that I can save money without any long-term obligation.

#### Acceptance Criteria

1. WHEN displaying RI recommendations for EC2, THE Act_Tab SHALL check if any recommended instance types have a free-tier-eligible equivalent (t2.micro or t3.micro) and the workload characteristics (CPU, memory usage) suggest the smaller instance could handle the load.
2. WHEN a free tier alternative exists, THE Act_Tab SHALL display a "💡 Free Tier Alternative" callout alongside the RI recommendation, showing: the current instance type, the free-tier-eligible type, the estimated monthly savings from using free tier instead of purchasing an RI, and a note about the capacity trade-off.
3. THE free tier alternative suggestion SHALL only appear for instances where the recommended RI count is 1 (single instance workloads) and the instance type is in the t-family (t3.small, t3.medium, etc.) indicating a burstable workload that may fit on a smaller instance.
4. WHEN displaying a free tier alternative, THE Act_Tab SHALL include a disclaimer: "Free tier alternatives require workload validation — verify your application performs acceptably on the smaller instance before migrating."
5. THE Act_Tab SHALL calculate and display the savings comparison: "RI commitment saves $X/month vs on-demand. Free tier migration saves $Y/month with zero commitment." where Y is the full on-demand cost of the current instance (since free tier has no cost).
6. WHEN displaying RDS RI recommendations, THE Act_Tab SHALL similarly check if the workload could run on a free-tier-eligible db.t2.micro or db.t3.micro instance and display the alternative if applicable.

### Requirement 10: Free Tier Alternatives — Eligibility Check

**User Story:** As a member, I want the free tier alternative suggestions to account for whether my account is still within the 12-month free tier eligibility window, so that I only see relevant suggestions.

#### Acceptance Criteria

1. WHEN evaluating free tier alternatives, THE Member_Handler SHALL determine whether the Customer_Account is within the 12-month free tier eligibility period by checking the account creation date from the free tier usage API response.
2. IF the account is beyond the 12-month free tier eligibility period for time-limited benefits (EC2 750 hrs, RDS 750 hrs), THEN THE Act_Tab SHALL not display free tier alternatives for those services.
3. WHEN the account has fewer than 3 months remaining in the free tier eligibility period, THE Act_Tab SHALL display a note: "Free tier eligibility expires in X months — consider an RI commitment for long-term savings after that date."
4. THE Act_Tab SHALL still display free tier alternatives for always-free benefits (Lambda 1M requests, DynamoDB 25 GB, CloudWatch 10 alarms) regardless of account age.
5. WHEN free tier eligibility cannot be determined (API limitation), THE Act_Tab SHALL display the alternative with a caveat: "Verify your account's free tier eligibility in the AWS Billing console."

### Requirement 11: Updated IAM Permission Requirements

**User Story:** As a developer, I want the cross-account role to include permissions for the expanded services and free tier API, so that all new features function correctly.

#### Acceptance Criteria

1. WHEN a member generates a cross-account CloudFormation template, THE Member_Handler SHALL include the `freetier:GetFreeTierUsage` IAM action in addition to all existing Cost Explorer permissions.
2. THE Member_Handler SHALL include RI recommendation permissions that cover all six RI_Supported_Services (the existing `ce:GetReservationPurchaseRecommendation` permission already covers all services — no additional service-specific permissions are needed).
3. WHEN the free tier scan detects a missing `freetier:GetFreeTierUsage` permission, THE Member_Handler SHALL return a specific error message listing the missing action and a link to the CloudFormation template update instructions.
4. THE Member_Handler SHALL verify free tier permissions by attempting the `freetier:GetFreeTierUsage` call and handling AccessDenied gracefully with a clear error message.

### Requirement 12: Updated Scan Response Schema

**User Story:** As a developer, I want the scan response to reflect the expanded services and removed laddering, so that the API contract is clear and consistent.

#### Acceptance Criteria

1. THE `POST /members/committed-discounts/scan` response SHALL include RI recommendations grouped by all six RI_Supported_Services instead of only EC2 and RDS.
2. THE scan response SHALL include SP recommendations for three types: Compute_Savings_Plan, EC2_Instance_Savings_Plan, and SageMaker_Savings_Plan (when applicable).
3. THE scan response SHALL include six term-payment combinations per SP type (adding PartialUpfront) instead of the previous four.
4. THE scan response SHALL NOT include a `ladderingStrategy` field.
5. THE scan response SHALL NOT include any reference to the ladder endpoint or laddering-related data.
6. THE scan response SHALL include a `freeTierSummary` field containing: the count of tracked benefits, count approaching limit, count exceeded, and estimated monthly savings from free tier — providing a quick overview without requiring a separate free tier API call.

