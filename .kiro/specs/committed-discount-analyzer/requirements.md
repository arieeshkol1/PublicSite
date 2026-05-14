# Requirements Document

## Introduction

SlashMyBill currently identifies cost optimization opportunities through waste cleanup, service optimization (rightsizing, Spot migration, Graviton), and scheduling. However, the platform does not yet provide guidance on **committed discount instruments** — Reserved Instances (RIs) and Savings Plans (SPs) — which represent the largest single savings lever for steady-state workloads (30–72% off On-Demand). This feature adds a new "Committed Discounts" card to the Act tab that analyzes current RI/SP coverage and utilization, retrieves AWS-native purchase recommendations, and presents an actionable laddering strategy with estimated savings, break-even analysis, and purchase guidance. The system uses the AWS Cost Explorer recommendation APIs (`ce:GetReservationPurchaseRecommendation`, `ce:GetSavingsPlansPurchaseRecommendation`) and coverage/utilization APIs (`ce:GetReservationCoverage`, `ce:GetReservationUtilization`, `ce:GetSavingsPlansCoverage`, `ce:GetSavingsPlansUtilization`) via the existing cross-account STS AssumeRole pattern.

## Glossary

- **Platform_Account**: The SlashMyBill AWS account (991105135552) where all platform infrastructure runs
- **Customer_Account**: An AWS account connected to SlashMyBill via a cross-account IAM role
- **Cross_Account_Role**: The IAM role `SlashMyBill-{accountId}` deployed in each Customer_Account, assumed by Platform_Account Lambdas using STS with ExternalId = SHA256(memberEmail)
- **Member_Handler**: The existing Lambda `aws-bill-analyzer-member-api` that handles all member API routes
- **Cost_Explorer_Client**: A boto3 Cost Explorer client created using temporary credentials from the Cross_Account_Role
- **Reserved_Instance (RI)**: A capacity reservation that provides a billing discount for a 1-year or 3-year term on specific instance types in specific regions
- **Savings_Plan (SP)**: A flexible pricing model that provides savings (similar to RIs) in exchange for a commitment to a consistent amount of usage (measured in $/hr) for a 1-year or 3-year term
- **Compute_Savings_Plan**: A Savings Plan that applies to any EC2, Fargate, or Lambda usage regardless of instance family, size, AZ, region, OS, or tenancy
- **EC2_Instance_Savings_Plan**: A Savings Plan that applies to a specific instance family in a specific region, offering deeper discounts than Compute Savings Plans
- **Standard_RI**: A Reserved Instance that cannot be exchanged for a different instance type; offers the deepest discount
- **Convertible_RI**: A Reserved Instance that can be exchanged for a different instance type, family, OS, or tenancy; offers a smaller discount than Standard RIs
- **Coverage_Percentage**: The proportion of eligible usage hours covered by active RIs or SPs, expressed as a percentage [0–100]
- **Utilization_Percentage**: The proportion of purchased RI/SP hours that are actually consumed, expressed as a percentage [0–100]
- **Laddering_Strategy**: A purchasing approach where commitments are staggered across multiple purchase dates so that they expire at different times, reducing renewal risk and enabling flexibility
- **Break_Even_Point**: The number of months after purchase at which cumulative savings exceed the upfront cost (for upfront payment options)
- **Commitment_Baseline**: The recommended commitment level, typically 60–70% of steady-state baseline usage, to avoid over-commitment during usage dips
- **Act_Tab**: The member portal tab containing actionable optimization features (Waste Cleanup, Service Optimization, Scheduler)
- **Database_Savings_Plan**: A Savings Plan that applies to RDS, ElastiCache, MemoryDB, and DynamoDB reserved capacity usage
- **P10_Baseline**: The 10th percentile of hourly compute spend over 30 days — represents the minimum sustained floor of usage and the safest commitment level
- **Organization_Sharing**: AWS feature where RIs and SPs purchased in one account automatically apply to eligible usage in other accounts within the same AWS Organization

## Requirements

### Requirement 1: Committed Discounts Navigation

