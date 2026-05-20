# Requirements Document

## Introduction

The Observe tab in the SlashMyBill Member Portal currently displays all dashboard widgets in a flat grid layout. As the platform grows with additional features (FinOps Dashboard, Live Business Metrics, FinOps Settings Healthcheck), this flat structure becomes difficult to navigate. This feature restructures the Observe tab into a left-nav + content-area pattern with four logical sections: Cost Analysis, Commitments, Business Metrics, and Health & Score. The restructure is a frontend-only layout change preserving all existing widget customization capabilities.

## Glossary

- **Observe_Tab**: The "Observe" tab in the SlashMyBill Member Portal that displays dashboard widgets and KPI metrics
- **Left_Navigation**: A vertical navigation panel on the left side of the Observe tab that allows switching between sections
- **Section**: A logical grouping of related widgets within the Observe tab (Cost Analysis, Commitments, Business Metrics, Health & Score)
- **Widget**: An individual chart or data visualization card rendered within a section
- **KPI_Bar**: A persistent summary bar displaying key performance indicators above the section content
- **Section_Layout**: A per-section localStorage array storing widget visibility and order preferences
- **Tag_Filter**: A filter control scoped to the Cost Analysis section that filters cost widgets by tag
- **Layout_Migration**: A one-time process that converts the old flat widget layout format into per-section layouts
- **Widget_Grid**: A responsive CSS grid container within each section that holds widget cards
- **ECharts_Instance**: An Apache ECharts chart object rendered within a widget card

## Requirements

### Requirement 1: Left Navigation

**User Story:** As a portal user, I want a left navigation panel in the Observe tab, so that I can quickly switch between different groups of dashboard widgets.

#### Acceptance Criteria

1. WHEN the Observe tab is displayed, THE Left_Navigation SHALL render four navigation buttons in top-to-bottom order: Cost Analysis, Commitments, Business Metrics, and Health & Score
2. WHEN a user clicks a navigation button, THE Left_Navigation SHALL apply the active visual state to that button and remove the active visual state from all other buttons, ensuring exactly one button is active at any time
3. WHEN the Observe tab loads, THE Left_Navigation SHALL read the value stored under the localStorage key "observeActiveSection" and set the corresponding navigation button as active
4. IF the stored active section value does not match one of the four valid section identifiers (Cost Analysis, Commitments, Business Metrics, Health & Score) or the localStorage key is absent, THEN THE Left_Navigation SHALL default to the Cost Analysis section as active
5. WHEN the viewport width is 768px or less, THE Left_Navigation SHALL collapse to 60px width showing only section icons without text labels, and WHEN the viewport width exceeds 768px, THE Left_Navigation SHALL display at 180px width with both icons and text labels

### Requirement 2: Section Switching

**User Story:** As a portal user, I want to switch between widget sections, so that I can focus on one domain of information at a time without visual clutter.

#### Acceptance Criteria

1. WHEN a user clicks a section navigation button, THE Observe_Tab SHALL display only the container matching the selected section identifier and set display to "none" on all other section containers
2. THE Observe_Tab SHALL maintain exactly one visible section at all times, defaulting to the first section in the navigation order when no previously saved section exists in localStorage
3. WHEN a section switch occurs, THE Observe_Tab SHALL persist the new active section identifier to localStorage under a dedicated key
4. WHEN the Observe_Tab is loaded, THE Observe_Tab SHALL read the saved section identifier from localStorage and activate that section if it matches a valid section identifier
5. IF _switchObserveSection is called with a section identifier that does not match any defined section container, THEN THE Observe_Tab SHALL make no DOM changes and retain the current active section
6. WHEN a section becomes visible, THE Observe_Tab SHALL trigger a resize on all ECharts_Instance elements within that section after a 50ms delay

### Requirement 3: Widget-to-Section Mapping

**User Story:** As a portal user, I want widgets organized into logical groups, so that I can find relevant cost and performance data without scrolling through unrelated charts.

#### Acceptance Criteria

1. THE Observe_Tab SHALL assign each widget to exactly one section based on the OBSERVE_WIDGET_SECTIONS mapping
2. THE Cost Analysis section SHALL contain the treemap, daily trend, monthly cost, regional cost, and tag distribution widgets
3. THE Commitments section SHALL contain the SP coverage, RI coverage, and waste detection widgets
4. THE Business Metrics section SHALL contain the live business metrics widget
5. THE Health & Score section SHALL contain the FinOps score summary widget
6. THE Observe_Tab SHALL NOT render any widget in more than one section
7. THE Observe_Tab SHALL render sections in the following top-to-bottom order: Cost Analysis, Commitments, Business Metrics, Health & Score
8. THE Observe_Tab SHALL display a visible heading label matching the section name above each group of widgets
9. IF a widget exists in the Observe_Tab but has no entry in the OBSERVE_WIDGET_SECTIONS mapping, THEN THE Observe_Tab SHALL NOT render that widget

