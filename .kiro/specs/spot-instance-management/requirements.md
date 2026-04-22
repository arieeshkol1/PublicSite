# Requirements Document

## Introduction

SlashMyBill currently identifies Spot Instance candidates passively through the waste-scan engine, flagging non-production EC2 instances with low CPU as advisory cards. This feature expands that passive detection into a full autonomous Spot Instance lifecycle orchestration system. The feature covers four major areas: **Configure** (IAM role expansion, Spot opt-in toggle, workload qualification), **Plan** (Spot Placement Score forecasting via Bedrock Agent, attribute-based instance selection, capacity mix configuration), **Observe** (dashboard widget for On-Demand vs Spot ratio, Effective Savings Rate tracking, savings ledger for gainshare billing), and **Act** (ASG migration to price-capacity-optimized strategy). The system operates cross-account via the existing STS AssumeRole pattern and stores savings tracking data in a new DynamoDB table (SpotSavingsLedger) to support the 30% gainshare billing model. ASG with price-capacity-optimized handles Spot interruptions natively — no custom replacement logic is needed. An EventBridge → SNS → Lambda push pipeline delivers real-time email notifications to the customer within seconds of an interruption.

## Glossary

- **Platform_Account**: The SlashMyBill AWS account (991105135552) where all platform infrastructure runs
- **Customer_Account**: An AWS account connected to SlashMyBill via a cross-account IAM role
- **Cross_Account_Role**: The IAM role `SlashMyBill-{accountId}` deployed in each Customer_Account, assumed by Platform_Account Lambdas using STS with ExternalId = SHA256(memberEmail)
- **Member_Handler**: The existing Lambda `aws-bill-analyzer-member-api` that handles all member API routes
- **Agent_Action_Lambda**: The existing Lambda that handles Bedrock Agent action group invocations
- **Bedrock_Agent**: The Bedrock Agent (IDG5VJGUOZ5W, Alias 9VYFXAEEH6) used for AI-powered cost optimization queries
- **Members_Table**: The DynamoDB table `MemberPortal-Members` that stores member data including `spotConfig`
- **SpotSavingsLedger**: A new DynamoDB table that tracks per-instance-hour savings deltas between On-Demand and Spot rates for gainshare billing
- **Spot_Config**: The `spotConfig` field on a member DynamoDB item that stores per-account Spot enablement, qualified ASGs, excluded ASGs, and migrated ASG snapshots
- **ASG**: Auto Scaling Group — the AWS resource that manages a fleet of EC2 instances
- **MixedInstancesPolicy**: An ASG configuration that blends On-Demand and Spot Instances using attribute-based instance selection
- **Capacity_Mix**: The On-Demand/Spot blend ratio defined by `onDemandBaseCapacity` and `onDemandPercentageAboveBase`
- **Spot_Placement_Score**: An AWS API (ec2:GetSpotPlacementScores) that returns a 1-10 score indicating Spot capacity availability per region/AZ
- **ESR**: Effective Savings Rate — the ratio of actual savings to maximum possible savings, bounded [0.0, 1.0]
- **Gainshare**: The 30% fee SlashMyBill charges on realized Spot savings
- **Interruption_Notification_Pipeline**: EventBridge rule in the Customer_Account catches Spot interruption events → publishes to SNS topic in Platform_Account → invokes Member_Handler Lambda → sends email to member via SES. Purpose: real-time email notification only (ASG handles replacement natively).
- **Workload_Qualification**: The process of evaluating which ASGs are safe for Spot migration based on tags, redundancy, statefulness, and environment

## Requirements

### Requirement 1: Spot Opt-In Configuration

**User Story:** As a member, I want to enable or disable Spot Instance management per connected account, so that I control which accounts participate in Spot optimization.

#### Acceptance Criteria

1. WHEN a member submits a Spot enablement request for a Customer_Account, THE Member_Handler SHALL validate account ownership, store the Spot_Config on the member item in the Members_Table, and return the updated configuration.
2. WHEN a member enables Spot management for a Customer_Account, THE Member_Handler SHALL accept a list of qualified ASG names and a list of excluded ASG names, and SHALL reject the request if any ASG name appears in both lists.
3. WHEN a member enables Spot management (`spotEnabled=true`), THE Member_Handler SHALL automatically deploy an EventBridge rule into the Customer_Account via the Cross_Account_Role that matches Spot interruption events and targets the platform SNS topic for real-time email notifications.
4. WHEN a member disables Spot management (`spotEnabled=false`), THE Member_Handler SHALL remove the EventBridge rule from the Customer_Account and clear the rule ARN from the Spot_Config.
5. IF the Cross_Account_Role lacks the required Spot permissions, THEN THE Member_Handler SHALL return an error indicating insufficient permissions and prompt the member to update the cross-account template.
6. WHEN a member submits ASG names for qualification, THE Member_Handler SHALL validate that each ASG exists in the Customer_Account before storing the qualified list.

