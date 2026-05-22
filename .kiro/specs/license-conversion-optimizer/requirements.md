# Requirements Document

## Introduction

The existing "Optimize Licensing" wizard in Act → Optimize scans for Windows/SQL Server instances and provides cost comparison recommendations across licensing strategies. This feature extends the wizard by adding **license conversion execution** — the ability to actually perform license type changes on EC2 instances directly from the portal. The conversion process involves stopping the target instance, modifying its license configuration (via AMI swap or license specification update), and restarting it. The feature adds a "Convert License" action button next to each instance with a conversion opportunity, a target license selector, cost savings estimates, a confirmation dialog with downtime warnings, and full execution with audit logging. The system operates cross-account via the existing STS AssumeRole pattern and uses EC2 and License Manager APIs to perform the conversion.

## Glossary

- **Platform_Account**: The SlashMyBill AWS account (991105135552) where all platform infrastructure runs
- **Customer_Account**: An AWS account connected to SlashMyBill via a cross-account IAM role
- **Cross_Account_Role**: The IAM role `SlashMyBill-{accountId}` deployed in each Customer_Account, assumed by Platform_Account Lambdas using STS with ExternalId = SHA256(memberEmail)
- **Member_Handler**: The existing Lambda `aws-bill-analyzer-member-api` that handles all member API routes
- **Members_Table**: The DynamoDB table `MemberPortal-Members` that stores member data
- **Licensing_Wizard**: The existing "Optimize Licensing" wizard card in Act → Optimize that orchestrates discovery, analysis, and recommendations for Windows/SQL Server licensing
- **Conversion_Engine**: The backend component that executes license type changes on EC2 instances by stopping, modifying, and restarting them
- **License_Included**: AWS pricing model where Windows Server or SQL Server license cost is included in the hourly instance price
- **BYOL**: Bring Your Own License — customer uses their existing Microsoft licenses on AWS, reducing the hourly instance cost
- **License_Specification**: The AWS License Manager configuration that binds a license type to an EC2 instance resource
- **Target_License**: The destination license configuration that an instance will be converted to (e.g., "Windows Standard" without SQL, or BYOL)
- **Source_License**: The current license configuration on an instance before conversion (e.g., "Windows Standard with SQL Server Standard")
- **Conversion_Opportunity**: An instance where a valid, cost-saving license type change is available
- **Conversion_Job**: A single execution of the license conversion process for one instance, tracked from initiation through completion
- **AMI_Swap**: The process of changing an instance's AMI to one with a different license type while preserving instance configuration and data volumes
- **Audit_Log**: A record stored in DynamoDB capturing who initiated a conversion, what changed, when it occurred, and the outcome
- **Backup_AMI**: A full Amazon Machine Image created before conversion begins, serving as a complete restore point including all EBS volume snapshots
- **Sanity_Check**: Automated post-conversion verification that confirms the instance is healthy and the new license configuration is active
- **Go_No_Go_Decision**: A member-facing prompt after sanity checks that allows the member to confirm conversion success or trigger a full rollback

## Requirements

### Requirement 1: Conversion Opportunity Detection

**User Story:** As a member, I want the Licensing_Wizard to identify which instances have valid license conversion opportunities, so that I can see where I can take direct action to reduce costs.

#### Acceptance Criteria

1. WHEN the Licensing_Wizard completes its scan for a Customer_Account, THE Conversion_Engine SHALL identify EC2 instances running license configurations that have cheaper valid alternatives (e.g., "Windows Standard with SQL Server Standard" convertible to "Windows Standard" without SQL).
2. WHEN identifying Conversion_Opportunities, THE Conversion_Engine SHALL query `ec2:DescribeImages` to verify that a compatible AMI with the Target_License exists in the same region as the instance.
3. WHEN a Conversion_Opportunity is identified, THE Conversion_Engine SHALL compute the estimated monthly savings as the difference between the current Source_License hourly rate and the Target_License hourly rate multiplied by 730 hours.
4. WHEN a Conversion_Opportunity is identified, THE Conversion_Engine SHALL verify that the Target_License AMI supports the same instance type, architecture, and virtualization type as the current instance.
5. IF no compatible Target_License AMI exists for an instance, THEN THE Conversion_Engine SHALL exclude that instance from conversion opportunities and note the reason in the scan results.
6. WHEN displaying Conversion_Opportunities, THE Licensing_Wizard SHALL show the Source_License, available Target_License options, and estimated monthly savings for each eligible instance.

