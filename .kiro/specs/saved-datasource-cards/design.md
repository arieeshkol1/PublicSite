# Design Document — Saved Datasource Cards

## Overview

This feature refactors the `SavedDataSources` module from a vertical list into a responsive card grid. Each `Datasource_Card` displays the datasource name and a contextual icon, with action buttons (edit, run, delete) revealed on hover/tap. The edit action opens the existing `DataSourceWizard` pre-filled with the saved `Query_Config` and overwrites on save. A structural placeholder reserves space for a future chart action.

### Key Design Decisions

1. **In-place module refactor** — The existing `SavedDataSources` IIFE in `saved-datasources.js` is refactored rather than replaced. This preserves the public API (`render`, `runSaved`, `deleteSaved`) and avoids breaking existing callers in `members.js`.

2. **CSS Grid for responsiveness** — A CSS Grid with `auto-fill` and media-query overrides handles the 1/2/3-column breakpoints (480px / 768px). No JavaScript resize listeners needed.

3. **Wizard edit mode via config injection** — Rather than duplicating wizard logic, we add an `openWithConfig(datasourceId, queryConfig, datasourceName)` method to `DataSourceWizard`. The wizard detects edit mode from the presence of a `datasourceId` and switches its save action from `PUT (create)` to `PUT (update)`.

4. **Action reveal via CSS hover + JS tap fallback** — Action buttons use `opacity: 0` by default and `opacity: 1` on `:hover`. A touch-device tap handler toggles a `.ds-card-active` class for the same effect.

5. **Future chart slot** — The action container uses flexbox with a hidden placeholder `<span class="ds-action-slot-chart"></span>` that occupies no space but can be swapped for a real button later without layout changes.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  members/index.html                                             │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  #saved-datasources-container  (or observe- variant)      │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐         │  │
│  │  │ DS Card 1   │ │ DS Card 2   │ │ DS Card 3   │  ...    │  │
│  │  │ icon + name │ │ icon + name │ │ icon + name │         │  │
│  │  │ [actions]   │ │ [actions]   │ │ [actions]   │         │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  DataSourceWizard (edit mode overlay)                     │  │
│  │  Title: "Editing: {datasource name}"                      │  │
│  │  Steps 1–4 pre-filled from saved Query_Config             │  │
│  │  Save → PUT /dashboard/datasources (overwrite by ID)      │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Card Grid Container (`SavedDataSources.render`)

Renders the responsive grid wrapper and iterates over fetched datasources to produce cards.

```javascript
// saved-datasources.js — render() refactored output structure
function render() {
  const datasources = await fetchDatasources();
  if (datasources.length === 0) return renderEmptyState();

  const grid = document.createElement('div');
  grid.className = 'ds-card-grid';
  datasources.forEach(ds => grid.appendChild(buildCard(ds)));
  container.innerHTML = '';
  container.appendChild(grid);
}
```

CSS grid rules (added to `members.css` or inline):

```css
.ds-card-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
@media (max-width: 767px) {
  .ds-card-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 479px) {
  .ds-card-grid { grid-template-columns: 1fr; }
}
```

### 2. Datasource Card (`buildCard`)

Each card is a fixed-height box with name, icon, and a hoverable action bar.

```javascript
function buildCard(ds) {
  const card = document.createElement('div');
  card.className = 'ds-card';
  card.innerHTML = `
    <div class="ds-card-header">
      <span class="ds-card-icon">${getIconForConfig(ds.query_config)}</span>
      <span class="ds-card-name">${escapeHtml(ds.name)}</span>
    </div>
    <div class="ds-card-actions">
      <button class="ds-action-edit" title="Edit">✏️</button>
      <button class="ds-action-run" title="Run">▶️</button>
      <button class="ds-action-delete" title="Delete">🗑️</button>
      <span class="ds-action-slot-chart"></span>
    </div>
  `;
  // Wire action handlers
  card.querySelector('.ds-action-edit').onclick = () => editSaved(ds);
  card.querySelector('.ds-action-run').onclick = () => runSaved(ds.datasource_id);
  card.querySelector('.ds-action-delete').onclick = () => deleteSaved(ds.datasource_id, ds.name);
  // Touch support
  card.addEventListener('touchstart', () => card.classList.toggle('ds-card-active'));
  return card;
}
```

Card CSS:

```css
.ds-card {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 16px;
  background: #fff;
  min-height: 80px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  position: relative;
  transition: box-shadow 0.15s;
}
.ds-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.ds-card-actions {
  display: flex;
  gap: 6px;
  opacity: 0;
  transition: opacity 0.15s;
}
.ds-card:hover .ds-card-actions,
.ds-card.ds-card-active .ds-card-actions {
  opacity: 1;
}
```

### 3. Edit Mode Extension (`DataSourceWizard.openWithConfig`)

New public method on the wizard module:

```javascript
// datasource-wizard.js — new method
let editingDatasourceId = null;
let editingDatasourceName = null;

function openWithConfig(datasourceId, queryConfig, name) {
  editingDatasourceId = datasourceId;
  editingDatasourceName = name;
  wizardConfig = { ...queryConfig };
  currentStep = 1;

  const overlay = document.getElementById('datasource-wizard-overlay');
  if (overlay) overlay.hidden = false;
  renderStep();
}
```

