# Requirements Document

## Introduction

SlashMyBill currently provides Windows/SQL Server licensing optimization advice through the Bedrock Agent chat and flags over-provisioned instances in the waste scan engine. This feature builds a dedicated **Optimize Licensing** wizard (Act > Optimize) that discovers all Windows Server and SQL Server workloads across connected accounts, analyzes their utilization against licensing costs, and produces a ranked report card of actionable savings strategies. The wizard covers EC2 instances with Platform=windows and RDS instances with engine=sqlserver-ee or sqlserver-se. It calculates cost comparisons across five strategies: current License Included pricing, BYOL with Software Assurance, Optimize CPUs (reduce active vCPUs), memory-optimized instance swap (fewer vCPUs, same memory), and Dedicated Host placement. The system operates cross-account via the existing STS AssumeRole pattern and retrieves pricing data from the AWS Pricing API in us-east-1.

## Glossary

- **Platform_Account**: The SlashMyBill AWS account (991105135552) where all platform infrastructure runs
- **Customer_Account**: An AWS account connected to SlashMyBill via a cross-account IAM role
- **Cross_Account_Role**: The IAM role `SlashMyBill-{accountId}` deployed in each Customer_Account, assumed by Platform_Account Lambdas using STS with ExternalId = SHA256(memberEmail)
- **Member_Handler**: The existing Lambda `aws-bill-analyzer-member-api` that handles all member API routes
- **Members_Table**: The DynamoDB table `MemberPortal-Members` that stores member data
- **Licensing_Wizard**: The new "Optimize Licensing" wizard card in Act > Optimize that orchestrates discovery, analysis, and recommendations for Windows/SQL Server licensing
- **License_Included**: AWS pricing model where Windows Server or SQL Server license cost is included in the hourly instance price
- **BYOL**: Bring Your Own License — customer uses their existing Microsoft licenses on AWS, reducing the hourly instance cost
- **Software_Assurance**: A Microsoft licensing benefit that enables License Mobility, allowing BYOL on AWS
- **Optimize_CPUs**: An EC2 feature that allows specifying a custom number of active vCPUs on an instance while retaining full memory and IOPS, reducing per-vCPU licensing costs
- **Dedicated_Host**: A physical server fully dedicated to a single customer, enabling licensing at the physical core level rather than per-vCPU
- **SQL_Enterprise**: SQL Server Enterprise Edition — full-featured, licensed per vCPU at premium pricing
- **SQL_Standard**: SQL Server Standard Edition — limited features, licensed per vCPU at lower pricing
- **vCPU**: Virtual CPU — the unit by which Windows Server and SQL Server are licensed on AWS
- **Report_Card**: The summary view showing total licensing spend, potential savings per strategy, and ranked recommendations
- **Pricing_API**: The AWS Price List Service API (`pricing:GetProducts`) available only in us-east-1, used to retrieve current instance pricing across license models

## Requirements

### Requirement 1: Windows/SQL Server Instance Discovery

**User Story:** As a member, I want the Licensing_Wizard to discover all Windows Server and SQL Server instances across my connected accounts, so that I have a complete inventory of licensable workloads.

#### Acceptance Criteria

1. WHEN a member initiates a licensing scan for a Customer_Account, THE Licensing_Wizard SHALL query `ec2:DescribeInstances` with filter `platform=windows` via the Cross_Account_Role and return all running Windows EC2 instances.
2. WHEN a member initiates a licensing scan for a Customer_Account, THE Licensing_Wizard SHALL query `rds:DescribeDBInstances` via the Cross_Account_Role and return all RDS instances where the engine starts with `sqlserver-`.
3. WHEN discovering EC2 Windows instances, THE Licensing_Wizard SHALL detect SQL Server presence by checking instance tags for keywords (sql, mssql, sqlserver) and by checking the AMI description for SQL Server edition identifiers.
4. WHEN discovering RDS SQL Server instances, THE Licensing_Wizard SHALL classify each instance as SQL_Enterprise (engine=sqlserver-ee) or SQL_Standard (engine=sqlserver-se).
5. FOR ALL discovered instances, THE Licensing_Wizard SHALL retrieve instance type specifications (vCPU count, memory, network bandwidth) via `ec2:DescribeInstanceTypes` for EC2 or from the RDS instance class metadata.
6. IF the Cross_Account_Role lacks the required discovery permissions, THEN THE Licensing_Wizard SHALL return an error indicating which specific permissions are missing and prompt the member to update the cross-account template.
7. WHEN discovery completes, THE Licensing_Wizard SHALL return a count of discovered instances grouped by type (EC2 Windows-only, EC2 Windows+SQL, RDS SQL Enterprise, RDS SQL Standard).

