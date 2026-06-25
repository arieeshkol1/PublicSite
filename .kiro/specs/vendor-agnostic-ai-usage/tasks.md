# Implementation Plan: Vendor-Agnostic AI Usage

## Overview

This plan converts the vendor-agnostic AI usage design into incremental Python coding steps for the SlashMyBill `member-handler` and `agent-action` Lambdas plus `infrastructure/`. It starts at the data layer (vendor-neutral cache schema + connector field mapping), builds the `get_ai_usage` connector contract, layers the three-tier resolver and Tips drilldown on top, wires the Provider_Router and Knowledge action group, replaces the OpenAI short-circuit in `handle_ai_query`, migrates the member-portal AI dashboard data path (`handle_dashboard_data`, the OpenAI dashboard data path, the per-user token graph endpoint, and `_refresh_cost_cache_for_account`) and `members/members.js` widgets onto the neutral schema and shared resolver, and finishes with the sensitive operations (migration, IAM, deploy) sequenced last and behind the pipeline.

Guardrails honored throughout: cache-first (Tier 1 always runs first), customer-connection-only (no platform AI spend), single-account per invocation, production DynamoDB writes are backup-first and run via GitHub Actions (the local user lacks scan/write), and all deploys happen via git push.

Implementation language: **Python** (matches existing `member-handler/` and `agent-action/` code). Property-based tests use Hypothesis with mocked DynamoDB/KMS/HTTP, ≥100 iterations each.

## Tasks

