# Implementation Plan: Saved Datasource Cards

## Overview

Refactor the `SavedDataSources` module from a vertical list to a responsive card grid with hover-revealed actions (edit, run, delete), and extend `DataSourceWizard` with an `openWithConfig` edit mode that pre-fills the wizard and overwrites on save. CSS grid handles responsiveness; the existing PUT endpoint handles overwrite — no backend changes required.

## Tasks

- [ ] 1. Refactor SavedDataSources to card grid layout
  - [ ] 1.1 Add card grid CSS styles to `members/members.css`
    - Add `.ds-card-grid` with CSS Grid (`repeat(3, 1fr)`) and responsive breakpoints (2-col at 767px, 1-col at 479px)
    - Add `.ds-card` styles: border, border-radius, padding, min-height, flex column layout, hover shadow
    - Add `.ds-card-header` styles: flex row with icon and name
    - Add `.ds-card-actions` styles: flex row, opacity 0 by default, opacity 1 on `.ds-card:hover` and `.ds-card.ds-card-active`
    - Add `.ds-action-slot-chart` placeholder (hidden span, no dimensions)
    - Add action button styles (`.ds-action-edit`, `.ds-action-run`, `.ds-action-delete`)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 7.1, 7.2_

  - [ ] 1.2 Refactor `render()` in `members/saved-datasources.js` to produce card grid
    - Replace the inline-styled vertical list with a `div.ds-card-grid` container
    - Create a `buildCard(ds)` helper that generates a `.ds-card` element per datasource
    - Each card renders: `.ds-card-header` with icon (from `getIconForConfig`) and escaped name, `.ds-card-actions` with edit/run/delete buttons plus chart placeholder span
    - Wire action button onclick handlers: edit → `editSaved(ds)`, run → `runSaved(ds.datasource_id)`, delete → `deleteSaved(ds.datasource_id, ds.name)`
    - Add touch support: `touchstart` listener toggles `.ds-card-active` class
    - Preserve existing empty-state rendering (zero datasources message)
    - Preserve existing error-state rendering (API error banner)
    - _Requirements: 1.1, 1.5, 1.6, 2.1, 2.2, 2.3, 6.1, 6.2_

  - [ ] 1.3 Add `getIconForConfig(queryConfig)` helper function
    - Return a contextual icon/emoji based on query_config attributes (e.g., cost → 💰, usage → 📊, generic → 📋)
    - _Requirements: 1.5_

- [ ] 2. Implement edit mode in DataSourceWizard
  - [ ] 2.1 Add edit-mode state variables and `openWithConfig` method to `members/datasource-wizard.js`
    - Add module-level `editingDatasourceId` and `editingDatasourceName` variables (null by default)
    - Implement `openWithConfig(datasourceId, queryConfig, datasourceName)` that sets edit state, copies queryConfig into `wizardConfig`, sets `currentStep = 1`, unhides overlay, and calls `renderStep()`
    - Export `openWithConfig` in the public API return object
    - _Requirements: 3.1, 3.2_

  - [ ] 2.2 Modify `renderStep()` to show datasource name in title during edit mode
    - When `editingDatasourceId` is set, prepend "Editing: {datasourceName}" to the wizard header area
    - When not in edit mode, keep existing step title behaviour
    - _Requirements: 3.2_

  - [ ] 2.3 Modify `saveDataSource()` to handle edit-mode overwrite
    - When `editingDatasourceId` is set: skip the name prompt, use existing `editingDatasourceName`, include `datasource_id` in the PUT body to trigger overwrite
    - On success: clear edit state (`editingDatasourceId = null`, `editingDatasourceName = null`), close wizard, refresh card grid
    - On error: show error notification, keep wizard open, retain original config
    - _Requirements: 3.3, 3.4, 3.5_

  - [ ] 2.4 Modify `close()` to reset edit state on cancel
    - When closing the wizard (overlay click or cancel), reset `editingDatasourceId` and `editingDatasourceName` to null
    - Ensure no API call is made on cancel
    - _Requirements: 3.4_

- [ ] 3. Wire edit action from cards to wizard
  - [ ] 3.1 Add `editSaved(ds)` function to `SavedDataSources` module
    - Call `DataSourceWizard.openWithConfig(ds.datasource_id, ds.query_config, ds.name)`
    - Export `editSaved` in the public API return object
    - _Requirements: 3.1_

- [ ] 4. Checkpoint
  - Ensure all changes work together: cards render in grid, hover reveals actions, edit opens wizard pre-filled, save overwrites via PUT, cancel preserves original. Ask the user if questions arise.

- [ ] 5. Verify run and delete actions work from card buttons
  - [ ] 5.1 Verify `runSaved` integration with card button
    - Ensure the run button in each card correctly calls the existing `runSaved(datasourceId)` which fetches the config and posts to query endpoint
    - Confirm `ResultTable.render` is called with response data and success notification includes datasource name
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ] 5.2 Verify `deleteSaved` integration with card button
    - Ensure the delete button calls existing `deleteSaved(datasourceId, name)` which prompts confirmation then calls DELETE endpoint
    - Confirm card grid re-renders after successful deletion
    - Confirm error notification on failed deletion
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ] 6. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- The project uses vanilla JavaScript IIFE modules with no build system — all changes are direct file edits
- CSS is in `members/members.css`; JavaScript in `members/saved-datasources.js` and `members/datasource-wizard.js`
- The existing PUT endpoint already supports overwrite when `datasource_id` is included in the body — no backend changes needed
- `runSaved` and `deleteSaved` already exist and are functional; they just need new trigger points from the card buttons
- Touch device support uses a simple class toggle (`.ds-card-active`) rather than JS resize listeners

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3", "2.1"] },
    { "id": 1, "tasks": ["1.2", "2.2", "2.4"] },
    { "id": 2, "tasks": ["2.3", "3.1"] },
    { "id": 3, "tasks": ["5.1", "5.2"] }
  ]
}
```
