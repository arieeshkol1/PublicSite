# Implementation Plan: Autonomous Spot Instance Management

## Overview

Expand SlashMyBill from passively flagging Spot candidates to actively orchestrating Spot Instance lifecycles. Implementation proceeds bottom-up: infrastructure (DynamoDB table + CloudFormation), then backend logic (configuration, qualification, planning, migration, dashboard, interruption handling), then Bedrock Agent tool, then frontend UI, then deploy pipeline. Python scripts are used for modifying the large `member-handler/lambda_function.py` (~9800 lines) and `members/members.js` (~6800 lines) files.

Key design decision: ASG with `price-capacity-optimized` handles Spot interruptions natively — no custom replacement logic needed. EventBridge + SNS push pipeline delivers real-time email notifications to the customer within seconds of an interruption.

## Tasks

- [ ] 1. Infrastructure — SpotSavingsLedger DynamoDB table and IAM updates
  - [ ] 1.1 Add SpotSavingsLedger DynamoDB table to `infrastructure/viewmybill-stack.yaml`
    - Table name: SpotSavingsLedger
    - Partition key: `pk` (S), Sort key: `sk` (S)
    - GSI `MemberTimeIndex`: partition key `memberEmail` (S), sort key `recordedAt` (S), ProjectionType ALL
    - TTL on `ttl` attribute
    - BillingMode: PAY_PER_REQUEST
    - Add `SPOT_LEDGER_TABLE_NAME` environment variable to Member Handler Lambda
    - _Requirements: 11.1, 11.2, 11.3, 8.4, 8.5_

  - [ ] 1.2 Add Spot-specific IAM actions to the cross-account CloudFormation template generator in `member-handler/lambda_function.py`
    - Add conditional Spot permissions block when `spotEnabled` is true on the account
    - Actions: `ec2:GetSpotPlacementScores`, `ec2:DescribeSpotInstanceRequests`, `autoscaling:UpdateAutoScalingGroup`, `autoscaling:DescribeAutoScalingGroups`, `events:PutRule`, `events:PutTargets`, `events:DeleteRule`, `events:RemoveTargets`
    - When Spot is not enabled, omit these actions from the template
    - _Requirements: 3.1, 3.2_

  - [ ] 1.3 Add SNS topic `SlashMyBill-SpotInterruptions` to `infrastructure/viewmybill-stack.yaml`
    - Cross-account publish policy allowing `events.amazonaws.com` from any customer account to publish
    - Lambda subscription targeting Member Handler for real-time interruption email notifications
    - Purpose: push-based email notification pipeline only (ASG handles replacement natively)
    - _Requirements: 10.1, 12.1_

- [ ] 2. Backend — Spot Configuration Manager
  - [ ] 2.1 Add `handle_spot_config` route handler to `member-handler/lambda_function.py`
    - Route: `POST /members/spot/config`
    - Validate JWT token and account ownership
    - Accept `spotEnabled`, `qualifiedASGs`, `excludedASGs`
    - Validate qualifiedASGs and excludedASGs are disjoint (reject if overlap)
    - Validate each ASG name exists in customer account via cross-account DescribeAutoScalingGroups
    - Store `spotConfig` field on member DynamoDB item
    - Return updated configuration
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ] 2.2 Add EventBridge interruption rule deployment logic
    - `_deploy_interruption_rule(member_email, account_id, enable)` function
    - When enable=True (triggered automatically when spotEnabled is set): create EventBridge rule `SlashMyBill-SpotInterruption-{accountId}` in customer account via cross-account role
    - Event pattern: `{"source":["aws.ec2"],"detail-type":["EC2 Instance Rebalance Recommendation","EC2 Spot Instance Interruption Warning"]}`
    - Target: platform SNS topic `arn:aws:sns:us-east-1:991105135552:SlashMyBill-SpotInterruptions`
    - When enable=False: remove targets and delete rule (handle ResourceNotFoundException gracefully)
    - Store/clear `eventBridgeRuleArn` in spotConfig
    - Idempotent: repeated enable = one rule, repeated disable = no orphans
    - Purpose: real-time email notification only (NOT operational recovery — ASG handles that)
    - _Requirements: 10.1, 10.3, 12.1_

  - [ ] 2.3 Add route to API Gateway dispatch table and register `POST /members/spot/config`
    - Add to the `routes` dict in `lambda_handler`
    - _Requirements: 1.1_

