# Requirements Document

## Introduction

The License Conversion Optimizer currently identifies five conversion opportunity types (ri_exchange, ri_to_sp, on_demand_to_committed, license_model_change, sp_upgrade) for member accounts. The existing `_identify_license_model_changes` function detects EC2 instances running "Windows with SQL Standard" or "Windows with SQL Enterprise" but only recommends converting to BYOL (Bring Your Own License). This feature adds a 6th conversion type — `sql_license_removal` — that identifies instances where SQL Server is bundled in the AMI but not actually in use, and recommends converting to a plain "Windows" AMI to eliminate the SQL Server licensing cost entirely. This is a distinct and often larger savings opportunity than BYOL, as SQL Server licensing on AWS adds significant per-vCPU cost. The conversion requires instance replacement (new AMI, data migration) and is flagged as high complexity.

## Glossary

- **License_Conversion_Optimizer**: The existing module in Member_Handler that analyzes a member's licensing portfolio and identifies conversion opportunities across six types
- **Member_Handler**: The existing Lambda `aws-bill-analyzer-member-api` that handles all member API routes, located at `member-handler/lambda_function.py`
- **SQL_License_Removal**: The new conversion type (`sql_license_removal`) that recommends removing an unused SQL Server license from an EC2 instance by switching to a plain Windows AMI
- **Windows_With_SQL**: An EC2 instance platform value of "Windows with SQL Standard" or "Windows with SQL Enterprise", indicating the AMI includes a bundled SQL Server license
- **Plain_Windows**: An EC2 instance platform value of "Windows", indicating a Windows Server AMI without any SQL Server license bundled
- **Pricing_API**: The AWS Price List Service API (`pricing:GetProducts`) available only in us-east-1, used to retrieve current instance pricing across license models and platforms
- **Conversion_Opportunity**: A data structure representing a recommended licensing change, including source/target descriptions, savings estimates, complexity, and prerequisites
- **Cross_Account_Role**: The IAM role `SlashMyBill-{accountId}` deployed in each customer account, assumed by Platform_Account Lambdas using STS
- **License_Conversion_Wizard**: The frontend wizard card in Act > License Conversion that displays conversion opportunities to members
- **Instance_Replacement**: The process of launching a new EC2 instance from a different AMI and migrating workloads from the original instance, required when changing the platform/OS license type

## Requirements

### Requirement 1: SQL License Removal Opportunity Detection

**User Story:** As a member, I want the License_Conversion_Optimizer to identify EC2 instances running Windows with SQL Server where the SQL Server license can be removed, so that I can see opportunities to eliminate unnecessary SQL licensing costs.

#### Acceptance Criteria

1. WHEN analyzing a member's portfolio, THE License_Conversion_Optimizer SHALL identify all on-demand EC2 instances where the platform is "Windows with SQL Standard" or "Windows with SQL Enterprise" as candidates for SQL_License_Removal.
2. WHEN an instance is identified as a SQL_License_Removal candidate, THE License_Conversion_Optimizer SHALL create a Conversion_Opportunity with type `sql_license_removal` that recommends converting to Plain_Windows.
3. WHEN generating SQL_License_Removal opportunities, THE License_Conversion_Optimizer SHALL set the complexity to "high" because the conversion requires Instance_Replacement.
4. WHEN generating SQL_License_Removal opportunities, THE License_Conversion_Optimizer SHALL set the timing to "scheduled" because the conversion requires a maintenance window.
5. WHEN an instance is already identified as a `license_model_change` (BYOL) opportunity, THE License_Conversion_Optimizer SHALL also generate a separate `sql_license_removal` opportunity for the same instance, allowing the member to choose between BYOL and full SQL license removal.

### Requirement 2: SQL License Removal Savings Calculation

**User Story:** As a member, I want to see the exact dollar savings from removing the SQL Server license, so that I can evaluate whether the conversion effort is worthwhile.

#### Acceptance Criteria

1. WHEN calculating savings for a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL query the Pricing_API for the hourly rate of the instance type with platform "Windows with SQL Standard" or "Windows with SQL Enterprise" (matching the current platform).
2. WHEN calculating savings for a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL query the Pricing_API for the hourly rate of the same instance type with platform "Windows" (Plain_Windows).
3. WHEN both pricing values are retrieved, THE License_Conversion_Optimizer SHALL compute the monthly savings as (SQL_platform_hourly_rate - Windows_hourly_rate) multiplied by 730 hours, rounded to 2 decimal places.
4. WHEN both pricing values are retrieved, THE License_Conversion_Optimizer SHALL compute the savings percentage as the monthly savings divided by the current monthly cost, multiplied by 100, rounded to 1 decimal place.
5. IF the Pricing_API returns no results for either the SQL platform rate or the Plain_Windows rate for a given instance type, THEN THE License_Conversion_Optimizer SHALL exclude that instance from SQL_License_Removal recommendations and log the pricing data gap.
6. WHEN computing annual savings, THE License_Conversion_Optimizer SHALL multiply the monthly savings by 12 and round to 2 decimal places.

### Requirement 3: SQL License Removal Prerequisites