### Requirement 2: Target License Selection

**User Story:** As a member, I want to choose from valid conversion targets for each instance, so that I can select the license configuration that best fits my needs.

#### Acceptance Criteria

1. WHEN a member clicks "Convert License" on an eligible instance, THE Licensing_Wizard SHALL display a dropdown selector populated with all valid Target_License options for that instance.
2. FOR ALL Target_License options displayed, THE Licensing_Wizard SHALL show the license name, the estimated monthly cost after conversion, and the estimated monthly savings compared to the Source_License.
3. WHEN populating Target_License options, THE Conversion_Engine SHALL query `license-manager:ListLicenseConfigurations` via the Cross_Account_Role to retrieve available license configurations in the Customer_Account.
4. WHEN a Target_License option requires BYOL, THE Licensing_Wizard SHALL display a warning that the member must have valid Microsoft Software Assurance or equivalent license mobility rights.
5. THE Licensing_Wizard SHALL sort Target_License options by estimated monthly savings in descending order, with the highest savings option pre-selected.

### Requirement 3: Conversion Confirmation and Warnings

**User Story:** As a member, I want to see clear warnings about the impact of a license conversion before confirming, so that I understand the downtime and risks involved.

#### Acceptance Criteria

1. WHEN a member selects a Target_License and clicks "Confirm Conversion", THE Licensing_Wizard SHALL display a confirmation dialog containing the instance identifier, current Source_License, selected Target_License, estimated monthly savings, and a downtime warning.
2. THE confirmation dialog SHALL display a warning stating that the instance will be stopped and restarted during conversion, with an estimated downtime duration based on the instance type.
3. THE confirmation dialog SHALL require the member to acknowledge the downtime by checking a checkbox labeled "I understand this instance will be temporarily stopped" before the "Execute Conversion" button becomes active.
4. WHEN the instance has attached EBS volumes, THE confirmation dialog SHALL confirm that data volumes will be preserved during the conversion.
5. IF the instance is part of an Auto Scaling Group, THEN THE confirmation dialog SHALL warn that the ASG may launch a replacement instance during the conversion and recommend temporarily suspending the ASG.
6. IF the instance has an Elastic IP attached, THEN THE confirmation dialog SHALL confirm that the Elastic IP association will be preserved after restart.

### Requirement 4: License Conversion Execution

**User Story:** As a member, I want the system to execute the license conversion automatically after I confirm, so that I do not need to manually stop, modify, and restart the instance.

#### Acceptance Criteria

1. WHEN a member confirms a license conversion, THE Conversion_Engine SHALL execute the following steps in order: create a backup AMI and wait for "available" state, stop the instance and wait for "stopped" state, modify the license configuration, start the instance and wait for "running" state, run sanity checks and present a Go/No-Go decision to the member.
2. WHEN beginning a conversion, THE Conversion_Engine SHALL first create a backup AMI via `ec2:CreateImage` with `NoReboot=false` and poll `ec2:DescribeImages` until the AMI state is "available", with a timeout of 10 minutes.
3. IF the backup AMI fails to reach "available" state within the timeout, THEN THE Conversion_Engine SHALL abort the conversion entirely, leave the instance unchanged, and report the failure to the member.
4. WHEN stopping the instance, THE Conversion_Engine SHALL call `ec2:StopInstances` via the Cross_Account_Role and poll `ec2:DescribeInstances` until the instance state is "stopped", with a timeout of 5 minutes.
5. WHEN the instance is stopped, THE Conversion_Engine SHALL modify the license by calling `ec2:ModifyInstanceAttribute` to change the AMI or by calling `license-manager:UpdateLicenseSpecificationsForResource` to update the License_Specification binding.
6. WHEN the license modification succeeds, THE Conversion_Engine SHALL call `ec2:StartInstances` via the Cross_Account_Role and poll `ec2:DescribeInstances` until the instance state is "running", with a timeout of 5 minutes.
7. WHEN the instance reaches "running" state, THE Conversion_Engine SHALL wait 60 seconds for OS boot, then run sanity checks and present the Go/No-Go decision to the member.
8. WHEN the member selects "Go" (Confirm Success), THE Conversion_Engine SHALL mark the conversion as complete and return a success result containing the instance identifier, old license, new license, actual downtime duration, backup AMI ID, and new estimated monthly cost.
9. WHEN the member selects "No-Go" (Rollback), THE Conversion_Engine SHALL trigger a full rollback from the backup AMI.
10. IF the instance fails to stop within the 5-minute timeout, THEN THE Conversion_Engine SHALL abort the conversion, leave the instance in its current state, and report the failure to the member with the error details.
11. IF the license modification API call fails, THEN THE Conversion_Engine SHALL attempt to restart the instance with its original configuration and report the failure to the member with the specific API error.
12. IF the instance fails to start after modification, THEN THE Conversion_Engine SHALL trigger a full rollback from the backup AMI and report the outcome to the member.

