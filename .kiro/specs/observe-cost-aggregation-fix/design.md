# Observe Cost Aggregation & AI Agent Tool Selection Bugfix Design

## Overview

This design addresses two related bugs in the member portal:

1. **Cost Aggregation Bug**: The Observe tab's dashboard shows inflated cost figures (~$400 instead of ~$141) because the account selector is a multi-select checkbox control with all accounts checked by default. The backend aggregates costs from all selected accounts into a combined total. The fix converts the selector to single-select (radio-style) so exactly one account is displayed at a time.

2. **AI Agent Tool Selection Bug**: The Bedrock AI agent selects the wrong tool (`getAIVendorUsage` via the legacy Knowledge action group path) for OpenAI-type accounts when a user asks about token consumption. The tool returns `notSupported: true` with available operations listed, but the agent retries the same failing tool 4 times instead of falling back to the correct tool (`getAIUsage`). The fix adds automatic fallback logic in the action group handler so that a `notSupported` response triggers a retry with the suggested operation.

## Glossary

- **Bug_Condition (C)**: For Bug 1 — multiple accounts are selected in the Observe tab simultaneously. For Bug 2 — the agent invokes a tool that returns `notSupported` for the target account's provider.
- **Property (P)**: For Bug 1 — exactly one account's cost data is displayed at a time. For Bug 2 — the correct provider-appropriate tool is invoked and returns useful data.
- **Preservation**: Mouse-click behavior, dashboard widget rendering, tag filtering, account switching reactivity, AWS tool routing, and first-attempt success paths must remain unchanged.
- **`populateDashAccounts()`**: Function in `members/members.js` (~line 3400) that renders the account selector dropdown with checkboxes and "Select All"/"Clear" controls.
- **`loadDashboardData()`**: Function in `members/members.js` (~line 3456) that reads checked account IDs and calls the `GET /members/dashboard-data` endpoint.
- **`handle_dashboard_data()`**: Function in `member-handler/lambda_function.py` (~line 2474) that aggregates cost data across all requested account IDs.
- **`route_tool()`**: Function in `agent-action/provider_router.py` (~line 600) that checks `SUPPORTED_OPERATIONS` and returns `notSupported` when a tool is not applicable.
- **`lambda_handler()`**: Function in `agent-action/lambda_function.py` that receives Bedrock Agent action group invocations and dispatches to `_execute_tool()`.
- **`legacy_mapper`**: Module that maps API paths like `/get-ai-vendor-usage` to tool names like `getAIVendorUsage`.

## Bug Details

### Bug Condition

The system has two independent bug conditions:

**Bug 1 — Cost Aggregation**: The bug manifests when the Observe tab loads with multiple accounts connected. The `populateDashAccounts()` function creates checkboxes with `cb.checked = true` for every account, causing `getDashSelectedAccountIds()` to return multiple IDs. The `loadDashboardData()` function passes all IDs to the backend, which iterates over each account, queries costs separately, and merges them into a single aggregate response.

**Bug 2 — AI Agent Tool Selection**: The bug manifests when the Bedrock Agent selects the `getAIVendorUsage` tool (mapped from the legacy `/get-ai-vendor-usage` path) for a non-AWS provider account (e.g., openai). The `route_tool()` function in `provider_router.py` checks `connector.SUPPORTED_OPERATIONS` and returns `notSupported: true` with an `availableOperations` list. The agent receives this response but does not interpret it as a signal to retry with a different tool — it simply retries the same failing invocation up to 4 times.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type {context: "observe_tab" | "agent_tool_call", ...}
  OUTPUT: boolean
  
  IF input.context == "observe_tab":
    RETURN input.selectedAccountCount > 1
  
  IF input.context == "agent_tool_call":
    RETURN input.toolName == "getAIVendorUsage"
           AND input.accountProvider NOT IN connector.SUPPORTED_OPERATIONS_FOR(input.toolName)
           AND response.notSupported == true
           AND response.availableOperations IS NOT EMPTY
  
  RETURN false