### Requirement 2: Workload Qualification Validation

**User Story:** As a member, I want SlashMyBill to evaluate which of my ASGs are safe for Spot migration, so that I avoid migrating database or stateful workloads that cannot tolerate interruptions.

#### Acceptance Criteria

1. WHEN a member requests workload qualification for a list of ASG names, THE Member_Handler SHALL return a qualification result for each ASG with status in {qualified, excluded, ineligible}.
2. WHEN evaluating an ASG, THE Member_Handler SHALL classify the ASG as excluded if the ASG name or tags contain database-related keywords (database, db, rds, mongo, redis, elastic).
3. WHEN evaluating an ASG, THE Member_Handler SHALL classify the ASG as excluded if the ASG has a `Stateful=true` tag.
4. WHEN evaluating an ASG, THE Member_Handler SHALL classify the ASG as excluded if the ASG has MaxSize of 1 or less (single-instance, no redundancy).
5. WHEN evaluating an ASG, THE Member_Handler SHALL classify the ASG as excluded if the ASG already has a MixedInstancesPolicy with a Spot allocation strategy.
6. WHEN evaluating an ASG, THE Member_Handler SHALL classify the ASG as excluded if the ASG is tagged as production and runs in fewer than 2 availability zones.
7. FOR ALL qualification requests containing N ASG names, THE Member_Handler SHALL return exactly N results where the count of qualified plus excluded plus ineligible equals N.
8. IF an ASG name does not exist in the Customer_Account, THEN THE Member_Handler SHALL classify that ASG as ineligible with reason "ASG not found".

### Requirement 3: IAM Cross-Account Template Expansion

**User Story:** As a member, I want the cross-account CloudFormation template to include all Spot management permissions, so that SlashMyBill can execute Spot operations in my account.

#### Acceptance Criteria

1. WHEN a member generates a cross-account CloudFormation template with Spot management enabled, THE Member_Handler SHALL include the following IAM actions: `ec2:GetSpotPlacementScores`, `ec2:DescribeSpotInstanceRequests`, `autoscaling:UpdateAutoScalingGroup`, `autoscaling:DescribeAutoScalingGroups`, `events:PutRule`, `events:PutTargets`, `events:DeleteRule`, `events:RemoveTargets`.
2. WHEN Spot management is not enabled for an account, THE Member_Handler SHALL generate the template without the Spot-specific IAM actions.

### Requirement 4: Spot Placement Score Forecasting

**User Story:** As a member, I want to query Spot capacity availability through the Bedrock Agent chat, so that I can assess Spot viability before committing to migration.

#### Acceptance Criteria

1. WHEN the Bedrock_Agent receives a Spot availability query, THE Agent_Action_Lambda SHALL call `ec2:GetSpotPlacementScores` in the Customer_Account using the Cross_Account_Role with the specified instance requirements.
2. WHEN returning Spot Placement Scores, THE Agent_Action_Lambda SHALL return scores sorted by score descending, with each score as an integer in the range [1, 10].
3. WHEN returning Spot Placement Scores, THE Agent_Action_Lambda SHALL include region and availability zone for each score entry, with no duplicate region-AZ combinations.
4. WHEN the Spot Placement Score API is unavailable, THE Agent_Action_Lambda SHALL return cached scores if available within a 15-minute window, or return a service unavailable error.
5. WHEN instance requirements are provided, THE Agent_Action_Lambda SHALL translate vCPU min/max and memory min/max into the `InstanceRequirementsWithMetadata` format required by the AWS API.

### Requirement 5: Capacity Mix Configuration

**User Story:** As a member, I want to configure the On-Demand/Spot blend ratio per ASG before migration, so that I can control my risk exposure and maintain a baseline of On-Demand capacity.

#### Acceptance Criteria

