# Implementation Plan: Multi-Tag Cost Cache

## Overview

Enhance the cost data cache to discover all active cost allocation tag keys, query Cost Explorer sequentially for each, store results in a nested structure, and update the dashboard read path to use cached multi-tag data with backward compatibility for the legacy flat format.

## Tasks

- [x] 1. Update data model and add utility functions
  - [x] 1.1 Update `CostDataItem` in `cache_types.py` to use nested tag_breakdown type
    - Change `tag_breakdown` type annotation from `dict[str, float]` to `dict[str, dict[str, float]]`
    - Update the docstring to describe the nested format: `{tag_key: {tag_value: cost_amount}}`
    - _Requirements: 3.1, 3.2_

  - [x] 1.2 Add `normalize_tag_breakdown` function to `cache_types.py`
    - Implement format detection: check if first value is a dict (nested) or number/string (flat)
    - Implement flat-to-nested conversion: split "tagKey=tagValue" keys, group under tag keys
    - Handle keys without "=" separator by placing under "unknown" tag key
    - Pass-through nested format with string-to-float conversion
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 1.3 Add constants `TOP_N_CAP_DEFAULT = 50` and `SIZE_LIMIT_BYTES = 350 * 1024` to `incremental_fetch_engine.py`
    - _Requirements: 4.1, 5.3_

- [x] 2. Implement multi-tag discovery and sequential querying
  - [x] 2.1 Add `_discover_active_tag_keys` method to `IncrementalFetchEngine`
    - Call `ce_client.get_tags()` with the refresh date range
    - Return all tag key strings on success
    - Log warning and return empty list on API failure (graceful degradation)
    - Log info and return empty list when no tags found
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 2.2 Add `_call_ce_for_single_tag` method to `IncrementalFetchEngine`
    - Accept `ce_client`, `date_range`, `tag_key`, `max_retries`, `base_delay` parameters
    - Call `get_cost_and_usage` with `GroupBy=[{'Type': 'TAG', 'Key': tag_key}]` and DAILY granularity
    - Implement exponential backoff retry for transient errors (same codes as `_call_ce_with_retry`)
    - Return `None` on failure after retry exhaustion (log warning with tag key name and error code)
    - _Requirements: 2.1, 2.2, 2.4, 10.4_

  - [x] 2.3 Add `_parse_single_tag_response` method to `IncrementalFetchEngine`
    - Parse CE response into `{date: {tag_value: cost}}` structure
    - Handle CE key format `tagKey$tagValue` — extract value after `$`
    - Store empty/missing tag values as "(untagged)"
    - Exclude zero-cost entries
    - _Requirements: 3.1, 3.3, 3.4_

  - [x] 2.4 Add `_fetch_all_tag_breakdowns` method to `IncrementalFetchEngine`
    - Call `_discover_active_tag_keys` to get all tag keys
    - Loop sequentially through each tag key, calling `_call_ce_for_single_tag`
    - Parse each successful response with `_parse_single_tag_response`
    - Log error if all queries fail, warning if some fail
    - Return `{tag_key: {date: {value: cost}}}` with only successful keys
    - _Requirements: 2.1, 2.2, 2.3, 10.1, 10.2, 10.3_

  - [ ]* 2.5 Write property test for tag response parsing (Property 1)
    - **Property 1: Tag response parsing produces valid nested format**
    - Generate random CE GetCostAndUsage responses; verify parsed output has no zero values, "(untagged)" for empty keys, and all costs are positive floats
    - **Validates: Requirements 3.1, 3.3, 3.4**

  - [ ]* 2.6 Write property test for error isolation (Property 8)
    - **Property 8: Partial tag key failure preserves successful results**
    - Generate N tag keys with K random failures; verify result contains exactly N-K keys with correct data
    - **Validates: Requirements 10.1**

