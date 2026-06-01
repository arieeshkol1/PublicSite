# Requirements Document

## Introduction

The "Cost By Service" widget adds a stacked bar/area chart to the Observer > Cost Analysis section that visualizes cost breakdown by AWS service over time (daily and hourly granularity). It sits alongside the existing "Cost Trend" line chart and reuses the existing `service_breakdown` data from the DynamoDB Cost_Cache_Table and the `costByService` field from the dashboard API. When a tag filter is active, the widget refreshes to show only the proportionally allocated service costs for the filtered tag.

## Glossary

- **Cost_By_Service_Widget**: The new stacked chart widget in the Observe > Cost Analysis section that displays per-service cost breakdown over time.
- **Dashboard_API**: The `GET /members/dashboard-data` endpoint in `member-handler/lambda_function.py` that returns cost data to the frontend.
- **Cost_Cache_Table**: The DynamoDB table storing daily cost data with `service_breakdown` per day per account.
- **Service_Breakdown**: A mapping of AWS service names to their individual cost amounts for a given day, stored in each cache record (e.g., `{"Amazon EC2": 55.29, "Amazon RDS": 1.28}`).
- **Tag_Filter**: The user-selected tag key/value pair that filters all cost widgets to show only costs attributed to resources with that tag.
- **Stacked_Chart**: An ECharts stacked bar or stacked area chart where each series represents one AWS service and the y-axis shows cumulative cost per time period.
- **Daily_Granularity**: Cost data aggregated per calendar day (YYYY-MM-DD).
- **Hourly_Granularity**: Cost data aggregated per hour, retrieved from the AWS Cost Explorer API (not cached).
- **Observer_Cost_Section**: The "Cost Analysis" sub-section within the Observe tab, identified by `observe-cost` in the widget section mapping.

## Requirements

### Requirement 1: Daily Service Breakdown Data in API Response

**User Story:** As a member, I want the dashboard API to return per-day service cost breakdown data, so that the frontend can render a stacked chart showing cost by service over time.

#### Acceptance Criteria

1. WHEN the Dashboard_API processes cached daily cost data, THE Dashboard_API SHALL include a `dailyServiceBreakdown` array in the response containing one object per day with the date and a mapping of service names to costs.
2. THE Dashboard_API SHALL structure each entry in `dailyServiceBreakdown` as `{"date": "YYYY-MM-DD", "services": {"ServiceName": cost_float, ...}}`.
3. THE Dashboard_API SHALL sort the `dailyServiceBreakdown` array in ascending date order.
4. WHEN multiple accounts are linked, THE Dashboard_API SHALL merge service costs across accounts for each date by summing costs per service per day.
5. IF a day's cache record has no `service_breakdown` field, THEN THE Dashboard_API SHALL omit that day from the `dailyServiceBreakdown` array.

### Requirement 2: Tag-Filtered Service Breakdown

**User Story:** As a member, I want the cost-by-service chart to update when I select a tag filter, so that I can see which services contribute to costs for a specific tag value.

#### Acceptance Criteria

1. WHEN a Tag_Filter is active, THE Dashboard_API SHALL compute proportional service costs by allocating each day's total tag cost across services based on the day's Service_Breakdown ratios.
2. WHEN a Tag_Filter is active, THE Dashboard_API SHALL include the filtered `dailyServiceBreakdown` in the response using the same structure as unfiltered data.
3. IF the Tag_Filter results in zero cost for all days, THEN THE Cost_By_Service_Widget SHALL display an empty-state message indicating no data is available for the selected tag.

### Requirement 3: Hourly Service Breakdown

**User Story:** As a member, I want to toggle the cost-by-service chart to hourly granularity, so that I can identify which services caused cost spikes within a day.

#### Acceptance Criteria

1. WHEN the user switches to hourly view, THE Dashboard_API SHALL call the AWS Cost Explorer API with `HOURLY` granularity and `GROUP_BY SERVICE` for the most recent 3 days.
2. THE Dashboard_API SHALL return an `hourlyServiceBreakdown` array with entries structured as `{"hour": "YYYY-MM-DDTHH:00", "services": {"ServiceName": cost_float, ...}}`.
3. IF hourly granularity is not enabled on the AWS account, THEN THE Cost_By_Service_Widget SHALL display a message directing the user to enable hourly granularity in AWS Cost Explorer settings.
4. WHEN a Tag_Filter is active and hourly view is selected, THE Dashboard_API SHALL apply the tag filter to the hourly Cost Explorer query.