**User Story:** As a member, I want to see a "Committed Discounts" section in the Act tab navigation, so that I can access RI and Savings Plan analysis alongside other optimization actions.

#### Acceptance Criteria

1. THE Act_Tab navigation pane SHALL include a "Committed Discounts" button with a 💰 icon, positioned after the Scheduler button.
2. WHEN a member clicks the "Committed Discounts" navigation button, THE Act_Tab SHALL display the committed discounts section and hide all other Act sections.
3. THE committed discounts section SHALL display two sub-sections: "Savings Plans" and "Reserved Instances".
4. WHEN the committed discounts section is displayed with no scan results, THE Act_Tab SHALL show an empty state prompting the member to select an account and scan for recommendations.

### Requirement 2: Current Coverage and Utilization Scan

**User Story:** As a member, I want to scan my account to see current RI and Savings Plan coverage and utilization, so that I understand my existing commitment posture before purchasing more.

#### Acceptance Criteria

1. WHEN a member triggers a committed discount scan for a Customer_Account, THE Member_Handler SHALL call `ce:GetSavingsPlansCoverage` and `ce:GetSavingsPlansUtilization` for the trailing 30-day period and return aggregate coverage and utilization percentages.
2. WHEN a member triggers a committed discount scan for a Customer_Account, THE Member_Handler SHALL call `ce:GetReservationCoverage` and `ce:GetReservationUtilization` for the trailing 30-day period and return aggregate coverage and utilization percentages.
3. WHEN returning coverage data, THE Member_Handler SHALL include a breakdown by service (EC2, RDS, ElastiCache, Redshift, OpenSearch) showing per-service coverage percentages.
4. WHEN returning utilization data, THE Member_Handler SHALL flag any RI or SP with utilization below 80% as "underutilized" with the specific utilization percentage.
5. IF the Cross_Account_Role lacks Cost Explorer permissions, THEN THE Member_Handler SHALL return an error indicating insufficient permissions and list the required actions.
6. WHEN the Cost Explorer API returns no data (new account or no usage history), THE Member_Handler SHALL return coverage of 0% and utilization of 0% with a message indicating insufficient usage history.

### Requirement 3: Savings Plan Purchase Recommendations

**User Story:** As a member, I want to receive Savings Plan purchase recommendations based on my usage patterns, so that I can commit to the right amount and type of Savings Plan.

#### Acceptance Criteria

1. WHEN a member requests Savings Plan recommendations, THE Member_Handler SHALL call `ce:GetSavingsPlansPurchaseRecommendation` for both Compute_Savings_Plan and EC2_Instance_Savings_Plan types.
2. WHEN requesting recommendations, THE Member_Handler SHALL query for all four term-payment combinations: 1-year No Upfront, 1-year All Upfront, 3-year No Upfront, and 3-year All Upfront.
3. WHEN returning recommendations, THE Member_Handler SHALL include for each recommendation: the plan type, term length, payment option, hourly commitment amount, estimated monthly savings, estimated savings percentage, and estimated monthly on-demand cost equivalent.
4. WHEN returning recommendations, THE Member_Handler SHALL calculate and include the break-even point in months for upfront payment options using the formula: `upfrontCost / monthlySavings`.
5. THE Member_Handler SHALL apply the Commitment_Baseline rule by flagging any recommendation whose hourly commitment exceeds 70% of the account's average hourly on-demand spend as "aggressive" and recommending the 60–70% range instead.
6. WHEN no Savings Plan recommendations are available from the API, THE Member_Handler SHALL return an empty recommendations list with a message indicating the account has insufficient usage history (minimum 7 days required).

### Requirement 4: Reserved Instance Purchase Recommendations

**User Story:** As a member, I want to receive Reserved Instance purchase recommendations for my EC2 and RDS workloads, so that I can lock in savings on steady-state instances.

#### Acceptance Criteria

