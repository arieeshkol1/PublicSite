# Implementation Plan: Observe Tab Restructure

## Overview

Restructure the Observe tab from a flat widget grid into a left-nav + content-area layout with four logical sections (Cost Analysis, Commitments, Business Metrics, Health & Score). Implementation is purely frontend — vanilla JavaScript, CSS, and HTML changes across three files: `members/index.html`, `members/members.js`, and `members/members.css`. The existing widget customization, KPI bar, and ECharts rendering are preserved and enhanced with per-section scoping and lazy rendering.

## Tasks

- [x] 1. Define section constants and widget-to-section mapping
  - [x] 1.1 Add OBSERVE_SECTIONS array and OBSERVE_WIDGET_SECTIONS mapping to members.js
    - Define the `OBSERVE_SECTIONS` array with `{id, label, icon}` for each of the four sections
    - Define the `OBSERVE_WIDGET_SECTIONS` object mapping section IDs to arrays of widget IDs
    - Place these constants near the top of members.js alongside existing `DASH_WIDGET_DEFS`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ]* 1.2 Write property test for widget-section mapping uniqueness
    - **Property 2: Widget-section mapping uniqueness**
    - **Validates: Requirements 3.1, 3.6**

- [x] 2. Implement HTML structure for left-nav and section containers
  - [x] 2.1 Restructure the dash-tab HTML in members/index.html
    - Replace the existing flat widget grid with the left-nav + content-area layout
    - Add `#observe-nav` container with four navigation buttons using `.act-nav-btn` class
    - Add section containers (`#observe-section-observe-cost`, etc.) with `.observe-widget-grid` divs
    - Keep KPI bar (`#dash-kpi-bar`) above and outside the nav+content layout
    - Add `#tag-filter-container` inside the Cost Analysis section
    - _Requirements: 1.1, 4.1, 3.7, 3.8, 7.1_

  - [x] 2.2 Add CSS rules for observe navigation and responsive behavior in members.css
    - Add `#observe-nav` styles (width: 180px, border-right, padding)
    - Add responsive media query for ≤768px (collapse nav to 60px, hide text labels)
    - Add `.observe-widget-grid` grid styles (auto-fit, minmax 380px, gap 16px)
    - Add single-column fallback for content area < 380px
    - _Requirements: 1.5, 11.1, 11.2, 11.3, 11.4_

- [x] 3. Implement section switching logic
  - [x] 3.1 Implement `_switchObserveSection(sectionId)` function in members.js
    - Validate sectionId against OBSERVE_SECTIONS
    - Update nav button active states (toggle `.active` class)
    - Toggle section container visibility (display: '' vs 'none')
    - Persist active section to localStorage key `observeActiveSection`
    - Schedule ECharts resize after 50ms delay for visible section
    - Cancel pending resize if another switch occurs before 50ms completes
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 9.1, 9.2, 9.3, 9.4_

  - [x] 3.2 Implement `_getActiveObserveSection()` function in members.js
    - Read `observeActiveSection` from localStorage
    - Validate against OBSERVE_SECTIONS IDs
    - Return default `'observe-cost'` if invalid or missing
    - _Requirements: 1.3, 1.4, 2.4, 10.2_

  - [ ]* 3.3 Write property test for section exclusivity
    - **Property 1: Section exclusivity**
    - **Validates: Requirements 2.1, 2.2, 1.2**

  - [ ]* 3.4 Write property test for invalid section handling
    - **Property 9: Invalid section handling**
    - **Validates: Requirements 2.4, 1.4**

  - [ ]* 3.5 Write property test for ECharts resize on section switch
    - **Property 5: ECharts resize on section switch**
    - **Validates: Requirements 9.1, 9.3, 2.5**