### Requirement 4: KPI Bar Persistence

**User Story:** As a portal user, I want to see key performance indicators regardless of which section I am viewing, so that I always have a high-level summary available.

#### Acceptance Criteria

1. THE KPI_Bar SHALL be rendered in the DOM hierarchy above and outside all section content containers, positioned between the header and the left-nav + content area layout
2. WHEN dashboard data is loaded, THE KPI_Bar SHALL render a horizontal row of KPI cards (Month-over-Month change, Efficiency Score, Potential Savings, Accounts count) within 2 seconds of data availability
3. WHEN the member switches between sections within the Observe tab, THE KPI_Bar SHALL remain visible and retain its current displayed values without being removed from or re-inserted into the DOM
4. IF dashboard data fails to load or returns an error, THEN THE KPI_Bar SHALL display a single-line error indicator with a retry action instead of disappearing
5. WHEN the member switches tabs and then returns to the Observe tab, THE KPI_Bar SHALL display the same data values it held before the switch unless a manual refresh is triggered

### Requirement 5: Per-Section Widget Customization

**User Story:** As a portal user, I want to hide, show, and reorder widgets within each section independently, so that I can personalize my dashboard view per domain.

#### Acceptance Criteria

1. WHEN a user clicks the hide button on a widget card, THE Section_Layout SHALL update the widget visibility to false and remove the widget from the DOM
2. IF one or more hidden widgets exist in a section, THEN THE Widget_Grid SHALL display an "Add Widget" button showing the count of hidden widgets (e.g., "Add Widget (2)")
3. WHEN a user clicks the "Add Widget" button, THE Widget_Grid SHALL display a list of hidden widget names for that section, and WHEN the user selects a widget from the list, THE Section_Layout SHALL update the widget visibility to true and append the widget to the end of the current section grid order
4. WHEN a section layout changes, THE Observe_Tab SHALL persist the updated layout to localStorage synchronously before the next user interaction is processed
5. THE Observe_Tab SHALL maintain independent layout state for each section such that hiding, showing, or reordering a widget in one section does not alter the layout of any other section
6. WHEN a user drags a widget card to a new position within the same section, THE Section_Layout SHALL update the widget order array to reflect the new position and re-render the section grid in the updated order
7. WHEN a user reorders widgets, THE Section_Layout SHALL persist the new order to localStorage using the same key pattern as visibility changes (observeLayout_{sectionId})
8. IF a section contains only one visible widget, THEN THE Section_Layout SHALL disable the hide button on that widget to prevent an empty section

### Requirement 6: Layout Migration

**User Story:** As an existing portal user, I want my previous widget customizations preserved when the Observe tab is restructured, so that I do not lose my personalized layout.

#### Acceptance Criteria

1. WHEN the old dashWidgetLayout key exists in localStorage and no per-section layout key (observeLayout_{sectionId}) exists for any section, THE Layout_Migration SHALL split the old layout into per-section layouts based on the OBSERVE_WIDGET_SECTIONS mapping
2. WHEN all per-section layout keys have been written to localStorage without error, THE Layout_Migration SHALL remove the old dashWidgetLayout key from localStorage
3. THE Layout_Migration SHALL preserve each widget's visible boolean flag and relative order within its target section's layout array
4. IF at least one per-section layout key (observeLayout_{sectionId}) already exists in localStorage, THEN THE Layout_Migration SHALL skip processing and make no changes
5. IF a localStorage write fails during migration, THEN THE Layout_Migration SHALL remove any per-section layout keys written during the current migration attempt and retain the old dashWidgetLayout key so migration can be retried on next load
6. IF the old dashWidgetLayout value is not a valid JSON array, THEN THE Layout_Migration SHALL make no changes and leave the key in place

### Requirement 7: Tag Filter Scoping

**User Story:** As a portal user, I want the tag filter to apply only to cost-related widgets, so that filtering by tag does not affect unrelated sections like Commitments or Business Metrics.

#### Acceptance Criteria

1. THE Tag_Filter SHALL render only within the Cost Analysis section header area, adjacent to the existing account selector
2. WHEN a tag filter is applied, THE Observe_Tab SHALL refresh only the cost-related widgets (treemap, daily trend, monthly cost, regional cost, and tag distribution) within the Cost Analysis section, without triggering data reload in any other section
3. WHILE a tag filter is active, THE Observe_Tab SHALL NOT modify the displayed data in the Commitments, Business Metrics, or Health & Score sections
4. WHEN a tag filter is cleared, THE Observe_Tab SHALL reload the cost-related widgets with unfiltered data while leaving Commitments, Business Metrics, and Health & Score sections unchanged

