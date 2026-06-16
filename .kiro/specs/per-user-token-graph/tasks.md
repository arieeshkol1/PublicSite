# Implementation Plan: Per-User Token Graph

## Overview

Add a per-user daily token consumption multi-line SVG chart to the AI Cost dashboard in `members/members.js`. The implementation adds helper functions for user extraction, data grouping, and color assignment, a main render function that outputs the widget HTML (checkbox filter + SVG chart), and an event-wiring function for interactive filtering. CSS for the filter area is added to `members/members.css`.

## Tasks

- [ ] 1. Implement helper functions and main chart renderer
  - [ ] 1.1 Add `_extractUsersFromTokenUsage(tokenUsage)` helper function
    - Accepts the token_usage array, returns sorted unique user_ids excluding "unknown" and empty strings
    - _Requirements: 2.1, 2.3_
  - [ ] 1.2 Add `_groupTokensByDateAndUser(tokenUsage, visibleUsers)` helper function
    - Groups token records by date and user_id, returns `{ dates: string[], series: { [userId]: number[] } }`
    - Each series value is `input_tokens + output_tokens` for that user on that date (0 if no data)
    - Dates sorted ascending
    - _Requirements: 4.2, 4.3, 4.4_
  - [ ] 1.3 Add `_assignUserColors(users)` helper function
    - Maps each user to a color from the 8-color `PER_USER_COLORS` palette, cycling via modulo
    - _Requirements: 5.1, 5.2_
  - [ ] 1.4 Add `_renderPerUserTokenChart(data)` main render function
    - Calls the three helpers above
    - Returns empty state HTML ("No per-user data available") when no valid users found
    - Otherwise returns `.openai-widget` card with: header, color-coded legend, checkbox filter area (with Select All / Deselect All buttons), and `<div id="peruser-token-chart-svg">` containing the SVG multi-line chart
    - SVG uses same dimensions/padding pattern as existing `_renderTokenUsageChart` (960×300, PADL=80, PAD=55, PADT=20)
    - One `<polyline>` per visible user, colored from palette
    - Y-axis grid lines + labels (5 ticks), X-axis date labels
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.2, 3.1, 3.2, 6.1_

- [ ] 2. Wire the chart into the dashboard rendering flow
  - [ ] 2.1 Insert `_renderPerUserTokenChart(data)` call in `_renderOpenAIDashboardSections()` after the Token Usage section
    - Add the section wrapped in `<div id="openai-section-peruser-token" class="openai-dash-section">`
    - Call `_wirePerUserTokenFilter(data)` after `contentEl.innerHTML = html`
    - _Requirements: 1.1, 6.1_

- [ ] 3. Implement interactive checkbox filter wiring
  - [ ] 3.1 Add `_wirePerUserTokenFilter(data)` function
    - Attaches `change` event listener on `#peruser-token-filter-area` container (event delegation)
    - On checkbox change: collects checked user_ids, updates `_openaiDashState.perUserVisible`, re-renders only `#peruser-token-chart-svg` innerHTML
    - Wire "Select All" button (`#peruser-select-all`): checks all checkboxes, re-renders SVG
    - Wire "Deselect All" button (`#peruser-deselect-all`): unchecks all checkboxes, re-renders SVG with empty state
    - _Requirements: 3.3, 3.4, 3.5_

- [ ] 4. Add CSS styles for the per-user chart filter area
  - [ ] 4.1 Add styles to `members/members.css`
    - `.peruser-filter-area` — flexbox wrap container with gap, padding, border-bottom separator
    - `.peruser-cb-label` — inline-flex label with align-items center, gap, cursor pointer, font-size 0.85em
    - `.peruser-color-dot` — 10×10px inline-block circle (border-radius 50%) for color indicator
    - `.peruser-filter-actions` — flex row for Select All / Deselect All buttons with margin-bottom
    - Buttons styled as small outlined buttons consistent with existing `.btn-outline.btn-sm`
    - _Requirements: 6.2, 6.3_

- [ ] 5. Checkpoint — Verify end-to-end rendering
  - Ensure all tests pass, ask the user if questions arise.
  - Verify the chart renders correctly with sample data containing multiple user_ids
  - Verify empty state appears when all user_ids are "unknown"
  - Verify checkbox toggling re-renders only the SVG area

## Notes

- This is a frontend-only feature — no backend or API changes needed
- All data comes from the existing `token_usage` array which already includes `user_id` per record
- The chart reuses the same SVG rendering pattern (viewBox, padding, polyline) as the existing Token Usage chart
- Files to modify: `members/members.js` (rendering + filter logic), `members/members.css` (filter styles)
