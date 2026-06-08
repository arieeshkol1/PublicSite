# Requirements Document

## Introduction

The Widget Builder Dashboard is a self-service analytics tool that allows authenticated members to create custom visualizations from their existing cost and usage data. Users select from a palette of widget types, bind each widget to data sources, configure filters/dimensions/aggregations, and arrange widgets on a drag-and-drop 12-column grid. Layouts are persisted per user in DynamoDB and loaded on login.

## Glossary

- **Dashboard**: A configurable page containing one or more widgets arranged on a 12-column grid
- **Widget**: A single visualization unit (chart, table, or KPI card) bound to a data source with configured filters and aggregations
- **Widget_Config**: The JSON schema defining a widget's type, data source, filters, dimensions, aggregation, and display options
- **Query_Engine**: The backend component that accepts a Widget_Config, resolves the data source, applies the filter/dimension/aggregation pipeline, and returns chart-ready data
- **Layout_Store**: The backend component responsible for CRUD operations on dashboard layouts in DynamoDB
- **Widget_Builder_UI**: The frontend drag-and-drop interface for creating, configuring, and arranging widgets
- **Data_Source**: One of the available data backends: Cost_Cache_Table, invoices, OpenAI usage, commitments, or business metrics
- **Grid_Position**: An object specifying a widget's placement on the 12-column grid (x, y, w, h)
- **Layout**: A named collection of widgets with their grid positions, persisted per user
- **Member**: An authenticated user of the platform with a valid Cognito JWT
- **DashboardLayouts_Table**: The DynamoDB table storing dashboard layouts (pk=member_email, sk=LAYOUT#{layout_id})

## Requirements

### Requirement 1: Widget Type Selection

**User Story:** As a member, I want to select from a palette of widget types, so that I can choose the best visualization for my data.

#### Acceptance Criteria

1. WHEN a member opens the widget builder THEN the Widget_Builder_UI SHALL display a palette offering bar chart, line chart, pie chart, table, KPI card, and gauge widget types
2. WHEN a member selects a widget type from the palette THEN the Widget_Builder_UI SHALL create a new widget instance of that type, add it to the grid, and display the widget in an empty state indicating that no data source has been configured
3. THE Widget_Builder_UI SHALL restrict widget type selection to exactly the six supported types (bar, line, pie, table, kpi, gauge)
4. IF a member selects a widget type and the grid already contains 20 widgets, THEN the Widget_Builder_UI SHALL not create the widget and SHALL display an error message indicating the maximum widget limit has been reached

### Requirement 2: Data Source Binding

**User Story:** As a member, I want to bind widgets to specific data sources, so that I can visualize different categories of cost and usage data.

#### Acceptance Criteria

1. WHEN a member opens the widget configuration panel THEN the Widget_Builder_UI SHALL display a data source picker showing available sources: cost_cache, invoices, openai_usage, commitments, and business_metrics
2. WHEN a member selects a data source THEN the Widget_Builder_UI SHALL present an account selector listing only accounts owned by the authenticated member, allowing selection of one or more accounts
3. IF a member selects a data source for which they have zero linked accounts THEN the Widget_Builder_UI SHALL display a message indicating no accounts are available for the selected source and disable query execution
4. WHEN a member configures a date range THEN the Widget_Builder_UI SHALL support both relative ranges (7d, 30d, 90d, 12m) and absolute date ranges (start/end dates), with a default selection of 30d
5. IF a submitted date range has a start date equal to or after the end date THEN the Query_Engine SHALL reject the query and return a 400 response with an error message indicating the invalid date range
6. IF a submitted date range span exceeds 365 days THEN the Query_Engine SHALL reject the query and return a 400 response with an error message indicating the maximum range has been exceeded

### Requirement 3: Query Execution

**User Story:** As a member, I want my widgets to fetch and display aggregated data, so that I can gain insights from my cost and usage information.

#### Acceptance Criteria

1. WHEN a valid Widget_Config is submitted to the query endpoint THEN the Query_Engine SHALL return a response containing labels (a list of strings representing dimension values or time periods) and datasets (a list of objects each containing a label string and a data array of numeric values corresponding positionally to the labels list)
2. WHEN the Query_Engine processes a query THEN the Query_Engine SHALL apply all configured filters such that only items satisfying every filter condition are included in the result
3. WHEN dimensions are specified THEN the Query_Engine SHALL group data by the specified dimensions (maximum 3 dimensions per query) before applying aggregation
4. WHEN an aggregation type is specified THEN the Query_Engine SHALL compute the mathematical result (sum, avg, max, min, or count) for each group, where avg returns 0 for groups containing no numeric values
5. WHEN the sum aggregation is applied across dimension groups THEN the sum of aggregated group values SHALL equal the aggregation applied to the unpartitioned data set
6. IF a data source fails to respond within the query timeout or returns a connection error THEN the Query_Engine SHALL return a response with an empty labels list, an empty datasets list, and an error description string in the metadata field
7. WHEN a valid query matches zero data items THEN the Query_Engine SHALL return a response with an empty labels list and datasets containing data arrays of zeroes

### Requirement 4: Filter Pipeline

**User Story:** As a member, I want to apply filters to my widget data, so that I can focus on specific services, accounts, or cost thresholds.

#### Acceptance Criteria

1. THE Query_Engine SHALL support filter operators: eq (equals), neq (not equals), gt (greater than), lt (less than), and contains (case-insensitive substring match)
2. WHEN filters are applied to a data set THEN the Query_Engine SHALL return only those data items where every filter condition evaluates to true, such that no item in the result set fails any active filter
3. WHEN a filter references a field not present in a data item THEN the Query_Engine SHALL exclude that item from the result
4. WHEN multiple filters are configured THEN the Query_Engine SHALL apply all filters conjunctively (AND logic) and support a maximum of 20 filters per query
5. IF a gt, lt, or eq filter is applied to a field whose value is not comparable to the filter value (e.g., gt applied to a non-numeric string) THEN the Query_Engine SHALL exclude that item from the result

### Requirement 5: Widget Configuration Validation

**User Story:** As a member, I want immediate feedback on invalid widget configurations, so that I can correct errors before querying data.

#### Acceptance Criteria

1. WHEN a Widget_Config is submitted THEN the Query_Engine SHALL validate it against the defined schema before executing any query
2. IF the Widget_Config is missing required fields (type, dataSource, aggregation) THEN the Query_Engine SHALL return a 400 response with an error message identifying the first missing field by name
3. IF the Widget_Config contains a widget type not in the supported set (bar, line, pie, table, kpi, gauge) THEN the Query_Engine SHALL return a 400 response with an error message indicating the invalid type value provided
4. IF the Widget_Config contains an aggregation type not in the supported set (sum, avg, max, min, count) THEN the Query_Engine SHALL return a 400 response with an error message indicating the invalid aggregation value provided
5. IF the Widget_Config dataSource field is missing required sub-fields (source, accountIds, dateRange) THEN the Query_Engine SHALL return a 400 response with an error message identifying the missing sub-field by name
6. IF the Widget_Config is null, not an object, or cannot be parsed THEN the Query_Engine SHALL return a 400 response with an error message indicating that a valid configuration object is required
7. THE Query_Engine SHALL perform validation without side effects or mutations to the input configuration

### Requirement 6: Grid Layout Management

**User Story:** As a member, I want to arrange widgets on a drag-and-drop grid, so that I can organize my dashboard to suit my workflow.

#### Acceptance Criteria

1. THE Widget_Builder_UI SHALL use a fixed 12-column grid with a maximum height of 48 rows for widget placement
2. WHEN a member drags a widget to a new position, THE Widget_Builder_UI SHALL update the widget's Grid_Position (x, y, w, h) to the column and row coordinates where the widget was dropped
3. IF a member attempts to place a widget in a position where it would overlap an existing widget, THEN THE Layout_Store SHALL reject the placement, preserve the widget's previous Grid_Position, and display an error indication to the member
4. IF a member attempts to place a widget whose Grid_Position would extend beyond column 12 or beyond row 48, THEN THE Layout_Store SHALL reject the placement, preserve the widget's previous Grid_Position, and display an error indication to the member
5. WHEN validating grid positions, THE Layout_Store SHALL verify that x and y are non-negative integers, and w and h are integers of at least 1, and that x + w does not exceed 12 and y + h does not exceed 48
6. THE Layout_Store SHALL enforce a maximum of 20 widgets per layout

### Requirement 7: Layout Persistence

**User Story:** As a member, I want my dashboard layouts to be saved and loaded automatically, so that I can return to my customized view on each login.

#### Acceptance Criteria

1. WHEN a member saves a layout, THE Layout_Store SHALL persist the layout to the DashboardLayouts_Table with the member's email as the partition key and a unique layout identifier as the sort key
2. WHEN a member loads their layouts, THE Layout_Store SHALL return only layouts belonging to that member, ordered by updated_at descending
3. WHEN a layout is saved, THE Layout_Store SHALL include an updated_at timestamp reflecting the current UTC time in ISO 8601 format
4. WHEN a member retrieves a previously saved layout, THE Layout_Store SHALL return all persisted widget configurations (widget type, data source, display settings) and grid positions (column, row, width, height) matching the original saved values
5. THE Layout_Store SHALL enforce a maximum of 20 widgets per layout
6. THE Layout_Store SHALL enforce a maximum of 10 layouts per member
7. IF a member attempts to save an 11th layout, THEN THE Layout_Store SHALL return a 409 conflict response indicating the layout limit has been reached
8. IF a member attempts to save a layout containing more than 20 widgets, THEN THE Layout_Store SHALL return a 400 response indicating the widget limit has been exceeded
9. THE Layout_Store SHALL enforce that each layout name is between 1 and 64 characters in length
10. IF a member saves a layout with a name that already exists for that member, THEN THE Layout_Store SHALL overwrite the existing layout entry and update the updated_at timestamp

### Requirement 8: Authentication and Authorization

**User Story:** As a member, I want my dashboard to be secured behind authentication, so that only I can access and modify my visualizations.

#### Acceptance Criteria

1. THE Dashboard_Handler SHALL validate the Cognito JWT token on every API request by verifying the token signature, confirming the token has not expired, and confirming the issuer matches the configured Cognito User Pool before processing the request
2. IF a request contains no JWT token, or a JWT token with an invalid signature, or an expired JWT token, THEN the Dashboard_Handler SHALL return a 401 unauthorized response and SHALL NOT process the request further
3. WHEN a widget query references account IDs, THEN the Query_Engine SHALL verify that every referenced account ID exists in the Accounts_Table with a memberEmail matching the authenticated member's identity
4. IF a query references one or more account IDs not owned by the authenticated member, THEN the Query_Engine SHALL reject the entire query and return a 403 forbidden response without returning any partial results
5. THE Query_Engine SHALL filter all query results server-side to include only data from accounts whose memberEmail in the Accounts_Table matches the authenticated member, ensuring that query results never contain data from accounts not owned by the requesting member
6. IF the Dashboard_Handler cannot validate the JWT token due to the Cognito service being unavailable or a validation timeout exceeding 5 seconds, THEN the Dashboard_Handler SHALL return a 503 service unavailable response and SHALL NOT process the request

### Requirement 9: Data Isolation

**User Story:** As a member, I want assurance that my data is isolated from other users, so that sensitive cost information remains private.

#### Acceptance Criteria

1. THE Layout_Store SHALL include the authenticated member's email as the DynamoDB partition key in every layout operation (create, read, update, delete), ensuring no operation can target a record under a different member's partition
2. THE Query_Engine SHALL include the authenticated member's email as the partition key condition in every DynamoDB query, ensuring query results never contain records belonging to a different member
3. WHEN a member lists layouts THEN the Layout_Store SHALL return only layouts whose partition key matches the authenticated member's email, resulting in zero layouts belonging to other members
4. IF a layout operation targets a layout_id that exists under a different member's partition key THEN the Layout_Store SHALL return a 404 response, not revealing whether the layout exists for another member
5. WHEN the Query_Engine resolves data for a widget THEN the Query_Engine SHALL filter account references to only those accounts owned by the authenticated member before executing the data source query

### Requirement 10: Cross-Provider Support

**User Story:** As a member, I want to visualize costs across multiple cloud providers (AWS, Azure, GCP, OpenAI), so that I can compare and analyze spending in a unified view.

#### Acceptance Criteria

1. IF the data source is openai_usage, THEN the Query_Engine SHALL fetch usage data from the OpenAI provider API and return a response within 30 seconds or return a timeout error
2. IF the data source is cost_cache, THEN the Query_Engine SHALL query the Cost_Cache_Table filtering entries by the requested provider (AWS, Azure, or GCP) using the cloud_provider field
3. THE Query_Engine SHALL normalize data from all providers into a common schema containing at minimum: date, service_name, cost_amount, currency, cloud_provider, and account_id before applying filters and aggregations
4. IF a provider data source is unreachable or returns an error during a cross-provider query, THEN the Query_Engine SHALL return available data from the remaining providers and include an error indicator identifying which provider failed

### Requirement 11: Error Handling and Resilience

**User Story:** As a member, I want graceful error handling, so that my dashboard remains usable even when some data is unavailable.

#### Acceptance Criteria

1. IF the JWT token expires during an active session THEN the Dashboard_Handler SHALL return a 401 response with a body indicating the token has expired, enabling the frontend to distinguish expiry from other authentication failures
2. WHEN a 401 response is received THEN the Widget_Builder_UI SHALL preserve the current widget configuration and any unsaved filter selections in localStorage and display a re-authentication prompt that allows the member to log in without navigating away from the dashboard
3. IF a provider API call fails or does not respond within 30 seconds THEN the Query_Engine SHALL return a partial response containing the data from all successful providers, with the metadata object including a list of failed providers and corresponding error descriptions, rather than failing the entire request
4. WHEN a widget has no data for the requested period THEN the Widget_Builder_UI SHALL display a "No data available" state with a retry button that re-fetches data from the Query_Engine for that widget only
5. IF the Widget_Builder_UI loses network connectivity THEN the Widget_Builder_UI SHALL display an offline indicator on affected widgets and automatically retry data fetches at 15-second intervals for up to 3 attempts before showing a manual retry option
6. WHEN a partial response is received containing at least one failed provider THEN the Widget_Builder_UI SHALL render all available data from successful providers and display an inline warning on each widget affected by the failed provider indicating which data source is unavailable

### Requirement 12: Performance

**User Story:** As a member, I want my dashboard to load quickly, so that I can access insights without delay.

#### Acceptance Criteria

1. WHEN querying cached data for a single widget with up to 365 data points, THE Query_Engine SHALL return results within 500 milliseconds measured from request receipt to response dispatch
2. WHEN querying live provider APIs for a single widget, THE Query_Engine SHALL return results within 2000 milliseconds measured from request receipt to response dispatch
3. IF a live provider API query exceeds 2000 milliseconds, THEN THE Query_Engine SHALL abort the provider call and return a timeout error indicator in the response metadata
4. WHEN a layout contains multiple widgets, THE Widget_Builder_UI SHALL fetch widget data for up to 12 widgets in parallel
5. THE Query_Engine SHALL use DynamoDB query operations (not scan) with partition key and sort key range conditions for data retrieval
