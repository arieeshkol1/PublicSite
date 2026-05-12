# Requirements Document

## Introduction

This document defines the requirements for the Tag-Based Cost Filtering feature in SlashMyBill. The feature enables users to filter all cost data on the Observe (dashboard) and Chat (AI query) tabs by a specific AWS cost allocation tag. Users select a Tag Key and Tag Value through cascading dropdowns, and all dashboard widgets (except Tag Distribution) refresh with filtered data. The filter state persists across tab switches and applies to AI chat queries.

## Glossary

- **Tag_Filter_Component**: The frontend UI element consisting of two cascading dropdowns (Tag Key and Tag Value) that allows users to select a cost allocation tag filter
- **Tag_Key_Endpoint**: The backend API endpoint (GET /members/tag-keys) that returns available cost allocation tag keys for connected accounts
- **Tag_Value_Endpoint**: The backend API endpoint (GET /members/tag-values) that returns available values for a specific tag key
- **Dashboard_Data_Endpoint**: The backend API endpoint (GET /members/dashboard-data) that returns cost data for dashboard widgets
- **AI_Query_Endpoint**: The backend API endpoint (POST /members/accounts/ai-query) that processes AI-powered cost questions
- **Tag_Distribution_Widget**: The dashboard widget that displays cost breakdown by tag, which remains unfiltered regardless of tag filter state
- **Global_Tag_Filter**: The client-side state object holding the currently selected tag key and tag value
- **Cost_Explorer_API**: The AWS Cost Explorer service used to retrieve cost data and tag metadata
- **Tag_Keys_Cache**: Client-side cache storing fetched tag keys with a 5-minute TTL
- **Tag_Values_Cache**: Client-side cache storing fetched tag values per key with a 5-minute TTL
- **CE_Filter**: A Cost Explorer filter expression in the format `{"Tags": {"Key": "<key>", "Values": ["<value>"]}}`
- **Member**: An authenticated user of the SlashMyBill platform

## Requirements

### Requirement 1: Tag Key Retrieval

**User Story:** As a member, I want to see all available cost allocation tag keys from my connected accounts, so that I can choose which tag dimension to filter by.

#### Acceptance Criteria

1. WHEN a member opens the Observe tab, THE Tag_Filter_Component SHALL load available tag keys from the Tag_Key_Endpoint
2. WHEN the Tag_Key_Endpoint receives a valid request, THE Tag_Key_Endpoint SHALL return a sorted, deduplicated list of tag keys from all specified connected accounts
3. WHEN the Tag_Key_Endpoint receives a request with account IDs not owned by the authenticated member, THE Tag_Key_Endpoint SHALL exclude those accounts from the tag key retrieval
4. IF the Tag_Key_Endpoint fails to assume a role into a specific account, THEN THE Tag_Key_Endpoint SHALL skip that account and continue processing remaining accounts
5. WHEN no cost allocation tags are activated in any connected account, THE Tag_Filter_Component SHALL display only the "All (no filter)" option and show an informational message

### Requirement 2: Tag Value Retrieval

**User Story:** As a member, I want to see available values for a selected tag key, so that I can filter costs to a specific tag value.

#### Acceptance Criteria

1. WHEN a member selects a tag key, THE Tag_Filter_Component SHALL fetch and display available values for that key from the Tag_Value_Endpoint
2. WHEN the Tag_Value_Endpoint receives a valid request with a tagKey parameter, THE Tag_Value_Endpoint SHALL return a sorted, deduplicated list of values for that key across all specified accounts
3. WHEN the Tag_Value_Endpoint receives a request without a tagKey parameter, THE Tag_Value_Endpoint SHALL return a 400 error with message "tagKey parameter is required"
4. IF the selected tag key has no values in the current time period, THEN THE Tag_Filter_Component SHALL display a "No values found" disabled option in the value dropdown

### Requirement 3: Tag Filter State Management

**User Story:** As a member, I want the tag filter to maintain consistent state, so that my filter selection behaves predictably.

#### Acceptance Criteria

1. THE Global_Tag_Filter SHALL enforce that when the tag key is null, the tag value is also null
2. WHEN a member selects a tag key without selecting a tag value, THE Tag_Filter_Component SHALL disable filtering until a value is also selected
3. WHEN a member clears the tag key selection (selects "All"), THE Tag_Filter_Component SHALL reset both key and value to null and disable the value dropdown
4. WHEN a member switches between the Observe tab and the Chat tab, THE Global_Tag_Filter SHALL retain the selected tag key and tag value

### Requirement 4: Dashboard Data Filtering

**User Story:** As a member, I want my dashboard to show cost data filtered by my selected tag, so that I can analyze spending for a specific tag dimension.

#### Acceptance Criteria