**User Story:** As a member, I want to see clear prerequisites before attempting a SQL license removal, so that I do not accidentally remove SQL Server from an instance that depends on it.

#### Acceptance Criteria

1. WHEN generating a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the prerequisite "Confirm SQL Server is not in use on this instance" in the prerequisites list.
2. WHEN generating a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the prerequisite "Schedule a maintenance window for instance replacement" in the prerequisites list.
3. WHEN generating a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the prerequisite "Identify or create a Windows-only AMI compatible with the instance type" in the prerequisites list.
4. WHEN generating a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the prerequisite "Plan data volume migration strategy (detach/reattach EBS volumes or copy data)" in the prerequisites list.

### Requirement 4: SQL License Removal Conversion Instructions

**User Story:** As a member, I want step-by-step instructions for performing the SQL license removal conversion, so that I can execute the change safely with minimal downtime.

#### Acceptance Criteria

1. WHEN generating an execution plan for a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the step "Create an AMI snapshot of the current instance for rollback purposes".
2. WHEN generating an execution plan for a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the step "Launch a new EC2 instance from a Windows-only AMI with the same instance type and VPC/subnet configuration".
3. WHEN generating an execution plan for a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the step "Detach non-root EBS data volumes from the original instance and attach them to the new instance".
4. WHEN generating an execution plan for a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the step "Migrate application data and configurations from the original instance to the new instance".
5. WHEN generating an execution plan for a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the step "Update DNS records, Elastic IPs, or load balancer target groups to point to the new instance".
6. WHEN generating an execution plan for a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the step "Verify application functionality on the new instance before terminating the original".
7. WHEN generating an execution plan for a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the step "Terminate the original instance after successful verification and monitoring period".
8. WHEN generating an execution plan for a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL set the estimated duration to "2-4 hours (includes instance replacement and verification)".

### Requirement 5: SQL License Removal Risk Documentation

**User Story:** As a member, I want to understand the risks associated with SQL license removal, so that I can make an informed decision and plan appropriate mitigations.

#### Acceptance Criteria

1. WHEN generating a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the risk "Application downtime during instance replacement" in the risks list.
2. WHEN generating a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the risk "Data loss if EBS volumes are not properly migrated" in the risks list.
3. WHEN generating a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the risk "Network configuration changes may be required (security groups, ENIs, Elastic IPs)" in the risks list.
4. WHEN generating a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL include the risk "Rollback requires relaunching from the original AMI snapshot" in the risks list.
5. WHEN generating a SQL_License_Removal opportunity, THE License_Conversion_Optimizer SHALL set `isReversible` to true because the original AMI snapshot enables rollback.

### Requirement 6: Frontend Display of SQL License Removal Opportunities

**User Story:** As a member, I want SQL license removal opportunities to appear in the License Conversion wizard alongside other conversion types, so that I can compare all available licensing optimizations in one place.

#### Acceptance Criteria

1. WHEN the License_Conversion_Wizard displays conversion opportunities, THE License_Conversion_Wizard SHALL render `sql_license_removal` opportunities with a distinct label "Remove SQL License" to differentiate them from `license_model_change` (BYOL) opportunities.
2. WHEN displaying a SQL_License_Removal opportunity, THE License_Conversion_Wizard SHALL show the source platform (Windows with SQL Standard or Windows with SQL Enterprise), the target platform (Windows), and the monthly savings amount.
3. WHEN displaying a SQL_License_Removal opportunity, THE License_Conversion_Wizard SHALL display a "High Complexity" badge to indicate that instance replacement is required.
4. WHEN displaying a SQL_License_Removal opportunity, THE License_Conversion_Wizard SHALL display the prerequisites list with a warning that SQL Server usage must be confirmed as inactive before proceeding.
5. WHEN the members.js file is modified for this feature, THE build process SHALL bump the version query parameter in members/index.html (members.js?v=XX).

### Requirement 7: Integration with Existing Conversion Pipeline

**User Story:** As a developer, I want the SQL license removal detection to integrate seamlessly with the existing License_Conversion_Optimizer pipeline, so that it runs alongside the other five conversion type detectors without disrupting existing functionality.

#### Acceptance Criteria

1. THE License_Conversion_Optimizer SHALL include `sql_license_removal` as a valid conversion type alongside the existing five types (ri_exchange, ri_to_sp, on_demand_to_committed, license_model_change, sp_upgrade).
2. WHEN the analysis pipeline executes, THE License_Conversion_Optimizer SHALL call the SQL_License_Removal detection function in the same pipeline loop as the other five detection functions.
3. WHEN scoring SQL_License_Removal opportunities with the feasibility scorer, THE License_Conversion_Optimizer SHALL apply the same scoring algorithm used for other conversion types (savings potential 35%, utilization improvement 25%, execution complexity 20%, risk level 20%).
4. WHEN the `_get_estimated_duration` function is called with conv_type `sql_license_removal`, THE License_Conversion_Optimizer SHALL return "2-4 hours (includes instance replacement and verification)".
5. WHEN generating the total potential savings summary, THE License_Conversion_Optimizer SHALL include SQL_License_Removal savings in the aggregate totals and SHALL NOT double-count savings with `license_model_change` opportunities for the same instance.

