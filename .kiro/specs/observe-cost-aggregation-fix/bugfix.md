# Bugfix Requirements Document

## Introduction

The Observe tab's cost dashboard shows inflated cost figures because the account selector dropdown is a multi-select (checkbox) control with all accounts checked by default. When multiple accounts are selected, the backend aggregates costs from all of them and returns a combined total. For a linked account with a real invoice of ~$141, the dashboard incorrectly displays ~$400 because it sums costs from 2 selected accounts. The fix requires converting the account selector to single-select and ensuring the account-scoped filter is correctly applied for exactly one account at a time.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user has multiple connected accounts AND the observe tab loads THEN the system selects ALL accounts by default (checkboxes all checked) and displays the summed cost across all selected accounts

1.2 WHEN a user views the observe tab with 2 or more accounts selected THEN the system returns a total spend that is the aggregate of costs from all selected accounts, showing an inflated figure that does not match any single account's actual invoice

1.3 WHEN the dashboard-data API receives multiple account IDs in the query string THEN the system iterates over all accounts, queries the cost API for each, and merges all costs into a single response without distinguishing per-account totals in the KPI bar

1.4 WHEN a user with an OpenAI-type account asks about token consumption AND the AI agent processes the query THEN the system selects the getAIVendorUsage tool (via Knowledge action group) which returns notSupported for openai accounts, and the agent retries the same failing tool up to 4 times before returning an unhelpful response

1.5 WHEN the Knowledge action group returns notSupported with availableOperations list THEN the AI agent does NOT retry with any of the suggested available operations (getAIUsage) and instead reports the tool failure to the user

### Expected Behavior (Correct)

2.1 WHEN a user has multiple connected accounts AND the observe tab loads THEN the system SHALL display a single-select dropdown (radio-style, not checkboxes) with exactly one account selected at a time (defaulting to the first connected account)

2.2 WHEN a user selects an account in the observe tab THEN the system SHALL display cost data for only that single account, matching the actual invoice amount for that account

2.3 WHEN the dashboard-data API receives a single account ID THEN the system SHALL apply the account-scoped filter for that account and return costs scoped to only that account

2.4 WHEN a user with a non-AWS provider account (e.g., openai) asks about usage or token consumption THEN the system SHALL route the query to the provider-appropriate tool (getAIUsage for openai accounts) without first attempting getAIVendorUsage

2.5 WHEN any tool returns a notSupported response with an availableOperations list THEN the system SHALL automatically retry with the first applicable operation from that list rather than failing

2.6 WHEN a tool invocation fails THEN the system SHALL NOT retry the same tool with the same parameters more than once

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user switches between accounts using the single-select dropdown THEN the system SHALL CONTINUE TO reload dashboard data for the newly selected account (same reactive behavior as before)

3.2 WHEN the cost API is called for an individual account THEN the system SHALL CONTINUE TO apply the account-scoped dimension filter correctly

3.3 WHEN a user has only one connected account THEN the system SHALL CONTINUE TO display that account's data without requiring manual selection

3.4 WHEN the dashboard-data API receives a valid account ID THEN the system SHALL CONTINUE TO return all existing dashboard widgets (waste detection, rightsizing, service breakdown, daily trend, etc.)

3.5 WHEN a tag filter is applied alongside the account selector THEN the system SHALL CONTINUE TO filter costs by the selected tag within the single selected account

3.6 WHEN a user with an AWS-type account asks about AI/ML spend THEN the system SHALL CONTINUE TO use the existing getCostData flow as documented in the agent's tool selection guide

3.7 WHEN the AI agent successfully selects the correct tool on first attempt THEN the system SHALL CONTINUE TO execute normally without any retry overhead
