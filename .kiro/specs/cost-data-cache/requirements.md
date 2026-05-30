# Requirements Document

## Introduction

This document defines the requirements for the Cost Data Cache feature in SlashMyBill. The platform currently calls AWS Cost Explorer APIs in real-time when members view their dashboards, which causes slow load times for large accounts and can timeout entirely. This feature introduces a local DynamoDB-based cache layer that stores cost data per tenant with proper isolation, and uses incremental fetching to only retrieve date ranges not already cached. The solution prioritizes cost-effectiveness, security through tenant isolation, and efficient incremental data retrieval.

## Glossary

- **Cost_Cache_Table**: The DynamoDB table that stores cached cost data, partitioned by tenant and date range
- **Cache_Service**: The backend service responsible for reading from and writing to the Cost_Cache_Table
- **Incremental_Fetch_Engine**: The component that determines which date ranges are missing from the cache and fetches only those ranges from the Cost Explorer API
- **Tenant**: A member organization identified by a unique member_id; each tenant has one or more connected AWS accounts
- **Cost_Explorer_API**: The AWS Cost Explorer service used to retrieve cost and usage data from connected accounts
- **Cache_Metadata**: The record tracking which date ranges have been successfully cached for a given account, including the last_fetched_date
- **Date_Range_Gap**: A contiguous period of dates for which no cached cost data exists for a specific account
- **TTL_Expiry**: The DynamoDB Time-To-Live attribute used to automatically expire stale cache entries after a configurable retention period
- **Dashboard_Data_Endpoint**: The backend API endpoint (GET /members/dashboard-data) that returns cost data for dashboard widgets
- **Member**: An authenticated user of the SlashMyBill platform
- **Account_ID**: The AWS account identifier linked to a member's tenant
- **Granularity**: The time resolution of cost data (DAILY only — monthly summaries are computed by aggregating daily items at query time)
- **Cache_Hit**: A request where all required date ranges are found in the Cost_Cache_Table
- **Cache_Miss**: A request where one or more required date ranges are not found in the Cost_Cache_Table and must be fetched from the Cost_Explorer_API
- **Partition_Key**: The DynamoDB partition key composed of tenant identifier and account ID (format: `{member_id}#{account_id}`)
- **Sort_Key**: The DynamoDB sort key composed of the date (format: `DAILY#{date}`)

## Requirements

### Requirement 1: Cache Table Design

**User Story:** As a platform operator, I want cost data stored in a DynamoDB table with proper key design, so that data retrieval is efficient and cost-effective.

#### Acceptance Criteria

1. THE Cost_Cache_Table SHALL use a composite Partition_Key in the format `{member_id}#{account_id}` to ensure tenant-scoped data access
2. THE Cost_Cache_Table SHALL use a Sort_Key in the format `DAILY#{date}` to enable efficient range queries on date periods
3. THE Cost_Cache_Table SHALL store cost data items containing: Partition_Key, Sort_Key, cost_amount, currency, service_breakdown, and fetched_at timestamp
4. THE Cost_Cache_Table SHALL use DynamoDB On-Demand capacity mode to minimize costs for variable workloads
5. THE Cost_Cache_Table SHALL configure a TTL_Expiry attribute to automatically delete cache entries older than 90 days

### Requirement 2: Tenant Isolation

**User Story:** As a platform operator, I want strict tenant isolation in the cache, so that each business sees only its own cost data.

#### Acceptance Criteria

1. WHEN a member requests cost data, THE Cache_Service SHALL construct queries using only the authenticated member's member_id in the Partition_Key
2. WHEN a member requests cost data for an account, THE Cache_Service SHALL verify that the account belongs to the authenticated member before reading from or writing to the Cost_Cache_Table
3. THE Cache_Service SHALL reject any request where the account_id in the query does not match an account owned by the authenticated member
4. THE Cost_Cache_Table SHALL not use a Global Secondary Index that could expose data across tenant boundaries
5. WHEN writing cost data to the cache, THE Cache_Service SHALL include the member_id in the Partition_Key to prevent cross-tenant data leakage

### Requirement 3: Incremental Data Fetching

**User Story:** As a member, I want the system to only fetch cost data for dates not already cached, so that dashboard loading is fast and API costs are minimized.

#### Acceptance Criteria

1. WHEN a member requests cost data for a date range, THE Incremental_Fetch_Engine SHALL query the Cost_Cache_Table to identify which dates within the range already have cached data
2. WHEN cached data exists for the entire requested date range, THE Cache_Service SHALL return the cached data without calling the Cost_Explorer_API
3. WHEN one or more Date_Range_Gaps exist within the requested range, THE Incremental_Fetch_Engine SHALL fetch only the missing date ranges from the Cost_Explorer_API
4. WHEN new cost data is fetched from the Cost_Explorer_API, THE Cache_Service SHALL write the fetched data to the Cost_Cache_Table with the current timestamp as fetched_at
5. WHEN the requested date range includes today's date, THE Incremental_Fetch_Engine SHALL always re-fetch the current day's data from the Cost_Explorer_API to capture intra-day updates

### Requirement 4: Cache Read Path

**User Story:** As a member, I want my dashboard to load cost data from the local cache first, so that page load times are consistently fast.

#### Acceptance Criteria

