"""Property-based tests for DataSourceQueryEngine server-side filter correctness.

Tests the filter application logic using hypothesis to verify that:
- All output records satisfy all filter conditions
- No valid records are excluded that should match
- Filter operators work correctly: equals, not_equals, greater_than, less_than
- Both text and numeric attribute filtering work
- Conjunctive (AND) filter logic works correctly
- Edge cases: empty filters, empty records, missing attributes
- Filters don't mutate input records
- Filter conditions are evaluated in the correct attribute type (text vs numeric)

Property 7: Server-side filter correctness

For any list of cost data records and any set of filter conditions, when applying
those filters via the _apply_filters() method:
1. All returned records must satisfy ALL filter conditions simultaneously
2. No records that satisfy all conditions should be excluded from results
3. Records that fail any condition must NOT be in results

Validates: Requirements 9.4
"""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck, assume

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datasource_query import DataSourceQueryEngine
from constants import (
    DATASOURCE_AVAILABLE_ATTRIBUTES,
    DATASOURCE_ATTRIBUTE_TYPES,
    DATASOURCE_FILTER_OPERATORS,
)


@pytest.fixture
def mock_dynamodb():
    """Create a mock DynamoDB resource."""
    return MagicMock()


@pytest.fixture
def engine(mock_dynamodb):
    """Create a DataSourceQueryEngine with mock DynamoDB."""
    return DataSourceQueryEngine(dynamodb_resource=mock_dynamodb)


# Strategy: Generate random text values for text attributes
@st.composite
def text_values(draw):
    """Generate random text values for filtering."""
    return draw(st.text(
        alphabet=st.characters(
            blacklist_categories=('Cc', 'Cs'),
            blacklist_characters='\x00'
        ),
        min_size=0,
        max_size=100
    ))


# Strategy: Generate random numeric values for numeric attributes
@st.composite
def numeric_values(draw):
    """Generate random numeric values for filtering (0.01 to 999999.99)."""
    return draw(st.decimals(
        min_value=0.01,
        max_value=999999.99,
        allow_nan=False,
        allow_infinity=False,
        places=2
    ))


# Strategy: Generate random cost data records
@st.composite
def cost_records(draw, num_records=None):
    """Generate a list of realistic cost data records.
    
    Each record has: date, account_id, service, cost_amount, currency, cloud_provider
    """
    # If num_records is a strategy, draw from it; otherwise use it as-is
    if num_records is None:
        num_records = draw(st.integers(min_value=1, max_value=50))
    elif isinstance(num_records, st.SearchStrategy):
        num_records = draw(num_records)
    elif isinstance(num_records, int):
        pass  # Already an int, use as-is
    else:
        num_records = draw(st.integers(min_value=1, max_value=50))
    
    records = []
    for _ in range(num_records):
        record = {
            "date": draw(st.dates(
                min_value=__import__('datetime').date(2024, 1, 1),
                max_value=__import__('datetime').date(2024, 12, 31)
            ).map(lambda d: d.isoformat())),
            "account_id": draw(st.text(
                alphabet='abcdefghijklmnopqrstuvwxyz0123456789-',
                min_size=5,
                max_size=30
            )),
            "service": draw(st.sampled_from([
                "EC2", "S3", "RDS", "Lambda", "DynamoDB", "CloudFront",
                "Route53", "IAM", "VPC", "EBS", "Elasticache", "SQS",
                "SNS", "API Gateway", "DataPipeline", "Custom Service"
            ])),
            "cost_amount": float(draw(numeric_values())),
            "currency": draw(st.sampled_from(["USD", "EUR", "GBP", "JPY", "CAD"])),
            "cloud_provider": draw(st.sampled_from(["aws", "custom", "azure", "gcp"])),
        }
        records.append(record)
    
    return records