1. WHEN a tag filter is active, THE Dashboard_Data_Endpoint SHALL apply a CE_Filter with the selected tag key and value to all Cost Explorer queries
2. WHEN a tag filter is active and an existing filter is already present on a Cost Explorer query, THE Dashboard_Data_Endpoint SHALL combine both filters using an "And" expression
3. WHEN no tag filter is active, THE Dashboard_Data_Endpoint SHALL make Cost Explorer queries without any tag-based filter (identical to pre-feature behavior)
4. WHEN a tag filter is active, THE Tag_Distribution_Widget SHALL display unfiltered cost-by-tag data regardless of the Global_Tag_Filter state
5. WHEN the tag filter selection changes, THE Tag_Filter_Component SHALL invalidate the dashboard data cache and trigger a data reload

### Requirement 5: AI Query Filtering

**User Story:** As a member, I want my AI chat queries to respect the active tag filter, so that AI answers are scoped to the filtered cost data.

#### Acceptance Criteria

1. WHEN a tag filter is active and a member submits an AI query, THE AI_Query_Endpoint SHALL apply the tag filter to all cost data retrieval for that query
2. WHEN no tag filter is active and a member submits an AI query, THE AI_Query_Endpoint SHALL retrieve cost data without any tag-based filter
3. WHEN a tag filter is active, THE AI_Query_Endpoint SHALL include the tag filter context in the AI-generated response

### Requirement 6: Client-Side Caching

**User Story:** As a member, I want tag metadata to be cached, so that the filter responds quickly without unnecessary API calls.

#### Acceptance Criteria

1. THE Tag_Keys_Cache SHALL store fetched tag keys with a time-to-live of 5 minutes
2. THE Tag_Values_Cache SHALL store fetched tag values per key with a time-to-live of 5 minutes
3. WHEN cached tag keys exist and the cache has not expired, THE Tag_Filter_Component SHALL use cached data instead of calling the Tag_Key_Endpoint
4. WHEN cached tag values exist for the selected key and the cache has not expired, THE Tag_Filter_Component SHALL use cached data instead of calling the Tag_Value_Endpoint
5. WHEN the account selection changes, THE Tag_Filter_Component SHALL invalidate both the Tag_Keys_Cache and the Tag_Values_Cache

### Requirement 7: CE Filter Construction

**User Story:** As a developer, I want tag filters to be correctly constructed for the Cost Explorer API, so that filtered queries return accurate results.

#### Acceptance Criteria

1. WHEN both a tag key and tag value are provided, THE Dashboard_Data_Endpoint SHALL construct a CE_Filter in the format `{"Tags": {"Key": "<key>", "Values": ["<value>"]}}`
2. WHEN either the tag key or tag value is empty or null, THE Dashboard_Data_Endpoint SHALL not add any tag-based filter to the Cost Explorer query
3. WHEN a tag filter is combined with an existing filter, THE Dashboard_Data_Endpoint SHALL produce a valid "And" expression containing both filters
4. THE Dashboard_Data_Endpoint SHALL not mutate the original query parameters when applying a tag filter

### Requirement 8: Security and Access Control

**User Story:** As a platform operator, I want tag data access to be properly secured, so that members can only see tags from their own accounts.

#### Acceptance Criteria

1. WHEN a request is made to the Tag_Key_Endpoint or Tag_Value_Endpoint, THE endpoint SHALL validate the JWT authentication token before processing
2. WHEN a request is made to the Tag_Key_Endpoint or Tag_Value_Endpoint, THE endpoint SHALL verify that the authenticated member owns the specified account IDs
3. THE Tag_Key_Endpoint SHALL only return tag keys from accounts owned by the authenticated member
4. THE Tag_Value_Endpoint SHALL only return tag values from accounts owned by the authenticated member
5. THE Tag_Key_Endpoint and Tag_Value_Endpoint SHALL pass tag key and tag value as structured parameters to the Cost Explorer API without string interpolation

### Requirement 9: Error Handling and Resilience

**User Story:** As a member, I want the tag filter to handle errors gracefully, so that failures in tag retrieval do not break my dashboard experience.

#### Acceptance Criteria

1. IF the tag key fetch exceeds 10 seconds, THEN THE Tag_Filter_Component SHALL fall back to displaying only the "All (no filter)" option
2. IF a role assumption fails for one account during tag retrieval, THEN THE Tag_Key_Endpoint SHALL continue processing remaining accounts and return partial results
3. IF a role assumption fails for one account during tag value retrieval, THEN THE Tag_Value_Endpoint SHALL continue processing remaining accounts and return partial results
4. WHEN a filtered query returns empty data, THE Tag_Filter_Component SHALL display a zero-state for all affected widgets