1. WHEN a member opens the dashboard, THE Dashboard_Data_Endpoint SHALL first query the Cost_Cache_Table for the requested date range
2. WHEN a full Cache_Hit occurs, THE Dashboard_Data_Endpoint SHALL return cached data to the frontend within 500 milliseconds
3. WHEN a partial Cache_Miss occurs, THE Dashboard_Data_Endpoint SHALL return cached data immediately for available dates and fetch missing dates asynchronously
4. WHEN the Cost_Explorer_API call for missing dates fails, THE Dashboard_Data_Endpoint SHALL return the available cached data with a flag indicating incomplete results
5. THE Dashboard_Data_Endpoint SHALL include a cache_status field in the response indicating whether the data was served from cache, partially from cache, or freshly fetched

### Requirement 5: Cache Write Path

**User Story:** As a platform operator, I want cost data written to the cache reliably, so that subsequent requests benefit from cached data.

#### Acceptance Criteria

1. WHEN cost data is fetched from the Cost_Explorer_API, THE Cache_Service SHALL write each day's cost data as a separate item in the Cost_Cache_Table
2. WHEN writing cost data, THE Cache_Service SHALL use DynamoDB BatchWriteItem to minimize write operations and cost
3. IF a write to the Cost_Cache_Table fails, THEN THE Cache_Service SHALL log the error and return the fetched data to the member without blocking the response
4. WHEN writing cost data, THE Cache_Service SHALL set the TTL_Expiry attribute to 90 days from the write timestamp
5. WHEN cost data for a date already exists in the cache, THE Cache_Service SHALL overwrite the existing item with the freshly fetched data

### Requirement 6: Background Cache Refresh

**User Story:** As a platform operator, I want the cache to be refreshed in the background, so that members always see up-to-date data without waiting.

#### Acceptance Criteria

1. WHEN a member's cached data for the most recent 3 days is older than 6 hours, THE Cache_Service SHALL trigger a background refresh for those dates
2. WHEN a background refresh is triggered, THE Incremental_Fetch_Engine SHALL fetch updated data from the Cost_Explorer_API without blocking the member's current request
3. IF a background refresh fails, THEN THE Cache_Service SHALL log the failure and serve stale cached data until the next refresh attempt
4. THE Cache_Service SHALL not trigger more than one background refresh per account per hour to avoid excessive API calls

### Requirement 7: Cost Effectiveness

**User Story:** As a platform operator, I want the caching solution to reduce AWS Cost Explorer API calls, so that platform operating costs are minimized.

#### Acceptance Criteria

1. THE Cost_Cache_Table SHALL use DynamoDB On-Demand pricing to avoid paying for unused provisioned capacity
2. WHEN a full Cache_Hit occurs, THE Cache_Service SHALL make zero calls to the Cost_Explorer_API
3. THE Incremental_Fetch_Engine SHALL batch date range gaps into the minimum number of Cost_Explorer_API calls required
4. THE Cost_Cache_Table SHALL store only the essential cost fields (amount, currency, service breakdown) to minimize storage costs
5. WHEN multiple members share the same AWS account, THE Cache_Service SHALL not duplicate cached data across tenants (each tenant caches independently based on their access pattern)

### Requirement 8: Security and Access Control

**User Story:** As a platform operator, I want cache access to be properly secured, so that cost data confidentiality is maintained.

#### Acceptance Criteria

1. WHEN a request is made to the Dashboard_Data_Endpoint, THE Cache_Service SHALL validate the JWT authentication token before accessing the Cost_Cache_Table
2. THE Cache_Service SHALL use IAM policies that restrict DynamoDB access to only the Cost_Cache_Table
3. THE Cost_Cache_Table SHALL enable encryption at rest using AWS-managed keys
4. WHEN constructing DynamoDB queries, THE Cache_Service SHALL use parameterized key conditions to prevent injection attacks
5. THE Cache_Service SHALL log all cache read and write operations with the member_id for audit purposes

### Requirement 9: Error Handling and Resilience

**User Story:** As a member, I want the dashboard to work even when the cache is unavailable, so that I can always access my cost data.

#### Acceptance Criteria

1. IF the Cost_Cache_Table is unavailable, THEN THE Dashboard_Data_Endpoint SHALL fall back to calling the Cost_Explorer_API directly
2. IF the Cost_Explorer_API call times out during incremental fetch, THEN THE Cache_Service SHALL return whatever cached data is available with a partial_data indicator
3. IF both the Cost_Cache_Table and the Cost_Explorer_API are unavailable, THEN THE Dashboard_Data_Endpoint SHALL return a clear error message indicating temporary unavailability
4. WHEN a Cost_Explorer_API call fails for a specific account during cache population, THE Cache_Service SHALL continue processing remaining accounts and log the failure
5. THE Cache_Service SHALL implement exponential backoff with a maximum of 3 retries for transient DynamoDB errors

### Requirement 10: Cache Invalidation

**User Story:** As a member, I want to be able to force a cache refresh, so that I can see the latest cost data when needed.

#### Acceptance Criteria

1. WHEN a member triggers a manual refresh on the dashboard, THE Cache_Service SHALL invalidate cached data for the requested date range and fetch fresh data from the Cost_Explorer_API
2. WHEN a member connects a new AWS account, THE Cache_Service SHALL not have any pre-existing cached data for that account (clean state)
3. WHEN a member disconnects an AWS account, THE Cache_Service SHALL delete all cached data for that account from the Cost_Cache_Table
4. WHEN the TTL_Expiry is reached for a cache item, THE Cost_Cache_Table SHALL automatically delete that item without requiring application logic
