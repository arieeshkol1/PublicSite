# Requirements Document

## Introduction

This document defines the requirements for enhancing the cost data cache to store cost breakdowns for ALL active cost allocation tag keys per daily cost item. Currently, the background cache refresh queries Cost Explorer for a single (primary) tag key and stores results in a flat `tag_breakdown` dictionary. This enhancement changes the cache to query each active tag key sequentially and store results as a nested structure keyed by tag key, enabling instant dashboard tag filtering from cache without live Cost Explorer calls.

## Glossary

- **Cache_Refresh_Engine**: The background process within the incremental fetch engine that populates the DynamoDB cost cache during asynchronous Lambda invocations
- **Cost_Cache_Table**: The DynamoDB table storing daily cost data items per member account
- **Tag_Breakdown**: The nested data structure within each cached daily cost item that maps tag keys to their value-cost dictionaries
- **Active_Tag_Key**: A cost allocation tag key that has been activated in the AWS Billing console and returns data from the Cost Explorer get_tags API
- **CE_Client**: The boto3 Cost Explorer client used to call GetCostAndUsage and GetTags APIs
- **Dashboard_Handler**: The Lambda function handler that serves dashboard-data requests and reads from the cost cache
- **Size_Guard**: The logic that monitors DynamoDB item size and truncates tag data to stay within safe storage limits
- **Top_N_Cap**: The maximum number of tag values retained per tag key, selected by descending cost amount
- **Flat_Format**: The legacy tag_breakdown format where keys are "tagKey=tagValue" strings mapped directly to cost floats
- **Nested_Format**: The new tag_breakdown format where the outer key is the tag key name and the inner dict maps tag values to cost floats
- **Read_Normalizer**: The read-time logic that detects Flat_Format data and converts it to Nested_Format on-the-fly for backward compatibility

## Requirements

### Requirement 1: Multi-Tag Key Discovery

**User Story:** As a platform operator, I want the cache refresh to discover all active cost allocation tag keys, so that the cache contains cost breakdowns for every tag dimension.

#### Acceptance Criteria

1. WHEN the Cache_Refresh_Engine begins a refresh cycle for an account, THE Cache_Refresh_Engine SHALL call the Cost Explorer get_tags API to retrieve all Active_Tag_Keys for the refresh date range
2. IF the get_tags API call fails, THEN THE Cache_Refresh_Engine SHALL log a warning and skip tag breakdown population for the current refresh cycle without failing the overall refresh
3. WHEN the get_tags API returns an empty list, THE Cache_Refresh_Engine SHALL skip tag breakdown population and store an empty Tag_Breakdown for each daily item

### Requirement 2: Sequential Tag Key Querying

**User Story:** As a platform operator, I want tag key queries to execute sequentially, so that the system avoids Cost Explorer API throttling.

#### Acceptance Criteria

1. WHEN the Cache_Refresh_Engine queries Cost Explorer for tag breakdowns, THE Cache_Refresh_Engine SHALL issue one GetCostAndUsage call per Active_Tag_Key in sequential order
2. THE Cache_Refresh_Engine SHALL wait for each tag key query to complete before issuing the next tag key query
3. IF a GetCostAndUsage call for a specific tag key fails after retry exhaustion, THEN THE Cache_Refresh_Engine SHALL log the failure and continue with the remaining tag keys
4. WHEN multiple Active_Tag_Keys exist, THE Cache_Refresh_Engine SHALL apply the same exponential backoff retry logic used for service-breakdown queries to each individual tag key query

### Requirement 3: Nested Tag Breakdown Storage

**User Story:** As a developer, I want tag breakdowns stored in a nested structure keyed by tag key, so that the dashboard can filter by any tag key without additional API calls.

#### Acceptance Criteria

1. THE Cache_Refresh_Engine SHALL store Tag_Breakdown in Nested_Format where the outer dictionary key is the tag key name and the inner dictionary maps tag values to cost amounts
2. WHEN writing a daily cost item to the Cost_Cache_Table, THE Cache_Refresh_Engine SHALL include the complete Nested_Format Tag_Breakdown as the tag_breakdown attribute
3. WHEN a tag value has zero cost for a given day, THE Cache_Refresh_Engine SHALL exclude that tag value from the inner dictionary for that day
4. WHEN untagged resources have non-zero cost for a tag key, THE Cache_Refresh_Engine SHALL store the cost under the value "(untagged)" within that tag key's inner dictionary

### Requirement 4: DynamoDB Item Size Protection

**User Story:** As a platform operator, I want the cache to stay within DynamoDB item size limits, so that write operations do not fail due to oversized items.

#### Acceptance Criteria