### Requirement 5: Conversion Progress Tracking

**User Story:** As a member, I want to see real-time progress of the license conversion, so that I know what step the system is on and whether it succeeded or failed.

#### Acceptance Criteria

1. WHEN a conversion is in progress, THE Licensing_Wizard SHALL display a progress indicator showing the current step: "Creating backup AMI", "Waiting for AMI available", "Stopping instance", "Waiting for stopped state", "Modifying license configuration", "Starting instance", "Waiting for running state", "Running sanity checks", "Awaiting Go/No-Go decision", "Conversion complete".
2. WHEN each step completes, THE Licensing_Wizard SHALL update the progress indicator to the next step within 5 seconds of the state change.
3. WHEN a conversion fails at any step, THE Licensing_Wizard SHALL display the failed step, the error message, and any rollback actions taken.
4. WHEN a conversion completes successfully, THE Licensing_Wizard SHALL display a success message with the actual downtime duration and the confirmed new license configuration.
5. WHILE a conversion is in progress for an instance, THE Licensing_Wizard SHALL disable the "Convert License" button for that instance to prevent duplicate executions.

### Requirement 6: Conversion Audit Logging

**User Story:** As a member, I want all license conversions to be logged with full details, so that I have an audit trail for compliance and troubleshooting.

#### Acceptance Criteria

1. WHEN a conversion is initiated, THE Conversion_Engine SHALL create an Audit_Log entry in DynamoDB containing: member email, Customer_Account ID, instance ID, Source_License, Target_License, timestamp, and status "initiated".
2. WHEN a conversion completes successfully, THE Conversion_Engine SHALL update the Audit_Log entry with status "completed", actual downtime duration, and the confirmed new license configuration.
3. WHEN a conversion fails, THE Conversion_Engine SHALL update the Audit_Log entry with status "failed", the step where failure occurred, the error message, and any rollback actions performed.
4. WHEN a member views the Licensing_Wizard, THE Licensing_Wizard SHALL display a "Conversion History" section showing past conversions for the selected Customer_Account with timestamp, instance, action taken, and outcome.
5. FOR ALL Audit_Log entries, THE Conversion_Engine SHALL store the entries with a TTL of 365 days to support annual compliance reviews.

### Requirement 7: Cross-Account Permission Validation for Conversion

**User Story:** As a member, I want the system to verify that the cross-account role has all permissions needed for conversion execution before I attempt it, so that I do not experience mid-conversion failures due to missing permissions.

#### Acceptance Criteria

1. WHEN a member clicks "Convert License" on an instance, THE Conversion_Engine SHALL validate that the Cross_Account_Role has the following permissions: `ec2:StopInstances`, `ec2:StartInstances`, `ec2:ModifyInstanceAttribute`, `ec2:DescribeInstances`, `ec2:DescribeImages`, `ec2:DescribeInstanceStatus`, `license-manager:UpdateLicenseSpecificationsForResource`, `ec2:CreateImage` (for backup AMI), `ec2:DeregisterImage` (for cleanup), `ec2:DeleteSnapshot` (for cleanup), `ec2:RunInstances` (for rollback — launching from AMI), and `ec2:TerminateInstances` (for rollback — removing failed instance).
2. IF any required conversion permission is missing, THEN THE Conversion_Engine SHALL display a message listing the missing permissions and instruct the member to update the CloudFormation template for the Cross_Account_Role.
3. WHEN all conversion permissions are validated, THE Conversion_Engine SHALL enable the Target_License selector and allow the member to proceed with the conversion flow.
4. THE Conversion_Engine SHALL cache the permission validation result for the duration of the member's session to avoid redundant validation calls.

