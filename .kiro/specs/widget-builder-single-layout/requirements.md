# Requirements Document

## Introduction

This is an amendment to the existing **Widget Builder Dashboard** feature (`.kiro/specs/widget-builder-dashboard/`). It simplifies the Widget Builder ("Custom Widget Builder" under SlashMyBill > Widget Builder) from a multi-named-layout model to a **single-layout-per-member** model.

Per the annotated header screenshot, two header controls are removed from `dashboard/index.html`:

1. The `-- Select Layout --` dropdown (`#layout-selector`), populated by `loadLayouts()` and driving `onLayoutSelected()` in `dashboard/dashboard.js`.
2. The `+ New Layout` button (`#new-layout-btn`), driving `newLayout()`.

The `💾 Save` button (`#save-layout-btn`, `saveLayout()`) is kept. On load, the member's single saved layout loads automatically into the grid. Save persists the current grid to localStorage and `PUT /dashboard/layouts`, always targeting the member's single current layout rather than creating new named layouts. All dead JavaScript referencing the removed elements is cleaned up.

This change is **frontend-only**. The backend `/dashboard/layouts` GET/PUT/DELETE endpoints and the `DashboardLayouts_Table` are not removed or modified. All other Widget Builder Dashboard requirements (widget types, query engine, data sources, filters/dimensions/aggregations, grid, authentication, data isolation) remain in force and must not regress.

## Glossary

Terms are reused from the parent spec (`widget-builder-dashboard/requirements.md`) and apply unchanged here.

