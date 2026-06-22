# Requirements Document

## Introduction

This feature transforms the existing vertical list of saved datasource configurations (in the Custom Dashboard section) into a responsive grid of compact cards. Each card provides quick-access actions: edit (re-open wizard pre-filled), run (execute query), and a structural placeholder for a future chart action. The edit action overwrites the original datasource when saved.

## Glossary

- **Card_Grid**: The responsive CSS grid container that renders saved datasource cards in rows of 2–3 items depending on viewport width
- **Datasource_Card**: A compact visual card representing a single saved datasource configuration, displaying the datasource name and a contextual icon
- **Wizard**: The existing 4-step DataSourceWizard module (accounts → attributes → timeframe → filters) used to create and edit datasource configurations
- **SavedDataSources_Module**: The frontend JavaScript module (`saved-datasources.js`) responsible for listing, running, and deleting saved datasources
- **Dashboard_API**: The backend HTTP endpoints (`GET /dashboard/datasources`, `PUT /dashboard/datasources`, `DELETE /dashboard/datasources/{id}`, `POST /dashboard/datasources/query`) that provide CRUD and query execution for saved datasource configurations
- **Query_Config**: The JSON object containing account_ids, attributes, timeframe, and filters that defines a datasource query

## Requirements

### Requirement 1: Card Grid Layout

**User Story:** As a member, I want to see my saved datasources as compact cards in a grid, so that I can visually scan and interact with them more efficiently than a vertical list.

#### Acceptance Criteria

1. THE Card_Grid SHALL render datasource cards in a responsive grid with 2 to 3 cards per row depending on the viewport width.
2. WHEN the viewport width is 768 pixels or wider, THE Card_Grid SHALL display 3 cards per row.
3. WHEN the viewport width is below 768 pixels, THE Card_Grid SHALL display 2 cards per row.
4. WHEN the viewport width is below 480 pixels, THE Card_Grid SHALL display 1 card per row.
5. THE Datasource_Card SHALL display the datasource name and a small contextual icon.
6. THE Datasource_Card SHALL have consistent height and spacing within the grid regardless of name length.

### Requirement 2: Card Action Visibility

**User Story:** As a member, I want card actions to appear on hover or click, so that the card remains uncluttered at rest.

#### Acceptance Criteria

1. WHILE the user hovers over a Datasource_Card, THE Datasource_Card SHALL reveal action buttons for edit, run, and delete.
2. WHEN the user taps a Datasource_Card on a touch device, THE Datasource_Card SHALL reveal action buttons for edit, run, and delete.
3. WHILE no hover or tap interaction is active, THE Datasource_Card SHALL hide the action buttons.

### Requirement 3: Edit Action (Re-open Wizard Pre-filled)

**User Story:** As a member, I want to edit a saved datasource by re-opening the wizard pre-filled with the saved configuration, so that I can adjust parameters without starting from scratch.

#### Acceptance Criteria

1. WHEN the user clicks the edit action on a Datasource_Card, THE Wizard SHALL open pre-filled with the saved Query_Config including account_ids, attributes, timeframe, and filters.
2. WHEN the Wizard opens in edit mode, THE Wizard SHALL display the datasource name in the title area to indicate which datasource is being edited.
3. WHEN the user completes the wizard in edit mode and saves, THE Dashboard_API SHALL overwrite the existing datasource configuration with the updated Query_Config.
4. WHEN the user cancels the wizard in edit mode, THE SavedDataSources_Module SHALL retain the original datasource configuration unchanged.
5. IF the Dashboard_API returns an error during save in edit mode, THEN THE SavedDataSources_Module SHALL display the error message and retain the original configuration.

### Requirement 4: Run Action

**User Story:** As a member, I want to run a saved datasource directly from its card, so that I can quickly execute the query without opening the wizard.

#### Acceptance Criteria

1. WHEN the user clicks the run action on a Datasource_Card, THE SavedDataSources_Module SHALL execute the saved Query_Config against the Dashboard_API.
2. WHEN the query completes successfully, THE SavedDataSources_Module SHALL render the results in the ResultTable component.
3. WHEN the query completes successfully, THE SavedDataSources_Module SHALL display a success notification with the datasource name.
4. IF the Dashboard_API returns an error during query execution, THEN THE SavedDataSources_Module SHALL display the error message to the user.

### Requirement 5: Delete Action

**User Story:** As a member, I want to delete a saved datasource from its card, so that I can remove configurations I no longer need.

#### Acceptance Criteria

1. WHEN the user clicks the delete action on a Datasource_Card, THE SavedDataSources_Module SHALL prompt the user for confirmation before deleting.
2. WHEN the user confirms deletion, THE SavedDataSources_Module SHALL call the Dashboard_API to delete the datasource.
3. WHEN deletion succeeds, THE Card_Grid SHALL re-render without the deleted card.
4. IF the Dashboard_API returns an error during deletion, THEN THE SavedDataSources_Module SHALL display the error message and retain the card.

### Requirement 6: Empty State

**User Story:** As a member, I want to see a helpful empty state when no datasources are saved, so that I understand how to create one.

#### Acceptance Criteria

1. WHEN the member has zero saved datasources, THE Card_Grid SHALL display an empty-state message indicating no saved datasources exist.
2. WHEN the member has zero saved datasources, THE empty-state message SHALL suggest creating a datasource using the wizard.

### Requirement 7: Future Chart Action Placeholder

**User Story:** As a developer, I want structural room for a chart action on each card, so that the feature can be added later without a layout refactor.

#### Acceptance Criteria

1. THE Datasource_Card action container SHALL reserve a slot for a future chart action button without rendering a visible element.
2. THE Datasource_Card action container layout SHALL accommodate an additional action button without requiring structural changes to the card markup.
