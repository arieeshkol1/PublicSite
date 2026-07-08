# Implementation Plan

## Overview

Fix two related bugs in the member portal Observe tab and AI agent tool routing:

1. **Cost Aggregation Bug**: The Observe tab account selector uses multi-select checkboxes with all accounts checked by default, causing `getDashSelectedAccountIds()` to return all account IDs. The backend aggregates costs from all accounts, displaying inflated totals (~$400 instead of ~$141). Fix: convert to single-select radio buttons in `populateDashAccounts()` in `members/members.js`, update `getDashSelectedAccountIds()`, and remove "Select All"/"Clear" links.

2. **AI Agent Tool Selection Bug**: The Bedrock agent selects the wrong tool (`getAIVendorUsage`) for OpenAI accounts. The tool returns `notSupported` with `availableOperations` list, but the agent retries the same failing tool 4 times instead of falling back. Fix: add fallback logic in `_execute_tool()` in `agent-action/lambda_function.py` when `notSupported` is returned, and update `legacy_mapper.py` to remap `/get-ai-vendor-usage` to `getAIUsage`.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["1", "2"],
      "description": "Write exploration and preservation tests BEFORE fix"
    },
    {
      "wave": 2,
      "tasks": ["3.1", "3.2", "3.3", "4.1", "4.2"],
      "description": "Implement both fixes (UI single-select + agent fallback logic)"
    },
    {
      "wave": 3,
      "tasks": ["3.4", "3.5", "4.3", "4.4"],
      "description": "Verify exploration tests pass and preservation tests still pass"
    },
    {
      "wave": 4,
      "tasks": ["5"],
      "description": "Final checkpoint - all tests pass"
    }
  ]
}
```

## Tasks

- [ ] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Multi-Account Cost Aggregation & Wrong Tool Selection
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bugs exist
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate both bugs exist
  - **Scoped PBT Approach**:
    - Bug 1: Scope to concrete case: 2+ connected accounts loaded in Observe tab → assert `getDashSelectedAccountIds()` returns exactly 1 account ID (not all)
    - Bug 2: Scope to concrete case: invoke `_execute_tool("getAIVendorUsage", openai_account_id, email, params)` → assert result does NOT contain `notSupported: true` (i.e., fallback was triggered)
  - **Bug 1 Test** (members.js): Create a JSDOM/mock environment with 2+ accounts in `allAccounts` array (connectionStatus='connected'), call `populateDashAccounts()`, then assert `getDashSelectedAccountIds().length === 1` (expected behavior from design). On UNFIXED code this will FAIL because all checkboxes are checked by default returning multiple IDs.
  - **Bug 2 Test** (lambda_function.py): Mock `provider_router.route_tool()` to return `{"notSupported": true, "availableOperations": ["getCostBreakdown", "getAIUsage", "getMonthlyTrend"]}` for `getAIVendorUsage`, and return valid data for `getAIUsage`. Call `_execute_tool("getAIVendorUsage", "openai-acct-123", "user@test.com", {})`. Assert the result does NOT have `notSupported: true` (expected: fallback to `getAIUsage`). On UNFIXED code this will FAIL because no fallback logic exists.
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct - it proves the bugs exist)
  - Document counterexamples found:
    - Bug 1: `getDashSelectedAccountIds()` returns `["acct1", "acct2"]` instead of `["acct1"]`
    - Bug 2: `_execute_tool("getAIVendorUsage", ...)` returns `{notSupported: true, availableOperations: [...]}` without attempting fallback
  - Mark task complete when tests are written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.4, 1.5_

- [ ] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Single-Account Dashboard & Supported Tool Routing
  - **IMPORTANT**: Follow observation-first methodology
  - **Observe on UNFIXED code**:
    - Observe: Single-account user (1 connected account) → `populateDashAccounts()` renders with that account checked → `getDashSelectedAccountIds()` returns `["acct1"]`
    - Observe: `_execute_tool("getCostBreakdown", "aws-acct-123", "user@test.com", {"accountId": "aws-acct-123", "memberEmail": "user@test.com"})` routes to `provider_router.route_tool()` and returns valid cost data (no `notSupported`)
    - Observe: Account change event triggers `loadDashboardData()` reload
    - Observe: Tag filter parameters are included in dashboard data request alongside selected account
  - **Property-based tests**:
    - For all single-account configurations (1 connected account with any accountId/name): `populateDashAccounts()` renders with that account selected, `getDashSelectedAccountIds()` returns exactly `[accountId]`
    - For all supported tool invocations (tool in connector.SUPPORTED_OPERATIONS for the account's provider): `_execute_tool(tool, accountId, email, params)` returns the same result as `provider_router.route_tool(tool, accountId, email, params)` directly — no fallback triggered
    - For all Knowledge tools (getOptimizationTips, getPricingData): routing continues to work without accountId
  - **Bug 1 Preservation** (members.js): For any single connected account, verify `getDashSelectedAccountIds()` returns exactly 1 ID. Verify `cb.onchange` triggers `loadDashboardData()`.
  - **Bug 2 Preservation** (lambda_function.py): For any tool in SUPPORTED_OPERATIONS (e.g., `getCostBreakdown` for AWS), verify `_execute_tool()` calls `provider_router.route_tool()` exactly once and returns the result directly without triggering fallback.
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [ ] 3. Fix for Observe Tab Cost Aggregation Bug (multi-select → single-select)

  - [ ] 3.1 Convert account selector to single-select radio buttons in `populateDashAccounts()`
    - In `members/members.js` (~line 3390), in the `connected.forEach` loop:
      - Replace `cb.type = 'checkbox'` with `cb.type = 'radio'`
      - Add `cb.name = 'dash-acct-radio'` so browser enforces single-select
      - Change `cb.checked = true` to `cb.checked = (idx === 0)` — only first account selected by default
    - Update `cb.className` from `'dash-acct-cb'` to `'dash-acct-radio'` (update all selectors accordingly)
    - Update `updateLabel()` to always show single-account label (remove "N accounts selected" branch)
    - _Bug_Condition: isBugCondition(input) where input.selectedAccountCount > 1_
    - _Expected_Behavior: getDashSelectedAccountIds().length === 1 always_
    - _Preservation: Single-account users continue to see their data without change_
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ] 3.2 Remove "Select All" and "Clear" links from account dropdown
    - Remove the `ctrlRow` element creation block (~line 3435-3441) including `selAll` and `selNone` links
    - These controls are irrelevant for single-select radio behavior
    - Remove `panel.appendChild(ctrlRow)` statement
    - _Requirements: 2.1_

  - [ ] 3.3 Update `getDashSelectedAccountIds()` to query radio buttons
    - Change selector from `'.dash-acct-cb:checked'` to `'.dash-acct-radio:checked'` (matching new class)
    - Add guard: if no radio is checked (edge case), find first `.dash-acct-radio` element and use its value
    - Function must always return an array of exactly 1 account ID
    - _Requirements: 2.1, 2.2, 2.3, 3.3_

  - [ ] 3.4 Verify bug condition exploration test now passes (Bug 1)
    - **Property 1: Expected Behavior** - Single Account Cost Display
    - **IMPORTANT**: Re-run the SAME test from task 1 (Bug 1 portion) - do NOT write a new test
    - The test from task 1 encodes: `getDashSelectedAccountIds().length === 1` for multi-account configs
    - When this test passes, it confirms the cost aggregation bug is fixed
    - Run bug condition exploration test for Bug 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2_

  - [ ] 3.5 Verify preservation tests still pass (Bug 1)
    - **Property 2: Preservation** - Single-Account Dashboard Rendering
    - **IMPORTANT**: Re-run the SAME tests from task 2 (Bug 1 preservation portion) - do NOT write new tests
    - Run preservation property tests for single-account dashboard behavior
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions in dashboard rendering)
    - Confirm single-account users, tag filtering, account switching, and widget rendering all work identically
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 4. Fix for AI Agent Tool Selection Bug (add fallback logic)

  - [ ] 4.1 Add fallback logic in `_execute_tool()` when `notSupported` is returned
    - In `agent-action/lambda_function.py`, in `_execute_tool()` after the `provider_router.route_tool()` call:
    - Check if `result.get('notSupported') == True` AND `result.get('availableOperations')` is a non-empty list
    - If detected: select the first tool from `availableOperations`, log warning: `logger.warning(f"Tool fallback: {tool_name} -> {fallback_tool} for account {account_id}")`
    - Re-invoke `provider_router.route_tool(fallback_tool, account_id, member_email, parameters)` with the fallback tool name
    - Limit to exactly ONE fallback retry — if fallback result also contains `notSupported`, return the error to the agent with guidance
    - Handle edge case: if `availableOperations` is empty list, return error with message `"Tool not supported for this account. No alternatives available."`
    - _Bug_Condition: response.notSupported == true AND response.availableOperations IS NOT EMPTY_
    - _Expected_Behavior: retry with first applicable operation from availableOperations, return that result_
    - _Preservation: Supported tools execute directly without any fallback overhead_
    - _Requirements: 2.4, 2.5, 2.6_

  - [ ] 4.2 Update `legacy_mapper.py` to remap `/get-ai-vendor-usage` to `getAIUsage`
    - In `agent-action/legacy_mapper.py`, change the mapping entry in `LEGACY_TO_NEUTRAL`:
      - FROM: `'/get-ai-vendor-usage': 'getAIVendorUsage'`
      - TO: `'/get-ai-vendor-usage': 'getAIUsage'`
    - This prevents the wrong tool from being invoked in the first place for the most common case
    - The fallback logic in task 4.1 handles any other `notSupported` scenarios generically
    - _Requirements: 2.4_

  - [ ] 4.3 Verify bug condition exploration test now passes (Bug 2)
    - **Property 1: Expected Behavior** - Tool Fallback on notSupported
    - **IMPORTANT**: Re-run the SAME test from task 1 (Bug 2 portion) - do NOT write a new test
    - The test from task 1 encodes: `_execute_tool("getAIVendorUsage", ...)` should NOT return `notSupported: true`
    - Run bug condition exploration test for Bug 2
    - **EXPECTED OUTCOME**: Test PASSES (confirms tool fallback works correctly)
    - _Requirements: 2.4, 2.5, 2.6_

  - [ ] 4.4 Verify preservation tests still pass (Bug 2)
    - **Property 2: Preservation** - AWS Tool Routing
    - **IMPORTANT**: Re-run the SAME tests from task 2 (Bug 2 preservation portion) - do NOT write new tests
    - Run preservation property tests for supported tool routing
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions in AWS tool routing)
    - Confirm supported tools (getCostBreakdown, getMonthlyTrend, etc.) execute without fallback overhead
    - _Requirements: 3.6, 3.7_

- [ ] 5. Checkpoint - Ensure all tests pass
  - Run full test suite covering both Bug 1 and Bug 2 fixes
  - Verify exploration tests (Property 1) now PASS on fixed code for both bugs
  - Verify preservation tests (Property 2) still PASS on fixed code for both bugs
  - Verify no regressions in:
    - Single-account dashboard data display (correct cost matching invoice)
    - Tag filtering within the single selected account
    - Account switching reactivity (radio change triggers reload)
    - Dashboard widget rendering (waste detection, rightsizing, service breakdown, daily trend)
    - AWS tool routing (getCostBreakdown, getMonthlyTrend, getComputeInstances, etc.)
    - Knowledge tools (getOptimizationTips, getPricingData) continue working without accountId
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- The exploration test (task 1) is expected to FAIL on unfixed code — this confirms both bugs exist
- The preservation tests (task 2) are expected to PASS on unfixed code — they capture existing correct behavior for non-buggy paths
- After implementing the fixes (tasks 3 and 4), both exploration AND preservation tests should PASS
- Bug 1 and Bug 2 are independent fixes that can be implemented in parallel (wave 2)
- The `legacy_mapper.py` change (task 4.2) is a belt-and-suspenders fix: it prevents the wrong tool from being selected, while the fallback logic (task 4.1) handles the general case of any `notSupported` response
- The `populateDashAccounts()` function is at ~line 3390 in `members/members.js`
- The `_execute_tool()` function is at ~line 80 in `agent-action/lambda_function.py`
- The `_sharedSelectedAccounts` sync behavior in other tabs (Act, Chat) is NOT affected — this fix only changes the Observe tab's dropdown rendering