- [ ] 3. Backend — Workload Qualification Validator
  - [ ] 3.1 Add `validate_workload_qualification` function to `member-handler/lambda_function.py`
    - Accept member_email, account_id, list of asg_names
    - Assume cross-account role, describe each ASG
    - Apply exclusion rules: database keywords in name/tags, Stateful=true tag, MaxSize <= 1, existing Spot allocation, production single-AZ
    - Classify each ASG as qualified/excluded/ineligible
    - Return results with `len(qualified) + len(excluded) + len(ineligible) == len(asg_names)`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [ ] 4. Backend — Capacity Mix Configurator (Plan)
  - [ ] 4.1 Add `handle_spot_plan` route handler to `member-handler/lambda_function.py`
    - Route: `POST /members/spot/plan`
    - Validate JWT, account ownership, ASG qualification
    - Fetch current ASG config from customer account
    - Validate capacity mix bounds: `onDemandBaseCapacity` in [0, maxSize], `onDemandPercentageAboveBase` in [0, 100]
    - Validate instance requirements match >= 10 instance types (attribute-based selection pool minimum)
    - Compute proposed On-Demand/Spot split: `onDemandCount = B + ceil((D - B) * P / 100)`, `spotCount = D - onDemandCount`
    - Query Spot Placement Scores for configured instance requirements
    - Estimate monthly savings based on On-Demand vs Spot pricing
    - Return current config, proposed config, placement scores, and savings estimate
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ] 4.2 Add `get_spot_placement_score` helper function
    - Assume cross-account role, call `ec2:GetSpotPlacementScores`
    - Translate vCPU/memory ranges to `InstanceRequirementsWithMetadata`
    - Sort results by score descending
    - Cache results in DynamoDB for 15 minutes
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ] 4.3 Add route to API Gateway dispatch table and register `POST /members/spot/plan`
    - _Requirements: 5.1_

- [ ] 5. Backend — Spot Migration Executor (Act)
  - [ ] 5.1 Add `handle_spot_migrate` route handler to `member-handler/lambda_function.py`
    - Route: `POST /members/spot/migrate`
    - Accept `accountId`, `asgName`, `action` (migrate | rollback | dry-run), `capacityMix`
    - Validate JWT, account ownership, ASG in qualified list and not in excluded list
    - Dispatch to dry-run, migrate, or rollback sub-handlers
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4_

  - [ ] 5.2 Implement `execute_spot_migration` function
    - Snapshot current ASG config (LaunchTemplate, DesiredCapacity, MinSize, MaxSize, existing MixedInstancesPolicy) to DynamoDB
    - Build MixedInstancesPolicy with `price-capacity-optimized`, configured OnDemandBaseCapacity, OnDemandPercentageAboveBaseCapacity, and attribute-based instance selection overrides
    - Call `autoscaling:UpdateAutoScalingGroup` with the new policy
    - Record migration event in SpotSavingsLedger
    - Update spotConfig.migratedASGs with snapshot and new config
    - Set rollbackExpiresAt to 7 days from now
    - _Requirements: 6.2, 6.3, 6.4_

  - [ ] 5.3 Implement `execute_spot_rollback` function
    - Load pre-migration snapshot from DynamoDB
    - Verify rollback has not expired (7-day window)
    - Restore ASG to exact pre-migration config
    - Record rollback event in SpotSavingsLedger
    - Remove migrated ASG entry from spotConfig
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ] 5.4 Implement `build_dry_run_response` function
    - Return proposed changes without modifying ASG
    - Include: LaunchTemplate → MixedInstancesPolicy conversion, instance type → attribute-based selection, allocation strategy, On-Demand/Spot split, estimated savings, risks
    - _Requirements: 6.1_

  - [ ] 5.5 Add route to API Gateway dispatch table and register `POST /members/spot/migrate`
    - _Requirements: 6.1_