# Strategy: Generate filter conditions for a specific attribute
@st.composite
def filter_for_attribute(draw, attribute):
    """Generate a single filter condition for a given attribute."""
    attr_type = DATASOURCE_ATTRIBUTE_TYPES.get(attribute, "text")
    operators = DATASOURCE_FILTER_OPERATORS.get(attr_type, [])
    
    if not operators:
        assume(False)  # Skip if no operators defined for attribute
    
    operator = draw(st.sampled_from(operators))
    
    if attr_type == "numeric":
        value = float(draw(numeric_values()))
    else:
        value = draw(text_values())
    
    return {
        "attribute": attribute,
        "operator": operator,
        "value": value
    }


class TestServerSideFilterCorrectness:
    """Property-based tests for server-side filter correctness.
    
    **Validates: Requirements 9.4**
    
    Requirement 9.4: Server-side filtering correctness
    When filters are applied to records, all output records must satisfy
    all filter conditions, and no valid records should be excluded.
    """

    @given(
        records=cost_records(num_records=st.integers(1, 30)),
        attribute=st.sampled_from(DATASOURCE_AVAILABLE_ATTRIBUTES),
    )
    @settings(max_examples=300, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_filtered_records_satisfy_all_conditions(self, engine, records, attribute):
        """Property: All filtered output records satisfy all filter conditions.
        
        For any list of records and any single filter condition, every record
        in the output must satisfy that condition based on its field value,
        the operator, and the target value.
        """
        # Generate a filter for this attribute
        attr_type = DATASOURCE_ATTRIBUTE_TYPES.get(attribute)
        operators = DATASOURCE_FILTER_OPERATORS.get(attr_type, [])
        assume(len(operators) > 0)
        
        operator = operators[0] if operators else "equals"
        
        # Use a value from the records if possible
        sample_value = draw(st.just(records[0].get(attribute)))
        
        filter_condition = [{
            "attribute": attribute,
            "operator": operator,
            "value": sample_value
        }]
        
        # Apply filter
        filtered = engine._apply_filters(records, filter_condition)
        
        # Verify each filtered record satisfies the condition
        for record in filtered:
            field_value = record.get(attribute)
            result = engine._evaluate_condition(
                field_value,
                operator,
                sample_value,
                attr_type
            )
            assert result, (
                f"Record {record} doesn't satisfy filter {filter_condition[0]}: "
                f"field_value={field_value}, operator={operator}, "
                f"target={sample_value}, attr_type={attr_type}, result={result}"
            )

    @given(
        records=cost_records(num_records=st.integers(1, 30)),
        num_filters=st.integers(1, 3),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_conjunctive_filters_all_must_pass(self, engine, records, num_filters):
        """Property: With multiple filters, records must pass ALL conditions (AND).
        
        For any set of filter conditions applied together, the output must
        contain only records that satisfy every single filter condition.
        """
        # Generate multiple filter conditions for different attributes
        filters = []
        attributes_used = []
        
        for _ in range(num_filters):
            # Pick an attribute that hasn't been used yet
            available = [a for a in DATASOURCE_AVAILABLE_ATTRIBUTES 
                        if a not in attributes_used]
            if not available:
                break
            
            attr = available[0]
            attributes_used.append(attr)
            attr_type = DATASOURCE_ATTRIBUTE_TYPES.get(attr)
            operators = DATASOURCE_FILTER_OPERATORS.get(attr_type, [])
            
            if not operators:
                continue
            
            operator = operators[0]
            
            # Pick a value from records or generate one
            if records:
                value = records[0].get(attr)
            else:
                value = ""
            
            filters.append({
                "attribute": attr,
                "operator": operator,
                "value": value
            })
        
        assume(len(filters) > 0)  # Need at least one filter
        
        # Apply filters
        filtered = engine._apply_filters(records, filters)
        
        # Verify each filtered record satisfies ALL conditions
        for record in filtered:
            for filt in filters:
                attr = filt["attribute"]
                op = filt["operator"]
                target_val = filt["value"]
                
                field_val = record.get(attr)
                attr_type = DATASOURCE_ATTRIBUTE_TYPES.get(attr)
                
                result = engine._evaluate_condition(field_val, op, target_val, attr_type)
                assert result, (
                    f"Record fails filter (conjunctive AND failed): "
                    f"filter={filt}, field_value={field_val}, result={result}"
                )

    @given(
        records=cost_records(num_records=st.integers(5, 30)),
        attribute=st.sampled_from(DATASOURCE_AVAILABLE_ATTRIBUTES),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_equals_operator_correctness(self, engine, records, attribute):
        """Property: equals operator correctly matches field values.
        
        For an 'equals' filter, output must include only records where
        the field value equals the target value.
        """
        assume(len(records) > 0)
        
        # Pick a value that exists in the records
        target_value = records[0].get(attribute)
        
        filter_cond = [{
            "attribute": attribute,
            "operator": "equals",
            "value": target_value
        }]
        
        filtered = engine._apply_filters(records, filter_cond)
        
        # Every filtered record must have field == target
        for record in filtered:
            field_val = record.get(attribute)
            # Handle numeric comparison
            attr_type = DATASOURCE_ATTRIBUTE_TYPES.get(attribute)
            if attr_type == "numeric":
                try:
                    assert float(field_val) == float(target_value)
                except (TypeError, ValueError):
                    pass  # Skip if conversion fails
            else:
                assert str(field_val) == str(target_value)
        
        # Verify no records were incorrectly excluded
        for record in records:
            field_val = record.get(attribute)
            attr_type = DATASOURCE_ATTRIBUTE_TYPES.get(attribute)
            
            values_match = False
            if attr_type == "numeric":
                try:
                    values_match = float(field_val) == float(target_value)
                except (TypeError, ValueError):
                    pass
            else:
                values_match = str(field_val) == str(target_value)
            
            if values_match:
                assert record in filtered, (
                    f"Record that should match was excluded: {record}, "
                    f"target={target_value}, field={field_val}"
                )

    @given(
        records=cost_records(num_records=st.integers(5, 30)),
        attribute=st.sampled_from(
            [a for a in DATASOURCE_AVAILABLE_ATTRIBUTES 
             if DATASOURCE_ATTRIBUTE_TYPES.get(a) == "numeric"]
        ),
    )
    @settings(max_examples=150, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_greater_than_operator_correctness(self, engine, records, attribute):
        """Property: greater_than operator correctly filters numeric values.
        
        For a 'greater_than' filter, output must include only records where
        the numeric field value is strictly greater than the target value.
        """
        assume(len(records) > 0)
        
        # Use a threshold value
        threshold = 500.0
        
        filter_cond = [{
            "attribute": attribute,
            "operator": "greater_than",
            "value": threshold
        }]
        
        filtered = engine._apply_filters(records, filter_cond)
        
        # Every filtered record must have field > threshold
        for record in filtered:
            field_val = record.get(attribute)
            try:
                assert float(field_val) > float(threshold), (
                    f"Record doesn't satisfy greater_than: "
                    f"field={field_val}, threshold={threshold}"
                )
            except (TypeError, ValueError):
                pass

    @given(
        records=cost_records(num_records=st.integers(5, 30)),
        attribute=st.sampled_from(
            [a for a in DATASOURCE_AVAILABLE_ATTRIBUTES 
             if DATASOURCE_ATTRIBUTE_TYPES.get(a) == "numeric"]
        ),
    )
    @settings(max_examples=150, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_less_than_operator_correctness(self, engine, records, attribute):
        """Property: less_than operator correctly filters numeric values.
        
        For a 'less_than' filter, output must include only records where
        the numeric field value is strictly less than the target value.
        """
        assume(len(records) > 0)
        
        # Use a threshold value
        threshold = 5000.0
        
        filter_cond = [{
            "attribute": attribute,
            "operator": "less_than",
            "value": threshold
        }]
        
        filtered = engine._apply_filters(records, filter_cond)
        
        # Every filtered record must have field < threshold
        for record in filtered:
            field_val = record.get(attribute)
            try:
                assert float(field_val) < float(threshold), (
                    f"Record doesn't satisfy less_than: "
                    f"field={field_val}, threshold={threshold}"
                )
            except (TypeError, ValueError):
                pass

    @given(records=cost_records(num_records=st.integers(1, 20)))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_empty_filters_returns_all_records(self, engine, records):
        """Property: Empty filter list returns all records unchanged.
        
        When no filters are provided, all records should be returned.
        """
        filtered = engine._apply_filters(records, [])
        
        assert len(filtered) == len(records), (
            f"Empty filters should return all records: "
            f"got {len(filtered)}, expected {len(records)}"
        )
        assert filtered == records, (
            "Empty filters should return records in same order"
        )

    @given(filters=st.lists(st.just({}), min_size=1, max_size=3))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_empty_records_returns_empty(self, engine, filters):
        """Property: Filtering empty record list always returns empty list.
        
        Regardless of filters, an empty input list should return empty.
        """
        filtered = engine._apply_filters([], filters)
        
        assert filtered == [], (
            f"Filtering empty records should return empty: got {filtered}"
        )

    @given(records=cost_records(num_records=st.integers(1, 20)))
    @settings(max_examples=150, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_filter_does_not_mutate_input_records(self, engine, records):
        """Property: Filtering does not modify the input records list.
        
        The _apply_filters method should not mutate the original records.
        """
        import copy
        records_copy = copy.deepcopy(records)
        
        filter_cond = [{
            "attribute": "cost_amount",
            "operator": "greater_than",
            "value": 100.0
        }]
        
        engine._apply_filters(records, filter_cond)
        
        # Records should be unchanged
        assert records == records_copy, (
            "Filter should not mutate input records"
        )

    @given(
        records=cost_records(num_records=st.integers(1, 10)),
    )
    @settings(max_examples=150, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_filter_with_nonexistent_attribute(self, engine, records):
        """Property: Filter on non-existent attribute excludes those records.
        
        If a record doesn't have the filter attribute, it should fail the filter.
        """
        # Create a filter for a non-existent attribute
        filter_cond = [{
            "attribute": "nonexistent_attr",
            "operator": "equals",
            "value": "something"
        }]
        
        filtered = engine._apply_filters(records, filter_cond)
        
        # Should return empty (all records missing the attribute)
        assert len(filtered) == 0, (
            f"Records with missing attribute should be excluded: got {filtered}"
        )

    @given(
        records=cost_records(num_records=st.integers(5, 20)),
        percentage=st.floats(min_value=0.1, max_value=0.9),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_not_equals_operator_correctness(self, engine, records, percentage):
        """Property: not_equals operator correctly excludes matching values.
        
        For a 'not_equals' filter, output must include only records where
        the field value does NOT equal the target value.
        """
        assume(len(records) > 0)
        
        # Pick a value from records
        target_value = records[0].get("service")
        
        filter_cond = [{
            "attribute": "service",
            "operator": "not_equals",
            "value": target_value
        }]
        
        filtered = engine._apply_filters(records, filter_cond)
        
        # Every filtered record must NOT match the target
        for record in filtered:
            field_val = record.get("service")
            assert str(field_val) != str(target_value), (
                f"Record shouldn't match in not_equals: {record}, target={target_value}"
            )

    @given(records=cost_records(num_records=st.integers(1, 20)))
    @settings(max_examples=150, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_filtered_records_are_valid_copies(self, engine, records):
        """Property: All filtered records maintain valid structure.
        
        Every record in the filtered output should be a valid dict with
        all expected attributes from the input.
        """
        filter_cond = [{
            "attribute": "cost_amount",
            "operator": "greater_than",
            "value": 0.0
        }]
        
        filtered = engine._apply_filters(records, filter_cond)
        
        expected_attrs = set(DATASOURCE_AVAILABLE_ATTRIBUTES)
        
        for record in filtered:
            assert isinstance(record, dict), f"Record should be dict: {type(record)}"
            # Check all expected attributes are present
            for attr in expected_attrs:
                assert attr in record, f"Record missing attribute: {attr}"

    @given(
        records=cost_records(num_records=st.integers(1, 10)),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_multiple_text_filters_all_must_match(self, engine, records):
        """Property: Multiple text attribute filters use AND logic.
        
        With multiple text filters, records must satisfy all of them.
        """
        assume(len(records) > 0)
        
        service_val = records[0].get("service")
        provider_val = records[0].get("cloud_provider")
        
        filters = [
            {"attribute": "service", "operator": "equals", "value": service_val},
            {"attribute": "cloud_provider", "operator": "equals", "value": provider_val},
        ]
        
        filtered = engine._apply_filters(records, filters)
        
        # Every filtered record must match both conditions
        for record in filtered:
            assert str(record.get("service")) == str(service_val)
            assert str(record.get("cloud_provider")) == str(provider_val)

    @given(
        records=cost_records(num_records=st.integers(1, 10)),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_multiple_numeric_filters_all_must_match(self, engine, records):
        """Property: Multiple numeric filters use AND logic.
        
        With multiple numeric filters, records must satisfy all.
        """
        assume(len(records) > 0)
        
        lower_bound = 10.0
        upper_bound = 10000.0
        
        filters = [
            {"attribute": "cost_amount", "operator": "greater_than", "value": lower_bound},
            {"attribute": "cost_amount", "operator": "less_than", "value": upper_bound},
        ]
        
        filtered = engine._apply_filters(records, filters)
        
        # Every filtered record must be between bounds (exclusive)
        for record in filtered:
            cost = float(record.get("cost_amount"))
            assert cost > lower_bound, f"Cost {cost} not > {lower_bound}"
            assert cost < upper_bound, f"Cost {cost} not < {upper_bound}"

    @given(
        records=cost_records(num_records=st.integers(5, 30)),
    )
    @settings(max_examples=150, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_filter_completeness_no_false_negatives(self, engine, records):
        """Property: No records that should match are excluded (no false negatives).
        
        For a given filter condition, every record that actually satisfies
        the condition must be included in the output (false negatives = 0).
        """
        # Use cost_amount > 100 as the condition
        threshold = 100.0
        
        filter_cond = [{
            "attribute": "cost_amount",
            "operator": "greater_than",
            "value": threshold
        }]
        
        filtered = engine._apply_filters(records, filter_cond)
        
        # Count how many records should match
        should_match = [
            r for r in records 
            if float(r.get("cost_amount", 0)) > threshold
        ]
        
        # Count how many actually matched
        assert len(filtered) == len(should_match), (
            f"Filter is excluding records that should match: "
            f"should_match={len(should_match)}, actual_filtered={len(filtered)}"
        )
        
        # Verify same records
        for record in should_match:
            assert record in filtered, (
                f"Record that should match was excluded: {record}"
            )

    @given(
        records=cost_records(num_records=st.integers(1, 20)),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_currency_text_filter_correctness(self, engine, records):
        """Property: Text filter on currency attribute works correctly.
        
        Currency filtering should work like any other text attribute.
        """
        assume(len(records) > 0)
        
        target_currency = records[0].get("currency")
        
        filter_cond = [{
            "attribute": "currency",
            "operator": "equals",
            "value": target_currency
        }]
        
        filtered = engine._apply_filters(records, filter_cond)
        
        # All filtered records should have matching currency
        for record in filtered:
            assert record.get("currency") == target_currency
        
        # All records with matching currency should be in filtered
        matching_records = [r for r in records if r.get("currency") == target_currency]
        assert len(filtered) == len(matching_records)

    @given(
        records=cost_records(num_records=st.integers(1, 20)),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_date_text_filter_correctness(self, engine, records):
        """Property: Text filter on date attribute works correctly.
        
        Date filtering (as text comparison) should work correctly.
        """
        assume(len(records) > 0)
        
        target_date = records[0].get("date")
        
        filter_cond = [{
            "attribute": "date",
            "operator": "equals",
            "value": target_date
        }]
        
        filtered = engine._apply_filters(records, filter_cond)
        
        # All filtered records should have matching date
        for record in filtered:
            assert record.get("date") == target_date
        
        # Verify completeness
        matching_records = [r for r in records if r.get("date") == target_date]
        assert len(filtered) == len(matching_records)

    @given(records=cost_records(num_records=st.integers(1, 15)))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_filter_stability_same_input_same_output(self, engine, records):
        """Property: Applying same filter twice yields identical results (idempotent).
        
        Filtering should be deterministic: same input filter = same output.
        """
        filter_cond = [{
            "attribute": "service",
            "operator": "equals",
            "value": "EC2"
        }]
        
        result1 = engine._apply_filters(records, filter_cond)
        result2 = engine._apply_filters(records, filter_cond)
        
        assert result1 == result2, (
            f"Filter is not deterministic: call1={result1}, call2={result2}"
        )




class TestFilterUnitCases:
    """Unit tests for filter edge cases and specific scenarios.
    
    **Validates: Requirements 9.4**
    """

    def test_single_record_passes_filter(self, engine):
        """Single record matching filter is returned."""
        records = [{
            "date": "2024-06-15",
            "account_id": "acc-123",
            "service": "EC2",
            "cost_amount": 500.0,
            "currency": "USD",
            "cloud_provider": "aws",
        }]
        
        filters = [{
            "attribute": "service",
            "operator": "equals",
            "value": "EC2"
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 1
        assert result[0] == records[0]

    def test_single_record_fails_filter(self, engine):
        """Single record not matching filter is excluded."""
        records = [{
            "date": "2024-06-15",
            "account_id": "acc-123",
            "service": "EC2",
            "cost_amount": 500.0,
            "currency": "USD",
            "cloud_provider": "aws",
        }]
        
        filters = [{
            "attribute": "service",
            "operator": "equals",
            "value": "RDS"
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 0

    def test_equals_with_zero_value(self, engine):
        """Equals filter with zero value works correctly."""
        records = [
            {"date": "2024-06-15", "account_id": "a1", "service": "EC2", 
             "cost_amount": 0.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a2", "service": "S3", 
             "cost_amount": 100.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        filters = [{
            "attribute": "cost_amount",
            "operator": "equals",
            "value": 0.0
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 1
        assert result[0]["service"] == "EC2"

    def test_greater_than_with_negative_threshold(self, engine):
        """greater_than with negative threshold."""
        records = [
            {"date": "2024-06-15", "account_id": "a1", "service": "EC2", 
             "cost_amount": -10.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a2", "service": "S3", 
             "cost_amount": 0.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a3", "service": "RDS", 
             "cost_amount": 10.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        filters = [{
            "attribute": "cost_amount",
            "operator": "greater_than",
            "value": 0.0
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 1
        assert result[0]["service"] == "RDS"

    def test_less_than_boundary_value(self, engine):
        """less_than filter correctly excludes boundary value."""
        records = [
            {"date": "2024-06-15", "account_id": "a1", "service": "EC2", 
             "cost_amount": 99.99, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a2", "service": "S3", 
             "cost_amount": 100.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a3", "service": "RDS", 
             "cost_amount": 100.01, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        filters = [{
            "attribute": "cost_amount",
            "operator": "less_than",
            "value": 100.0
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 1
        assert result[0]["service"] == "EC2"

    def test_not_equals_text_correctly_excludes_match(self, engine):
        """not_equals correctly excludes the target value."""
        records = [
            {"date": "2024-06-15", "account_id": "a1", "service": "EC2", 
             "cost_amount": 100.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a2", "service": "EC2", 
             "cost_amount": 200.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a3", "service": "RDS", 
             "cost_amount": 150.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        filters = [{
            "attribute": "service",
            "operator": "not_equals",
            "value": "EC2"
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 1
        assert result[0]["service"] == "RDS"

    def test_case_sensitive_text_comparison_equals(self, engine):
        """Text comparisons are case-sensitive."""
        records = [
            {"date": "2024-06-15", "account_id": "a1", "service": "ec2", 
             "cost_amount": 100.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a2", "service": "EC2", 
             "cost_amount": 200.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        filters = [{
            "attribute": "service",
            "operator": "equals",
            "value": "EC2"
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 1
        assert result[0]["service"] == "EC2"

    def test_filter_with_special_characters_in_value(self, engine):
        """Filters work with special characters in values."""
        records = [
            {"date": "2024-06-15", "account_id": "acc-123-special", "service": "EC2", 
             "cost_amount": 100.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "acc-456", "service": "S3", 
             "cost_amount": 200.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        filters = [{
            "attribute": "account_id",
            "operator": "equals",
            "value": "acc-123-special"
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 1
        assert result[0]["account_id"] == "acc-123-special"

    def test_filter_with_whitespace_in_text_value(self, engine):
        """Filters handle whitespace in text values."""
        records = [
            {"date": "2024-06-15", "account_id": "a1", "service": "API Gateway", 
             "cost_amount": 100.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a2", "service": "EC2", 
             "cost_amount": 200.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        filters = [{
            "attribute": "service",
            "operator": "equals",
            "value": "API Gateway"
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 1
        assert result[0]["service"] == "API Gateway"

    def test_multiple_filters_progressively_reduce_results(self, engine):
        """Each additional filter reduces result count (AND logic)."""
        records = [
            {"date": "2024-06-01", "account_id": "a1", "service": "EC2", 
             "cost_amount": 100.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-02", "account_id": "a1", "service": "EC2", 
             "cost_amount": 200.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-03", "account_id": "a1", "service": "RDS", 
             "cost_amount": 150.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        # First filter: service == "EC2" -> 2 results
        filter1 = [{"attribute": "service", "operator": "equals", "value": "EC2"}]
        result1 = engine._apply_filters(records, filter1)
        assert len(result1) == 2
        
        # Add second filter: cost_amount > 150 -> 1 result
        filter2 = filter1 + [{"attribute": "cost_amount", "operator": "greater_than", "value": 150}]
        result2 = engine._apply_filters(records, filter2)
        assert len(result2) == 1
        assert result2[0]["cost_amount"] == 200.0

    def test_filter_on_each_available_attribute(self, engine):
        """Filters work on each available attribute individually."""
        record = {
            "date": "2024-06-15",
            "account_id": "acc-123",
            "service": "EC2",
            "cost_amount": 500.0,
            "currency": "USD",
            "cloud_provider": "aws",
        }
        records = [record]
        
        # Test each attribute
        tests = [
            ("date", "equals", "2024-06-15", 1),
            ("account_id", "equals", "acc-123", 1),
            ("service", "equals", "EC2", 1),
            ("cost_amount", "equals", 500.0, 1),
            ("currency", "equals", "USD", 1),
            ("cloud_provider", "equals", "aws", 1),
        ]
        
        for attr, op, val, expected_len in tests:
            filters = [{"attribute": attr, "operator": op, "value": val}]
            result = engine._apply_filters(records, filters)
            assert len(result) == expected_len, (
                f"Filter on {attr} failed: expected {expected_len}, got {len(result)}"
            )

    def test_numeric_filter_with_string_conversion(self, engine):
        """Numeric filters convert strings to numbers correctly."""
        records = [
            {"date": "2024-06-15", "account_id": "a1", "service": "EC2", 
             "cost_amount": 500.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a2", "service": "S3", 
             "cost_amount": 100.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        # String value "300" should be converted to 300.0 for comparison
        filters = [{
            "attribute": "cost_amount",
            "operator": "greater_than",
            "value": "300"
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 1
        assert result[0]["service"] == "EC2"

    def test_invalid_filter_missing_attribute_key(self, engine):
        """Filter missing 'attribute' key is skipped gracefully."""
        records = [
            {"date": "2024-06-15", "account_id": "a1", "service": "EC2", 
             "cost_amount": 500.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        # Filter with missing 'attribute' key
        filters = [{"operator": "equals", "value": "EC2"}]
        
        result = engine._apply_filters(records, filters)
        # Should return all records (invalid filter skipped)
        assert len(result) == len(records)

    def test_invalid_filter_missing_operator_key(self, engine):
        """Filter missing 'operator' key is skipped gracefully."""
        records = [
            {"date": "2024-06-15", "account_id": "a1", "service": "EC2", 
             "cost_amount": 500.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        # Filter with missing 'operator' key
        filters = [{"attribute": "service", "value": "EC2"}]
        
        result = engine._apply_filters(records, filters)
        # Should return all records (invalid filter skipped)
        assert len(result) == len(records)

    def test_large_numeric_values_filtered_correctly(self, engine):
        """Large numeric values are compared correctly."""
        records = [
            {"date": "2024-06-15", "account_id": "a1", "service": "EC2", 
             "cost_amount": 999999.99, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a2", "service": "S3", 
             "cost_amount": 100000.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        filters = [{
            "attribute": "cost_amount",
            "operator": "greater_than",
            "value": 500000.0
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 1
        assert result[0]["cost_amount"] == 999999.99

    def test_very_small_numeric_values_filtered_correctly(self, engine):
        """Very small numeric values are compared correctly."""
        records = [
            {"date": "2024-06-15", "account_id": "a1", "service": "EC2", 
             "cost_amount": 0.01, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a2", "service": "S3", 
             "cost_amount": 1.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        filters = [{
            "attribute": "cost_amount",
            "operator": "less_than",
            "value": 0.5
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 1
        assert result[0]["cost_amount"] == 0.01

    def test_all_records_match_all_filters(self, engine):
        """When all records match all filters, return all."""
        records = [
            {"date": "2024-06-15", "account_id": "a1", "service": "EC2", 
             "cost_amount": 100.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a2", "service": "EC2", 
             "cost_amount": 200.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        filters = [{
            "attribute": "service",
            "operator": "equals",
            "value": "EC2"
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 2

    def test_no_records_match_any_filter(self, engine):
        """When no records match, return empty."""
        records = [
            {"date": "2024-06-15", "account_id": "a1", "service": "EC2", 
             "cost_amount": 100.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a2", "service": "S3", 
             "cost_amount": 200.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        filters = [{
            "attribute": "service",
            "operator": "equals",
            "value": "RDS"
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 0

    def test_numeric_not_equals_excludes_only_matching(self, engine):
        """Numeric not_equals excludes only the matching value."""
        records = [
            {"date": "2024-06-15", "account_id": "a1", "service": "EC2", 
             "cost_amount": 100.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a2", "service": "S3", 
             "cost_amount": 100.0, "currency": "USD", "cloud_provider": "aws"},
            {"date": "2024-06-15", "account_id": "a3", "service": "RDS", 
             "cost_amount": 200.0, "currency": "USD", "cloud_provider": "aws"},
        ]
        
        filters = [{
            "attribute": "cost_amount",
            "operator": "not_equals",
            "value": 100.0
        }]
        
        result = engine._apply_filters(records, filters)
        assert len(result) == 1
        assert result[0]["service"] == "RDS"