1. WHEN a member requests RI recommendations, THE Member_Handler SHALL call `ce:GetReservationPurchaseRecommendation` for services EC2 and RDS.
2. WHEN requesting recommendations, THE Member_Handler SHALL query for both Standard_RI and Convertible_RI offering classes.
3. WHEN requesting recommendations, THE Member_Handler SHALL query for all three payment options: No Upfront, Partial Upfront, and All Upfront, for both 1-year and 3-year terms.
4. WHEN returning recommendations, THE Member_Handler SHALL include for each recommendation: the service, instance type, region, offering class (Standard or Convertible), term, payment option, recommended instance count, estimated monthly savings, and estimated savings percentage versus on-demand.
5. WHEN returning recommendations, THE Member_Handler SHALL calculate and include the break-even point in months for Partial Upfront and All Upfront options.
6. WHEN returning recommendations, THE Member_Handler SHALL include a comparison note for each instance type showing the discount difference between Standard and Convertible RIs.
7. IF no RI recommendations are available from the API for a service, THEN THE Member_Handler SHALL return an empty list for that service with a message indicating no steady-state usage patterns detected.

### Requirement 5: Laddering Strategy Generation

**User Story:** As a member, I want a staggered purchase plan that spreads my commitments over time, so that I reduce renewal risk and maintain flexibility to adjust as my usage evolves.

#### Acceptance Criteria

1. WHEN a member requests a laddering strategy, THE Member_Handler SHALL divide the total recommended commitment into quarterly tranches spread over 12 months (4 purchase events).
2. WHEN generating a laddering strategy, THE Member_Handler SHALL allocate each tranche as approximately 25% of the total recommended hourly commitment, rounded to the nearest $0.01/hr.
3. WHEN generating a laddering strategy, THE Member_Handler SHALL assign purchase dates at months 0, 3, 6, and 9 from the current date.
4. WHEN returning the laddering strategy, THE Member_Handler SHALL include for each tranche: the purchase date, the hourly commitment amount, the cumulative committed amount after purchase, and the estimated monthly savings at that point.
5. WHEN generating a laddering strategy, THE Member_Handler SHALL prefer Compute_Savings_Plan for the first two tranches (flexibility) and allow EC2_Instance_Savings_Plan for later tranches (deeper discount) if usage patterns are stable.
6. THE Member_Handler SHALL validate that the total laddered commitment does not exceed 70% of the account's trailing 30-day average hourly on-demand spend.

### Requirement 6: Savings Estimation and Comparison

**User Story:** As a member, I want to see a clear comparison of savings across different commitment options, so that I can make an informed purchase decision.

#### Acceptance Criteria

1. WHEN displaying recommendations, THE Act_Tab SHALL show a comparison table with columns: Type (SP/RI), Term (1yr/3yr), Payment Option, Monthly Cost, Monthly Savings, Savings Percentage, and Break-Even Months.
2. WHEN displaying Savings Plan recommendations, THE Act_Tab SHALL highlight the Compute_Savings_Plan option as "Recommended for flexibility" when the member has diverse workloads (more than 2 services with significant spend).
3. WHEN displaying RI recommendations, THE Act_Tab SHALL show both Standard and Convertible options side-by-side with the discount difference clearly labeled.
4. WHEN displaying payment option comparisons, THE Act_Tab SHALL show the total cost of ownership over the full term for each payment option (No Upfront total, Partial Upfront total, All Upfront total).
5. THE Act_Tab SHALL display a summary card at the top showing: current coverage percentage, current utilization percentage, total estimated annual savings if all recommendations are adopted, and the recommended commitment level (60–70% of baseline).

### Requirement 7: Purchase Guidance

**User Story:** As a member, I want clear instructions on how to purchase the recommended RIs and Savings Plans, so that I can act on the recommendations without confusion.

#### Acceptance Criteria

