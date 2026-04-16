# Implementation Plan: Live Business Metrics

## Overview

Replace the manual Unit Cost Trend widget with an automated live metrics system. The backend adds a `GET /members/live-metrics` endpoint to the existing member-handler Lambda that discovers operational metrics from 7 AWS sources (Cognito, DynamoDB, API Gateway, Route 53, CloudWatch custom, Lambda, S3), combines them with Cost Explorer cost data, computes unit economics, and persists results. The frontend replaces the existing `dash-unit-economics` widget with a dual-axis ECharts chart featuring metric and cost dimension selectors.

## Tasks

- [x] 1. Implement MetricsDiscoveryService in member-handler
  - [x] 1.1 Create the `discover_all_metrics` orchestrator function and individual source discovery functions
    - Add `discover_all_metrics(credentials, account_id)` that calls each source discovery function wrapped in try/except for graceful degradation
    - Implement `_discover_cognito_metrics(credentials)` — list User Pools, get total and active user counts, label with pool name and source "aws-cognito"
    - Implement `_discover_dynamodb_metrics(credentials)` — list tables (up to 20), get item counts, exclude zero-count tables, label with table name and source "aws-dynamodb"
    - Implement `_discover_apigateway_metrics(credentials)` — get REST/HTTP APIs, query CloudWatch for request counts per API per month (6 months), label with API name and source "aws-apigateway"
    - Implement `_discover_route53_metrics(credentials)` — list hosted zones, query CloudWatch for DNS query counts per zone per month (6 months), label with zone name and source "aws-route53"
    - Implement `_discover_cloudwatch_custom_metrics(credentials)` — list custom namespaces (exclude "AWS/" prefix, cap at 10 namespaces, 5 metrics each), get Sum statistic per month (6 months), label with namespace/metric name and source "aws-cloudwatch-custom"
    - Implement `_discover_lambda_metrics(credentials)` — query CloudWatch for Lambda invocation counts per month (6 months), label with source "aws-lambda"
    - Implement `_discover_s3_metrics(credentials)` — query CloudWatch S3 NumberOfObjects per bucket per month (6 months), label with source "aws-s3"
    - Each metric returns: `{metricName, volume, source, month, description, accountId}`
    - Collect warnings for any source that throws an exception (AccessDeniedException, etc.)
    - Use a Python script to add the code to `member-handler/lambda_function.py` since the file is large
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 15.1, 15.3_

  - [ ]* 1.2 Write property test for source labeling correctness
    - **Property 1: Source labeling correctness**
    - Generate random resource names and metric source types, verify source field matches expected identifier and metricName contains resource name
    - **Validates: Requirements 1.4, 2.2, 3.2, 4.2, 5.3, 6.3**

  - [ ]* 1.3 Write property test for zero-count metric exclusion
    - **Property 2: Zero-count metric exclusion**
    - Generate random lists of DynamoDB tables with random item counts (0 to 1M), verify no zero-count metrics in output
    - **Validates: Requirements 2.3**

  - [ ]* 1.4 Write property test for custom namespace filtering and capping
    - **Property 3: Custom namespace filtering and capping**
    - Generate random namespace lists mixing "AWS/" and custom prefixes, verify filtering excludes AWS-managed and caps at 10 namespaces / 5 metrics each
    - **Validates: Requirements 5.1**

  - [ ]* 1.5 Write property test for graceful degradation under partial source failures
    - **Property 8: Graceful degradation under partial source failures**
    - Generate random subsets of failing sources, verify partial results returned and warnings array contains one entry per failed source
    - **Validates: Requirements 15.1**

- [x] 2. Implement UnitEconomicsEngine and cost data fetching
  - [x] 2.1 Create `fetch_cost_data` and `compute_unit_economics` functions
    - Implement `fetch_cost_data(credentials, cost_dimension, months)` — query Cost Explorer GetCostAndUsage grouped by SERVICE for 6 months, support "total", service name, and "tag:Key=Value" dimensions
    - Implement `compute_unit_economics(metrics, cost_data, cost_dimension)` — compute cost/volume rounded to 6 decimal places, return null for zero volume, treat missing cost as zero
    - Return time-series array: `[{month, metricName, volume, cost, costPerUnit}]`
    - Implement default cost dimension mapping: aws-cognito → "Amazon Cognito", aws-dynamodb → "Amazon DynamoDB", aws-apigateway → "Amazon API Gateway", aws-route53 → "Amazon Route 53", aws-lambda → "AWS Lambda", aws-s3 → "Amazon Simple Storage Service", aws-cloudwatch-custom/manual → "total"
    - Use a Python script to add the code to `member-handler/lambda_function.py`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 13.3_

  - [ ]* 2.2 Write property test for unit economics computation correctness
    - **Property 4: Unit economics computation correctness**
    - Generate random cost/volume pairs for 6 months, verify: positive cost+volume → round(cost/volume, 6), zero volume → null, missing cost → zero, all fields present
    - **Validates: Requirements 7.4, 8.1, 8.3, 8.4**

  - [ ]* 2.3 Write property test for default cost dimension mapping
    - **Property 7: Default cost dimension mapping**
    - Generate random metrics with all source types, verify default cost dimension maps correctly per the mapping table
    - **Validates: Requirements 13.3**