1. WHEN a member submits a capacity mix plan for an ASG, THE Member_Handler SHALL fetch the current ASG configuration from the Customer_Account and return both the current and proposed configurations.
2. WHEN calculating the proposed configuration, THE Member_Handler SHALL compute the On-Demand count as `onDemandBaseCapacity + ceil((desiredCapacity - onDemandBaseCapacity) * onDemandPercentageAboveBase / 100)` and the Spot count as `desiredCapacity - onDemandCount`.
3. WHEN a capacity mix plan is submitted, THE Member_Handler SHALL query Spot Placement Scores for the configured instance requirements and include the scores in the response.
4. WHEN a capacity mix plan is submitted, THE Member_Handler SHALL estimate monthly savings based on current On-Demand pricing versus historical Spot pricing for the matching instance types.
5. WHEN instance requirements are configured, THE Member_Handler SHALL validate that the attribute-based selection matches at least 10 distinct instance types in the target region. IF fewer than 10 match, THEN THE Member_Handler SHALL reject the plan with an error suggesting broader requirements.
6. WHEN a capacity mix plan is submitted, THE Member_Handler SHALL validate that `onDemandBaseCapacity` is between 0 and the ASG maxSize, and `onDemandPercentageAboveBase` is between 0 and 100.

### Requirement 6: ASG Spot Migration Execution

**User Story:** As a member, I want to execute the migration of an ASG to use Spot Instances with the price-capacity-optimized strategy, so that I can realize cost savings on my compute workloads.

#### Acceptance Criteria

1. WHEN a member requests a dry-run migration, THE Member_Handler SHALL return the proposed changes (LaunchTemplate to MixedInstancesPolicy conversion, instance type to attribute-based selection, allocation strategy, On-Demand/Spot split) without modifying the ASG.
2. WHEN a member requests a migration execution, THE Member_Handler SHALL snapshot the current ASG configuration (LaunchTemplate, DesiredCapacity, MinSize, MaxSize, existing MixedInstancesPolicy) to DynamoDB before applying changes.
3. WHEN executing a migration, THE Member_Handler SHALL apply a MixedInstancesPolicy with `SpotAllocationStrategy` set to `price-capacity-optimized`, the configured `OnDemandBaseCapacity`, `OnDemandPercentageAboveBaseCapacity`, and attribute-based instance selection overrides.
4. WHEN a migration completes, THE Member_Handler SHALL record the migration event in the SpotSavingsLedger and update the Spot_Config with the migrated ASG details.
5. WHEN a member requests a migration, THE Member_Handler SHALL verify the ASG is in the qualified list and not in the excluded list before proceeding. IF the ASG is excluded, THEN THE Member_Handler SHALL reject the request with the exclusion reasons.
6. IF the ASG update fails during migration, THEN THE Member_Handler SHALL return an error without attempting automatic rollback (the ASG remains unchanged on API failure).

### Requirement 7: Migration Rollback

**User Story:** As a member, I want to roll back a Spot migration to restore the original ASG configuration, so that I can revert if the migration causes issues.

#### Acceptance Criteria

1. WHEN a member requests a rollback for a migrated ASG, THE Member_Handler SHALL restore the ASG to the exact pre-migration configuration stored in the DynamoDB snapshot (LaunchTemplate, DesiredCapacity, MinSize, MaxSize, and removal of MixedInstancesPolicy if none existed before).
2. WHEN a migration is executed, THE Member_Handler SHALL make the rollback available for 7 days from the migration timestamp.
3. IF a member requests a rollback after the 7-day window, THEN THE Member_Handler SHALL reject the request with an error indicating the rollback has expired.
4. WHEN a rollback completes, THE Member_Handler SHALL record the rollback event in the SpotSavingsLedger and update the Spot_Config to remove the migrated ASG entry.

### Requirement 8: Spot Savings Ledger

**User Story:** As a platform operator, I want to track the per-instance-hour savings delta between On-Demand and Spot rates, so that I can calculate the 30% gainshare billing accurately.

#### Acceptance Criteria

1. WHEN a savings entry is recorded, THE Member_Handler SHALL compute `savingsPerHour` as `onDemandRate - spotRate`, `totalSavings` as `savingsPerHour * hours`, and `gainshareAmount` as `totalSavings * 0.30`.
2. WHEN a savings entry is recorded, THE Member_Handler SHALL validate that `spotRate` is less than or equal to `onDemandRate`.
3. WHEN a savings entry is recorded, THE Member_Handler SHALL set a TTL of 12 months from the recording timestamp for automatic cleanup.
4. THE SpotSavingsLedger SHALL use partition key `memberEmail#accountId` and sort key `timestamp#instanceId` to support efficient per-account time-range queries.
5. THE SpotSavingsLedger SHALL include a Global Secondary Index (MemberTimeIndex) with partition key `memberEmail` and sort key `recordedAt` to support cross-account aggregation queries.
6. WHEN recording a savings entry, THE Member_Handler SHALL include the `eventType` field with value in {running, interrupted, migrated, rolled-back} to distinguish between ongoing savings and lifecycle events.

### Requirement 9: Spot Operations Dashboard

