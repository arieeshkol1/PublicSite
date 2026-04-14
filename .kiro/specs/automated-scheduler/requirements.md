# Requirements Document

## Introduction

SlashMyBill is a FinOps SaaS platform that manages multiple customer AWS accounts via cross-account IAM roles. The Scheduler feature in the Act tab currently saves schedule intent to DynamoDB but does not execute any actions. This feature converts the Scheduler into a real automated execution engine using Amazon EventBridge Scheduler. At the scheduled time, a dedicated executor Lambda in the SlashMyBill platform account (991105135552) assumes the cross-account role into the customer's account and performs the stop/start/scale/scan actions.

## Glossary

- **Platform_Account**: The SlashMyBill AWS account (991105135552) where all platform infrastructure runs
- **Customer_Account**: An AWS account connected to SlashMyBill via a cross-account IAM role
- **Cross_Account_Role**: The IAM role `SlashMyBill-{accountId}` deployed in each Customer_Account, assumed by Platform_Account Lambdas using STS with ExternalId = SHA256(memberEmail)
- **Member_Handler**: The existing Lambda `aws-bill-analyzer-member-api` that handles all member API routes
- **Scheduler_Executor**: A new Lambda in the Platform_Account that receives EventBridge Scheduler payloads and executes actions in Customer_Accounts
- **EventBridge_Scheduler**: The AWS EventBridge Scheduler service used to create one-time or recurring schedules that invoke the Scheduler_Executor
- **Schedule_Pair**: For stop/start resource types, two EventBridge Scheduler schedules (one for stop, one for start) that together define an office-hours window
- **Stop_Start_Type**: Schedule types that stop and start resources on a recurring basis (EC2, RDS, ASG, EKS, SageMaker, Redshift, WorkSpaces, ELB)
- **Review_Type**: Schedule types that trigger a scan or analysis rather than a stop/start action (Waste Scan, Snapshot Cleanup, gp2→gp3 Migration, SP/RI Review)
- **Members_Table**: The DynamoDB table `MemberPortal-Members` that stores member data including `userSchedules`
- **Wizard_UI**: The existing schedule creation modal in the member portal Act tab
- **Schedule_Card**: A UI card in the scheduler list that displays schedule details and action buttons

## Requirements

### Requirement 1: EventBridge Schedule Creation

**User Story:** As a member, I want my schedule to be backed by a real EventBridge Scheduler schedule, so that actions execute automatically at the configured times without manual intervention.

#### Acceptance Criteria

1. WHEN a member submits the Wizard_UI to create a Stop_Start_Type schedule, THE Member_Handler SHALL create a Schedule_Pair in EventBridge_Scheduler — one schedule for the stop action and one for the start action — using the member-specified days, times, and timezone.
2. WHEN a member submits the Wizard_UI to create a Review_Type schedule, THE Member_Handler SHALL create a single EventBridge_Scheduler schedule using the member-specified frequency, time, and timezone.
3. WHEN creating an EventBridge_Scheduler schedule, THE Member_Handler SHALL set the schedule target to the Scheduler_Executor Lambda ARN and include the schedule payload containing: schedule ID, schedule type, account ID, resource ARNs or tag filter, member email, and action (stop/start/scan).
4. WHEN creating an EventBridge_Scheduler schedule, THE Member_Handler SHALL store the EventBridge schedule name(s) and ARN(s) in the schedule record in the Members_Table so that schedules can be paused, resumed, or deleted later.
5. IF EventBridge_Scheduler schedule creation fails, THEN THE Member_Handler SHALL return an error response to the Wizard_UI and SHALL NOT save a partial schedule record to the Members_Table.

### Requirement 2: Scheduler Executor Lambda

**User Story:** As a platform operator, I want a dedicated Lambda that executes scheduled actions in customer accounts, so that the execution is isolated from the member API and can be independently scaled and monitored.

#### Acceptance Criteria

1. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a stop action for `ec2-stop-start` type, THE Scheduler_Executor SHALL assume the Cross_Account_Role for the target Customer_Account and call `ec2:StopInstances` for the specified instance ARNs.
2. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a start action for `ec2-stop-start` type, THE Scheduler_Executor SHALL assume the Cross_Account_Role and call `ec2:StartInstances` for the specified instance ARNs.
3. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a stop action for `rds-stop-start` type, THE Scheduler_Executor SHALL assume the Cross_Account_Role and call `rds:StopDBInstance` for each specified RDS instance.
4. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a start action for `rds-stop-start` type, THE Scheduler_Executor SHALL assume the Cross_Account_Role and call `rds:StartDBInstance` for each specified RDS instance.
5. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a stop action for `asg-scale-zero` type, THE Scheduler_Executor SHALL assume the Cross_Account_Role, read the current MinSize, MaxSize, and DesiredCapacity of each specified Auto Scaling Group, store those original values in the schedule record in the Members_Table, and call `autoscaling:UpdateAutoScalingGroup` to set MinSize, MaxSize, and DesiredCapacity to 0.
6. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a start action for `asg-scale-zero` type, THE Scheduler_Executor SHALL assume the Cross_Account_Role, retrieve the stored original MinSize, MaxSize, and DesiredCapacity from the Members_Table, and call `autoscaling:UpdateAutoScalingGroup` to restore those values.
7. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a stop action for `eks-scale-zero` type, THE Scheduler_Executor SHALL assume the Cross_Account_Role, read the current minSize and desiredSize of each specified EKS node group, store those original values in the Members_Table, and call `eks:UpdateNodegroupConfig` to set minSize and desiredSize to 0.
8. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a start action for `eks-scale-zero` type, THE Scheduler_Executor SHALL assume the Cross_Account_Role, retrieve the stored original minSize and desiredSize from the Members_Table, and call `eks:UpdateNodegroupConfig` to restore those values.
9. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a stop action for `sagemaker-stop` type, THE Scheduler_Executor SHALL assume the Cross_Account_Role and call `sagemaker:StopNotebookInstance` for each specified notebook instance.
10. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a start action for `sagemaker-stop` type, THE Scheduler_Executor SHALL assume the Cross_Account_Role and call `sagemaker:StartNotebookInstance` for each specified notebook instance.
11. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a stop action for `redshift-pause` type, THE Scheduler_Executor SHALL assume the Cross_Account_Role and call `redshift:PauseCluster` for each specified Redshift cluster.
12. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a start action for `redshift-pause` type, THE Scheduler_Executor SHALL assume the Cross_Account_Role and call `redshift:ResumeCluster` for each specified Redshift cluster.
13. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a stop action for `workspaces-autostop` type, THE Scheduler_Executor SHALL assume the Cross_Account_Role and call `workspaces:ModifyWorkspaceProperties` to set RunningMode to `AUTO_STOP` for each specified WorkSpace.
14. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a stop action for `elb-teardown` type, THE Scheduler_Executor SHALL assume the Cross_Account_Role and call `elasticloadbalancing:DeleteLoadBalancer` for each specified load balancer. The Scheduler_Executor SHALL NOT create a start action for `elb-teardown` because load balancers require recreation.
15. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a `waste-scan` Review_Type action, THE Scheduler_Executor SHALL trigger the existing waste scan logic for the specified Customer_Account.
16. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a `snapshot-cleanup` Review_Type action, THE Scheduler_Executor SHALL assume the Cross_Account_Role, identify unused or old snapshots, and call `ec2:DeleteSnapshot` for each qualifying snapshot.
17. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a `gp2-migration` Review_Type action, THE Scheduler_Executor SHALL assume the Cross_Account_Role, identify gp2 EBS volumes, and call `ec2:ModifyVolume` to convert each to gp3.
18. WHEN EventBridge_Scheduler invokes the Scheduler_Executor with a `commitment-review` Review_Type action, THE Scheduler_Executor SHALL generate a Savings Plans and Reserved Instances utilization review report and store the results in the Members_Table.
19. IF the Scheduler_Executor fails to assume the Cross_Account_Role (AccessDenied, expired credentials, or role does not exist), THEN THE Scheduler_Executor SHALL log the error with the schedule ID, account ID, and error details, and SHALL record the failure in the schedule's execution history in the Members_Table.
20. IF an individual resource action fails (resource not found, insufficient permissions, resource in incompatible state), THEN THE Scheduler_Executor SHALL log the error for that resource, continue processing remaining resources in the same schedule, and record partial success with per-resource status in the Members_Table.