- [ ] 6. Backend — Savings Ledger and Dashboard
  - [ ] 6.1 Add `record_savings_entry` function to `member-handler/lambda_function.py`
    - Compute `savingsPerHour = onDemandRate - spotRate`
    - Compute `totalSavings = savingsPerHour * hours`
    - Compute `gainshareAmount = totalSavings * 0.30`
    - Validate `spotRate <= onDemandRate`
    - Validate `eventType` in {running, interrupted, migrated, rolled-back}
    - Set TTL to 12 months from recording timestamp
    - Write to SpotSavingsLedger with pk=`memberEmail#accountId`, sk=`timestamp#instanceId`
    - _Requirements: 8.1, 8.2, 8.3, 8.6_

  - [ ] 6.2 Add `handle_spot_dashboard` route handler
    - Route: `GET /members/spot/dashboard`
    - Aggregate Spot vs On-Demand instance counts across migrated ASGs via `autoscaling:DescribeAutoScalingGroups` + `ec2:DescribeInstances`
    - Compute capacity ratio: `total = onDemand + spot`, `spotPercentage = round(spot / total * 100)` or 0 if total == 0
    - Compute ESR: `actual_savings / maximum_possible_savings`, bounded [0.0, 1.0], return 0.0 if no records
    - Build savings trend sorted by date ascending, each entry: `savings = onDemandCost - spotCost`
    - Read interruption history via `ec2:DescribeSpotInstanceRequests` (API polling, no EventBridge needed)
    - Return migrated ASGs list with status, spot percentage, monthly savings
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ] 6.3 Add `calculate_effective_savings_rate` helper function
    - Query SpotSavingsLedger for period
    - Sum on-demand and spot costs from running records
    - ESR = actual_savings / (total_on_demand_cost * 0.90), capped at 1.0
    - Return 0.0 if no records
    - _Requirements: 9.2_

  - [ ] 6.4 Add routes to API Gateway dispatch table: `GET /members/spot/dashboard`, `GET /members/spot/ledger`
    - _Requirements: 9.1_

- [ ] 7. Backend — Spot Email Notifications (Push-Based)
  - [ ] 7.1 Add `_send_spot_notification` helper function to `member-handler/lambda_function.py`
    - Use existing `ses_client` and `SES_SENDER_EMAIL` (`noreply@slashmycloudbill.com`)
    - Build HTML email template matching existing OTP email style
    - Accept notification type: `migration-complete`, `rollback-complete`, `interruption-detected`
    - _Requirements: 12.6_

  - [ ] 7.2 Send migration confirmation email after successful `execute_spot_migration`
    - Include: ASG name, capacity mix (On-Demand base + Spot %), estimated monthly savings, rollback available for 7 days
    - _Requirements: 12.3_

  - [ ] 7.3 Send rollback confirmation email after successful `execute_spot_rollback`
    - Include: ASG name, confirmation that original config is restored
    - _Requirements: 12.4_

  - [ ] 7.4 Add `handle_spot_interruption_event` function (invoked by SNS → Lambda)
    - Parse SNS message containing EventBridge event payload from customer account
    - Extract `instance-id`, `account` from event detail
    - Lookup member email by account ID (scan MemberPortal-Accounts table)
    - If unknown account: log warning, discard
    - Deduplicate: check `lastNotifiedInterruption` timestamp on Spot_Config, skip if same instance notified within 5 minutes
    - Assume cross-account role, describe the instance to get ASG name, instance type, tags
    - Send email immediately via SES with: ASG name, interrupted instance ID/type, interruption reason, timestamp, and confirmation that ASG has automatically launched a replacement
    - Record interruption event in SpotSavingsLedger for dashboard metrics
    - Update `lastNotifiedInterruption` timestamp
    - _Requirements: 10.2, 12.1, 12.2, 12.5_

  - [ ] 7.5 Register SNS event handler in Lambda dispatch
    - Detect SNS invocation by checking `event.get('Records', [{}])[0].get('EventSource') == 'aws:sns'`
    - Route to `handle_spot_interruption_event` when SNS topic ARN contains `SlashMyBill-SpotInterruptions`
    - _Requirements: 10.1_

- [ ] 8. Bedrock Agent — Spot Placement Score Tool
  - [ ] 8.1 Add `getSpotPlacementScore` operation to `agent-action/openapi-schema.json`
    - Path: `/get-spot-placement-score`
    - Parameters: accountId, memberEmail, vCpuMin, vCpuMax, memoryMiBMin, memoryMiBMax, targetCapacity (optional, default 10), regions (optional)
    - _Requirements: 4.1, 4.5_

  - [ ] 8.2 Add `_get_spot_placement_score` handler to `agent-action/lambda_function.py`
    - Assume cross-account role for the member's account
    - Translate parameters to `InstanceRequirementsWithMetadata` format
    - Call `ec2:GetSpotPlacementScores`
    - Sort results by score descending, validate scores in [1, 10], no duplicate region-AZ pairs
    - Return formatted scores with region, AZ, and score
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [ ] 8.3 Add route dispatch for `/get-spot-placement-score` in agent-action Lambda handler
    - _Requirements: 4.1_

- [ ] 9. Checkpoint — Verify all backend logic
  - Run existing tests to ensure no regressions
  - Verify all new routes are registered in the dispatch table
  - Verify SpotSavingsLedger table definition in CloudFormation