- [x] 4. Checkpoint - Ensure navigation and section switching work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement per-section layout persistence
  - [x] 5.1 Implement `_getObserveSectionLayout(sectionId)` function in members.js
    - Read from localStorage key `observeLayout_{sectionId}`
    - Parse JSON, validate structure (array of `{id, visible}` objects)
    - Fall back to default layout (all widgets visible in definition order) if invalid
    - Append any new widgets from OBSERVE_WIDGET_SECTIONS not in saved layout with `visible: true`
    - Silently drop widget IDs not in OBSERVE_WIDGET_SECTIONS[sectionId]
    - _Requirements: 10.1, 10.3, 10.4, 10.5, 12.1_

  - [x] 5.2 Implement `_saveObserveSectionLayout(sectionId, layout)` function in members.js
    - Serialize layout array to JSON
    - Write to localStorage key `observeLayout_{sectionId}`
    - Handle localStorage write errors gracefully (retain in-memory state)
    - _Requirements: 5.4, 5.7, 10.1, 12.4_

  - [ ]* 5.3 Write property test for section layout persistence roundtrip
    - **Property 4: Section layout persistence roundtrip**
    - **Validates: Requirements 10.3, 5.4**

  - [ ]* 5.4 Write property test for new widget graceful addition
    - **Property 6: New widget graceful addition**
    - **Validates: Requirements 10.5**

  - [ ]* 5.5 Write property test for section layout independence
    - **Property 13: Section layout independence**
    - **Validates: Requirements 5.5**

- [x] 6. Implement layout migration from old format
  - [x] 6.1 Implement `_migrateObserveLayout()` function in members.js
    - Check if old `dashWidgetLayout` key exists and no per-section keys exist
    - Build reverse lookup (widgetId → sectionId) from OBSERVE_WIDGET_SECTIONS
    - Distribute old layout items to section arrays preserving order and visibility
    - Write all per-section layouts to localStorage
    - Remove old `dashWidgetLayout` key only after all writes succeed
    - Handle partial failure: remove written keys and retain old key for retry
    - Skip if per-section keys already exist (idempotence)
    - Skip if old key is not valid JSON array
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 12.3_

  - [ ]* 6.2 Write property test for layout migration preserves widget state
    - **Property 3: Layout migration preserves widget state**
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [ ]* 6.3 Write property test for migration idempotence
    - **Property 12: Migration idempotence**
    - **Validates: Requirements 6.4**

- [x] 7. Checkpoint - Ensure layout persistence and migration work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement section widget builder and customization
  - [x] 8.1 Implement `_buildObserveSectionWidgets(sectionId, container)` function in members.js
    - Get section layout via `_getObserveSectionLayout`
    - Render visible widgets using existing `_addWidget` helper
    - Show "+ Add Widget" button with hidden widget count if any are hidden
    - Disable hide button if only one visible widget remains in section
    - _Requirements: 5.1, 5.2, 5.3, 5.8, 3.9_

  - [x] 8.2 Implement `_showAddWidgetPicker(container, sectionId)` function in members.js
    - Display list of hidden widget names for the section
    - On selection, update layout visibility to true and re-render section
    - Trigger chart rendering for restored widget
    - _Requirements: 5.3, 5.6_

  - [x] 8.3 Implement `_hideObserveWidget(sectionId, widgetId)` and `_restoreObserveWidget(sectionId, widgetId)` in members.js
    - Update layout visibility flag
    - Save layout to localStorage
    - Re-render section widget grid
    - Re-render charts for restored widgets
    - _Requirements: 5.1, 5.3, 5.4, 5.5_

  - [ ]* 8.4 Write property test for widget visibility toggle correctness
    - **Property 10: Widget visibility toggle correctness**
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [ ]* 8.5 Write property test for unknown widget graceful handling
    - **Property 11: Unknown widget graceful handling**
    - **Validates: Requirements 12.1, 12.3**