### Requirement 8: Lazy Chart Rendering

**User Story:** As a portal user, I want the dashboard to load quickly, so that I can start viewing data without waiting for all charts across all sections to render.

#### Acceptance Criteria

1. WHEN the Observe tab loads, THE Observe_Tab SHALL initialize ECharts_Instance elements only for widgets that are both in the active section and have visibility set to true in the Section_Layout
2. WHEN a user switches to a section, THE Observe_Tab SHALL initialize ECharts_Instance elements for all visible widgets in that section that do not already have an initialized ECharts_Instance
3. THE Observe_Tab SHALL NOT initialize ECharts_Instance elements for widgets in non-active sections during initial load
4. WHEN switching back to a previously rendered section, THE Observe_Tab SHALL skip ECharts_Instance initialization for any widget whose ECharts_Instance is already initialized and whose underlying data has not changed since last render
5. WHEN dashboard data is refreshed while a section has previously rendered ECharts_Instance elements, THE Observe_Tab SHALL mark that section as stale and re-render its ECharts_Instance elements the next time the section becomes active

### Requirement 9: ECharts Resize on Section Switch

**User Story:** As a portal user, I want charts to display correctly when I switch sections, so that charts are not clipped or incorrectly sized after becoming visible.

#### Acceptance Criteria

1. WHEN a section becomes visible after a switch, THE Observe_Tab SHALL wait 50ms for DOM reflow and then call resize on all ECharts_Instance elements in that section
2. IF another section switch occurs before the 50ms resize delay completes, THEN THE Observe_Tab SHALL cancel the pending resize for the previous section and schedule a new resize for the newly visible section
3. IF an ECharts_Instance is not yet initialized when resize is triggered, THEN THE Observe_Tab SHALL skip that instance without throwing an exception or producing a visible error in the UI
4. IF the visible section contains zero ECharts_Instance elements, THEN THE Observe_Tab SHALL complete the resize cycle as a no-op without error

### Requirement 10: Section Layout Persistence

**User Story:** As a portal user, I want my section preferences and widget layouts to persist across browser sessions, so that I do not need to reconfigure my view each time I visit.

#### Acceptance Criteria

1. THE Observe_Tab SHALL store per-section widget layouts in localStorage using the key pattern observeLayout_{sectionId}
2. THE Observe_Tab SHALL store the active section identifier in localStorage using the key observeActiveSection
3. WHEN a saved section layout is loaded, THE Observe_Tab SHALL restore widget order and visibility exactly as saved
4. IF localStorage contains invalid JSON for a section layout, THEN THE Observe_Tab SHALL fall back to the default layout with all widgets visible in definition order
5. WHEN a new widget is added to OBSERVE_WIDGET_SECTIONS that does not exist in the saved layout, THE Observe_Tab SHALL append the new widget with visible set to true without altering existing widget order

### Requirement 11: Responsive Behavior

**User Story:** As a mobile user, I want the Observe tab to adapt to smaller screens, so that I can navigate sections without the navigation panel consuming excessive screen space.

#### Acceptance Criteria

1. WHEN the viewport width is 768px or less, THE Left_Navigation SHALL collapse to 60px width showing only section icons with accessible tooltip labels on hover and focus
2. WHEN the viewport width exceeds 768px, THE Left_Navigation SHALL display at full 180px width with icons and text labels
3. THE Widget_Grid SHALL use responsive grid columns (minmax 380px, 1fr) with auto-fill that reflow based on available content area width
4. WHEN the available content area width is less than 380px, THE Widget_Grid SHALL display a single column at 100% of the available width
5. WHEN the viewport crosses the 768px threshold, THE Observe_Tab SHALL trigger a resize on all visible ECharts_Instance elements after a 100ms delay to accommodate the layout change

### Requirement 12: Error Handling

**User Story:** As a portal user, I want the dashboard to handle errors gracefully, so that a corrupted preference or missing widget does not break the entire Observe tab.

#### Acceptance Criteria

1. IF a section layout references a widget ID not present in DASH_WIDGET_DEFS, THEN THE Observe_Tab SHALL skip that widget during rendering and remove it from the persisted section layout immediately after rendering completes
2. IF localStorage is unavailable or throws an error on read, THEN THE Observe_Tab SHALL render all sections using default layouts with all widgets visible in definition order and SHALL NOT display any error to the user
3. IF the Layout_Migration encounters a widget ID that does not map to any section in OBSERVE_WIDGET_SECTIONS, THEN THE Layout_Migration SHALL omit that widget entry from all per-section layouts and complete migration without interruption
4. IF localStorage throws an error on write during layout persistence, THEN THE Observe_Tab SHALL retain the current in-memory layout state and continue operating without interrupting the user interaction
