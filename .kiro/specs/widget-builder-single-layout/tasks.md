# Implementation Plan: Widget Builder Single Layout

## Overview

This is a **frontend-only** amendment to the existing Widget Builder Dashboard. It collapses the dashboard from a multi-named-layout model into a single-layout-per-member model. The work touches three files: a new pure helper `dashboard/layout-model.js`, the header markup in `dashboard/index.html`, and the load/save/init logic in `dashboard/dashboard.js`. `dashboard/grid-manager.js` and the backend `/dashboard/layouts` endpoints are reused as-is and are not modified.

Implementation language: **JavaScript** (matching the existing dashboard IIFE modules). Property-based tests use **fast-check** with the project's existing JS test runner and `jsdom` for the DOM/`localStorage` round-trip.

## Tasks

- [x] 1. Create the pure `LayoutModel` helper
  - [x] 1.1 Implement `dashboard/layout-model.js`
    - Create a dependency-free IIFE `LayoutModel` with no DOM or network access
    - Implement `isValidWidget(widget)`: true iff `type` is a non-empty string and `gridPosition` has numeric `x, y, w, h`
    - Implement `parseStoredLayout(rawString)` returning `{ status: 'empty' }` for null/empty/zero-widget layouts, `{ status: 'unparseable' }` when `JSON.parse` throws, and `{ status: 'ok', layout, validWidgets, omittedCount }` otherwise (filtering invalid widget entries)
    - Implement `buildSavePayload(widgets, currentLayoutId)` returning `{ layout_id: currentLayoutId || undefined, layout_name: 'My Dashboard', widgets }`
    - Export `isValidWidget`, `parseStoredLayout`, `buildSavePayload`, and `DEFAULT_LAYOUT_NAME = 'My Dashboard'`
    - _Requirements: 4.3, 4.4, 4.5, 4.6, 5.1, 5.3, 7.3_

  - [ ]* 1.2 Write property test for `parseStoredLayout`
    - **Property 1: Stored-layout parse classification and value preservation**
    - Generator: arbitrary mix of `null`/`''`/non-JSON strings/valid-JSON layouts whose `widgets` mix valid and field-missing entries
    - Assert `status`, that `validWidgets` is exactly the valid subset, that `omittedCount` equals the invalid count, and that no blocking error is thrown
    - **Validates: Requirements 4.3, 4.4, 4.5**

  - [ ]* 1.3 Write property test for `buildSavePayload`
    - **Property 3: Save payload conformance and stable single-layout target**
    - Generator: arbitrary widget arrays and arbitrary `currentLayoutId` (string or null)
    - Assert payload key set is a subset of `{ layout_id, layout_name, widgets }`, `layout_name` is exactly `"My Dashboard"`, `widgets` equals input, and `layout_id` equals `currentLayoutId` unchanged when set
    - **Validates: Requirements 5.1, 5.3, 7.3**

  - [ ]* 1.4 Write unit tests for `LayoutModel` edge cases
    - Cover `isValidWidget` boundaries (missing `type`, non-numeric `gridPosition` fields) and the `parseStoredLayout` contract table (null, empty string, valid-JSON-zero-widgets, unparseable, mixed valid/invalid, all-valid)
    - _Requirements: 4.3, 4.4, 4.5, 4.6_

- [x] 2. Update the dashboard header markup
  - [x] 2.1 Edit `dashboard/index.html` header
    - Within `<div class="header-right">`, remove the `#layout-selector` `<select>` and the `#new-layout-btn` "+ New Layout" `<button>`
    - Retain `#save-layout-btn` and `#header-email`
    - Add a `<script>` tag for `dashboard/layout-model.js`, loaded before `dashboard.js`
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 6.1_

  - [ ]* 2.2 Write unit test for header markup
    - Load `index.html` in jsdom; assert zero `#layout-selector`, zero `#new-layout-btn` / "+ New Layout", and a present visible `#save-layout-btn`
    - _Requirements: 1.1, 1.2, 2.1, 3.1_

