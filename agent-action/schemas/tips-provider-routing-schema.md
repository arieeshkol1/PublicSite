# Tips Table `providerRouting` Schema Extension

## Overview

The `providerRouting` attribute extends the `ViewMyBill-CostOptimizationTips` DynamoDB table
to store provider-specific API endpoints, parameter schemas, response formats, and cost
thresholds per tip. This enables the Agent_Action_Lambda to dynamically route and
parameterize optimization checks without hardcoded provider logic.

## Table Context

- **Table Name:** `ViewMyBill-CostOptimizationTips`
- **Partition Key:** `service` (String)
- **Sort Key:** `tipId` (String)
- **Existing Fields:** service, tipId, title, description, estimatedSavings, difficulty, category, cloud, checkImplemented, actionType, actionLabel, level, serviceKey, automatedCheck

## `providerRouting` Attribute Format

The `providerRouting` attribute is a DynamoDB **Map (M)** type at the top level of each tip item.
It contains provider-keyed entries where each key is a supported cloud provider identifier.

### Structure

```json
{
  "providerRouting": {
    "<providerKey>": {
      "apiEndpoint": "<string>",
      "parameterSchema": { ... },
      "responseFormat": "<string>",
      "costThresholds": { ... }
    }
  }
}
```

### Provider Keys

| Key       | Description                     |
|-----------|---------------------------------|
| `aws`     | Amazon Web Services             |
| `azure`   | Microsoft Azure                 |
| `gcp`     | Google Cloud Platform           |
| `openai`  | OpenAI (AI vendor)              |

### Field Definitions

#### `apiEndpoint` (String, required)

The provider-specific API call(s) needed to execute the optimization check for this tip.
Multiple APIs are separated by ` + ` when the check requires data from more than one source.

Examples:
- AWS: `"ec2:DescribeInstances + cloudwatch:GetMetricStatistics"`
- Azure: `"Microsoft.Compute/virtualMachines + Microsoft.Monitor/metrics"`
- GCP: `"compute.instances.list + monitoring.timeSeries.list"`

#### `parameterSchema` (Map, required)

A map of parameter names to their values or constraints that the connector should use
when invoking the API for this tip's optimization check.

| Field             | Type            | Description                                           |
|-------------------|-----------------|-------------------------------------------------------|
| `metricsWindow`   | String          | Time window for metric lookups (e.g., `"14d"`, `"30d"`) |
| `cpuThreshold`    | Number          | CPU utilization threshold percentage for right-sizing |
| `memoryThreshold` | Number          | Memory utilization threshold percentage               |
| `storageClass`    | String          | Target storage class for tiering recommendations      |
| `retentionDays`   | Number          | Retention period for lifecycle policy checks          |
| `granularity`     | String          | Data granularity (`"DAILY"`, `"HOURLY"`)              |
| `groupBy`         | List of String  | Grouping dimensions for cost breakdown                |

Note: The `parameterSchema` is extensible — each tip may include different parameters
relevant to its specific optimization check. The connector reads only the parameters it
recognizes.

#### `responseFormat` (String, required)

Identifier for the expected response structure from the provider API. The connector
uses this to determine how to normalize the raw response into the vendor-neutral schema.

Examples:
| Value                    | Description                                          |
|--------------------------|------------------------------------------------------|
| `ec2_instance_list`      | AWS EC2 DescribeInstances response format            |
| `azure_vm_list`          | Azure Compute Management VM list format              |
| `gce_instance_list`      | GCP Compute Engine instances.list format             |
| `cloudwatch_metrics`     | AWS CloudWatch GetMetricStatistics format            |
| `azure_monitor_metrics`  | Azure Monitor metrics query format                   |
| `gcp_monitoring_series`  | GCP Cloud Monitoring timeSeries format               |
| `cost_explorer_results`  | AWS Cost Explorer GetCostAndUsage format             |
| `azure_cost_mgmt`        | Azure Cost Management query results format           |
| `bigquery_billing`       | GCP BigQuery Billing Export format                   |
| `s3_bucket_list`         | AWS S3 ListBuckets + configuration format            |
| `azure_blob_list`        | Azure Blob Storage containers list format            |
| `gcs_bucket_list`        | GCP Cloud Storage buckets list format                |
| `openai_usage_report`    | OpenAI API usage/billing response format             |

#### `costThresholds` (Map, required)

Defines minimum thresholds that must be met before the tip is considered actionable.
This prevents noise from low-value recommendations.

| Field              | Type   | Description                                              |
|--------------------|--------|----------------------------------------------------------|
| `minSavingsUSD`    | Number | Minimum estimated monthly savings (USD) to surface tip   |
| `minResourceCount` | Number | Minimum number of applicable resources to surface tip    |
| `minUtilization`   | Number | Minimum utilization % below which tip applies            |
| `maxUtilization`   | Number | Maximum utilization % above which tip does NOT apply     |

Note: All fields in `costThresholds` are optional. Only include thresholds relevant
to the specific tip.

## Complete Example

```json
{
  "service": "EC2",
  "tipId": "ec2-001",
  "title": "Right-size EC2 instances",
  "description": "Use AWS Compute Optimizer to analyze historical utilization...",
  "estimatedSavings": "20-40%",
  "difficulty": "easy",
  "cloud": "AWS",
  "providerRouting": {
    "aws": {
      "apiEndpoint": "ec2:DescribeInstances + cloudwatch:GetMetricStatistics",
      "parameterSchema": {
        "metricsWindow": "14d",
        "cpuThreshold": 30,
        "memoryThreshold": 30
      },
      "responseFormat": "ec2_instance_list",
      "costThresholds": {
        "minSavingsUSD": 10,
        "minResourceCount": 1
      }
    },
    "azure": {
      "apiEndpoint": "Microsoft.Compute/virtualMachines + Microsoft.Monitor/metrics",
      "parameterSchema": {
        "metricsWindow": "14d",
        "cpuThreshold": 30,
        "memoryThreshold": 30
      },
      "responseFormat": "azure_vm_list",
      "costThresholds": {
        "minSavingsUSD": 10,
        "minResourceCount": 1
      }
    },
    "gcp": {
      "apiEndpoint": "compute.instances.list + monitoring.timeSeries.list",
      "parameterSchema": {
        "metricsWindow": "14d",
        "cpuThreshold": 30,
        "memoryThreshold": 30
      },
      "responseFormat": "gce_instance_list",
      "costThresholds": {
        "minSavingsUSD": 10,
        "minResourceCount": 1
      }
    }
  }
}
```

## Behavioral Rules

1. **Loading providerRouting**: When the Agent_Action_Lambda executes an optimization
   check referenced by a tip, it loads the `providerRouting` entry matching the
   resolved `cloudProvider` to determine the correct API endpoint and parameters.

2. **Missing provider entry**: If a tip does not have a `providerRouting` entry for
   the resolved `cloudProvider`, the Agent_Action_Lambda skips that tip and logs a
   warning indicating the tip is not supported for that provider.

3. **Backward compatibility**: Tips without a `providerRouting` attribute continue
   to function using the existing `automatedCheck` field for AWS-only execution.
   The presence of `providerRouting` signals multi-provider support.

4. **Extensibility**: New providers can be added by inserting a new key in the
   `providerRouting` map without modifying existing entries.