- [x] 9. Refactor renderDashboardWidgets for section-aware rendering
  - [x] 9.1 Refactor `renderDashboardWidgets(data)` in members.js
    - Keep KPI bar rendering unchanged (always visible)
    - Determine active section via `_getActiveObserveSection()`
    - Call `_buildObserveSectionWidgets` for the active section
    - Call `_renderVisibleSectionCharts` for the active section only
    - Cache dashboard data for use when switching sections
    - _Requirements: 4.1, 4.2, 4.3, 8.1, 8.3_

  - [x] 9.2 Implement `_renderVisibleSectionCharts(data, sectionId)` in members.js
    - Initialize ECharts only for visible widgets in the specified section
    - Skip already-initialized charts whose data hasn't changed
    - Mark sections as stale when data is refreshed
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 9.3 Write property test for KPI bar persistence across sections
    - **Property 7: KPI bar persistence across sections**
    - **Validates: Requirements 4.1, 4.3**

- [x] 10. Implement tag filter scoping
  - [x] 10.1 Implement `_renderObserveTagFilter(container)` in members.js
    - Render tag filter UI within the Cost Analysis section header (`#tag-filter-container`)
    - Move existing tag filter logic from flat layout into scoped function
    - _Requirements: 7.1_

  - [x] 10.2 Implement `_applyObserveTagFilter()` in members.js
    - Refresh only cost-related widgets (treemap, daily, monthly, regional, tag distribution)
    - Do not trigger data reload for Commitments, Business Metrics, or Health sections
    - Handle filter clear by reloading cost widgets with unfiltered data
    - _Requirements: 7.2, 7.3, 7.4_

  - [ ]* 10.3 Write property test for tag filter scoping
    - **Property 8: Tag filter scoping**
    - **Validates: Requirements 7.2, 7.3**

- [x] 11. Checkpoint - Ensure widget rendering and tag filter work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Wire everything together and handle edge cases
  - [x] 12.1 Integrate migration call and section initialization into tab load flow in members.js
    - Call `_migrateObserveLayout()` on Observe tab activation
    - Call `_getActiveObserveSection()` and `_switchObserveSection()` after data loads
    - Wire nav button click handlers to `_switchObserveSection`
    - Add window resize listener to trigger ECharts resize after 100ms on viewport threshold crossing
    - _Requirements: 2.2, 2.4, 6.1, 11.5_

  - [x] 12.2 Implement error handling for localStorage unavailability in members.js
    - Wrap all localStorage reads in try/catch, fall back to defaults
    - Wrap all localStorage writes in try/catch, retain in-memory state on failure
    - Ensure KPI bar shows error indicator with retry on data load failure
    - _Requirements: 12.2, 12.4, 4.4_

  - [x] 12.3 Update widget hide/close button handlers to use section-scoped functions
    - Replace existing flat-layout hide logic with `_hideObserveWidget(sectionId, widgetId)`
    - Ensure widget drag-reorder updates section-specific layout
    - _Requirements: 5.1, 5.6, 5.7_

  - [ ]* 12.4 Write unit tests for error handling scenarios
    - Test corrupted localStorage JSON fallback
    - Test missing widget definition graceful skip
    - Test localStorage unavailability fallback
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All implementation is vanilla JavaScript (no frameworks) matching existing codebase patterns
- The three target files are: `members/index.html`, `members/members.js`, `members/members.css`
- ECharts resize timing (50ms for section switch, 100ms for viewport change) is specified in the design

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "2.2"] },
    { "id": 2, "tasks": ["3.1", "3.2", "5.1", "5.2"] },
    { "id": 3, "tasks": ["3.3", "3.4", "3.5", "5.3", "5.4", "5.5", "6.1"] },
    { "id": 4, "tasks": ["6.2", "6.3", "8.1"] },
    { "id": 5, "tasks": ["8.2", "8.3"] },
    { "id": 6, "tasks": ["8.4", "8.5", "9.1"] },
    { "id": 7, "tasks": ["9.2", "10.1"] },
    { "id": 8, "tasks": ["9.3", "10.2"] },
    { "id": 9, "tasks": ["10.3", "12.1"] },
    { "id": 10, "tasks": ["12.2", "12.3"] },
    { "id": 11, "tasks": ["12.4"] }
  ]
}
```
