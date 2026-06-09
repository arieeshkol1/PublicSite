# Implementation Plan: AI Chat UX Enhancements

## Overview

This plan implements two AI chat improvements: (1) Data Source Buttons with collapsible tables rendered in the frontend, and (2) Backend-Generated Follow-up Question Suggestions replacing the client-side keyword matching. Changes span the backend Lambda (`member-handler/lambda_function.py`) and the frontend (`members/members.js` + `members/members.css`).

## Tasks

- [x] 1. Implement backend follow-up and data source generation
  - [x] 1.1 Implement `_generate_follow_ups` function in `member-handler/lambda_function.py`
    - Create a new function that accepts `account_data`, `answer`, and `question` parameters
    - Extract significant services (cost_usd > 1.0) from `cost_by_service`
    - Apply adaptive count logic: 3 questions for 3+ significant services, 2 for 1-2 services, empty for 0
    - Generate template-based questions referencing actual service names and cost patterns
    - Enforce 100-character limit per question via truncation
    - Return list of follow-up question strings
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 6.1, 6.2, 6.3, 6.4_

  - [x] 1.2 Implement `_extract_data_sources` function in `member-handler/lambda_function.py`
    - Create a new function that accepts `account_data` and `chart_data` parameters
    - Iterate over chart_data items, extract `title`, `labels`, `data`, and optional `data2`
    - Skip entries with empty labels or data arrays
    - Build row objects with `name` from labels and `value`/`value2` from data arrays
    - Return list of `{label, data}` objects
    - _Requirements: 7.3_

  - [x] 1.3 Modify `_invoke_bedrock_agent` to include new fields in response
    - After building the agent answer, call `_generate_follow_ups()` wrapped in try/except (return `[]` on error)
    - Call `_build_chart_data()` to get chart_data
    - Call `_extract_data_sources()` to build dataSources field
    - Add `followUpQuestions` and `dataSources` to the response payload alongside existing fields
    - Ensure `chartData` field remains unchanged for backward compatibility
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 1.4 Write property tests for `_generate_follow_ups`
    - **Property 7: Follow-up count adapts to data richness**
    - **Property 8: Follow-up character limit invariant**
    - **Property 9: Follow-up questions reference input data**
    - **Validates: Requirements 4.1, 4.3, 4.5, 6.1, 6.2, 6.3, 6.4**

  - [ ]* 1.5 Write property tests for `_extract_data_sources`
    - **Property 4: Table structure matches source data dimensions**
    - **Property 10: API response contract structure**
    - **Validates: Requirements 3.1, 7.1, 7.2, 7.3, 7.4**

  - [ ]* 1.6 Write unit tests for error resilience
    - Test that `_generate_follow_ups` exception is caught and `followUpQuestions` returns `[]`
    - Test that `_extract_data_sources` exception is caught and `dataSources` returns `[]`
    - Test that main answer is still returned when follow-up generation fails
    - **Property 11: Follow-up generation error resilience**
    - **Validates: Requirements 7.5**

- [x] 2. Checkpoint - Ensure backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement frontend data source buttons
  - [x] 3.1 Add CSS styles for data source buttons and tables in `members/members.css`
    - Add `.ai-datasource-wrapper` style for button container spacing
    - Add `.ai-datasource-btn` style extending `btn btn-outline btn-sm` with hover/active states
    - Add `.ai-datasource-btn[aria-expanded="true"]` style with highlighted border (#6366f1)
    - Add `.ai-datasource-table` style for table container
    - Add `.ai-source-table` styles for table headers and rows
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.2 Implement `_formatCellValue` function in `members/members.js`
    - Detect currency keys (contains "cost", "value", "amount", "price") and format as `$X.XX`
    - Detect percentage keys (contains "pct", "percent", "change") and format as `X.X%`
    - Return `'-'` for null/undefined values
    - Escape string values using existing `esc()` function
    - _Requirements: 3.2, 3.3_

  - [x] 3.3 Implement `_buildDataTable` function in `members/members.js`
    - Accept array of row objects and build HTML table string
    - Extract column keys from first row for headers
    - Render `<thead>` with column headers and `<tbody>` with formatted cell values
    - Return "No data" message when rows array is empty
    - _Requirements: 3.1_

  - [x] 3.4 Implement `_renderDataSourceButtons` function in `members/members.js`
    - Accept `tableArea` DOM element and `dataSources` array
    - Guard against null/empty inputs (no buttons rendered)
    - For each source: create wrapper div, button with `📋` prefix + label, and hidden table container
    - Set button `aria-expanded="false"` and directional indicator ▶ by default
    - Attach click handler toggling expand/collapse state, indicator (▶/▼), and border highlight
    - Each button toggles independently without affecting siblings
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.4, 3.5_

  - [ ]* 3.5 Write property tests for frontend data source rendering
    - **Property 1: Data source button count equals chart data items**
    - **Property 2: Default collapsed state invariant**
    - **Property 3: Independent toggle isolation**
    - **Validates: Requirements 1.1, 1.2, 1.3, 2.2, 3.5**

  - [ ]* 3.6 Write property tests for cell formatting
    - **Property 5: Currency formatting round-trip preserves value**
    - **Property 6: Percentage formatting correctness**
    - **Validates: Requirements 3.2, 3.3**

- [x] 4. Implement frontend follow-up suggestion integration
  - [x] 4.1 Modify `askAI` to pass `followUpQuestions` to `addAIMessage`
    - Extract `data.followUpQuestions` from API response (default to `[]`)
    - Pass as fourth argument to `addAIMessage(type, content, topServices, backendFollowUps)`
    - _Requirements: 5.1_

  - [x] 4.2 Modify `addAIMessage` to accept and use backend follow-ups
    - Add fourth parameter `backendFollowUps` (array, default `[]`)
    - When `backendFollowUps` is non-empty, render those as follow-up buttons directly
    - When `backendFollowUps` is absent or empty, fall back to existing client-side keyword-matching logic
    - Render follow-up buttons using existing `ai-followup-btn` CSS class
    - Attach click handler that submits the question text as a new AI query
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 4.3 Write property tests for conditional follow-up rendering
    - **Property 12: Conditional follow-up source selection**
    - **Validates: Requirements 5.1, 5.2, 5.4**

- [x] 5. Wire data source buttons into the chat flow
  - [x] 5.1 Integrate `_renderDataSourceButtons` call into `askAI` response handling
    - After `addAIMessage` renders the answer, locate the `.ai-table-area` in the new message
    - Call `_renderDataSourceButtons(tableArea, data.dataSources)` to render buttons
    - Ensure backward compatibility: if `dataSources` is undefined/empty, no buttons render
    - _Requirements: 1.1, 3.4_

- [x] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python, frontend uses JavaScript — no new frameworks introduced
- The feature extends existing endpoint response; no new infrastructure required

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "3.1", "3.2"] },
    { "id": 1, "tasks": ["1.3", "3.3"] },
    { "id": 2, "tasks": ["1.4", "1.5", "1.6", "3.4"] },
    { "id": 3, "tasks": ["3.5", "3.6", "4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3"] },
    { "id": 5, "tasks": ["5.1"] }
  ]
}
```
