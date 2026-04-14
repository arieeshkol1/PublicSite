# Implementation Plan: Automated Scheduler

## Overview

Convert SlashMyBill's schedule-intent-only Scheduler into a real execution engine using Amazon EventBridge Scheduler. Implementation proceeds bottom-up: executor Lambda first, then Member Handler integration, then frontend, then admin panel, then deploy pipeline. Python scripts are used for modifying the large `members/members.js` file.

## Tasks

- [x] 1. Create Scheduler Executor Lambda — core scaffolding and action dispatch
  - [x] 1.1 Create `scheduler-executor/lambda_function.py` with entry point, payload parsing, STS AssumeRole logic, and dispatch router
    - Parse EventBridge payload (scheduleId, scheduleType, action, accountId, memberEmail, resources, tagFilter)
    - Look up member in DynamoDB to compute ExternalId = SHA256(memberEmail)
    - Assume `SlashMyBill-{accountId}` cross-account role with ExternalId
    - If tagFilter is set, resolve resources via `resourcegroupstaggingapi:GetResources`
    - Dispatch to correct handler based on (scheduleType, action) pair
    - Raise error for invalid combinations (e.g., start for elb-teardown)
    - _Requirements: 2.1–2.18, 2.19, 9.1, 9.2_

  - [x] 1.2 Implement EC2 stop/start action handlers (`execute_ec2_stop`, `execute_ec2_start`)
    - Check instance state before acting (idempotent)
    - Return `ResourceResult` per instance with success/failure
    - _Requirements: 2.1, 2.2_

  - [x] 1.3 Implement RDS stop/start action handlers (`execute_rds_stop`, `execute_rds_start`)
    - Call `rds:StopDBInstance` / `rds:StartDBInstance` per instance
    - Handle already-stopped/started state gracefully
    - _Requirements: 2.3, 2.4_

  - [x] 1.4 Implement ASG scale-zero/restore handlers (`execute_asg_scale_zero`, `execute_asg_restore`)
    - Read current MinSize/MaxSize/DesiredCapacity, store in `originalScaleValues` on the schedule record in DynamoDB
    - Set all to 0 on stop; restore from stored values on start
    - _Requirements: 2.5, 2.6_

  - [x] 1.5 Implement EKS scale-zero/restore handlers (`execute_eks_scale_zero`, `execute_eks_restore`)
    - Read current minSize/desiredSize of each node group, store originals in DynamoDB
    - Set to 0 on stop; restore on start
    - _Requirements: 2.7, 2.8_

  - [x] 1.6 Implement SageMaker, Redshift, WorkSpaces, and ELB action handlers
    - `execute_sagemaker_stop` / `execute_sagemaker_start`: StopNotebookInstance / StartNotebookInstance
    - `execute_redshift_pause` / `execute_redshift_resume`: PauseCluster / ResumeCluster
    - `execute_workspaces_autostop`: ModifyWorkspaceProperties → RunningMode=AUTO_STOP
    - `execute_elb_teardown`: DeleteLoadBalancer (no start action)
    - _Requirements: 2.9–2.14_

  - [x] 1.7 Implement Review-Type action handlers (waste-scan, snapshot-cleanup, gp2-migration, commitment-review)
    - `execute_waste_scan`: Trigger existing waste scan logic for the account
    - `execute_snapshot_cleanup`: Identify unused/old snapshots, call `ec2:DeleteSnapshot`
    - `execute_gp2_migration`: Identify gp2 volumes, call `ec2:ModifyVolume` to convert to gp3
    - `execute_commitment_review`: Generate SP/RI utilization review, store results in DynamoDB
    - _Requirements: 2.15–2.18_

  - [x] 1.8 Implement execution history recording and error handling
    - After all resource actions complete, write execution record to DynamoDB (`executionHistory` on the schedule)
    - Record: timestamp, action, status (success/partial/failure), resourceCount, successCount, failureCount, per-resource details
    - Handle STS AssumeRole failure: log error, write failure record, exit
    - Handle individual resource failures: continue processing, record partial success
    - Handle tag resolution returning 0 resources: log warning, record as success with 0 resources
    - Best-effort DynamoDB write for history (log to CloudWatch if DynamoDB fails)
    - _Requirements: 2.19, 2.20, 5.1_

  - [ ]* 1.9 Write property test for action dispatch routing correctness
    - **Property 3: Action dispatch routing correctness**
    - **Validates: Requirements 2.1–2.18**

  - [ ]* 1.10 Write property test for partial failure continuation and count invariant
    - **Property 4: Partial failure continuation and count invariant**
    - **Validates: Requirements 2.20**

  - [ ]* 1.11 Write property test for execution record field completeness
    - **Property 6: Execution record field completeness**
    - **Validates: Requirements 5.1**

  - [x] 1.12 Create `scheduler-executor/requirements.txt` with boto3 dependency
    - _Requirements: 2.1–2.18_