### Requirement 8: Conversion Eligibility Rules

**User Story:** As a member, I want the system to enforce conversion eligibility rules, so that I cannot accidentally perform an invalid or harmful license conversion.

#### Acceptance Criteria

1. WHEN evaluating conversion eligibility, THE Conversion_Engine SHALL reject conversions from SQL Server Enterprise to SQL Server Standard if the instance tags or member confirmation indicate Enterprise-only features are in use.
2. WHEN evaluating conversion eligibility, THE Conversion_Engine SHALL reject conversions where the Target_License AMI does not support the instance's current EBS volume configuration (e.g., NVMe vs non-NVMe boot requirements).
3. WHEN evaluating conversion eligibility, THE Conversion_Engine SHALL reject conversions for instances in a "stopping", "pending", or "shutting-down" state and instruct the member to wait until the instance reaches a stable state.
4. WHEN evaluating conversion eligibility, THE Conversion_Engine SHALL reject conversions for instances that are part of an active Spot request.
5. WHEN evaluating conversion eligibility, THE Conversion_Engine SHALL reject conversions for instances that have instance store volumes (ephemeral storage), because ephemeral data would be lost during the stop/start cycle and cannot be recovered from the backup AMI.
6. WHEN converting from a SQL Server license to a non-SQL Target_License, THE Conversion_Engine SHALL display a warning to the member stating that SQL Server databases on the instance will become inaccessible after conversion, and require explicit acknowledgment before proceeding.
7. IF a conversion is rejected due to eligibility rules, THEN THE Conversion_Engine SHALL display the specific reason for rejection and any remediation steps the member can take.

### Requirement 9: UI Integration for Conversion Actions

**User Story:** As a member, I want the conversion actions to integrate seamlessly into the existing Licensing_Wizard results view, so that I can convert licenses directly from the scan results without navigating elsewhere.

#### Acceptance Criteria

1. WHEN the Licensing_Wizard displays scan results, THE Licensing_Wizard SHALL show a "Convert License" button next to each instance that has at least one valid Conversion_Opportunity.
2. WHEN an instance has no valid Conversion_Opportunities, THE Licensing_Wizard SHALL display the instance without a "Convert License" button and show the reason (e.g., "No compatible AMI available", "Already on lowest-cost license").
3. WHEN a conversion completes successfully, THE Licensing_Wizard SHALL update the instance row to reflect the new license configuration and remove the "Convert License" button if no further conversions are available.
4. THE Licensing_Wizard SHALL display a summary banner at the top of the results showing the total number of instances with conversion opportunities and the total potential monthly savings from conversions.
5. WHEN the members.js file is modified for this feature, THE build process SHALL bump the version query parameter in members/index.html (members.js?v=XX).

### Requirement 10: Conversion Rollback Capability

**User Story:** As a member, I want the system to automatically attempt rollback if a conversion fails mid-process, so that my instance is not left in a broken state.

#### Acceptance Criteria

1. WHEN a license modification fails after the instance has been stopped, THE Conversion_Engine SHALL attempt to restart the instance with its original Source_License configuration.
2. WHEN a rollback is attempted, THE Conversion_Engine SHALL call `ec2:StartInstances` and poll until the instance reaches "running" state, with a timeout of 5 minutes.
3. IF the rollback succeeds, THEN THE Conversion_Engine SHALL report to the member that the conversion failed but the instance has been restored to its original state.
4. IF the rollback fails, THEN THE Conversion_Engine SHALL report to the member that manual intervention is required, provide the instance ID, the last known state, and recommend checking the AWS Console.
5. WHEN a rollback is performed, THE Conversion_Engine SHALL update the Audit_Log entry with rollback details including whether the rollback succeeded or failed.

### Requirement 11: Pre-Conversion Backup (AMI Snapshot)

**User Story:** As a member, I want the system to create a full AMI backup of my instance before any license modification begins, so that I have a complete restore point in case anything goes wrong during conversion.