- [x] 3. Implement LiveMetricsHandler and DynamoDB persistence
  - [x] 3.1 Create `handle_live_metrics` route handler and wire into Lambda dispatch
    - Implement `handle_live_metrics(event)` — validate JWT, get memberEmail, query connected accounts, loop through accounts (max 5), assume cross-account role, call `discover_all_metrics`, call `fetch_cost_data`, persist metrics to DynamoDB, call `compute_unit_economics`, build response
    - Add `'GET /members/live-metrics': handle_live_metrics` to the routes dict in `lambda_handler`
    - Persist discovered metrics to `MemberPortal-BusinessMetrics` table with composite SK format `{YYYY-MM}#{metricName}`, upsert (overwrite) existing auto-discovered metrics, preserve manual metrics (source="manual")
    - Build response with: metrics array, unitEconomics array, availableMetrics list (grouped "Auto-Discovered" / "Manual"), availableCostDimensions list, warnings array
    - Return 200 with empty arrays when no connected accounts exist
    - Use a Python script to add the code to `member-handler/lambda_function.py`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4, 10.5, 14.1, 14.2_

  - [ ]* 3.2 Write property test for metric upsert idempotence
    - **Property 5: Metric upsert idempotence**
    - Generate random metrics, write twice with different volumes, verify single record with latest value
    - **Validates: Requirements 9.3**

  - [ ]* 3.3 Write property test for manual metric preservation
    - **Property 6: Manual metric preservation**
    - Generate manual + auto-discovered metrics with overlapping names, verify manual metrics are never overwritten or deleted
    - **Validates: Requirements 9.4**

- [x] 4. Checkpoint — Backend verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Add API Gateway route for live-metrics endpoint
  - [x] 5.1 Add `GET /members/live-metrics` route to API Gateway
    - Add the route to the CloudFormation template or via CLI for API Gateway ID `l2fd4h481h`
    - Ensure the route has the same authorization configuration as existing member routes
    - Add OPTIONS preflight route for CORS support
    - _Requirements: 10.1_

- [x] 6. Implement Live Metrics Widget in frontend
  - [x] 6.1 Replace the existing Unit Cost Trend widget with the Live Metrics Widget
    - Use a Python script to modify `members/members.js` since the file is large
    - Replace the `dash-unit-economics` widget definition to use the new live metrics rendering
    - Implement `_fetchLiveMetrics(costDimension)` — call `GET /members/live-metrics?costDimension=...` via the existing `api()` helper
    - Implement `_renderLiveMetrics(data)` — main render function that builds the dual-axis ECharts chart (volume bars on primary Y-axis, cost-per-unit line on secondary Y-axis), 6-month X-axis
    - Implement `_buildMetricSelector(metrics)` — populate dropdown with discovered metrics grouped under "Auto-Discovered" and "Manual" labels, show "Auto"/"Manual" badge next to each metric name
    - Implement `_buildCostDimensionSelector(dims)` — populate dropdown with "Total Account Cost", service names, and tag-based options; default to the service most closely associated with the selected metric
    - Implement `_updateLiveMetricsChart(data)` — update chart when metric or cost dimension selection changes, re-fetch with new costDimension if needed
    - Handle empty state: show "No business metrics discovered. Connect an AWS account to get started."
    - Handle warnings: show dismissible notification banner above chart
    - Handle cost data unavailable: show volume bars only, hide cost-per-unit line, show info message
    - Default to first discovered metric on load; default cost dimension to associated service
    - When both auto-discovered and manual metrics exist for same name/month, show auto-discovered value with manual value as tooltip comparison
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 12.1, 12.2, 12.3, 12.4, 13.1, 13.2, 13.3, 13.4, 14.1, 14.2, 14.3, 14.4, 15.2, 15.4_

- [x] 7. Checkpoint — Full integration verification
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Update IAM permissions and infrastructure
  - [x] 8.1 Update member-handler Lambda IAM role with required permissions
    - Add permissions for the member-handler Lambda role to call: `cognito-idp:ListUserPools`, `cognito-idp:DescribeUserPool`, `dynamodb:ListTables`, `dynamodb:DescribeTable`, `apigateway:GetRestApis`, `apigateway:GetApis`, `route53:ListHostedZones`, `cloudwatch:ListMetrics`, `cloudwatch:GetMetricStatistics`, `lambda:ListFunctions`, `s3:ListAllMyBuckets`, `ce:GetCostAndUsage` via the cross-account role
    - These permissions are exercised through the assumed cross-account role, so verify the `SlashMyBill-{accountId}` role template includes ReadOnlyAccess or equivalent
    - Update CloudFormation template if needed
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 6.1, 6.2, 7.1_

- [x] 9. Final checkpoint — End-to-end verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The member-handler Lambda file is large — use Python scripts for modifications as noted in each task
- Deploy by pushing to main branch after all tasks are complete
- API Gateway ID: `l2fd4h481h`