- **Widget_Builder_UI**: The frontend interface for creating, configuring, and arranging widgets, including `dashboard/index.html`, `dashboard/dashboard.js`, and `dashboard/grid-manager.js`
- **Query_Engine**: The backend component that accepts a Widget_Config, resolves the data source, applies the filter/dimension/aggregation pipeline, and returns chart-ready data
- **Dashboard_Handler**: The backend Lambda that validates auth and routes `/dashboard/*` requests
- **Layout_Store**: The backend component responsible for CRUD operations on dashboard layouts in DynamoDB
- **DashboardLayouts_Table**: The DynamoDB table storing dashboard layouts (pk=member_email, sk=LAYOUT#{layout_id})
- **Member**: An authenticated user of the platform with a valid Cognito JWT
- **Current_Layout**: The single dashboard layout associated with a member under the single-layout model
- **Default_Layout_Name**: The fixed layout name applied when persisting the Current_Layout in the absence of a user-supplied name (value: "My Dashboard")
- **Layout_Selector**: The removed `-- Select Layout --` dropdown control (`#layout-selector`)
- **New_Layout_Button**: The removed `+ New Layout` button control (`#new-layout-btn`)
- **Save_Button**: The retained `💾 Save` button control (`#save-layout-btn`)
- **Local_Layout_Store**: The browser `localStorage` entry (key `smb_widget_layouts`) holding the member's Current_Layout

## Requirements

### Requirement 1: Remove the Layout Selector Control

**User Story:** As a member, I want a single dashboard without a layout picker, so that the header is simpler and I am not asked to choose among multiple layouts.

#### Acceptance Criteria

1. WHEN the dashboard page in `dashboard/index.html` finishes loading, THE Widget_Builder_UI SHALL render the dashboard header containing zero DOM elements matching the Layout_Selector selector (`#layout-selector`)
2. WHEN the dashboard page in `dashboard/index.html` finishes loading, THE Widget_Builder_UI SHALL render the dashboard header containing zero "+ New Layout" control elements
3. THE Widget_Builder_UI SHALL contain in `dashboard/dashboard.js` zero JavaScript handlers that populate the Layout_Selector and zero JavaScript handlers bound to a Layout_Selector change event
4. WHEN the dashboard page in `dashboard/index.html` finishes loading, THE Widget_Builder_UI SHALL issue zero network requests to `/dashboard/layouts` for the purpose of populating a Layout_Selector
5. IF any retained code path previously invoked the Layout_Selector population routine, THEN THE Widget_Builder_UI SHALL complete dashboard initialization with zero uncaught JavaScript errors that reference the removed Layout_Selector element, and SHALL preserve all remaining dashboard rendering behavior unchanged

### Requirement 2: Remove the New Layout Control

**User Story:** As a member, I want no explicit "new layout" action in the header, so that the dashboard reflects a single-layout model.

#### Acceptance Criteria

1. WHILE the dashboard is loaded, THE Widget_Builder_UI SHALL render zero DOM elements matching the New_Layout_Button selector (`#new-layout-btn`)
2. THE Widget_Builder_UI SHALL register zero click-event listeners for the New_Layout_Button, as no element matching its selector exists to bind to
3. THE Widget_Builder_UI SHALL contain no code path that clears the grid and resets the Current_Layout in response to a New_Layout_Button action
4. WHEN the dashboard finishes loading, THE Widget_Builder_UI SHALL complete initialization with zero JavaScript errors arising from the removal of the New_Layout_Button click handler

### Requirement 3: Retain the Save Control

**User Story:** As a member, I want to keep saving my dashboard, so that my arrangement persists across sessions.

#### Acceptance Criteria

1. WHEN the Widget_Builder_UI renders the dashboard header, THE Widget_Builder_UI SHALL display the Save_Button element (`#save-layout-btn`) in the header
2. WHEN a member activates the Save_Button, THE Widget_Builder_UI SHALL overwrite the single layout entry for the member in the Local_Layout_Store under the key `smb_widget_layouts` with the current grid widgets, replacing any previously stored value
3. WHEN a member activates the Save_Button, THE Widget_Builder_UI SHALL send a `PUT /dashboard/layouts` request containing the current grid widgets to the Layout_Store and SHALL treat the request as failed if no response is received within 10 seconds
4. WHEN the `PUT /dashboard/layouts` request returns a success response, THE Widget_Builder_UI SHALL display a success indication confirming the layout was saved
5. IF writing to the Local_Layout_Store fails, THEN THE Widget_Builder_UI SHALL display an error indication that the layout could not be saved locally and SHALL retain the current grid widgets unchanged in the UI
6. IF the `PUT /dashboard/layouts` request fails or times out, THEN THE Widget_Builder_UI SHALL display an error indication that the layout could not be saved to the Layout_Store and SHALL retain the layout previously persisted to the Local_Layout_Store

### Requirement 4: Automatic Single-Layout Load

**User Story:** As a member, I want my saved dashboard to appear automatically when I open the Widget Builder, so that I do not have to select it.

#### Acceptance Criteria

1. WHEN the dashboard view is rendered to an authenticated member, THE Widget_Builder_UI SHALL load the member's Current_Layout from the Local_Layout_Store into the grid without requiring any member action, provided a stored layout containing at least one widget is present
2. WHEN a stored layout containing at least one widget is present, THE Widget_Builder_UI SHALL complete loading the Current_Layout into the grid within 2 seconds of the dashboard view being rendered
3. IF the Local_Layout_Store contains no stored layout or a stored layout with zero widgets, THEN THE Widget_Builder_UI SHALL display the existing empty grid state without displaying any error indication
4. IF the Local_Layout_Store contains a value that cannot be parsed as a layout object, THEN THE Widget_Builder_UI SHALL display the existing empty grid state, SHALL retain the unparseable stored value unchanged, and SHALL continue accepting member interaction without displaying a blocking error
5. IF a stored layout parses successfully but contains one or more widget entries missing a required field (widget type, grid position, or size), THEN THE Widget_Builder_UI SHALL load only the widget entries that contain all required fields, SHALL omit each invalid entry from the grid, and SHALL continue operating without a blocking error
6. WHEN the Current_Layout is loaded into the grid, THE Widget_Builder_UI SHALL restore, for each stored widget, the widget type, the grid position (column and row), the widget size, and the saved widget configuration values to the values that were persisted at the last successful save

### Requirement 5: Save Behavior Without a Layout Selector

**User Story:** As a member, I want saving to update my one dashboard, so that I do not accumulate multiple named layouts.

#### Acceptance Criteria

1. WHEN a member activates the Save_Button, THE Widget_Builder_UI SHALL persist the current layout to the Local_Layout_Store and issue a `PUT /dashboard/layouts` request using the Default_Layout_Name "My Dashboard" without prompting the member to enter a layout name
2. WHEN a member activates the Save_Button and a `PUT /dashboard/layouts` response returns a layout identifier, THE Widget_Builder_UI SHALL retain that identifier as the Current_Layout identifier for subsequent saves
3. WHEN a member activates the Save_Button more than once in a session and a prior save has returned a layout identifier, THE Widget_Builder_UI SHALL target the same Current_Layout identifier on each subsequent save rather than creating an additional layout
4. THE Widget_Builder_UI SHALL NOT invoke the removed Layout_Selector population routine at any point during or after a save
5. WHEN a `PUT /dashboard/layouts` request completes successfully, THE Widget_Builder_UI SHALL display a confirmation indication that the dashboard has been saved
6. IF the `PUT /dashboard/layouts` request fails or does not complete within 10 seconds, THEN THE Widget_Builder_UI SHALL retain the layout persisted to the Local_Layout_Store, SHALL display an error message indicating that the save did not reach the server, and SHALL allow the member to continue editing without blocking further interaction

### Requirement 6: Dead Code Cleanup

**User Story:** As a developer, I want no dangling references to removed controls, so that the dashboard does not throw runtime errors and the code stays maintainable.

#### Acceptance Criteria

1. THE Widget_Builder_UI SHALL contain zero occurrences of the element identifiers `#layout-selector` and `#new-layout-btn` across both `dashboard/index.html` and `dashboard/dashboard.js`
2. THE Widget_Builder_UI SHALL contain zero definitions and zero invocations of the removed layout-selector population routine (`loadLayouts`), the layout-selection change handler (`onLayoutSelected`), and the new-layout handler (`newLayout`) in `dashboard/dashboard.js`
3. WHEN the dashboard finishes loading, THE Widget_Builder_UI SHALL complete initialization with zero JavaScript reference errors referencing `#layout-selector`, `#new-layout-btn`, `loadLayouts`, `onLayoutSelected`, or `newLayout` reported to the browser console
4. WHEN a member activates the Save_Button, THE Widget_Builder_UI SHALL complete the save action with zero JavaScript reference errors referencing the removed controls or their handlers reported to the browser console
5. WHERE the module previously exported the removed layout-selector population routine (`loadLayouts`) in its public interface, THE Widget_Builder_UI SHALL expose a public interface in which `loadLayouts`, `onLayoutSelected`, and `newLayout` are absent and undefined when accessed

### Requirement 7: Backend Unchanged

**User Story:** As a platform operator, I want the dashboard backend to remain stable, so that the simplification carries no backend risk.

#### Acceptance Criteria

1. THE Layout_Store SHALL continue to expose the GET, PUT, and DELETE methods on the `/dashboard/layouts` endpoint, with request and response schemas, field names, field types, and status outcomes identical to those in effect immediately before this amendment
2. THE Layout_Store SHALL retain the DashboardLayouts_Table with table name, key schema, and attribute definitions identical to those in effect immediately before this amendment
3. WHEN the Widget_Builder_UI persists a layout, THE Widget_Builder_UI SHALL send the request to the existing `PUT /dashboard/layouts` endpoint using the request body schema in effect immediately before this amendment, with no added, renamed, or removed fields
4. THE widget-builder-single-layout amendment SHALL introduce zero additions, modifications, or deletions to Layout_Store endpoint handlers or to the DashboardLayouts_Table schema

### Requirement 8: No Regression of Existing Dashboard Behavior

**User Story:** As a member, I want all existing dashboard capabilities to keep working, so that removing two header controls does not break the rest of the Widget Builder.

#### Acceptance Criteria

1. WHEN a member selects any existing widget type (bar, line, pie, table, KPI card, gauge), THE Widget_Builder_UI SHALL render and configure that widget with the same observable output as before the Layout_Selector and New_Layout_Button controls were removed, as specified in the parent Widget Builder Dashboard requirements
2. WHEN a widget requests data, THE Query_Engine SHALL resolve the data source, apply the configured filters, dimensions, and aggregations, and return chart-ready data identical to the output produced before the two controls were removed, as specified in the parent Widget Builder Dashboard requirements
3. WHEN a member drags a widget onto the 12-column grid, THE Widget_Builder_UI SHALL place the widget at the target grid position with the same observable behavior as before the two controls were removed, as specified in the parent Widget Builder Dashboard requirements
4. THE Dashboard_Handler SHALL enforce authentication and data isolation identically to the behavior specified in the parent Widget Builder Dashboard requirements, with no change introduced by the removal of the two controls
5. WHEN the parent dashboard auto-populates widgets from a parent-window data message, THE Widget_Builder_UI SHALL render those widgets without invoking or referencing the removed Layout_Selector or New_Layout_Button controls
6. IF any code path attempts to reference the removed Layout_Selector or New_Layout_Button controls during dashboard rendering or auto-population, THEN THE Widget_Builder_UI SHALL complete rendering of all unaffected widgets without raising a runtime error that halts the dashboard