The `renderStep` function checks `editingDatasourceId` to display the datasource name in the title. The `saveDataSource` function is modified to call `PUT /dashboard/datasources` with the existing `datasource_id` when in edit mode, overwriting the configuration.

### 4. Run Action (unchanged logic, new trigger point)

The existing `SavedDataSources.runSaved(datasourceId)` is reused as-is. The card's run button calls it directly.

### 5. Delete Action (unchanged logic, new trigger point)

The existing `SavedDataSources.deleteSaved(datasourceId, name)` is reused. It already prompts for confirmation and re-renders on success.

## Interfaces

### Frontend Public API Changes

**SavedDataSources** (modified):
```javascript
return {
  render,        // Existing — refactored to produce card grid
  runSaved,      // Existing — unchanged
  deleteSaved,   // Existing — unchanged
  editSaved      // NEW — opens wizard in edit mode
};
```

**DataSourceWizard** (modified):
```javascript
return {
  init,
  open,
  close,
  openWithConfig,  // NEW — opens pre-filled for editing
  nextStep,
  prevStep,
  addFilter,
  removeFilter,
  runQuery,
  saveDataSource   // MODIFIED — handles edit-mode overwrite
};
```

### Backend API (existing, no changes needed)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/dashboard/datasources` | List saved datasources |
| PUT | `/dashboard/datasources` | Create or update (overwrite) a datasource |
| DELETE | `/dashboard/datasources/{id}` | Delete a datasource |
| POST | `/dashboard/datasources/query` | Execute a query config |

The `PUT` endpoint already supports overwrite by including `datasource_id` in the body — no backend changes required.

## Data Models

### Datasource Object (from API)

```javascript
{
  datasource_id: "uuid-string",
  name: "My Cost Report",
  query_config: {
    account_ids: ["123456789012"],
    attributes: ["date", "service", "cost_amount"],
    timeframe: { preset: "last_30d", start_date: null, end_date: null },
    filters: [{ attribute: "service", operator: "equals", value: "EC2" }]
  },
  created_at: "2024-01-15T10:30:00Z"
}
```

### Wizard Edit State (internal)

```javascript
// Additional state in DataSourceWizard module
let editingDatasourceId = null;   // null = create mode, string = edit mode
let editingDatasourceName = null;  // displayed in wizard title during edit
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| API error on `GET /dashboard/datasources` | Show error banner in container, no cards rendered |
| API error on `PUT /dashboard/datasources` (edit save) | Show error notification, retain original config, wizard stays open |
| API error on `POST /dashboard/datasources/query` (run) | Show error notification, no results rendered |
| API error on `DELETE /dashboard/datasources/{id}` | Show error notification, card remains in grid |
| Network failure (fetch throws) | Generic "Connection error" notification |
| Wizard cancel in edit mode | Close wizard, no API call, original config preserved |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Card contains datasource name and icon

*For any* valid datasource object with a non-empty name, the rendered card HTML SHALL contain the datasource name text and at least one icon element.

**Validates: Requirements 1.5**

### Property 2: Edit pre-fills wizard with saved config

*For any* valid Query_Config (containing account_ids, attributes, timeframe, and filters), opening the wizard in edit mode with that config SHALL result in the wizard internal state matching the provided config exactly.

**Validates: Requirements 3.1**

### Property 3: Edit mode displays datasource name in title

*For any* datasource name string, opening the wizard in edit mode SHALL result in the wizard title area containing that datasource name.

**Validates: Requirements 3.2**

### Property 4: Edit save overwrites existing datasource

*For any* existing datasource_id and any updated Query_Config, saving in edit mode SHALL call the API with that datasource_id and the new config, replacing the stored configuration.

**Validates: Requirements 3.3**

### Property 5: Non-successful edit preserves original config

*For any* datasource and any non-successful outcome (user cancels or API returns an error), the saved datasource configuration SHALL remain identical to its state before the edit was initiated.

**Validates: Requirements 3.4, 3.5**

### Property 6: Run action executes saved Query_Config

*For any* datasource with a saved Query_Config, triggering the run action SHALL call the query API with exactly that Query_Config as the request body.

**Validates: Requirements 4.1**

### Property 7: Successful run renders results and notifies with name

*For any* successful query response containing rows and columns, and for any datasource name, the module SHALL call ResultTable.render with those rows/columns AND display a success notification containing the datasource name.

**Validates: Requirements 4.2, 4.3**

### Property 8: Error responses are displayed to the user

*For any* API error message (from run, edit-save, or delete), the module SHALL display a notification containing that error message.

**Validates: Requirements 4.4, 3.5, 5.4**

### Property 9: Deletion removes card from rendered grid

*For any* list of datasources and any datasource_id that is successfully deleted, re-rendering the grid SHALL produce output that does not contain the deleted datasource_id or its name.

**Validates: Requirements 5.3**

### Property 10: Delete confirmation is required before API call

*For any* datasource, clicking the delete action SHALL present a confirmation prompt before making any API call. If the user declines, no DELETE request is made and the card remains.

**Validates: Requirements 5.1, 5.2**