### Requirement 3: Schedule Lifecycle Management

**User Story:** As a member, I want to pause, resume, and delete my schedules, so that I can control automation without losing my schedule configuration.

#### Acceptance Criteria

1. WHEN a member requests to pause an active schedule, THE Member_Handler SHALL disable the corresponding EventBridge_Scheduler schedule(s) and update the schedule status to `paused` in the Members_Table.
2. WHEN a member requests to resume a paused schedule, THE Member_Handler SHALL enable the corresponding EventBridge_Scheduler schedule(s) and update the schedule status to `active` in the Members_Table.
3. WHEN a member requests to delete a schedule, THE Member_Handler SHALL delete the corresponding EventBridge_Scheduler schedule(s) and remove the schedule record from the Members_Table.
4. IF the EventBridge_Scheduler schedule does not exist when a member requests pause, resume, or delete, THEN THE Member_Handler SHALL clean up the orphaned record from the Members_Table and return a success response.

### Requirement 4: API Endpoints for Schedule Management

**User Story:** As a frontend developer, I want dedicated API endpoints for deleting and pausing/resuming schedules, so that the Wizard_UI can provide full schedule lifecycle controls.

#### Acceptance Criteria

1. THE Member_Handler SHALL expose a `DELETE /members/schedules/delete` endpoint that accepts a schedule ID and deletes the schedule and its EventBridge_Scheduler schedule(s).
2. THE Member_Handler SHALL expose a `PUT /members/schedules/pause` endpoint that accepts a schedule ID and pauses the schedule by disabling the EventBridge_Scheduler schedule(s).
3. THE Member_Handler SHALL expose a `PUT /members/schedules/resume` endpoint that accepts a schedule ID and resumes the schedule by enabling the EventBridge_Scheduler schedule(s).
4. WHEN any schedule management endpoint is called, THE Member_Handler SHALL validate the JWT token and verify the schedule belongs to the authenticated member before performing the action.

### Requirement 5: Schedule Status and Execution History

**User Story:** As a member, I want to see the real status of my schedules and their execution history, so that I can verify automation is working correctly.

#### Acceptance Criteria

1. WHEN the Scheduler_Executor completes an execution (success or failure), THE Scheduler_Executor SHALL write an execution record to the Members_Table containing: timestamp, action performed, resources affected, success/failure status, and error details for failures.
2. WHEN the member loads the scheduler view, THE Member_Handler SHALL return each schedule's current status (active, paused), next scheduled execution time, and the last 10 execution records.
3. THE Member_Handler SHALL compute the next execution time from the EventBridge_Scheduler schedule expression and timezone and include the value in the schedule response.

### Requirement 6: Frontend Schedule Cards

**User Story:** As a member, I want schedule cards that show real status, next execution time, and action buttons, so that I can monitor and control my automated schedules from the portal.

#### Acceptance Criteria

1. THE Schedule_Card SHALL display the schedule name, type, status (Active or Paused), next execution time formatted in the schedule's configured timezone, and the target resources or tag filter.
2. WHEN a schedule has status `active`, THE Schedule_Card SHALL display a Pause button and a Delete button.
3. WHEN a schedule has status `paused`, THE Schedule_Card SHALL display a Resume button and a Delete button.
4. WHEN a member clicks the Pause button on a Schedule_Card, THE Wizard_UI SHALL call the pause endpoint and update the Schedule_Card status to `paused` without a full page reload.
5. WHEN a member clicks the Resume button on a Schedule_Card, THE Wizard_UI SHALL call the resume endpoint and update the Schedule_Card status to `active` without a full page reload.
6. WHEN a member clicks the Delete button on a Schedule_Card, THE Wizard_UI SHALL display a confirmation dialog, and upon confirmation, call the delete endpoint and remove the Schedule_Card from the list.
7. WHEN a member expands a Schedule_Card, THE Schedule_Card SHALL display the execution history showing the last 10 executions with timestamp, action, result (success/partial/failure), and affected resource count.

