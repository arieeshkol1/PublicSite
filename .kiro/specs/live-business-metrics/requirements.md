# Requirements Document — Live Business Metrics

## Introduction

Replace the manually-entered KPI data in the Unit Cost Trend widget on the Observe dashboard with real, auto-discovered business metrics pulled from the customer's AWS account via the existing cross-account role. The system queries operational data sources (Cognito, DynamoDB, API Gateway, Route 53, CloudWatch, Lambda, S3) and combines them with Cost Explorer data to compute real unit economics displayed as a time-series chart with selectable metrics and cost dimensions.

## Glossary

- **Metrics_Discovery_Service**: The backend component that queries customer AWS accounts to discover and collect real operational metrics via STS AssumeRole.
- **Unit_Economics_Engine**: The backend component that combines discovered metric volumes with Cost Explorer cost data to compute cost-per-unit values.
- **Live_Metrics_Widget**: The frontend chart component in the Observe dashboard that displays time-series business metrics with dual axes (volume bars and cost-per-unit line).
- **Cross_Account_Role**: The IAM role `SlashMyBill-{accountId}` with ReadOnlyAccess in the customer's AWS account, assumed via STS.
- **Business_Metric**: A named operational measurement (e.g., active users, API requests, DynamoDB items) with a numeric volume for a given time period.
- **Cost_Dimension**: A cost grouping the user selects to compare against a metric — total account cost, a specific AWS service cost, or a tag-based cost allocation.
- **Metric_Source**: An AWS service from which operational metrics are collected (Cognito, DynamoDB, API Gateway, Route 53, CloudWatch, Lambda, S3).
- **Member**: An authenticated SlashMyBill user with one or more connected AWS accounts.

## Requirements

### Requirement 1: Discover Cognito User Metrics

**User Story:** As a Member, I want the system to automatically discover user counts from my Cognito User Pools, so that I can see real user-based unit economics without manual data entry.

#### Acceptance Criteria

1. WHEN a Member's connected account contains Cognito User Pools, THE Metrics_Discovery_Service SHALL list all User Pools and retrieve the total user count for each pool.
2. WHEN a Member's connected account contains Cognito User Pools, THE Metrics_Discovery_Service SHALL retrieve the count of users who have signed in within the last 30 days as the "active users" metric.
3. IF the Cross_Account_Role lacks permission to access Cognito, THEN THE Metrics_Discovery_Service SHALL skip Cognito discovery and log a warning without failing the overall discovery process.
4. THE Metrics_Discovery_Service SHALL label each Cognito metric with the User Pool name and the source identifier "aws-cognito".

### Requirement 2: Discover DynamoDB Table Metrics

**User Story:** As a Member, I want the system to automatically discover item counts from my DynamoDB tables, so that I can track data volume growth against cost.

#### Acceptance Criteria

1. WHEN a Member's connected account contains DynamoDB tables, THE Metrics_Discovery_Service SHALL retrieve the item count for each table (up to 20 tables).
2. THE Metrics_Discovery_Service SHALL label each DynamoDB metric with the table name and the source identifier "aws-dynamodb".
3. IF a DynamoDB table returns an item count of zero, THEN THE Metrics_Discovery_Service SHALL exclude that table from the discovered metrics.
4. IF the Cross_Account_Role lacks permission to describe DynamoDB tables, THEN THE Metrics_Discovery_Service SHALL skip DynamoDB discovery and log a warning without failing the overall discovery process.

### Requirement 3: Discover API Gateway Request Metrics

**User Story:** As a Member, I want the system to automatically discover API request counts from my API Gateway APIs, so that I can compute cost per API request.

#### Acceptance Criteria

1. WHEN a Member's connected account contains API Gateway REST or HTTP APIs, THE Metrics_Discovery_Service SHALL retrieve the total request count per API for each of the last 6 months via CloudWatch metrics.
2. THE Metrics_Discovery_Service SHALL label each API Gateway metric with the API name and the source identifier "aws-apigateway".
3. IF no API Gateway APIs exist in the account, THEN THE Metrics_Discovery_Service SHALL return an empty result for this Metric_Source without error.
4. IF the Cross_Account_Role lacks permission to access API Gateway or CloudWatch, THEN THE Metrics_Discovery_Service SHALL skip API Gateway discovery and log a warning without failing the overall discovery process.

### Requirement 4: Discover Route 53 DNS Query Metrics

**User Story:** As a Member, I want the system to automatically discover DNS query counts from my Route 53 hosted zones, so that I can track DNS traffic volume against cost.

#### Acceptance Criteria