**User Story:** As a member, I want to see a dashboard widget showing my On-Demand vs Spot capacity ratio, savings trend, and interruption metrics, so that I can monitor the health and value of my Spot usage.

#### Acceptance Criteria

1. WHEN a member loads the Spot dashboard, THE Member_Handler SHALL return capacity ratio data where `total` equals `onDemand + spot`, and `spotPercentage` equals `round(spot / total * 100)` when total is greater than 0, or 0 when total equals 0.
2. WHEN a member loads the Spot dashboard, THE Member_Handler SHALL return the Effective Savings Rate (ESR) computed as `actual_savings / maximum_possible_savings`, bounded in the range [0.0, 1.0].
3. WHEN no Spot instances are running for a member, THE Member_Handler SHALL return ESR of 0.0 and empty savings trend data.
4. WHEN a member loads the Spot dashboard, THE Member_Handler SHALL return a savings trend array sorted by date ascending, where each entry satisfies `savings == onDemandCost - spotCost`.
5. WHEN a member loads the Spot dashboard, THE Member_Handler SHALL query `ec2:DescribeSpotInstanceRequests` via API polling to return interruption metrics including count in the last 30 days.
6. WHEN a member loads the Spot dashboard, THE Member_Handler SHALL return a list of migrated ASGs with their current status, Spot percentage, and monthly savings estimate.

### Requirement 10: Spot Interruption Notification Pipeline (Push-Based)

**User Story:** As a member, I want to receive an email notification within seconds of a Spot interruption in my account, so that I'm immediately informed that an instance was reclaimed and the ASG is replacing it.

#### Acceptance Criteria

1. WHEN Spot management is enabled for a Customer_Account, THE Member_Handler SHALL deploy an EventBridge rule in the Customer_Account matching event patterns `EC2 Instance Rebalance Recommendation` and `EC2 Spot Instance Interruption Warning` from source `aws.ec2`, targeting the platform SNS topic.
2. WHEN the SNS topic receives an interruption event, THE Member_Handler Lambda SHALL be invoked, look up the member by account ID, and send an email notification via SES within seconds of the event.
3. WHEN deploying or removing the EventBridge rule, THE Member_Handler SHALL ensure idempotency: repeated enable calls produce exactly one rule, and repeated disable calls leave no orphaned rules.
4. WHEN an interruption event is received for an unknown account (no member mapping), THE Member_Handler SHALL log a warning and discard the event without processing.
5. THE Member_Handler SHALL deduplicate interruption notifications: if the same instance ID was notified within the last 5 minutes, skip the duplicate event.

### Requirement 11: SpotSavingsLedger DynamoDB Table

**User Story:** As a platform operator, I want a dedicated DynamoDB table for Spot savings tracking, so that savings data is isolated from member configuration and can scale independently.

#### Acceptance Criteria

1. THE SpotSavingsLedger table SHALL be provisioned with PAY_PER_REQUEST billing mode in the CloudFormation stack.
2. THE SpotSavingsLedger table SHALL have TTL enabled on the `ttl` attribute for automatic record expiration.
3. THE SpotSavingsLedger table SHALL include the MemberTimeIndex GSI for cross-account time-range queries.

### Requirement 12: Spot Event Email Notifications

**User Story:** As a member, I want to receive email notifications when Spot interruptions occur and when replacement instances are provisioned, so that I stay informed about my infrastructure health without needing to check the dashboard.

#### Acceptance Criteria

1. WHEN the Interruption_Notification_Pipeline delivers a Spot interruption event to the Member_Handler, THE Member_Handler SHALL immediately send an email notification to the member's registered email address via the existing SES infrastructure (`noreply@slashmycloudbill.com`).
2. THE interruption notification email SHALL include: the ASG name, the interrupted instance ID and type, the interruption reason (capacity-oversubscribed or price), the timestamp, and confirmation that the ASG has automatically launched a replacement instance.
3. WHEN a Spot migration is executed successfully, THE Member_Handler SHALL send a confirmation email to the member with: the ASG name, the new capacity mix (On-Demand base + Spot percentage), estimated monthly savings, and a note that rollback is available for 7 days.
4. WHEN a rollback is executed, THE Member_Handler SHALL send a confirmation email to the member confirming the ASG has been restored to its original configuration.
5. THE Member_Handler SHALL track which interruption events have already been notified (via a `lastNotifiedInterruption` timestamp on the Spot_Config) to avoid sending duplicate emails on subsequent dashboard loads.
6. ALL Spot notification emails SHALL use the existing SES sender `SlashMyBill <noreply@slashmycloudbill.com>` and follow the same HTML template style as existing OTP emails.