- [x] 1. Vendor-neutral cache schema helpers and neutral read/write
  - [x] 1.1 Add neutral key builders and item shapers in cache layer
    - In `member-handler/cache_service.py`, add helpers to build `COST#{date}` and `USAGE#{date}#{actor}#{service}` sort keys and to shape `CostRollupItem`/`UsageDetailItem` dicts with required neutral fields (`pk={memberEmail}#{accountId}`, cost amount, currency, `cached_at`; detail: usage quantity, unit, cost amount, actor, service)
    - Set absent neutral fields to `null` rather than omitting them
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6_

  - [x] 1.2 Implement neutral COST#/USAGE# window read and write-back in the fetch engine
    - In `member-handler/incremental_fetch_engine.py`, implement reading a window via `Key('pk').eq(pk) & Key('sk').between('COST#{start}','COST#{end}')` (and USAGE# equivalents) and a write-back path that persists neutral items produced by Tier 2/Tier 3
    - Reuse `cost_normalizer` output where available; do not touch the AWS `DAILY#` path
    - _Requirements: 2.1, 2.2, 4.6_

  - [x]* 1.3 Write property test for neutral schema and key format
    - **Property 3: Cached items conform to the neutral schema and key format**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 6.3**
    - Generate random write inputs; assert sort keys match `COST#{date}` / `USAGE#{date}#{actor}#{service}` and all required fields present (mock DynamoDB)

- [x] 2. Base connector contract and AIVendorConnector.get_ai_usage
  - [x] 2.1 Add get_ai_usage to the base CloudConnector contract
    - In `agent-action/connectors/` base connector, add `get_ai_usage(account_id, member_email, params)` raising `NotImplementedError` by default so AWS/Azure/GCP inherit it
    - _Requirements: 1.5, 11.3_

  - [x] 2.2 Implement AIVendorConnector.get_ai_usage with field mapping and dimension projection
    - In `agent-action/connectors/ai_vendor_connector.py`, implement `get_ai_usage` reusing `_fetch_usage_data` / `fetch_per_user_daily_usage` / `cost_normalizer`; map raw fields per the field-mapping table (tokens→units, user_id→actor, model→service, currency uppercased default USD)
    - Add `"getAIUsage"` to `SUPPORTED_OPERATIONS`; project by `dimension` (`cost`→rollups, `units`→grouped quantity, `actor`→detail grouped by actor); default window to last 30 days when `period` absent
    - Set neutral fields with no source to `null`
    - _Requirements: 1.2, 2.5, 2.6, 3.6, 11.2_

  - [x]* 2.3 Write property test for vendor-to-neutral field mapping
    - **Property 4: Vendor fields map onto neutral fields, with nulls for missing sources**
    - **Validates: Requirements 2.5, 2.6**
    - Generate raw OpenAI buckets including missing `user_id`/`model`/token fields and non-ASCII actors; assert mapping direction and null-not-omitted (mock HTTP)

  - [x]* 2.4 Write property test for default 30-day window
    - **Property 5: Default resolution window is the most recent 30 days**
    - **Validates: Requirements 3.6**

  - [x]* 2.5 Write property test for unsupported-connector response
    - **Property 2: Unsupported connectors return a structured notSupported response**
    - **Validates: Requirements 1.5**
    - Assert routing `getAIUsage` to AWS/Azure/GCP connectors yields `notSupported = true` and never raises

- [x] 3. Three-tier resolver, staleness, and Tips drilldown executor
  - [x] 3.1 Implement resolve_ai_usage orchestrator with cache-first tier ordering
    - In the AI_Usage_Service (`member-handler/cache_service.py` / `incremental_fetch_engine.py`), implement `resolve_ai_usage(member_email, account_id, dimension, service, period)`: Tier 1 cache read first, short-circuit on fresh full coverage with no service scope, else Tier 2, else bounded Tier 3
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 11.1_

  - [x] 3.2 Implement staleness check and the five Tier-2 triggers
    - Add `within_staleness` using `AI_USAGE_STALENESS_HOURS` (default 48h); implement trigger predicate as union of T1 missing-latest, T2 gap, T3 specific-service, T4 empty, T5 stale
    - _Requirements: 4.5, 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 3.3 Implement Tips-drilldown executor via customer connection (Tier 2)
    - In `member-handler/provider_invoices.py`, query `ViewMyBill-CostOptimizationTips` for `drilldownApis`/`checkConnection`, load customer credentials via the existing `_get_credentials`/KMS path scoped to `(memberEmail, accountId)`, execute drilldown through `AIVendorConnector`, normalize to `Usage_Detail_Item`, and write back to cache
    - Return a structured "configure connection in Configure tab" error when credentials are missing
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 4.6_

  - [x] 3.4 Implement bounded/async Tier-3 live call and response builder with cap
    - Implement Tier 3 reusing the existing 20s `ThreadPoolExecutor` bound; on timeout return best Tier-1/Tier-2 result with `live_partial=true`; build `AIUsageResponse` capping to top-N highest-cost entries with `truncated=true`; return admin-key-required message when Tier 3 needs an Admin_Key the account lacks
    - _Requirements: 4.4, 4.6, 12.1, 12.2, 12.3, 12.4_

  - [x]* 3.5 Write property test for cache-first strict tier ordering
    - **Property 6: Resolution is cache-first and tiers run in strict order**
    - **Validates: Requirements 4.1, 4.3, 4.4, 11.1**

  - [x]* 3.6 Write property test for fresh full-coverage short-circuit
    - **Property 7: Fresh full-coverage cache short-circuits deeper tiers**
    - **Validates: Requirements 4.2**

  - [x]* 3.7 Write property test for exact staleness comparison
    - **Property 8: Staleness is an exact age comparison**
    - **Validates: Requirements 4.5**
    - Include `cached_at` exactly at the threshold edge case

  - [x]* 3.8 Write property test for Tier-2 trigger predicate
    - **Property 9: Tier-2 trigger predicate is exactly the union of the five conditions**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

  - [x]* 3.9 Write property test for Tier-2/Tier-3 write-back under neutral keys
    - **Property 10: Tier-2/Tier-3 results are written back under neutral keys**
    - **Validates: Requirements 4.6**

  - [x]* 3.10 Write property test for customer-credential single-account retrieval
    - **Property 11: All AI usage retrieval uses customer credentials for exactly one account**
    - **Validates: Requirements 6.1, 6.2, 11.2, 11.3, 8.4**

  - [x]* 3.11 Write property test for response capping
    - **Property 15: Responses are capped to the highest-cost entries**
    - **Validates: Requirements 12.2**

  - [x]* 3.12 Write property test for bounded Tier-3 degradation
    - **Property 16: Tier 3 is bounded and degrades to the best lower-tier result**
    - **Validates: Requirements 12.3, 12.4**

  - [x]* 3.13 Write unit tests for Tier-2 credential and Tier-3 admin-key errors
    - Missing customer credentials at Tier 2 → structured Configure-tab error (Req 6.4)
    - Admin-key gap at Tier 3 → structured "admin-level key" message (Req 12.1)
    - _Requirements: 6.4, 12.1_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Provider_Router wiring
  - [x] 5.1 Register getAIUsage in TOOL_TO_METHOD and neutral cache prefix
    - In `agent-action/provider_router.py`, map `getAIUsage` → `get_ai_usage`, remove the superseded `getAIVendorUsage` entry (keep map at 22), and replace the `OPENAI_DAILY#` prefix in `_read_cost_cache`/`_write_cost_cache` with the neutral `COST#` family for `ai_vendor` accounts (AWS `DAILY#` untouched)
    - _Requirements: 1.1, 1.3, 1.4_

  - [x]* 5.2 Update provider router tests for getAIUsage
    - Assert `TOOL_TO_METHOD['getAIUsage'] == 'get_ai_usage'` and `len(TOOL_TO_METHOD) == 22`; update `test_all_expected_tools_mapped` to expect `getAIUsage`
    - _Requirements: 1.3, 1.4_

  - [x]* 5.3 Write property test for provider selection purity
    - **Property 1: Provider selection is a pure function of cloudProvider**
    - **Validates: Requirements 1.1, 1.2**

- [x] 6. Knowledge schema and agent instructions
  - [x] 6.1 Add /get-ai-usage operation to knowledge.json
    - In `agent-action/schemas/knowledge.json`, define `getAIUsage` at `/get-ai-usage` with required `accountId`/`memberEmail`/`dimension` (enum `cost,units,actor`) and optional `service`/`period`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 6.2 Update agent-instructions.txt to describe getAIUsage
    - Document the vendor-agnostic tool and its dimensions in `agent-action/agent-instructions.txt`
    - _Requirements: 10.2_

  - [x]* 6.3 Write unit test asserting knowledge.json schema facts
    - Assert `/get-ai-usage`, `operationId getAIUsage`, required params and enum values
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 7. Intent gate in handle_ai_query
  - [x] 7.1 Implement vendor-agnostic intent gate and remove OpenAI short-circuit
    - In `member-handler/lambda_function.py`, add `is_ai_cost_or_usage_question` classifier and route classified `ai_vendor` single-account questions to `resolve_ai_usage_response`; replace the `_answer_openai_query` short-circuit; non-AI-cost questions fall through to `_invoke_bedrock_agent` unchanged
    - Remove `OPENAI_DAILY#` reads inside `_invoke_bedrock_agent`; surface graceful-degradation messages (cap/partial) from the resolver
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 9.6, 12.2, 12.3_

  - [x]* 7.2 Write property test for intent-gate routing
    - **Property 12: Intent gate routes AI-cost questions to the neutral path and others unchanged**
    - **Validates: Requirements 8.1, 8.3**

  - [x]* 7.3 Write property test for post-cutover neutral-only reads
    - **Property 14: Post-cutover reads use only neutral keys**
    - **Validates: Requirements 9.6**

  - [x]* 7.4 Write unit test that _answer_openai_query is not invoked on neutral path
    - _Requirements: 8.2_

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. AI dashboard data path on the neutral cache
  - [x] 9.1 Migrate handle_dashboard_data and the OpenAI dashboard data path to neutral reads + shared resolver
    - In `member-handler/lambda_function.py`, change `handle_dashboard_data` and the OpenAI dashboard data path to resolve the connector via the account's `cloudProvider` through `Provider_Router` (no vendor-specific branching), perform Tier-1 neutral reads of `COST#` rollups and `USAGE#` detail for the window, and on missing/stale data call the shared `resolve_ai_usage` (which writes neutral items back); remove the `OPENAI_DAILY#` reads on this path; build the neutral dashboard payload shape (`rollups[]`/`usage[]`) for `members/members.js`; retrieve data exclusively from the Customer_Connection (never platform AI spend) and resolve exactly one account per request
    - _Requirements: 13.1, 13.2, 13.4, 13.6, 9.7, 11.4, 11.5_

  - [x] 9.2 Migrate the per-user token consumption graph endpoint to neutral USAGE# reads
    - In `member-handler/lambda_function.py` (~lines 13332–13389), change the per-user token consumption graph endpoint to read `Usage_Detail_Item` records keyed by `actor` and `service` from the `USAGE#` family instead of `OPENAI_DAILY#`, grouping tokens by actor for the graph; customer-connection-only, single account
    - _Requirements: 13.5, 9.7, 11.4, 11.5_

  - [x] 9.3 Migrate _refresh_cost_cache_for_account to write the neutral schema via the shared resolver
    - In `member-handler/lambda_function.py`, change `_refresh_cost_cache_for_account` to call the shared `resolve_ai_usage` and persist `Cost_Rollup_Item`/`Usage_Detail_Item` records via the same `write_cache` used by the resolver, never `OPENAI_DAILY#`; customer-connection-only, single account
    - Production cache writes are backup-first and run via the GitHub Actions pipeline (the local user lacks DynamoDB write)
    - _Requirements: 13.3, 13.6, 11.4, 11.5_

  - [x] 9.4 Render AI_Dashboard_Widgets from the neutral payload in members.js
    - In `members/members.js`, update the AI_Dashboard_Widgets (AI cost summary, per-model cost breakdown, per-user token consumption graph) to render from the neutral payload shape (`rollups[]`/`usage[]`) returned by `handle_dashboard_data`
    - Bump the `members.js` cache-busting `?v=N` query string wherever the script is referenced (e.g. `members/index.html`) so the updated JS is picked up
    - _Requirements: 13.7_

  - [x]* 9.5 Write property test for dashboard neutral-only reads
    - **Property 17: Dashboard data path reads only neutral keys**
    - **Validates: Requirements 9.7, 13.1, 13.2, 13.5**
    - Generate random neutral/legacy cache mixes; assert dashboard reads (cost summary, per-model breakdown, per-user token graph) issue only `COST#`/`USAGE#` key conditions — the per-user graph reading `Usage_Detail_Item` by actor/service — and never `OPENAI_DAILY#` (mock DynamoDB)

  - [x]* 9.6 Write property test for dashboard neutral writes and customer-scoped single-account refresh
    - **Property 18: Dashboard refresh writes neutral schema and stays customer-scoped single-account**
    - **Validates: Requirements 13.3, 13.6, 11.4, 11.5**
    - Generate random refresh inputs; assert every item written by `_refresh_cost_cache_for_account` matches the neutral `COST#{date}`/`USAGE#{date}#{actor}#{service}` schema and that retrieval loads credentials scoped to the single `(memberEmail, accountId)` pair, never platform-owned AI spend (mock DynamoDB/KMS)

  - [x]* 9.7 Write example test for the members.js neutral payload contract
    - Assert the `handle_dashboard_data` payload exposes the neutral cost-summary, per-model, and per-user token-graph fields consumed by `members/members.js`
    - _Requirements: 13.7_

- [x] 10. Migration job (OPENAI_DAILY# -> COST#/USAGE#)
  - [x] 10.1 Implement idempotent migration script
    - Create `infrastructure/migrate_openai_daily.py` scanning `OPENAI_DAILY#` items, writing `COST#{date}` rollups and `USAGE#{date}#{actor}#{service}` detail with `PutItem` keyed by `(pk, sk)` (overwrite-by-key), preserving cost amount, currency, and date; on any write failure, log the failed count and `sys.exit(1)`, else `sys.exit(0)`
    - Emit `Cost_Rollup_Item` and `Usage_Detail_Item` records sufficient to render the AI_Dashboard_Widgets without pre-cutover data loss — per-actor/per-service detail in `OPENAI_DAILY#` items becomes `USAGE#{date}#{actor}#{service}` records that back the per-user token graph
    - Production scan/write runs backup-first via the pipeline (GitHubDeployRole); the local user lacks DynamoDB scan/write
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.8_

  - [x]* 10.2 Write property test for migration data-preservation and idempotency
    - **Property 13: Migration preserves data and is idempotent**
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.8**
    - Run migration twice over generated `OPENAI_DAILY#` sets; assert identical cache state (mock DynamoDB)
    - Extend generators to include `OPENAI_DAILY#` items with per-actor/per-service detail and assert the resulting `USAGE#` detail is sufficient to render the AI_Dashboard_Widgets (Req 9.8)

  - [x]* 10.3 Write unit test for migration failure exit code
    - Forced write failure → non-zero exit and logged failed count
    - _Requirements: 9.5_

- [x] 11. IAM permission updates
  - [x] 11.1 Add scoped IAM permissions to deployment definitions
    - In `.github/workflows/deploy.yml` (and supporting `infrastructure/` definitions), add cache read+write on `COST#`/`USAGE#` keys, `ViewMyBill-CostOptimizationTips` read, `MemberPortal-Invoices` read, and `kms:Decrypt` scoped to the credential CMK with `{memberEmail, accountId}` encryption context
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 11.2 Write integration test asserting IAM policy contents
    - Assert deployment policy documents include cache RW on neutral keys, Tips read, Invoices read, and scoped KMS decrypt
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 12. Deploy orchestration and agent preparation
  - [x] 12.1 Wire getAIUsage into deploy-agent-action-groups.py
    - Ensure `infrastructure/deploy-agent-action-groups.py` re-uploads the Knowledge schema, re-applies instructions, calls `PrepareAgent`, and updates the alias in order; each step logs the failing step and exits non-zero on failure
    - Deploy runs via git push (GitHub Actions), not locally
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 12.2 Write integration test for deploy step ordering and failure exit
    - Mock the Bedrock client; assert order action-group-update → instructions-update → PrepareAgent → alias-update and non-zero exit on a forced step failure
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all property, unit, and integration tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP; core implementation sub-tasks must be implemented.
- Each task references specific requirements/properties for traceability.
- Property tests (Properties 1-18) run ≥100 iterations with mocked DynamoDB/KMS/HTTP and are tagged `Feature: vendor-agnostic-ai-usage, Property {number}`.
- The AI dashboard data path (Task 9) shares the neutral cache, `Provider_Router` connector resolution, and the three-tier `resolve_ai_usage` resolver with the chat path; Properties 17 and 18 cover its neutral reads and neutral/customer-scoped refresh.
- Task 9.4 changes `members/members.js`; bump the `?v=N` cache-busting query string on the script reference so the updated widgets are served.
- Sensitive operations are sequenced last: the migration job (10) and deploy (12) run backup-first and via the GitHub Actions pipeline because the local user lacks DynamoDB scan/write and deploys happen via git push. Dashboard production cache writes (9.3) are likewise backup-first via the pipeline.
- Guardrails enforced structurally: cache-first ordering, customer-connection-only retrieval, single-account per invocation — applied to both the chat path and the dashboard path.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "6.1", "6.2", "10.1", "11.1"] },
    { "id": 1, "tasks": ["1.2", "2.2", "1.3", "5.1", "6.3", "10.2", "10.3", "11.2", "12.1"] },
    { "id": 2, "tasks": ["2.3", "2.4", "2.5", "3.1", "5.2", "5.3", "12.2"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4"] },
    { "id": 4, "tasks": ["3.5", "3.6", "3.7", "3.8", "3.9", "3.10", "3.11", "3.12", "3.13", "7.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "7.4", "9.1", "9.4"] },
    { "id": 6, "tasks": ["9.2"] },
    { "id": 7, "tasks": ["9.3"] },
    { "id": 8, "tasks": ["9.5", "9.6", "9.7"] }
  ]
}
```