- [x] 2. Checkpoint — Verify executor Lambda
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Enhance Member Handler — EventBridge schedule creation
  - [x] 3.1 Add cron expression generation utility to `member-handler/lambda_function.py`
    - Build EventBridge cron expressions from days/time/timezone config
    - Handle daily, weekdays, custom day subsets
    - Map schedule config to `cron(min hour ? * DAY-LIST *)` format with timezone
    - _Requirements: 1.1, 1.2_

  - [ ]* 3.2 Write property test for cron expression generation correctness
    - **Property 1: Cron expression generation correctness**
    - **Validates: Requirements 1.1, 1.2**

  - [x] 3.3 Modify `handle_create_schedule` to create real EventBridge Scheduler schedules (use Python script for modification)
    - For Stop_Start_Type: create Schedule_Pair (`smb-{scheduleId}-stop` and `smb-{scheduleId}-start`)
    - For Review_Type: create single schedule (`smb-{scheduleId}-scan`)
    - Set target to Scheduler Executor Lambda ARN with payload containing scheduleId, scheduleType, action, accountId, memberEmail, resources/tagFilter
    - Store `ebScheduleNames` and `ebScheduleArns` in the schedule record in DynamoDB
    - Implement rollback: if stop schedule created but start fails, delete stop schedule; if DynamoDB write fails, delete all EB schedules
    - On any EB creation failure, return error and do NOT save partial record
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 3.4 Write property test for schedule payload completeness
    - **Property 2: Schedule payload completeness**
    - **Validates: Requirements 1.3**

- [x] 4. Add lifecycle management endpoints to Member Handler
  - [x] 4.1 Implement `handle_pause_schedule` — PUT /members/schedules/pause (use Python script for modification)
    - Validate JWT and verify schedule belongs to authenticated member
    - Call `scheduler:UpdateSchedule` with State=DISABLED for each EB schedule name
    - Update schedule status to `paused` in DynamoDB
    - If EB schedule not found, clean up orphaned DynamoDB record and return success
    - _Requirements: 3.1, 3.4, 4.2, 4.4_

  - [x] 4.2 Implement `handle_resume_schedule` — PUT /members/schedules/resume (use Python script for modification)
    - Validate JWT and verify schedule belongs to authenticated member
    - Call `scheduler:UpdateSchedule` with State=ENABLED for each EB schedule name
    - Update schedule status to `active` in DynamoDB
    - If EB schedule not found, clean up orphaned DynamoDB record and return success
    - _Requirements: 3.2, 3.4, 4.3, 4.4_

  - [x] 4.3 Implement `handle_delete_schedule` — DELETE /members/schedules/delete (use Python script for modification)
    - Validate JWT and verify schedule belongs to authenticated member
    - Call `scheduler:DeleteSchedule` for each EB schedule name
    - Remove schedule record from `userSchedules` array in DynamoDB
    - If EB schedule not found, clean up orphaned DynamoDB record and return success
    - _Requirements: 3.3, 3.4, 4.1, 4.4_

  - [x] 4.4 Register new routes in the Member Handler route table (use Python script for modification)
    - Add `PUT /members/schedules/pause` → `handle_pause_schedule`
    - Add `PUT /members/schedules/resume` → `handle_resume_schedule`
    - Add `DELETE /members/schedules/delete` → `handle_delete_schedule`
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ]* 4.5 Write property test for schedule ownership authorization
    - **Property 5: Schedule ownership authorization**
    - **Validates: Requirements 4.4**