- [x] 3. Refactor `dashboard/dashboard.js` for the single-layout model
  - [x] 3.1 Remove dead layout-selector / new-layout code
    - Delete the `loadLayouts()`, `onLayoutSelected(e)`, and `newLayout()` functions
    - Remove the `#new-layout-btn` listener block and the `#layout-selector` change listener block from `init()`; keep only the `#save-layout-btn` click listener
    - Remove `loadLayouts` (and `onLayoutSelected`, `newLayout`) from the module's returned public interface so they are `undefined` when accessed
    - Remove the `prompt(...)` call and the `await loadLayouts()` call from `saveLayout()`
    - Ensure zero remaining occurrences of `#layout-selector`, `#new-layout-btn`, `loadLayouts`, `onLayoutSelected`, `newLayout` in the file
    - _Requirements: 1.3, 2.2, 2.3, 5.4, 6.1, 6.2, 6.5_

  - [x] 3.2 Add request timeout support and implement auto-load
    - Add an optional `timeoutMs` parameter to `apiRequest` implemented with `AbortController` so a stalled request is treated as failed after the timeout
    - Rewrite `showDashboard()` to call `GridManager.init()`, read `smb_widget_layouts` from `localStorage`, call `LayoutModel.parseStoredLayout(raw)`, and call `GridManager.loadLayout({ widgets: result.validWidgets })` only when `status === 'ok'` and `validWidgets.length > 0`
    - For empty/unparseable/all-invalid results, leave the empty grid state with no error banner; leave the unparseable raw value untouched in `localStorage`
    - _Requirements: 1.4, 1.5, 2.4, 3.3, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.6, 6.3_

  - [x] 3.3 Implement local-first `saveLayout()`
    - Build `layoutData` with `layout_name: LayoutModel.DEFAULT_LAYOUT_NAME`, current `GridManager.getWidgets()`, and a `savedAt` timestamp; write it to `localStorage` under `smb_widget_layouts`, overwriting any prior value
    - On `localStorage` write failure, show a local-save error, retain the grid unchanged, and skip the `PUT`
    - On successful local write, call `apiRequest('PUT', '/dashboard/layouts', LayoutModel.buildSavePayload(widgets, currentLayoutId), 10000)`; on success update `currentLayoutId` from the response and show a success indication
    - On `PUT` failure/timeout, show a server-save error and retain the local copy, allowing continued editing
    - Add non-blocking `showSaveSuccess` / `showSaveError` helpers using existing dashboard styling
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 5.1, 5.2, 5.3, 5.5, 5.6, 6.4_

- [ ] 4. Tests for save/load behavior and regression safety
  - [ ]* 4.1 Write property test for the save → auto-load round-trip
    - **Property 2: Save-then-auto-load round-trip restores valid widgets as the single layout**
    - Generator: arrays of valid widget configs (random type, gridPosition, size, config) plus an arbitrary prior stored value; use a `localStorage` stub under jsdom
    - Assert the grid receives exactly the saved widgets with `type`, position (`x`, `y`), size (`w`, `h`), and config preserved, and that `smb_widget_layouts` holds a single layout replacing any prior value
    - **Validates: Requirements 3.2, 4.1, 4.6**

  - [ ]* 4.2 Write unit tests for save flows
    - Save success: mock `PUT` → 200 `{layout_id}`; assert success indication and `currentLayoutId` updated
    - Save timeout: mock a never-resolving `PUT` with fake timers; assert it is aborted and handled as failed after 10s
    - `localStorage` write failure: stub `setItem` to throw; assert local-save error, grid unchanged, no `PUT`
    - `PUT` failure: mock reject; assert server-save error and local copy retained; assert no reference errors to removed names
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 5.2, 5.5, 5.6, 6.4_

  - [ ]* 4.3 Write unit tests for auto-load, interface absence, and source scan
    - Run `init`/`showDashboard` with a fetch spy and a `console.error` spy; assert no GET to populate a selector and no reference errors
    - Assert `Dashboard.loadLayouts`, `Dashboard.onLayoutSelected`, `Dashboard.newLayout` are `undefined`
    - Scan `index.html` and `dashboard.js` for zero occurrences of `#layout-selector`, `#new-layout-btn`, `loadLayouts`, `onLayoutSelected`, `newLayout`
    - _Requirements: 1.3, 1.4, 1.5, 2.3, 2.4, 5.4, 6.1, 6.2, 6.3, 6.5_

  - [ ]* 4.4 Write tests for auto-populate and no-regression smoke checks
    - Dispatch a `dashboard-data` parent-window message; assert widgets render with no reference to removed controls and rendering completes without throwing
    - Confirm no backend handler or `DashboardLayouts_Table` files are modified by this amendment, and existing parent widget-type/grid-placement/query-engine/auth tests remain green
    - _Requirements: 7.1, 7.2, 7.4, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 5. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test tasks and can be skipped for a faster MVP.
- Each task references specific requirements clauses for traceability.
- `dashboard.js` edits (3.1 → 3.2 → 3.3) are sequenced across waves because they modify the same file.
- Property tests validate the three universal correctness properties; unit tests validate the static DOM edits, code-absence assertions, and deterministic error paths.
- Each property-based test runs a minimum of 100 iterations and is tagged with a comment referencing its design property.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "2.2", "3.1"] },
    { "id": 2, "tasks": ["3.2"] },
    { "id": 3, "tasks": ["3.3"] },
    { "id": 4, "tasks": ["4.1", "4.2", "4.3", "4.4"] }
  ]
}
```