- [x] 3. Implement Top-N cap and Size Guard
  - [x] 3.1 Add `_apply_top_n_cap` method to `IncrementalFetchEngine`
    - Sum costs per tag value across all dates for each tag key
    - Retain only top 50 values (by descending total cost) per tag key
    - Aggregate discarded values into "(other)" entry per day
    - Preserve "(untagged)" entries regardless of ranking
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 3.2 Add `_apply_size_guard` method to `IncrementalFetchEngine`
    - Serialize tag_data to JSON and check UTF-8 byte size against 350KB limit
    - While over limit: find tag key with fewest distinct values, remove it, log warning with tag key name and account ID
    - Return reduced structure within size limit
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 3.3 Write property test for Top-N ordering (Property 3)
    - **Property 3: Top-N cap retains only highest-cost values**
    - Generate random tag data with >50 values; verify retained values all have total cost >= any discarded value
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 3.4 Write property test for "(other)" aggregation (Property 4)
    - **Property 4: Discarded values aggregate into "(other)"**
    - Generate random tag data; verify "(other)" per day equals sum of discarded values for that day
    - **Validates: Requirements 5.4**

  - [ ]* 3.5 Write property test for size guard invariant (Property 2)
    - **Property 2: Size guard ensures output fits within DynamoDB limit**
    - Generate oversized tag breakdowns; verify output serialized size is always ≤ 350KB
    - **Validates: Requirements 4.2**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Integrate multi-tag fetch into the refresh pipeline and update write path
  - [x] 5.1 Refactor `fetch_cost_data` in `IncrementalFetchEngine` to use `_fetch_all_tag_breakdowns`
    - Replace the existing `_call_ce_by_tag` / `_parse_tag_response` call with `_fetch_all_tag_breakdowns`
    - Apply `_apply_top_n_cap` then `_apply_size_guard` to the result
    - Merge tag data into each `CostDataItem.tag_breakdown` by extracting the per-date dict for each tag key: `{tag_key: date_values[item.date]}`
    - Ensure service-breakdown caching completes regardless of tag query outcomes
    - _Requirements: 2.1, 4.4, 9.1, 9.2, 9.3, 10.3_

  - [x] 5.2 Update `write_cost_data` in `cache_service.py` to serialize nested tag_breakdown
    - Change serialization from `{k: str(v) for k, v in item.tag_breakdown.items()}` to nested format: `{tag_key: {tag_val: str(cost) for tag_val, cost in values.items()} for tag_key, values in item.tag_breakdown.items()}`
    - _Requirements: 3.2_

- [x] 6. Update dashboard read path with normalization and fallback
  - [x] 6.1 Integrate `normalize_tag_breakdown` into the dashboard read path in `lambda_function.py`
    - Import `normalize_tag_breakdown` from `cache_types`
    - When reading `tag_breakdown` from cached items, pass through `normalize_tag_breakdown` before use
    - Extract costs for the selected tag key directly from the normalized nested structure
    - _Requirements: 6.1, 6.2, 7.1, 7.2_

  - [x] 6.2 Implement tag key fallback logic in dashboard handler
    - When the selected tag key exists in the normalized cache → use cached data (no CE call)
    - When the selected tag key does NOT exist in the normalized cache → fall back to live CE query
    - Ensure resource state data (rightsizing, waste, EBS) continues to use live APIs
    - _Requirements: 6.3, 6.4, 8.1, 8.2_

  - [ ]* 6.3 Write property test for dashboard extraction (Property 5)
    - **Property 5: Dashboard correctly extracts tag key costs from nested format**
    - Generate random nested breakdowns; verify extracted daily costs match inner dict values exactly
    - **Validates: Requirements 6.2**

  - [ ]* 6.4 Write property test for flat-to-nested normalization (Property 6)
    - **Property 6: Flat-to-nested normalization preserves all cost data**
    - Generate random flat-format dicts; verify total cost sum is preserved and entries are grouped correctly
    - **Validates: Requirements 7.1, 7.4**

  - [ ]* 6.5 Write property test for normalization idempotence (Property 7)
    - **Property 7: Nested format normalization is idempotent**
    - Generate random nested-format dicts; verify normalize returns identical structure (with float conversion)
    - **Validates: Requirements 7.2**

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python, matching the existing Lambda codebase
- The legacy `_call_ce_by_tag`, `_get_primary_tag_key`, and `_parse_tag_response` methods can be removed once the new multi-tag pipeline is wired in (task 5.1)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3"] },
    { "id": 2, "tasks": ["2.4", "3.1", "3.2"] },
    { "id": 3, "tasks": ["2.5", "2.6", "3.3", "3.4", "3.5"] },
    { "id": 4, "tasks": ["5.1", "5.2"] },
    { "id": 5, "tasks": ["6.1", "6.2"] },
    { "id": 6, "tasks": ["6.3", "6.4", "6.5"] }
  ]
}
```