#### Acceptance Criteria

1. WHEN a conversion is confirmed and before stopping the instance, THE Conversion_Engine SHALL create a Backup_AMI via `ec2:CreateImage` with `NoReboot=false` (the instance will be stopped as part of the conversion flow).
2. WHEN creating the Backup_AMI, THE Conversion_Engine SHALL tag the AMI with the following tags: `SlashMyBill-ConversionBackup=true`, `SourceInstanceId=<instance-id>`, `CreatedAt=<ISO-8601-timestamp>`, and `SourceLicense=<Source_License>`.
3. WHEN the Backup_AMI is created, THE Conversion_Engine SHALL poll `ec2:DescribeImages` until the AMI state reaches "available", with a timeout of 10 minutes.
4. IF the Backup_AMI fails to reach "available" state within the timeout or the `ec2:CreateImage` call fails, THEN THE Conversion_Engine SHALL abort the conversion entirely, leave the instance unchanged, and report the failure to the member.
5. WHEN the Backup_AMI reaches "available" state, THE Licensing_Wizard SHALL display the Backup_AMI ID in the progress tracker so the member can reference it for manual recovery if needed.
6. THE Conversion_Engine SHALL retain the Backup_AMI for 7 days by default (configurable per member), then auto-cleanup via a tag-based lifecycle policy that deregisters the AMI and deletes associated EBS snapshots.

### Requirement 12: Post-Conversion Sanity Test (Go/No-Go)

**User Story:** As a member, I want the system to perform automated sanity checks after the license is modified and the instance is restarted, so that I can confirm the conversion succeeded before it is finalized.

#### Acceptance Criteria

1. WHEN the instance reaches "running" state after license modification, THE Conversion_Engine SHALL wait 60 seconds for OS boot before initiating Sanity_Checks.
2. WHEN performing Sanity_Checks, THE Conversion_Engine SHALL verify: instance status checks pass via `ec2:DescribeInstanceStatus` (system reachability check and instance reachability check both report "ok"), and the new license configuration is confirmed via instance metadata or `ec2:DescribeInstances` platform details.
3. WHEN Sanity_Checks complete, THE Licensing_Wizard SHALL present the results to the member with a Go_No_Go_Decision: a "Confirm Success" button and a "Rollback" button.
4. IF the instance does not reach 2/2 status checks within 5 minutes of reaching "running" state, THEN THE Conversion_Engine SHALL auto-trigger a full rollback from the Backup_AMI without waiting for member input.
5. WHEN the member clicks "Rollback", THE Conversion_Engine SHALL trigger a full rollback from the Backup_AMI created in Requirement 11.
6. WHEN the member clicks "Confirm Success", THE Conversion_Engine SHALL mark the Conversion_Job as complete, log success in the Audit_Log, and update the Licensing_Wizard UI to reflect the new license.

### Requirement 13: Full Rollback from Backup AMI

**User Story:** As a member, I want the system to fully restore my instance to its pre-conversion state using the backup AMI, so that I can recover from a failed or undesirable conversion.

#### Acceptance Criteria

1. WHEN a full rollback is triggered (manually by the member or automatically by failed Sanity_Checks), THE Conversion_Engine SHALL stop the current modified instance.
2. WHEN the modified instance is stopped, THE Conversion_Engine SHALL launch a new instance from the Backup_AMI using `ec2:RunInstances` with the same instance type, security groups, subnet, IAM role, tags, and key pair as the original instance.
3. IF the original instance had an Elastic IP associated, THEN THE Conversion_Engine SHALL reassociate the Elastic IP to the newly launched instance via `ec2:AssociateAddress`.
4. WHEN the replacement instance reaches "running" state and passes 2/2 status checks, THE Conversion_Engine SHALL terminate the failed/modified instance via `ec2:TerminateInstances`.
5. WHEN a rollback is performed, THE Conversion_Engine SHALL update the Audit_Log entry with rollback details including the new instance ID, the Backup_AMI ID used, and whether the rollback succeeded or failed.
6. IF the rollback fails (e.g., the Backup_AMI is corrupted or `ec2:RunInstances` fails), THEN THE Conversion_Engine SHALL report to the member with manual recovery instructions, the Backup_AMI ID, and recommend checking the AWS Console.
