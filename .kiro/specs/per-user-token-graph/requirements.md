# Requirements Document — Per-User Token Graph

## Introduction

Adds a per-user daily token consumption multi-line SVG chart to the existing AI Cost Usage Dashboard. The chart visualizes daily total tokens (input + output) per user as separate polylines, with an interactive checkbox filter for showing/hiding individual users. All data is sourced from the existing `token_usage` array in the `openai-usage` API response — no new backend endpoints are required.

## Glossary

- **Per_User_Chart**: The frontend widget component that renders the per-user daily token consumption multi-line SVG chart and checkbox filter within the AI Cost dashboard.
- **Dashboard**: The AI Cost Usage Dashboard rendered by `_renderOpenAIDashboardSections()` in `members/members.js`.
- **Token_Usage_Array**: The `token_usage` field in the openai-usage API response, containing records with `date`, `user_id`, `model`, `input_tokens`, and `output_tokens` fields.
- **Color_Palette**: A fixed array of 8 hex color values used to distinguish users in the chart, cycling for more than 8 users.
- **Visible_Users**: The set of user IDs currently selected via checkboxes whose polylines are rendered in the chart SVG.

## Requirements

### Requirement 1: Per-User Token Chart Widget Rendering

**User Story:** As a dashboard user, I want to see a per-user daily token consumption chart, so that I can understand which users consume the most tokens over time.

#### Acceptance Criteria

1. WHEN the AI Cost dashboard is rendered, THE Dashboard SHALL display a "Per-User Token Consumption" widget section after the "Token Usage Over Time" section.
2. THE Per_User_Chart SHALL render one SVG polyline per visible user showing daily total tokens (input_tokens + output_tokens) aggregated across all models.
3. THE Per_User_Chart widget SHALL use the `.openai-widget` card CSS class consistent with existing dashboard widget sections.
4. THE Per_User_Chart SHALL display a color-coded legend mapping each user to their assigned line color.

### Requirement 2: User Extraction and Filtering

**User Story:** As a dashboard user, I want invalid or unknown user IDs excluded from the chart, so that the visualization only shows meaningful per-user data.

#### Acceptance Criteria

1. WHEN token_usage data contains records with valid user_ids, THE Per_User_Chart SHALL extract unique user_ids excluding those that are "unknown" or empty.
2. WHEN all user_ids in token_usage are "unknown" or empty, THE Per_User_Chart SHALL display an empty state message "No per-user data available".
3. THE Per_User_Chart SHALL sort extracted user IDs alphabetically for consistent display order.

### Requirement 3: Interactive Checkbox Filter

**User Story:** As a dashboard user, I want to show or hide individual users in the chart via checkboxes, so that I can focus on specific users without losing context of the overall data.

#### Acceptance Criteria

1. THE Per_User_Chart SHALL display a checkbox filter area with one checkbox per discovered user, labeled with the user ID and colored with the user's assigned chart color.
2. THE Per_User_Chart SHALL include "Select All" and "Deselect All" buttons in the filter area.
3. WHEN a user checkbox is toggled, THE Per_User_Chart SHALL re-render only the SVG chart area without re-rendering the full dashboard.
4. WHEN "Select All" is clicked, THE Per_User_Chart SHALL check all user checkboxes and re-render the chart with all users visible.
5. WHEN "Deselect All" is clicked, THE Per_User_Chart SHALL uncheck all user checkboxes and display an empty chart state.

### Requirement 4: Data Grouping and Aggregation

**User Story:** As a dashboard user, I want token data correctly aggregated by date and user, so that the chart accurately reflects daily consumption per user.

#### Acceptance Criteria

1. THE Per_User_Chart SHALL source all data from the existing token_usage array in the openai-usage API response without requiring a new API endpoint.
2. FOR any set of visible users and token_usage data, the sum of all grouped series values SHALL equal the sum of (input_tokens + output_tokens) for records whose user_id is in the visible set.
3. WHEN a user has no data on a particular date, THE Per_User_Chart SHALL plot zero for that user on that date.
4. THE Per_User_Chart SHALL sort dates in ascending chronological order on the X-axis.

### Requirement 5: Color Assignment

**User Story:** As a dashboard user, I want each user to have a distinct, consistent color, so that I can easily identify individual users across chart updates.

#### Acceptance Criteria

1. THE Per_User_Chart SHALL assign each user a distinct color from a fixed 8-color palette, cycling for more than 8 users.
2. WHEN _assignUserColors is called with the same user array, THE Per_User_Chart SHALL produce identical color mappings (deterministic assignment by array position).

### Requirement 6: Styling and Layout

**User Story:** As a dashboard user, I want the per-user chart to match the existing dashboard styling, so that the UI feels cohesive and professional.

#### Acceptance Criteria

1. THE Per_User_Chart SHALL be placed in the dashboard after the existing "Token Usage Over Time" section.
2. THE Per_User_Chart filter area SHALL be styled with appropriate spacing, flexbox layout, and consistent font sizes matching the existing dashboard aesthetic.
3. THE Per_User_Chart checkbox labels SHALL display the user's assigned color as a visual indicator beside the user ID text.