1. WHEN a member clicks "How to Purchase" for a Savings Plan recommendation, THE Act_Tab SHALL display step-by-step instructions including: navigate to AWS Cost Explorer → Savings Plans → Purchase Savings Plans, select the plan type, enter the hourly commitment, choose the term and payment option.
2. WHEN a member clicks "How to Purchase" for an RI recommendation, THE Act_Tab SHALL display step-by-step instructions including: navigate to the relevant service console (EC2 or RDS) → Reserved Instances → Purchase Reserved Instances, select the instance type, choose the offering class, term, and payment option.
3. THE purchase guidance SHALL include a direct link to the relevant AWS console page for the Customer_Account (using the account's region).
4. THE purchase guidance SHALL include a warning that purchases are non-refundable commitments and recommend starting with the laddering strategy rather than purchasing the full recommended amount at once.

### Requirement 8: IAM Permission Requirements

**User Story:** As a member, I want the cross-account role to include Cost Explorer permissions, so that SlashMyBill can retrieve my RI and SP data.

#### Acceptance Criteria

1. WHEN a member generates a cross-account CloudFormation template with committed discount analysis enabled, THE Member_Handler SHALL include the following IAM actions: `ce:GetSavingsPlansPurchaseRecommendation`, `ce:GetReservationPurchaseRecommendation`, `ce:GetSavingsPlansUtilization`, `ce:GetSavingsPlansCoverage`, `ce:GetReservationUtilization`, `ce:GetReservationCoverage`.
2. WHEN the committed discount scan detects missing permissions, THE Member_Handler SHALL return a specific error message listing the missing IAM actions and a link to the CloudFormation template update instructions.
3. THE Member_Handler SHALL verify Cost Explorer permissions by attempting a lightweight API call (`ce:GetSavingsPlansCoverage` with a 1-day range) before executing the full scan, and return a clear permission error if it fails.

### Requirement 9: Scan Results Caching

**User Story:** As a member, I want scan results to be cached so that navigating between tabs does not trigger repeated API calls, so that the experience is fast and responsive.

#### Acceptance Criteria

1. WHEN a committed discount scan completes, THE Member_Handler SHALL cache the results in the member's session context (frontend) for the duration of the browser session.
2. WHEN a member navigates back to the Committed Discounts section within the same session, THE Act_Tab SHALL display cached results immediately without re-scanning.
3. WHEN a member clicks "Rescan" or selects a different account, THE Act_Tab SHALL clear the cache for that account and perform a fresh scan.
4. THE Member_Handler SHALL include a `scannedAt` timestamp in the response so the frontend can display when the data was last refreshed.

### Requirement 10: Committed Discount API Route

**User Story:** As a developer, I want a dedicated API route for committed discount analysis, so that the feature is cleanly separated from other member handler routes.

#### Acceptance Criteria

1. THE Member_Handler SHALL expose a `POST /members/committed-discounts/scan` route that accepts `accountId` in the request body and returns coverage, utilization, SP recommendations, RI recommendations, and a laddering strategy.
2. THE Member_Handler SHALL validate the JWT token and verify account ownership before processing the scan request.
3. WHEN the scan route is called, THE Member_Handler SHALL return a response within 30 seconds. IF the Cost Explorer APIs take longer, THEN THE Member_Handler SHALL return a timeout error with a suggestion to retry.
4. THE Member_Handler SHALL expose a `POST /members/committed-discounts/ladder` route that accepts `accountId` and `totalHourlyCommitment` and returns a customized laddering strategy.
5. WHEN the ladder route receives a `totalHourlyCommitment` that exceeds 70% of the account's average hourly spend, THE Member_Handler SHALL return a warning indicating the commitment is aggressive and suggest the 60–70% range.


### Requirement 11: Database Savings Plans

**User Story:** As a member with RDS, ElastiCache, MemoryDB, or DynamoDB workloads, I want to receive Database Savings Plan recommendations, so that I can save on database services beyond just compute.

#### Acceptance Criteria

1. WHEN a member requests Savings Plan recommendations, THE Member_Handler SHALL also query for Database Savings Plans (SageMaker Savings Plans type "SageMakerSavingsPlans" is separate; for databases use the reservation recommendation API for RDS/ElastiCache/MemoryDB).
2. WHEN the account has RDS or ElastiCache spend exceeding $50/month, THE Member_Handler SHALL include Database Savings Plan recommendations alongside Compute SP recommendations.
3. WHEN displaying Database SP recommendations, THE Act_Tab SHALL clearly label them as "Database Savings Plan" and explain they apply to RDS, ElastiCache, MemoryDB, and DynamoDB reserved capacity.
4. THE comparison table SHALL include Database SP options alongside Compute SP and EC2 Instance SP for accounts with significant database spend.

### Requirement 12: P10 Baseline Commitment Calculation

**User Story:** As a member, I want my commitment recommendation to be based on the 10th percentile of my hourly spend (not just an average), so that I avoid over-committing during usage dips.

#### Acceptance Criteria

1. WHEN calculating the Commitment_Baseline, THE Member_Handler SHALL retrieve hourly cost data for the trailing 30 days using `ce:GetCostAndUsage` with HOURLY granularity.
2. THE Member_Handler SHALL sort the hourly spend values ascending and use the 10th percentile (p10) as the maximum safe commitment amount.
3. WHEN the p10 baseline is significantly lower than the average (more than 30% difference), THE Act_Tab SHALL display a warning: "Your usage is variable — committing to the p10 floor ensures you never waste commitment dollars during low-usage periods."
4. THE Act_Tab SHALL display both the p10 baseline and the average hourly spend, with a visual indicator showing the safe commitment zone (p10 to 70% of average).
5. WHEN the account has fewer than 7 days of hourly data, THE Member_Handler SHALL fall back to daily granularity and note that hourly precision is not yet available.

### Requirement 13: Rightsize-First Warning

**User Story:** As a member, I want to be warned not to purchase commitments on oversized instances, so that I don't lock in waste for 1-3 years.

#### Acceptance Criteria

1. WHEN displaying RI or SP recommendations, THE Act_Tab SHALL check if the member has pending rightsizing recommendations (from Compute Optimizer or the Service Optimization scan).
2. IF rightsizing recommendations exist for instances that would be covered by the proposed commitment, THEN THE Act_Tab SHALL display a prominent warning: "⚠️ Rightsize first — do NOT buy commitments on oversized instances. Downsize these instances first, then commit at the lower rate."
3. THE warning SHALL list the specific instances that should be rightsized before committing, with their current type and recommended type.
4. THE Act_Tab SHALL provide a link to the Service Optimization → Resize section for each flagged instance.

### Requirement 14: Expiring Commitments Timeline

**User Story:** As a member, I want to see when my existing RIs and Savings Plans expire, so that I can plan renewals and avoid coverage gaps.

#### Acceptance Criteria

1. WHEN displaying current coverage data, THE Member_Handler SHALL retrieve active RI and SP details including their expiration dates.
2. THE Act_Tab SHALL display a timeline showing commitments expiring in the next 90 days with their monthly value and coverage impact.
3. WHEN a commitment expires within 30 days, THE Act_Tab SHALL highlight it with a "⚠️ Expiring Soon" badge and recommend renewal or replacement.
4. THE Act_Tab SHALL calculate the coverage gap (percentage drop) that will occur when each commitment expires, helping the member understand the urgency of renewal.
5. WHEN no commitments are expiring in the next 90 days, THE Act_Tab SHALL display "No upcoming expirations" with the next expiration date if any exist.

### Requirement 15: Organization-Wide Sharing Awareness

**User Story:** As a member with multiple connected accounts in an AWS Organization, I want to understand how RI/SP sharing works across accounts, so that I can optimize at the organization level.

#### Acceptance Criteria

1. WHEN a member has multiple connected accounts, THE Act_Tab SHALL display a note explaining that Savings Plans and RIs can be shared across accounts in the same AWS Organization.
2. WHEN displaying recommendations, THE Member_Handler SHALL indicate whether the recommendation applies to a single account or could benefit from organization-wide sharing.
3. IF the scanned account is a management (payer) account, THEN THE Member_Handler SHALL aggregate usage across all linked accounts when generating recommendations (using the management account's Cost Explorer which sees consolidated billing).
4. THE Act_Tab SHALL include a "💡 Tip" explaining: "Purchase commitments from the management account for maximum flexibility — they automatically apply to the highest-matching usage across all linked accounts."