### Requirement 2: Utilization Analysis

**User Story:** As a member, I want the Licensing_Wizard to analyze 30 days of CPU and memory utilization for my Windows/SQL Server instances, so that I can identify over-provisioned workloads where vCPU reduction is safe.

#### Acceptance Criteria

1. WHEN analyzing an EC2 instance, THE Licensing_Wizard SHALL retrieve 30 days of `CPUUtilization` metrics from CloudWatch and compute the average, maximum, and p95 values.
2. WHEN analyzing an EC2 instance with CloudWatch Agent installed, THE Licensing_Wizard SHALL retrieve 30 days of `mem_used_percent` metrics and compute the average and maximum values.
3. WHEN analyzing an RDS instance, THE Licensing_Wizard SHALL retrieve 30 days of `CPUUtilization` and `FreeableMemory` metrics from CloudWatch and compute the average, maximum, and p95 CPU values.
4. WHEN CPU p95 utilization is below 50% of the instance vCPU capacity, THE Licensing_Wizard SHALL flag the instance as a candidate for vCPU reduction.
5. WHEN memory utilization data is unavailable (no CloudWatch Agent), THE Licensing_Wizard SHALL proceed with CPU-only analysis and note that memory data is unavailable in the recommendation.
6. FOR ALL analyzed instances, THE Licensing_Wizard SHALL compute the ratio of actual peak CPU usage to total available vCPUs and include this as `cpuEfficiencyRatio` in the analysis result.

### Requirement 3: Licensing Cost Calculation

**User Story:** As a member, I want the Licensing_Wizard to calculate and compare costs across different licensing strategies for each instance, so that I can see exactly how much each optimization would save.

#### Acceptance Criteria

1. WHEN calculating costs for an instance, THE Licensing_Wizard SHALL query the Pricing_API in us-east-1 with `serviceCode=AmazonEC2`, the instance type, `operatingSystem=Windows`, and `licenseModel=License Included` to retrieve the current License_Included hourly rate.
2. WHEN calculating costs for an instance, THE Licensing_Wizard SHALL query the Pricing_API with `licenseModel=Bring your own license` to retrieve the BYOL hourly rate for the same instance type.
3. WHEN calculating the Optimize_CPUs strategy, THE Licensing_Wizard SHALL compute the reduced cost based on the target vCPU count where the target equals the minimum vCPUs needed to sustain the p95 CPU load, rounded up to the nearest valid core count for the instance type.
4. WHEN calculating the memory-optimized swap strategy, THE Licensing_Wizard SHALL identify alternative instance types that provide equal or greater memory with fewer vCPUs, query their License_Included pricing, and compute the cost difference.
5. WHEN calculating the Dedicated_Host strategy, THE Licensing_Wizard SHALL retrieve Dedicated Host pricing for the instance family and compute the per-instance cost based on the number of instances that fit on a single host.
6. FOR ALL cost calculations, THE Licensing_Wizard SHALL express savings as both monthly dollar amounts and percentage reduction relative to the current License_Included cost.
7. WHEN calculating RDS SQL Server costs, THE Licensing_Wizard SHALL retrieve RDS pricing with the appropriate engine edition and compute the cost difference for instance class downsizing (fewer vCPUs, same or greater memory).

### Requirement 4: Optimization Recommendations

**User Story:** As a member, I want the Licensing_Wizard to provide specific, actionable recommendations ranked by savings, so that I know exactly what changes to make and how much each one saves.

#### Acceptance Criteria