- [x] 5. Enhance GET /members/schedules response with execution data
  - [x] 5.1 Modify `handle_get_schedules` to return status, next execution time, and last 10 execution records (use Python script for modification)
    - Compute next execution time from EB cron expression and timezone
    - Return exactly min(N, 10) most recent execution records in descending order by timestamp
    - Include schedule status (active/paused)
    - _Requirements: 5.2, 5.3_

  - [ ]* 5.2 Write property test for execution history returning most recent 10
    - **Property 7: Execution history returns most recent 10**
    - **Validates: Requirements 5.2**

  - [ ]* 5.3 Write property test for next execution time correctness
    - **Property 8: Next execution time is in the future and matches cron**
    - **Validates: Requirements 5.3**

- [x] 6. Checkpoint — Verify Member Handler integration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Update cross-account CloudFormation template permissions
  - [x] 7.1 Modify `handle_generate_template` in `member-handler/lambda_function.py` to add missing write permissions (use Python script for modification)
    - Add to inline policy: `ec2:StartInstances`, `rds:StopDBInstance`, `rds:StartDBInstance`, `eks:UpdateNodegroupConfig`, `eks:DescribeNodegroup`, `sagemaker:StopNotebookInstance`, `sagemaker:StartNotebookInstance`, `redshift:PauseCluster`, `redshift:ResumeCluster`, `workspaces:ModifyWorkspaceProperties`, `ec2:ModifyVolume`
    - _Requirements: 8.1–8.7_

  - [ ]* 7.2 Write property test for cross-account template permissions
    - **Property 9: Cross-account template contains all required permissions**
    - **Validates: Requirements 8.1–8.7**

- [x] 8. Update frontend schedule cards in `members/members.js`
  - [x] 8.1 Update `_renderSchedulerList` to render real schedule cards with status, next execution time, and action buttons (use Python script for modification)
    - Display schedule name, type, status badge (Active green / Paused gray), next execution time in configured timezone, target resources or tag filter
    - Show Pause + Delete buttons when status is `active`
    - Show Resume + Delete buttons when status is `paused`
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 8.2 Implement Pause, Resume, and Delete button handlers with API calls (use Python script for modification)
    - Pause button calls PUT /members/schedules/pause, updates card status to paused without full page reload
    - Resume button calls PUT /members/schedules/resume, updates card status to active without full page reload
    - Delete button shows confirmation dialog, then calls DELETE /members/schedules/delete and removes card from list
    - _Requirements: 6.4, 6.5, 6.6_

  - [x] 8.3 Add expandable execution history section to schedule cards (use Python script for modification)
    - Collapsible `<details>` element showing last 10 executions
    - Each row: status icon (✅/⚠️/❌), timestamp in schedule timezone, action, resource counts
    - Failure details expandable per-resource with error messages
    - Empty state: "No executions yet — schedule will run at the next scheduled time"
    - Header shows "Execution History (N runs)"
    - _Requirements: 6.7_

- [x] 9. Update knowledge base tips with scheduler integration
  - [x] 9.1 Update `knowledge-base/aws-cost-optimization-tips.json` — add `implementedInScheduler` flag to scheduling tips
    - Update tips ec2-004, ec2-011, rds-007, eks-003, sagemaker-001, redshift-001, workspaces-001 with `implementedInScheduler: true`, updated descriptions pointing to Act → Scheduler, `actionLabel` → "Go to Scheduler", `actionTarget` → "act:scheduler"
    - Add new tips asg-001 (ASG scale-down scheduling) and elb-001 (ELB teardown scheduling)
    - _Requirements: Design Component 7_

  - [ ]* 9.2 Write property test for scheduling tips flags
    - **Property 10: Scheduling tips have implementedInScheduler flag**
    - **Validates: Design Component 7**