1. THE Size_Guard SHALL calculate the serialized size of the Tag_Breakdown before writing each daily cost item to the Cost_Cache_Table
2. WHILE the serialized Tag_Breakdown size exceeds 350 kilobytes, THE Size_Guard SHALL remove the tag key with the fewest total values from the Tag_Breakdown until the size is within the limit
3. WHEN the Size_Guard removes a tag key due to size constraints, THE Size_Guard SHALL log a warning including the removed tag key name and the account identifier
4. THE Size_Guard SHALL evaluate item size after applying the Top_N_Cap to all tag keys

### Requirement 5: Top-N Value Cap Per Tag Key

**User Story:** As a platform operator, I want each tag key limited to the top N values by cost, so that high-cardinality tags do not consume excessive storage.

#### Acceptance Criteria

1. THE Cache_Refresh_Engine SHALL retain only the top N tag values per tag key, ranked by descending cost amount across the refresh period
2. WHEN a tag key has more values than the Top_N_Cap, THE Cache_Refresh_Engine SHALL discard values with the lowest cost amounts
3. THE Top_N_Cap SHALL default to 50 values per tag key
4. WHEN values are discarded due to the Top_N_Cap, THE Cache_Refresh_Engine SHALL aggregate discarded values into a single "(other)" entry per tag key per day

### Requirement 6: Dashboard Read Path — Nested Format

**User Story:** As a member, I want the dashboard tag filter to read from the cached nested structure, so that tag filtering is instant without live API calls.

#### Acceptance Criteria

1. WHEN a tag filter is active and cached data is available, THE Dashboard_Handler SHALL read the Tag_Breakdown from cache and extract cost data for the selected tag key
2. WHEN the selected tag key exists in the cached Tag_Breakdown, THE Dashboard_Handler SHALL use the inner dictionary values to compute filtered daily cost trends and service allocations
3. WHEN the selected tag key does not exist in the cached Tag_Breakdown, THE Dashboard_Handler SHALL fall back to a live Cost Explorer query with the tag filter applied
4. THE Dashboard_Handler SHALL not make live Cost Explorer calls for tag filtering when the requested tag key is present in the cached Tag_Breakdown

### Requirement 7: Backward Compatibility — Read-Time Normalization

**User Story:** As a developer, I want the system to handle both old flat-format and new nested-format cache items, so that existing cached data remains usable during the migration period.

#### Acceptance Criteria

1. WHEN the Dashboard_Handler reads a cache item with Flat_Format tag_breakdown, THE Read_Normalizer SHALL convert the data to Nested_Format by grouping "tagKey=tagValue" entries under their respective tag keys
2. WHEN the Dashboard_Handler reads a cache item with Nested_Format tag_breakdown, THE Read_Normalizer SHALL pass the data through without modification
3. THE Read_Normalizer SHALL detect the format by checking whether the first value in the tag_breakdown dictionary is a number (Flat_Format) or a dictionary (Nested_Format)
4. WHEN a Flat_Format entry contains a key without an equals sign separator, THE Read_Normalizer SHALL place that entry under an "unknown" tag key

### Requirement 8: Resource State Exclusion

**User Story:** As a platform operator, I want resource-level state data to remain sourced from live APIs, so that real-time accuracy is maintained for operational data.

#### Acceptance Criteria

1. THE Dashboard_Handler SHALL continue to retrieve resource state data (rightsizing recommendations, waste detection, EBS volumes) from live AWS APIs regardless of cache state
2. THE Cache_Refresh_Engine SHALL store only cost amount data and tag cost breakdowns in the Tag_Breakdown structure, excluding resource metadata or state information

### Requirement 9: Refresh Scope and Granularity

**User Story:** As a platform operator, I want the multi-tag refresh to cover the same 90-day window at daily granularity, so that tag data aligns with existing cached cost data.

#### Acceptance Criteria

1. THE Cache_Refresh_Engine SHALL query each Active_Tag_Key using DAILY granularity matching the existing cost data refresh granularity
2. THE Cache_Refresh_Engine SHALL query each Active_Tag_Key for the same date range used in the current refresh batch
3. WHEN the refresh covers multiple date range batches, THE Cache_Refresh_Engine SHALL query all Active_Tag_Keys for each batch before proceeding to the next batch

### Requirement 10: Error Isolation

**User Story:** As a platform operator, I want failures in tag key queries to be isolated, so that a single tag key failure does not prevent caching of other tag keys or service cost data.

#### Acceptance Criteria

1. IF a single tag key query fails, THEN THE Cache_Refresh_Engine SHALL include successfully queried tag keys in the Tag_Breakdown and omit only the failed tag key
2. IF all tag key queries fail, THEN THE Cache_Refresh_Engine SHALL store an empty Tag_Breakdown and log an error summarizing the failure count
3. THE Cache_Refresh_Engine SHALL complete service-breakdown caching regardless of tag key query outcomes
4. WHEN a tag key query fails, THE Cache_Refresh_Engine SHALL include the tag key name and error code in the warning log entry