- [ ] 10. Property-Based Tests
  - [ ]* 10.1 Write property test: Capacity mix invariant — On-Demand + Spot = Total
    - Generate random desiredCapacity (1-1000), onDemandBaseCapacity (0-desiredCapacity), onDemandPercentageAboveBase (0-100)
    - Verify `onDemandCount + spotCount == desiredCapacity`
    - Minimum 100 iterations
    - **Property 1: Capacity mix invariant**
    - **Validates: Requirement 5.2**

  - [ ]* 10.2 Write property test: Savings ledger arithmetic consistency
    - Generate random onDemandRate (0.01-50.0), spotRate (0.001-onDemandRate), hours (0.1-744)
    - Verify `savingsPerHour == onDemandRate - spotRate`, `totalSavings == savingsPerHour * hours`, `gainshareAmount == totalSavings * 0.30`
    - Verify spotRate <= onDemandRate invariant
    - Verify eventType validation rejects invalid values
    - Minimum 100 iterations
    - **Property 2: Savings ledger arithmetic consistency**
    - **Validates: Requirements 8.1, 8.2, 8.6**

  - [ ]* 10.3 Write property test: ESR bounded [0, 1]
    - Generate random lists of savings records with varying rates and hours (including empty lists)
    - Verify ESR is always in [0.0, 1.0]
    - Verify ESR == 0.0 when no records
    - Minimum 100 iterations
    - **Property 3: Effective Savings Rate bounded**
    - **Validates: Requirement 9.2**

  - [ ]* 10.4 Write property test: Workload qualification completeness and exclusion correctness
    - Generate random lists of N ASG names (1-50) with random tag/config combinations
    - Include ASGs with database keywords, Stateful=true, MaxSize<=1, existing Spot, prod single-AZ
    - Verify `len(qualified) + len(excluded) + len(ineligible) == N`
    - Verify exclusion rules are correctly applied
    - Minimum 100 iterations
    - **Property 4: Workload qualification completeness**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7**

  - [ ]* 10.5 Write property test: Migration rollback round-trip
    - Generate random ASG configurations (varying LaunchTemplate, DesiredCapacity, MinSize, MaxSize, with/without existing MixedInstancesPolicy)
    - Simulate migrate then rollback
    - Verify restored config matches original snapshot exactly
    - Minimum 100 iterations
    - **Property 5: Migration rollback restores original config**
    - **Validates: Requirement 7.1**

  - [ ]* 10.6 Write property test: Spot Placement Score response validity
    - Generate random vCPU ranges, memory ranges, target capacities
    - Generate random raw score data with potential duplicates and out-of-range values
    - Verify output is sorted descending, all scores in [1, 10], no duplicate region-AZ pairs
    - Minimum 100 iterations
    - **Property 6: Placement score response validity**
    - **Validates: Requirements 4.2, 4.3**

  - [ ]* 10.7 Write property test: Attribute-based selection pool minimum
    - Generate random instance requirement ranges (narrow to broad)
    - Verify narrow ranges matching < 10 types are rejected
    - Verify broad ranges matching >= 10 types are accepted
    - Minimum 100 iterations
    - **Property 7: Pool minimum validation**
    - **Validates: Requirement 5.5**

  - [ ]* 10.8 Write property test: Interruption notification deduplication
    - Generate random sequences of interruption events for the same instance within varying time windows
    - Verify events within 5-minute window are deduplicated (only one email sent)
    - Verify events outside 5-minute window trigger new notifications
    - Minimum 100 iterations
    - **Property 8: Interruption notification deduplication**
    - **Validates: Requirement 12.5**

  - [ ]* 10.9 Write property test: Cross-account template Spot permissions
    - Generate random 12-digit account IDs and email addresses
    - Verify generated template contains all required Spot IAM actions (`ec2:GetSpotPlacementScores`, `ec2:DescribeSpotInstanceRequests`, `autoscaling:UpdateAutoScalingGroup`, `autoscaling:DescribeAutoScalingGroups`, `events:PutRule`, `events:PutTargets`, `events:DeleteRule`, `events:RemoveTargets`)
    - Verify template without Spot enabled omits Spot actions
    - Minimum 100 iterations
    - **Property 9: Template Spot permissions**
    - **Validates: Requirement 3.1**

  - [ ]* 10.10 Write property test: Dashboard capacity ratio and savings trend consistency
    - Generate random onDemand (0-1000) and spot (0-1000) counts
    - Generate random savings trend entries
    - Verify `total == onDemand + spot`, `spotPercentage` formula, `savings == onDemandCost - spotCost`, date ascending sort
    - Minimum 100 iterations
    - **Property 10: Dashboard data consistency**
    - **Validates: Requirements 9.1, 9.4**

  - [ ]* 10.11 Write property test: Disjoint ASG sets
    - Generate random qualified and excluded ASG name lists with intentional overlaps
    - Verify overlapping lists are rejected, disjoint lists are accepted
    - Minimum 100 iterations
    - **Property 11: Disjoint ASG sets**
    - **Validates: Requirement 1.2**

  - [ ]* 10.12 Write property test: EventBridge rule deployment idempotency
    - Generate random sequences of enable/disable operations (1-20 ops)
    - Verify final state matches last operation
    - Verify no duplicate rules after repeated enables
    - Minimum 100 iterations
    - **Property 12: EventBridge idempotency**
    - **Validates: Requirement 10.3**