- [x] 10. Checkpoint — Verify frontend and knowledge base changes
  - Ensure all tests pass, ask the user if questions arise.

- [-] 11. Add Admin Panel scheduler visibility
  - [x] 11.1 Add `GET /admin/schedules` endpoint to `admin-handler/lambda_function.py`
    - Scan MemberPortal-Members table for all members with non-empty `userSchedules`
    - Return aggregated schedule list with memberEmail, scheduleId, name, type, status, accountId, lastExecution
    - Return stats: totalSchedules, activeSchedules, pausedSchedules, executionsLast24h, failuresLast24h
    - Require admin authentication
    - _Requirements: Design Component 8_

  - [x] 11.2 Add "⏰ Sched" badge to admin Tips table for tips with `implementedInScheduler: true` (modify `admin/admin.js`)
    - Display alongside existing "✓ Act" badge
    - _Requirements: Design Component 8_

  - [x] 11.3 Add "Schedules" column to admin Subscribers table showing active schedule count per member (modify `admin/admin.js`)
    - Clicking count opens detail view with schedule name, type, status, account, last execution result
    - _Requirements: Design Component 8_

  - [x] 11.4 Add Schedules overview section to admin panel (modify `admin/admin.js` and `admin/index.html`)
    - Stats bar: total schedules (active/paused/total), executions last 24h, failure rate
    - Schedule table: all schedules across members with Member, Name, Type, Account, Status, Last Run, Last Result columns
    - Filter/search by member email, schedule type, status, account ID
    - Failure drill-down: click failed execution to see per-resource error details
    - _Requirements: Design Component 8_

- [x] 12. Update deployment pipeline
  - [x] 12.1 Add scheduler-executor Lambda packaging step to `.github/workflows/deploy.yml`
    - Create `.build-scheduler-executor/` directory, install dependencies, copy `scheduler-executor/lambda_function.py`
    - Zip and upload to S3 as `lambda-packages/scheduler-executor.zip`
    - Add `aws lambda update-function-code` for `slashmybill-scheduler-executor`
    - _Requirements: 10.1_

  - [x] 12.2 Add new API Gateway routes to deploy pipeline
    - Add routes: `DELETE /members/schedules/delete`, `PUT /members/schedules/pause`, `PUT /members/schedules/resume` targeting Member Handler integration
    - Add route: `GET /admin/schedules` targeting Admin Handler integration
    - _Requirements: 10.2_

  - [x] 12.3 Add `scheduler-executor/**` to deploy trigger paths in deploy.yml
    - _Requirements: 10.3_

- [x] 13. Add IAM resources to CloudFormation stack
  - [x] 13.1 Add Scheduler Executor Lambda resource, execution role, and EventBridge Scheduler execution role to `infrastructure/viewmybill-stack.yaml`
    - Executor Lambda: `slashmybill-scheduler-executor`, 512MB memory, 300s timeout
    - Executor role: `sts:AssumeRole` on `arn:aws:iam::*:role/SlashMyBill-*`, DynamoDB read/write on MemberPortal-Members
    - EventBridge Scheduler role: `SlashMyBill-EventBridge-Scheduler-Role`, trust `scheduler.amazonaws.com`, policy `lambda:InvokeFunction` on executor ARN
    - Add `scheduler:CreateSchedule`, `scheduler:DeleteSchedule`, `scheduler:UpdateSchedule`, `scheduler:GetSchedule`, `iam:PassRole` to Member Handler execution role
    - _Requirements: 7.1, 7.2, 7.3_

- [x] 14. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Python scripts should be used for modifying `members/members.js` (large file)
- All Python Lambda code uses boto3 for AWS SDK calls
- Deploy by pushing to main branch — GitHub Actions handles everything
- Each property test maps to a correctness property from the design document
- Checkpoints ensure incremental validation at key integration points