### Requirement 7: IAM Permissions and Roles

**User Story:** As a platform operator, I want the correct IAM permissions configured so that the Member_Handler can create EventBridge schedules and the Scheduler_Executor can be invoked by EventBridge.

#### Acceptance Criteria

1. THE Member_Handler Lambda execution role SHALL have permissions for `scheduler:CreateSchedule`, `scheduler:DeleteSchedule`, `scheduler:UpdateSchedule`, `scheduler:GetSchedule`, and `iam:PassRole` (scoped to the EventBridge Scheduler execution role).
2. THE Platform_Account SHALL have an IAM role that EventBridge_Scheduler assumes to invoke the Scheduler_Executor Lambda, with permissions limited to `lambda:InvokeFunction` on the Scheduler_Executor ARN.
3. THE Scheduler_Executor Lambda execution role SHALL have permissions for `sts:AssumeRole` on `arn:aws:iam::*:role/SlashMyBill-*` and read/write access to the Members_Table.

### Requirement 8: Cross-Account Role Permission Updates

**User Story:** As a platform operator, I want the cross-account CloudFormation template to include all permissions needed for scheduled actions, so that the Scheduler_Executor can execute stop/start/scale operations in customer accounts.

#### Acceptance Criteria

1. THE Cross_Account_Role template generated by `handle_generate_template` SHALL include `ec2:StartInstances` in the inline policy (not relying on ReadOnlyAccess for write actions).
2. THE Cross_Account_Role template SHALL include `rds:StopDBInstance` and `rds:StartDBInstance` in the inline policy.
3. THE Cross_Account_Role template SHALL include `eks:UpdateNodegroupConfig` and `eks:DescribeNodegroup` in the inline policy.
4. THE Cross_Account_Role template SHALL include `sagemaker:StopNotebookInstance` and `sagemaker:StartNotebookInstance` in the inline policy.
5. THE Cross_Account_Role template SHALL include `redshift:PauseCluster` and `redshift:ResumeCluster` in the inline policy.
6. THE Cross_Account_Role template SHALL include `workspaces:ModifyWorkspaceProperties` in the inline policy.
7. THE Cross_Account_Role template SHALL include `ec2:ModifyVolume` in the inline policy for gp2→gp3 migration.

### Requirement 9: Tag-Based Resource Resolution

**User Story:** As a member, I want to target resources by tag filter instead of selecting individual ARNs, so that newly created resources matching the tag are automatically included in the schedule.

#### Acceptance Criteria

1. WHEN a schedule specifies a tag filter instead of explicit resource ARNs, THE Scheduler_Executor SHALL resolve matching resources at execution time by calling `resourcegroupstaggingapi:GetResources` with the tag filter in the Customer_Account.
2. WHEN tag-based resolution returns zero matching resources, THE Scheduler_Executor SHALL log a warning and record the empty execution in the Members_Table without treating the execution as a failure.

### Requirement 10: Deployment Pipeline

**User Story:** As a platform operator, I want the Scheduler_Executor Lambda packaged and deployed through the existing CI/CD pipeline, so that changes are deployed automatically on push to main.

#### Acceptance Criteria

1. WHEN code is pushed to the `main` branch with changes in the `scheduler-executor/` directory, THE deploy pipeline SHALL package the Scheduler_Executor Lambda code into a zip file, upload the zip to the S3 storage bucket, and update the Lambda function code.
2. THE deploy pipeline SHALL create API Gateway routes for `DELETE /members/schedules/delete`, `PUT /members/schedules/pause`, and `PUT /members/schedules/resume` targeting the Member_Handler integration.
3. THE deploy pipeline SHALL include the `scheduler-executor/**` path in the deploy trigger paths.