1. WHEN a Member's connected account contains Route 53 hosted zones, THE Metrics_Discovery_Service SHALL retrieve the DNS query count per hosted zone for each of the last 6 months via CloudWatch metrics.
2. THE Metrics_Discovery_Service SHALL label each Route 53 metric with the hosted zone name and the source identifier "aws-route53".
3. IF no hosted zones exist in the account, THEN THE Metrics_Discovery_Service SHALL return an empty result for this Metric_Source without error.
4. IF the Cross_Account_Role lacks permission to access Route 53 or CloudWatch, THEN THE Metrics_Discovery_Service SHALL skip Route 53 discovery and log a warning without failing the overall discovery process.

### Requirement 5: Discover CloudWatch Custom Metrics

**User Story:** As a Member, I want the system to discover custom CloudWatch metrics I have published, so that I can use my own business KPIs for unit economics.

#### Acceptance Criteria

1. WHEN a Member's connected account contains custom CloudWatch namespaces (namespaces not prefixed with "AWS/"), THE Metrics_Discovery_Service SHALL list up to 10 custom namespaces and retrieve up to 5 metrics per namespace.
2. FOR each discovered custom metric, THE Metrics_Discovery_Service SHALL retrieve the Sum statistic for each of the last 6 months.
3. THE Metrics_Discovery_Service SHALL label each custom metric with the namespace, metric name, and the source identifier "aws-cloudwatch-custom".
4. IF no custom namespaces exist, THEN THE Metrics_Discovery_Service SHALL return an empty result for this Metric_Source without error.

### Requirement 6: Enhance Existing Lambda and S3 Metric Discovery

**User Story:** As a Member, I want Lambda invocation counts and S3 object counts collected on a monthly basis, so that they can be used in time-series unit economics alongside the new metric sources.

#### Acceptance Criteria

1. THE Metrics_Discovery_Service SHALL retrieve Lambda invocation counts per month for each of the last 6 months via CloudWatch metrics (not just a 30-day aggregate).
2. THE Metrics_Discovery_Service SHALL retrieve S3 object counts per bucket via CloudWatch S3 metrics (NumberOfObjects) for each of the last 6 months.
3. THE Metrics_Discovery_Service SHALL label Lambda metrics with the source identifier "aws-lambda" and S3 metrics with "aws-s3".

### Requirement 7: Retrieve Service-Level Cost Data for Unit Economics

**User Story:** As a Member, I want cost data broken down by service and by month, so that the system can compute accurate cost-per-unit for each metric.

#### Acceptance Criteria

1. THE Unit_Economics_Engine SHALL retrieve monthly cost data from Cost Explorer grouped by AWS service for each of the last 6 months.
2. THE Unit_Economics_Engine SHALL retrieve monthly total account cost (unblended) for each of the last 6 months.
3. WHEN a Member selects a tag-based Cost_Dimension, THE Unit_Economics_Engine SHALL retrieve monthly cost data filtered by the specified tag key and value.
4. IF Cost Explorer returns no data for a given month, THEN THE Unit_Economics_Engine SHALL treat the cost as zero for that month.

### Requirement 8: Compute Unit Economics

**User Story:** As a Member, I want the system to compute cost-per-unit by dividing cost by metric volume, so that I can see real unit economics trends over time.

#### Acceptance Criteria

1. WHEN both cost data and metric volume data are available for a given month, THE Unit_Economics_Engine SHALL compute cost-per-unit as (cost / volume) rounded to 6 decimal places.
2. THE Unit_Economics_Engine SHALL support the following cost-per-unit calculations: cost per user (total or Cognito service cost / Cognito active users), cost per API request (API Gateway service cost / API Gateway request count), cost per DynamoDB item (DynamoDB service cost / total DynamoDB items), and cost per transaction (total cost / total API requests).
3. IF the metric volume for a given month is zero, THEN THE Unit_Economics_Engine SHALL return null for cost-per-unit for that month instead of dividing by zero.
4. THE Unit_Economics_Engine SHALL return a time-series array with one entry per month containing: month, metric name, volume, cost, and cost-per-unit.

### Requirement 9: Persist Discovered Metrics

**User Story:** As a Member, I want discovered metrics stored so that historical data is preserved even if the AWS account state changes.

#### Acceptance Criteria

1. WHEN the Metrics_Discovery_Service completes discovery, THE Metrics_Discovery_Service SHALL store each discovered metric in the MemberPortal-BusinessMetrics DynamoDB table with the source field set to the Metric_Source identifier.
2. THE Metrics_Discovery_Service SHALL store metrics with a composite key of memberEmail and metricMonth, matching the existing table schema.
3. WHEN a metric for the same member, month, and metric name already exists, THE Metrics_Discovery_Service SHALL update the volume value rather than creating a duplicate.
4. THE Metrics_Discovery_Service SHALL preserve any manually-entered metrics (source = "manual") and not overwrite them with discovered data.

### Requirement 10: Live Metrics API Endpoint

**User Story:** As a Member, I want a dedicated API endpoint that triggers metric discovery and returns unit economics, so that the frontend can fetch live data on demand.