### Requirement 4: Widget Registration and Layout

**User Story:** As a member, I want the Cost By Service chart to appear in the Cost Analysis section next to the existing Cost Trend chart, so that I can compare total cost trends with per-service breakdowns side by side.

#### Acceptance Criteria

1. THE Cost_By_Service_Widget SHALL be registered in the `OBSERVE_WIDGET_SECTIONS` mapping under the `observe-cost` section with widget ID `dash-cost-by-service`.
2. THE Cost_By_Service_Widget SHALL render within the existing `observe-widget-grid` CSS grid layout at a minimum width of 380px.
3. THE Cost_By_Service_Widget SHALL include a widget header with the title "Cost By Service" and a toggle control for switching between daily and hourly granularity.
4. WHEN the Observe tab is activated and the Cost Analysis section is visible, THE Cost_By_Service_Widget SHALL render using the data already fetched by the dashboard API call.

### Requirement 5: Stacked Chart Rendering

**User Story:** As a member, I want to see a stacked visualization of cost per service per day, so that I can quickly identify which services drive my spending over time.

#### Acceptance Criteria

1. THE Cost_By_Service_Widget SHALL render a stacked bar chart using ECharts where each series represents one AWS service.
2. THE Cost_By_Service_Widget SHALL display the top 8 services by total cost and group remaining services into an "Other" category.
3. THE Cost_By_Service_Widget SHALL assign a distinct color to each service series, reusing the existing `_treemapColors` palette.
4. WHEN the user hovers over a bar segment, THE Cost_By_Service_Widget SHALL display a tooltip showing the service name, cost amount (formatted as USD with 2 decimal places), and percentage of that day's total.
5. THE Cost_By_Service_Widget SHALL include a legend below the chart showing service names with their assigned colors.
6. WHEN the browser window is resized, THE Cost_By_Service_Widget SHALL resize the ECharts instance to fit the new container dimensions.

### Requirement 6: Granularity Toggle Behavior

**User Story:** As a member, I want to switch between daily and hourly views within the Cost By Service widget, so that I can drill into finer-grained cost patterns.

#### Acceptance Criteria

1. THE Cost_By_Service_Widget SHALL default to Daily_Granularity on initial render.
2. WHEN the user clicks the hourly toggle, THE Cost_By_Service_Widget SHALL replace the chart data with hourly service breakdown data.
3. WHEN the user clicks the daily toggle, THE Cost_By_Service_Widget SHALL restore the chart to daily service breakdown data without re-fetching from the API.
4. WHILE hourly data is being fetched, THE Cost_By_Service_Widget SHALL display a loading indicator within the chart area.
5. THE Cost_By_Service_Widget SHALL persist the selected granularity for the duration of the browser session.

### Requirement 7: Cache-First Data Loading

**User Story:** As a member, I want the widget to load instantly from cached data, so that I do not experience delays when viewing cost breakdowns.

#### Acceptance Criteria

1. THE Dashboard_API SHALL build the `dailyServiceBreakdown` response field from the Cost_Cache_Table records without calling the AWS Cost Explorer API.
2. WHEN cache records are available, THE Dashboard_API SHALL return `dailyServiceBreakdown` within the same response time as other cached fields (no additional API latency).
3. IF no cache records exist for the requested period, THEN THE Dashboard_API SHALL return an empty `dailyServiceBreakdown` array and THE Cost_By_Service_Widget SHALL display an empty-state message.

### Requirement 8: Widget Refresh on Tag Filter Change

**User Story:** As a member, I want the Cost By Service widget to automatically refresh when I change the tag filter, so that the chart always reflects my current filter selection.

#### Acceptance Criteria

1. WHEN the Tag_Filter selection changes, THE Cost_By_Service_Widget SHALL re-render with the updated `dailyServiceBreakdown` data from the refreshed API response.
2. WHILE the filtered data is loading, THE Cost_By_Service_Widget SHALL display a loading indicator.
3. WHEN the Tag_Filter is cleared, THE Cost_By_Service_Widget SHALL revert to showing unfiltered service breakdown data.