END FUNCTION
```

### Examples

- **Bug 1 Example 1**: User has AWS account (invoice $141) and OpenAI account (invoice $259). Observe tab loads → both checked → backend returns $400 total → user sees inflated cost.
- **Bug 1 Example 2**: User has 3 AWS accounts ($100, $200, $50). Dashboard shows $350 instead of the first account's $100.
- **Bug 1 Example 3**: User has 1 account ($141). Dashboard correctly shows $141 (no aggregation occurs — this is the non-buggy path).
- **Bug 2 Example 1**: User asks "how many tokens did I use?" for OpenAI account → agent picks `getAIVendorUsage` → returns `notSupported` with `availableOperations: ["getCostBreakdown", "getAIUsage", "getMonthlyTrend"]` → agent retries same tool 3 more times → user gets unhelpful error.
- **Bug 2 Example 2**: User asks about AWS AI spend → agent picks correct tool → works on first try (non-buggy path).
- **Bug 2 Edge Case**: Tool returns `notSupported` but `availableOperations` is empty → should fail gracefully with error message rather than retrying.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Mouse clicks on dashboard widgets and all interactive elements must continue working
- Dashboard widget rendering (waste detection, rightsizing, service breakdown, daily trend) must remain unchanged
- Tag filtering within the selected account must continue to work
- Account switching reactivity (reload on selection change) must be preserved
- Single-account users must see their data without requiring manual selection
- AWS accounts using `getCostData` flow must continue using the same path
- Successful first-attempt tool selections must execute without retry overhead
- The `route_tool()` function's `notSupported` response format must remain unchanged for backward compatibility

**Scope:**
All inputs that do NOT involve multi-account selection or legacy `getAIVendorUsage` invocations should be completely unaffected by this fix. This includes:
- Single-account Observe tab loads
- AI agent queries that select the correct tool on first attempt
- All Chat tab and Act tab functionality
- Mouse/touch interactions with dashboard elements
- API calls that already pass a single accountId

## Hypothesized Root Cause

Based on the bug analysis, the root causes are:

1. **Bug 1 — Default Selection Logic**: In `populateDashAccounts()` (members.js ~line 3423), every account checkbox is created with `cb.checked = true`. This means `getDashSelectedAccountIds()` always returns ALL accounts. The backend `handle_dashboard_data()` iterates over all provided account IDs and merges costs into a single aggregate without per-account distinction in the KPI bar.

2. **Bug 1 — UI Control Type**: The account selector uses `<input type="checkbox">` elements, which inherently allow multi-select. The dropdown panel includes "Select All" and "Clear" links reinforcing multi-select behavior.

3. **Bug 2 — Legacy Path Still Mapped**: The `legacy_mapper.py` still maps `/get-ai-vendor-usage` → `getAIVendorUsage`, but `getAIVendorUsage` was removed from `TOOL_TO_METHOD` in `provider_router.py` (replaced by `getAIUsage`). When the agent selects the Knowledge action group with this legacy path, the router cannot find it in `TOOL_TO_METHOD` and returns "Unknown tool" — or if the agent somehow invokes a tool the connector doesn't support, it gets `notSupported`.

4. **Bug 2 — No Fallback Logic in Lambda Handler**: The `lambda_handler()` in `agent-action/lambda_function.py` returns the raw `notSupported` response to the Bedrock Agent. The agent interprets this as a tool execution result (not an error signal), so it retries the same tool repeatedly without understanding it should switch tools.

## Correctness Properties

Property 1: Bug Condition - Single Account Cost Display

_For any_ Observe tab load where multiple accounts are connected (isBugCondition returns true for context "observe_tab"), the fixed `populateDashAccounts()` function SHALL render a single-select radio-style control with exactly one account selected, and `getDashSelectedAccountIds()` SHALL return an array of length 1 containing only the selected account's ID.

**Validates: Requirements 2.1, 2.2**

Property 2: Bug Condition - Tool Fallback on notSupported

_For any_ agent tool invocation where the response contains `notSupported: true` with a non-empty `availableOperations` list (isBugCondition returns true for context "agent_tool_call"), the fixed `_execute_tool()` function SHALL automatically retry with the first applicable operation from `availableOperations` and return that result to the agent.

**Validates: Requirements 2.4, 2.5, 2.6**

Property 3: Preservation - Dashboard Widget Rendering

_For any_ single-account dashboard data request (isBugCondition returns false), the fixed code SHALL produce the same dashboard widget data, KPI values, and chart rendering as the original code, preserving all existing functionality for single-account views.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

Property 4: Preservation - AWS Tool Routing

_For any_ agent tool invocation where the tool IS supported by the connector (isBugCondition returns false for context "agent_tool_call"), the fixed code SHALL execute the tool directly without any fallback overhead, preserving the existing routing path for AWS and other correctly-matched tools.

**Validates: Requirements 3.6, 3.7**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `members/members.js`

**Function**: `populateDashAccounts()`

**Specific Changes**:
1. **Replace checkbox with radio buttons**: Change `cb.type = 'checkbox'` to `cb.type = 'radio'` and add a shared `name` attribute (e.g., `name='dash-acct-radio'`) so only one can be selected at a time.
2. **Default to first account**: Set `cb.checked = true` only for the first account (`index === 0`), not all accounts.
3. **Remove "Select All" and "Clear" links**: These are irrelevant for single-select. Replace with simpler label text showing the selected account.
4. **Update CSS class**: Change `dash-acct-cb` to `dash-acct-radio` (or keep the class but update the selector behavior).
5. **Update `getDashSelectedAccountIds()`**: Modify to query `.dash-acct-cb:checked` (or new class) and always return exactly one account ID.
6. **Remove shared multi-account sync**: Remove `_sharedSelectedAccounts` syncing for the Observe tab or limit it to single-value.

**File**: `agent-action/lambda_function.py`

**Function**: `_execute_tool()`

**Specific Changes**:
1. **Add fallback logic after `route_tool()` returns**: After calling `provider_router.route_tool()`, check if the result contains `notSupported: true` with a non-empty `availableOperations` list.
2. **Retry with first applicable operation**: If `notSupported` is detected, select the first tool from `availableOperations` that exists in `TOOL_TO_METHOD`, and re-invoke `provider_router.route_tool()` with that tool name.
3. **Limit retries to exactly one fallback**: Only attempt one automatic retry to prevent infinite loops. If the fallback also returns `notSupported`, return the error to the agent.
4. **Log the fallback for observability**: Log a warning when automatic fallback is triggered so it appears in CloudWatch for audit purposes.

**File**: `agent-action/legacy_mapper.py`

**Specific Changes**:
1. **Remap legacy path**: Change `/get-ai-vendor-usage` mapping from `getAIVendorUsage` to `getAIUsage` so that even if the agent selects the legacy Knowledge path, it routes to the correct modern tool.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bugs on unfixed code, then verify the fixes work correctly and preserve existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate both bugs BEFORE implementing the fix. Confirm or refute the root cause analysis.

**Test Plan**: For Bug 1, render the account selector with 2+ accounts and assert that `getDashSelectedAccountIds()` returns multiple IDs. For Bug 2, invoke the agent action lambda with a `getAIVendorUsage` tool call for an OpenAI account and observe the `notSupported` response without fallback.

**Test Cases**:
1. **Multi-Account Default Selection**: Load Observe tab with 2 accounts → assert all checkboxes checked (will confirm bug on unfixed code)
2. **Cost Aggregation**: Call `handle_dashboard_data` with 2 accountIds → assert total is sum of both (will confirm bug on unfixed code)
3. **Agent Tool Selection**: Invoke `_execute_tool("getAIVendorUsage", openai_account_id, ...)` → assert response contains `notSupported: true` (will confirm bug on unfixed code)
4. **No Fallback**: Verify that `notSupported` response is returned directly without retry attempt (will confirm bug on unfixed code)

**Expected Counterexamples**:
- `getDashSelectedAccountIds()` returns `["acct1", "acct2"]` when 2 accounts exist
- `handle_dashboard_data` returns merged costs from both accounts ($141 + $259 = $400)
- `_execute_tool("getAIVendorUsage", ...)` returns `{notSupported: true, availableOperations: [...]}` without attempting `getAIUsage`

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed functions produce the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  IF input.context == "observe_tab":
    result := populateDashAccounts_fixed(input.accounts)
    ASSERT getDashSelectedAccountIds().length == 1
    ASSERT dashboardData.totalSpend == singleAccountInvoice

  IF input.context == "agent_tool_call":
    result := _execute_tool_fixed(input.toolName, input.accountId, ...)
    ASSERT result.notSupported IS UNDEFINED OR result HAS valid data
    ASSERT retryCount <= 1
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed functions produce the same result as the original functions.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  IF input.context == "observe_tab":
    ASSERT populateDashAccounts_original(input) renders same as populateDashAccounts_fixed(input)
    // Single-account case: same data displayed

  IF input.context == "agent_tool_call":
    ASSERT route_tool_original(input) == route_tool_fixed(input)
    // Supported tools: no fallback triggered, same result
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many random account configurations and tool invocations automatically
- It catches edge cases (empty account lists, single accounts, tools at boundary of SUPPORTED_OPERATIONS)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for single-account dashboard loads and supported tool invocations, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Single Account Dashboard**: Verify single-account users see correct data both before and after fix
2. **Supported Tool Routing**: Verify AWS `getCostBreakdown` continues to work without fallback
3. **Tag Filter Preservation**: Verify tag filters still apply within the single selected account
4. **Account Switching**: Verify selecting a different account reloads dashboard data
5. **Widget Rendering**: Verify all dashboard widgets render identically for single-account queries

### Unit Tests

- Test `populateDashAccounts()` renders radio buttons instead of checkboxes
- Test `getDashSelectedAccountIds()` returns exactly 1 ID after fix
- Test `_execute_tool()` fallback logic when `notSupported` is returned
- Test `_execute_tool()` does NOT fallback when tool succeeds
- Test `_execute_tool()` limits fallback to exactly 1 retry
- Test legacy mapper resolves `/get-ai-vendor-usage` to `getAIUsage`
- Test edge case: `notSupported` with empty `availableOperations` returns error

### Property-Based Tests

- Generate random sets of 1-5 accounts and verify the selector always picks exactly 1
- Generate random tool names and provider combinations, verify fallback only triggers on `notSupported` with non-empty `availableOperations`
- Generate random dashboard-data requests with single accountId and verify response matches direct per-account query
- Generate random sequences of account selection changes and verify each triggers exactly one API call with one accountId

### Integration Tests

- Full Observe tab load with 3 accounts → verify single account displayed with correct invoice amount
- Agent invocation flow: OpenAI account → token question → verify `getAIUsage` result returned (not `notSupported`)
- Agent invocation flow: AWS account → cost question → verify `getCostBreakdown` works without fallback
- Tag filter + single account selection → verify filtered costs match expected values
- Account switching sequence → verify each switch shows correct single-account data