- [ ] 11. Frontend — Spot Management UI in Member Portal
  - [ ] 11.1 Add Spot configuration panel to the Configure tab in `members/members.js`
    - Spot opt-in toggle per connected account
    - ASG qualification list (qualified vs excluded) with checkboxes
    - Call `POST /members/spot/config` on save
    - Show workload qualification results with risk indicators (low/medium/high)
    - _Requirements: 1.1, 1.2, 2.1_

  - [ ] 11.2 Add Capacity Mix Planner to the Plan tab in `members/members.js`
    - ASG selector dropdown (from qualified ASGs)
    - On-Demand base capacity input
    - On-Demand percentage above base slider (0-100%)
    - Instance requirements form (vCPU min/max, memory min/max)
    - Call `POST /members/spot/plan` and display: current vs proposed config, placement scores, estimated savings
    - _Requirements: 5.1, 5.2, 5.5, 5.6_

  - [ ] 11.3 Add Spot Migration cards to the Act tab in `members/members.js`
    - Dry-run button showing proposed changes and risks
    - Migrate button with confirmation dialog
    - Rollback button (visible for 7 days post-migration)
    - Status indicators: pending, migrated, rolled-back
    - Call `POST /members/spot/migrate` with appropriate action
    - _Requirements: 6.1, 6.5, 7.1, 7.3_

  - [ ] 11.4 Add Spot Dashboard widget to the Observe tab in `members/members.js`
    - ECharts donut chart: On-Demand vs Spot capacity ratio
    - ECharts line chart: savings trend (On-Demand cost, Spot cost, savings)
    - ESR gauge with trend sparkline
    - Interruption metrics card (count, avg recovery, drain success rate)
    - Migrated ASGs table with status and monthly savings
    - Call `GET /members/spot/dashboard` on tab load
    - _Requirements: 9.1, 9.2, 9.4, 9.5, 9.6_

  - [ ] 11.5 Add Spot-related HTML structure to `members/index.html`
    - Spot config section in Configure tab
    - Capacity mix planner section in Plan tab
    - Spot migration cards section in Act tab
    - Spot dashboard widget containers in Observe tab
    - _Requirements: 1.1, 5.1, 6.1, 9.1_

- [ ] 12. Frontend — CSS Styling
  - [ ] 12.1 Add Spot-specific styles to `members/members.css`
    - Spot toggle and qualification list styles
    - Capacity mix slider and planner layout
    - Migration card styles with status indicators
    - Dashboard widget containers and chart sizing
    - _Requirements: 9.1_

- [ ] 13. API Gateway — Register new routes
  - [ ] 13.1 Add Spot API routes to API Gateway configuration in `infrastructure/viewmybill-stack.yaml`
    - `POST /members/spot/config`
    - `POST /members/spot/plan`
    - `POST /members/spot/migrate`
    - `GET /members/spot/dashboard`
    - `GET /members/spot/ledger`
    - All routes integrated with Member Handler Lambda
    - _Requirements: 1.1, 5.1, 6.1, 9.1_

- [ ] 14. Deployment — Update deploy scripts
  - [ ] 14.1 Update `infrastructure/deploy-viewmybill-lambda.ps1` to include new environment variables
    - `SPOT_LEDGER_TABLE_NAME=SpotSavingsLedger`
    - _Requirements: 11.1_

  - [ ] 14.2 Update Bedrock Agent action group with new OpenAPI schema
    - Deploy updated `agent-action/openapi-schema.json` with `getSpotPlacementScore` operation
    - _Requirements: 4.1_

- [ ] 15. Final Checkpoint — End-to-end verification
  - Deploy CloudFormation stack with SpotSavingsLedger table and SNS topic
  - Verify all API routes respond correctly
  - Verify Bedrock Agent can query Spot Placement Scores
  - Verify EventBridge rule deploys into customer account and interruption events trigger email notifications
  - Verify frontend renders all Spot management UI components
  - Run all property-based tests (minimum 100 iterations each)