#### Acceptance Criteria

1. THE Member_Handler SHALL expose a `GET /members/live-metrics` endpoint that triggers metric discovery across all connected accounts and returns the unit economics time-series.
2. WHEN the endpoint is called, THE Member_Handler SHALL run discovery for all enabled Metric_Sources (Cognito, DynamoDB, API Gateway, Route 53, CloudWatch custom, Lambda, S3) and compute unit economics.
3. THE endpoint SHALL return a JSON response containing: an array of discovered metrics, an array of unit economics time-series entries, and a list of available metric names for the selector.
4. IF no connected accounts exist, THEN THE endpoint SHALL return an empty result with a 200 status code.
5. THE endpoint SHALL complete within 30 seconds for accounts with up to 5 connected AWS accounts.

### Requirement 11: Dual-Axis Time-Series Chart

**User Story:** As a Member, I want to see business metrics displayed as a dual-axis time-series chart, so that I can visually correlate volume trends with cost-per-unit trends.

#### Acceptance Criteria

1. THE Live_Metrics_Widget SHALL render a chart with a primary Y-axis for volume (displayed as bars) and a secondary Y-axis for cost-per-unit (displayed as a line).
2. THE Live_Metrics_Widget SHALL display data points for each of the last 6 months on the X-axis.
3. THE Live_Metrics_Widget SHALL use the Apache ECharts library consistent with the existing dashboard charts.
4. WHEN no metric data is available, THE Live_Metrics_Widget SHALL display a message stating "No business metrics discovered. Connect an AWS account to get started."

### Requirement 12: Metric Selector

**User Story:** As a Member, I want to select which business metric to display in the chart, so that I can focus on the KPI most relevant to my business.

#### Acceptance Criteria

1. THE Live_Metrics_Widget SHALL display a dropdown selector populated with all discovered metric names.
2. WHEN the Member selects a different metric from the dropdown, THE Live_Metrics_Widget SHALL update the chart to show the selected metric's volume and cost-per-unit data.
3. THE Live_Metrics_Widget SHALL default to the first discovered metric in the list when the widget loads.
4. WHEN manually-entered metrics and auto-discovered metrics both exist, THE Live_Metrics_Widget SHALL display both in the dropdown, with auto-discovered metrics grouped under an "Auto-Discovered" label and manual metrics under a "Manual" label.

### Requirement 13: Cost Dimension Selector

**User Story:** As a Member, I want to choose which cost dimension to compare against the selected metric, so that I can analyze unit economics from different cost perspectives.

#### Acceptance Criteria

1. THE Live_Metrics_Widget SHALL display a second dropdown for selecting the Cost_Dimension with options: "Total Account Cost", each discovered AWS service name, and any tag-based cost allocations.
2. WHEN the Member selects a different Cost_Dimension, THE Live_Metrics_Widget SHALL recompute and display the cost-per-unit line using the selected cost data.
3. THE Live_Metrics_Widget SHALL default the Cost_Dimension to the AWS service most closely associated with the selected metric (e.g., "Amazon Cognito" for Cognito user metrics).
4. WHEN a tag-based Cost_Dimension is selected, THE Live_Metrics_Widget SHALL fetch tag-filtered cost data from the backend and update the chart.

### Requirement 14: Replace Manual Entry with Auto-Discovery

**User Story:** As a Member, I want the Unit Cost Trend widget to prioritize auto-discovered metrics over manual entry, so that I get accurate data without manual effort.

#### Acceptance Criteria

1. WHEN auto-discovered metrics are available, THE Live_Metrics_Widget SHALL display auto-discovered data by default instead of manually-entered data.
2. THE Live_Metrics_Widget SHALL retain the ability to display manually-entered metrics when selected from the metric dropdown.
3. THE Live_Metrics_Widget SHALL display a visual indicator (badge or icon) next to each metric name showing whether the metric source is "Auto" or "Manual".
4. WHEN both auto-discovered and manual metrics exist for the same metric name and month, THE Live_Metrics_Widget SHALL display the auto-discovered value and show the manual value as a tooltip comparison.

### Requirement 15: Graceful Degradation and Error Handling

**User Story:** As a Member, I want the widget to work even when some data sources are unavailable, so that partial data is still useful.

#### Acceptance Criteria

1. IF one or more Metric_Sources fail during discovery, THEN THE Metrics_Discovery_Service SHALL return results from the successful sources and include a warnings array listing the failed sources.
2. IF Cost Explorer data is unavailable, THEN THE Live_Metrics_Widget SHALL display volume bars without the cost-per-unit line and show a message indicating cost data is unavailable.
3. IF the Cross_Account_Role assumption fails for an account, THEN THE Metrics_Discovery_Service SHALL skip that account and include it in the warnings array.
4. THE Live_Metrics_Widget SHALL display any warnings returned by the API as a dismissible notification banner above the chart.