1. FOR ALL analyzed instances, THE Licensing_Wizard SHALL generate recommendations ranked by estimated monthly savings in descending order.
2. WHEN an instance has CPU p95 below 50% of vCPU capacity, THE Licensing_Wizard SHALL recommend the Optimize_CPUs strategy with the specific target vCPU count and the calculated monthly savings.
3. WHEN a memory-optimized alternative exists with fewer vCPUs and equal or greater memory, THE Licensing_Wizard SHALL recommend the instance swap with the specific target instance type, vCPU reduction, and calculated monthly savings.
4. WHEN BYOL pricing is lower than License_Included pricing for an instance, THE Licensing_Wizard SHALL recommend BYOL with the savings amount and a note that Software_Assurance is required.
5. WHEN an RDS instance runs SQL_Enterprise and the member confirms Enterprise-specific features are not in use, THE Licensing_Wizard SHALL recommend downgrading to SQL_Standard with the calculated monthly savings.
6. WHEN generating recommendations, THE Licensing_Wizard SHALL include a plain-language action description (e.g., "Reduce vCPUs from 8 to 4 using Optimize CPUs") and the specific monthly dollar savings.
7. WHEN a recommendation involves the Resize a Server wizard, THE Licensing_Wizard SHALL include a deep-link to Act > Optimize > Resize a Server pre-filtered to the target instance.
8. THE Licensing_Wizard SHALL NOT recommend AWS Console actions — all actionable recommendations SHALL reference in-app features or advisory guidance.

### Requirement 5: Report Card Generation

**User Story:** As a member, I want to see a summary report card showing my total Windows/SQL licensing spend and potential savings across all strategies, so that I can prioritize which optimizations to pursue first.

#### Acceptance Criteria

1. WHEN the analysis completes, THE Licensing_Wizard SHALL generate a Report_Card containing the total current monthly licensing spend across all discovered Windows and SQL Server instances.
2. THE Report_Card SHALL display potential savings grouped by strategy (Optimize_CPUs, Memory-Optimized Swap, BYOL, Edition Downgrade, Dedicated_Host) with the total monthly savings for each strategy.
3. THE Report_Card SHALL rank strategies by total potential savings in descending order.
4. THE Report_Card SHALL display a per-instance breakdown showing the instance identifier, current monthly cost, best recommended action, and estimated savings for that action.
5. WHEN the total potential savings across all strategies is computed, THE Report_Card SHALL display the maximum achievable savings (best single strategy per instance, not cumulative across conflicting strategies).
6. THE Report_Card SHALL include a summary line showing the count of instances analyzed, the count with recommendations, and the total potential monthly savings.

### Requirement 6: Cross-Account Permission Validation

**User Story:** As a member, I want the Licensing_Wizard to validate that the cross-account role has all required permissions before starting the scan, so that I get clear guidance on fixing permission gaps rather than partial failures.

#### Acceptance Criteria

1. WHEN a member initiates a licensing scan, THE Licensing_Wizard SHALL first validate that the Cross_Account_Role can be assumed for the target Customer_Account.
2. WHEN validating permissions, THE Licensing_Wizard SHALL test the following actions: `ec2:DescribeInstances`, `ec2:DescribeInstanceTypes`, `rds:DescribeDBInstances`, `cloudwatch:GetMetricStatistics`, and `compute-optimizer:GetEC2InstanceRecommendations`.
3. IF any required permission is missing, THEN THE Licensing_Wizard SHALL return a list of missing permissions and a message instructing the member to update the CloudFormation template for the Cross_Account_Role.
4. WHEN all permissions are validated, THE Licensing_Wizard SHALL proceed with the discovery and analysis phases without re-validating permissions for each API call.

### Requirement 7: Compute Optimizer Integration

**User Story:** As a member, I want the Licensing_Wizard to incorporate AWS Compute Optimizer recommendations when available, so that I benefit from ML-based rightsizing suggestions in addition to utilization-based analysis.

#### Acceptance Criteria

1. WHEN analyzing EC2 instances, THE Licensing_Wizard SHALL query `compute-optimizer:GetEC2InstanceRecommendations` via the Cross_Account_Role for all discovered Windows instances.
2. WHEN Compute Optimizer returns recommendations for an instance, THE Licensing_Wizard SHALL include the recommended instance type and estimated savings alongside the utilization-based recommendations.
3. WHEN Compute Optimizer recommends a smaller instance type with fewer vCPUs, THE Licensing_Wizard SHALL calculate the licensing cost difference and include it in the savings estimate.
4. IF Compute Optimizer is not enabled in the Customer_Account, THEN THE Licensing_Wizard SHALL proceed with utilization-based analysis only and note that enabling Compute Optimizer would provide additional ML-based recommendations.

### Requirement 8: Wizard UI Integration

**User Story:** As a member, I want to access the Licensing_Wizard from the Act > Optimize section alongside the existing Resize and Cluster wizards, so that I can find licensing optimization in the same place as other optimization tools.

#### Acceptance Criteria

1. THE Licensing_Wizard SHALL appear as a new card titled "Optimize Licensing" in the Act > Optimize section alongside the existing "Resize a Server" and "Optimize a Cluster" cards.
2. WHEN a member selects the "Optimize Licensing" card, THE Licensing_Wizard SHALL display an account selector showing all connected Customer_Accounts for the member.
3. WHEN a member selects an account and initiates the scan, THE Licensing_Wizard SHALL display a progress indicator showing the current phase (Discovering instances, Analyzing utilization, Calculating costs, Generating recommendations).
4. WHEN the scan completes, THE Licensing_Wizard SHALL display the Report_Card with expandable sections for each strategy and per-instance details.
5. WHEN displaying the Report_Card, THE Licensing_Wizard SHALL allow the member to filter results by instance type (EC2 Windows, EC2 SQL Server, RDS SQL Server) and by strategy (Optimize_CPUs, BYOL, Instance Swap, Edition Downgrade, Dedicated_Host).
6. WHEN the members.js file is modified for this feature, THE build process SHALL bump the version query parameter in members/index.html (members.js?v=XX).

### Requirement 9: Pricing Data Retrieval

**User Story:** As a member, I want the Licensing_Wizard to use current AWS pricing data for all cost calculations, so that my savings estimates are accurate and up-to-date.

#### Acceptance Criteria

1. THE Licensing_Wizard SHALL query the Pricing_API exclusively in the us-east-1 region using the PRICING_REGION environment variable.
2. WHEN retrieving pricing for an instance type, THE Licensing_Wizard SHALL query with filters for `instanceType`, `operatingSystem=Windows`, `tenancy=Shared`, `preInstalledSw` (None or SQL Std or SQL Ent), and `licenseModel` (License Included or Bring your own license).
3. WHEN retrieving RDS pricing, THE Licensing_Wizard SHALL query with `serviceCode=AmazonRDS`, the specific `databaseEngine` (SQL Server Enterprise or SQL Server Standard), and the `instanceType`.
4. IF the Pricing_API returns no results for a specific instance type and license model combination, THEN THE Licensing_Wizard SHALL exclude that strategy from the recommendations for that instance and note the pricing data gap.
5. THE Licensing_Wizard SHALL cache pricing data for the duration of a single scan session to avoid redundant API calls for instances sharing the same instance type.

### Requirement 10: SQL Server Edition Downgrade Assessment

**User Story:** As a member, I want the Licensing_Wizard to help me assess whether my SQL Server Enterprise instances can be downgraded to Standard edition, so that I can save on licensing costs when Enterprise features are not needed.

#### Acceptance Criteria

1. WHEN an EC2 or RDS instance runs SQL_Enterprise, THE Licensing_Wizard SHALL present a checklist of Enterprise-only features (table partitioning, data compression, Always On AG with multiple secondaries, online index operations, resource governor) and ask the member to confirm which features are in use.
2. WHEN the member confirms that no Enterprise-only features are in use, THE Licensing_Wizard SHALL calculate the cost difference between SQL_Enterprise and SQL_Standard pricing for the same instance type and include it as a recommendation.
3. WHEN the member indicates that Enterprise-only features are in use, THE Licensing_Wizard SHALL exclude the edition downgrade recommendation for that instance.
4. THE Licensing_Wizard SHALL display the annual savings for edition downgrade prominently, as SQL Server Enterprise-to-Standard savings are typically the largest single optimization.
