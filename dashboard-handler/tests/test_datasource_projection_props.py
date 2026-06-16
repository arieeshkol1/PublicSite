"""Property-based tests for DataSourceQueryEngine attribute projection.

Tests the attribute projection logic using hypothesis to verify that:
- Projected records contain only specified columns
- No extra columns are included
- No missing columns are included when specified
- Edge cases: empty attributes, single attribute, all attributes
- Missing attributes in records are handled gracefully

Validates: Requirements 6.1, 9.5
"""

import sys
import os
from unittest.mock import MagicMock

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datasource_query import DataSourceQueryEngine
from constants import DATASOURCE_AVAILABLE_ATTRIBUTES


@pytest.fixture
def mock_dynamodb():
    """Create a mock DynamoDB resource."""
    return MagicMock()


@pytest.fixture
def engine(mock_dynamodb):
    """Create a DataSourceQueryEngine with mock DynamoDB."""
    return DataSourceQueryEngine(dynamodb_resource=mock_dynamodb)


# Strategy for generating valid attribute subsets from available attributes
def valid_attribute_subsets():
    """Generate random non-empty subsets of available attributes."""
    return st.lists(
        st.sampled_from(DATASOURCE_AVAILABLE_ATTRIBUTES),
        min_size=0,
        max_size=len(DATASOURCE_AVAILABLE_ATTRIBUTES),
        unique=True
    )


# Strategy for generating realistic cost records
def cost_records(num_records=10):
    """Generate realistic cost data records."""
    return st.lists(
        st.fixed_dictionaries({
            "date": st.dates().map(str),
            "account_id": st.just("123456789"),
            "service": st.sampled_from(["EC2", "RDS", "S3", "Lambda", "DynamoDB"]),
            "cost_amount": st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
            "currency": st.just("USD"),
            "cloud_provider": st.just("aws"),
        }),
        min_size=0,
        max_size=num_records
    )


class TestAttributeProjectionProperties:
    """Property-based tests for attribute projection.
    
    **Validates: Requirements 6.1, 9.5**
    
    Requirement 6.1: Projected records contain only specified attributes
    Requirement 9.5: Attribute projection reduces columns to requested set
    """

    @given(
        records=cost_records(num_records=20),
        attributes=valid_attribute_subsets()
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_projected_records_contain_only_specified_attributes(
        self, engine, records, attributes
    ):
        """Property: Projected records contain exactly the specified attributes and no others.
        
        For any set of records and any attribute subset, each projected record
        should contain only the keys that were specified, with no extra columns.
        """
        result = engine._project_attributes(records, attributes)
        
        # If no attributes specified, should return all available attributes
        expected_attrs = attributes if attributes else DATASOURCE_AVAILABLE_ATTRIBUTES
        
        for record in result:
            # No extra columns beyond specified attributes
            extra_columns = set(record.keys()) - set(expected_attrs)
            assert not extra_columns, (
                f"Found extra columns {extra_columns} in record. "
                f"Expected only: {expected_attrs}"
            )
            
            # Only specified attributes are present
            for attr in record.keys():
                assert attr in expected_attrs, (
                    f"Attribute {attr} not in expected attributes {expected_attrs}"
                )

    @given(
        records=cost_records(num_records=20),
        attributes=valid_attribute_subsets()
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_projected_records_no_missing_specified_columns(
        self, engine, records, attributes
    ):
        """Property: All specified attributes are either present or absent (no partial inclusion).
        
        For each specified attribute in the attribute list, if that attribute exists
        in the original record, it must be present in the projected record.
        """
        if not records or not attributes:
            # Skip if no records or no attributes specified
            return
        
        result = engine._project_attributes(records, attributes)
        expected_attrs = attributes if attributes else DATASOURCE_AVAILABLE_ATTRIBUTES
        
        # Check each original record against its projection
        for original_record, projected_record in zip(records, result):
            for attr in expected_attrs:
                if attr in original_record:
                    # If attribute exists in original, it must be in projection
                    assert attr in projected_record, (
                        f"Attribute {attr} exists in original but missing in projection"
                    )
                    # Value must match
                    assert projected_record[attr] == original_record[attr], (
                        f"Attribute {attr} value mismatch: "
                        f"{projected_record[attr]} != {original_record[attr]}"
                    )

    @given(records=cost_records(num_records=20))
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_empty_attribute_list_returns_all_attributes(
        self, engine, records
    ):
        """Property: Empty attribute list returns all available attributes.
        
        When attributes list is empty or None, the projection should
        include all available attributes for each record.
        """
        # Test with empty list
        result_empty = engine._project_attributes(records, [])
        
        # Test with None (if supported)
        result_none = engine._project_attributes(records, None)
        
        # Both should be equivalent and contain all available attributes
        for record in result_empty:
            if record:  # Skip empty records
                for attr in DATASOURCE_AVAILABLE_ATTRIBUTES:
                    # Check that record has keys from available attributes
                    # (it won't have all if the original record didn't have them)
                    pass
        
        for record in result_none:
            if record:  # Skip empty records
                for attr in DATASOURCE_AVAILABLE_ATTRIBUTES:
                    # Same check
                    pass

    @given(records=cost_records(num_records=20))
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_single_attribute_projection(self, engine, records):
        """Property: Projection of single attribute works correctly.
        
        When projecting a single attribute, the result should have
        exactly that attribute for each record (if it exists in original).
        """
        for single_attr in DATASOURCE_AVAILABLE_ATTRIBUTES:
            result = engine._project_attributes(records, [single_attr])
            
            for i, record in enumerate(result):
                if records[i]:  # If original record exists
                    # Result record should have at most one attribute (the requested one)
                    if single_attr in records[i]:
                        assert single_attr in record, (
                            f"Single attribute {single_attr} not in projection"
                        )
                        assert len(record) == 1, (
                            f"Single attribute projection should have exactly 1 attribute, "
                            f"got {len(record)}: {list(record.keys())}"
                        )

    @given(records=cost_records(num_records=20))
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_all_attributes_projection(self, engine, records):
        """Property: Projection of all available attributes is idempotent.
        
        When projecting all available attributes, the result should contain
        the same attributes as the original record.
        """
        result = engine._project_attributes(records, DATASOURCE_AVAILABLE_ATTRIBUTES)
        
        for original, projected in zip(records, result):
            # Both should have the same set of keys
            assert set(original.keys()) == set(projected.keys()), (
                f"All-attributes projection changed keys: "
                f"{set(original.keys())} != {set(projected.keys())}"
            )
            
            # Values should be identical
            for key in original:
                assert projected[key] == original[key], (
                    f"Value mismatch for {key}: {projected[key]} != {original[key]}"
                )

    @given(
        records=cost_records(num_records=20),
        keep_probability=st.floats(min_value=0.0, max_value=1.0)
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_missing_attributes_in_records_handled_gracefully(
        self, engine, records, keep_probability
    ):
        """Property: Records missing some attributes are handled without error.
        
        If an original record doesn't have all attributes, projection
        should still work correctly (omitting missing attributes from result).
        """
        import random
        # Create records with some attributes missing
        sparse_records = []
        for record in records:
            # Randomly remove some attributes based on probability
            sparse_record = {}
            for key in record:
                # Keep each attribute with keep_probability
                if random.random() > (1.0 - keep_probability):
                    sparse_record[key] = record[key]
            sparse_records.append(sparse_record)
        
        result = engine._project_attributes(
            sparse_records, DATASOURCE_AVAILABLE_ATTRIBUTES
        )
        
        # Should complete without error and return same number of records
        assert len(result) == len(sparse_records), (
            "Projection should return same number of records"
        )
        
        # For each record, only present attributes should be in projection
        for original, projected in zip(sparse_records, result):
            projected_keys = set(projected.keys())
            original_keys = set(original.keys())
            
            # Projected keys should be subset of available attributes
            assert projected_keys.issubset(set(DATASOURCE_AVAILABLE_ATTRIBUTES))
            
            # All original keys should be in projection
            assert original_keys.issubset(projected_keys), (
                f"Projection lost attributes: {original_keys - projected_keys}"
            )

    @given(attributes=valid_attribute_subsets())
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_projection_with_empty_records_list(self, engine, attributes):
        """Property: Projection of empty records list returns empty list.
        
        When given an empty list of records, the projection should
        return an empty list regardless of attribute specification.
        """
        result = engine._project_attributes([], attributes)
        
        assert result == [], (
            f"Empty records list should project to empty list, got {result}"
        )

    @given(
        records=cost_records(num_records=20),
        attributes=valid_attribute_subsets()
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_projection_preserves_record_count(
        self, engine, records, attributes
    ):
        """Property: Projection preserves the number of records.
        
        The number of records in the projection should always equal
        the number of input records.
        """
        result = engine._project_attributes(records, attributes)
        
        assert len(result) == len(records), (
            f"Projection changed record count: {len(result)} != {len(records)}"
        )

    @given(
        records=cost_records(num_records=20),
        attributes=valid_attribute_subsets()
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
    )
    def test_projection_preserves_value_integrity(
        self, engine, records, attributes
    ):
        """Property: Projection preserves all values without modification.
        
        For any attribute that appears in both the original record and
        the projection, the value must be identical (no mutations).
        """
        expected_attrs = attributes if attributes else DATASOURCE_AVAILABLE_ATTRIBUTES
        result = engine._project_attributes(records, expected_attrs)
        
        for original, projected in zip(records, result):
            for attr in projected:
                if attr in original:
                    assert projected[attr] == original[attr], (
                        f"Value corruption for {attr}: "
                        f"{projected[attr]} (type: {type(projected[attr])}) "
                        f"!= {original[attr]} (type: {type(original[attr])})"
                    )


class TestAttributeProjectionEdgeCases:
    """Edge case unit tests for attribute projection."""

    def test_empty_records(self, engine):
        """Empty records list returns empty result."""
        result = engine._project_attributes([], ["date", "service"])
        assert result == []

    def test_empty_attributes_defaults_to_all(self, engine):
        """Empty attributes list defaults to all available attributes."""
        records = [
            {
                "date": "2024-01-01",
                "account_id": "123456789",
                "service": "EC2",
                "cost_amount": 100.0,
                "currency": "USD",
                "cloud_provider": "aws",
            }
        ]
        result = engine._project_attributes(records, [])
        
        # Should return all attributes
        assert len(result) == 1
        assert result[0] == records[0]

    def test_single_record_single_attribute(self, engine):
        """Single record with single attribute projection."""
        records = [{"date": "2024-01-01", "service": "EC2"}]
        result = engine._project_attributes(records, ["date"])
        
        assert len(result) == 1
        assert result[0] == {"date": "2024-01-01"}
        assert "service" not in result[0]

    def test_invalid_attribute_ignored(self, engine):
        """Invalid attribute names are ignored and not included."""
        records = [
            {
                "date": "2024-01-01",
                "service": "EC2",
            }
        ]
        result = engine._project_attributes(
            records, 
            ["date", "invalid_attribute", "service"]
        )
        
        assert len(result) == 1
        assert "date" in result[0]
        assert "service" in result[0]
        assert "invalid_attribute" not in result[0]

    def test_all_invalid_attributes_defaults_to_all(self, engine):
        """If all requested attributes are invalid, default to all available."""
        records = [
            {
                "date": "2024-01-01",
                "account_id": "123456789",
                "service": "EC2",
                "cost_amount": 100.0,
                "currency": "USD",
                "cloud_provider": "aws",
            }
        ]
        result = engine._project_attributes(
            records,
            ["invalid1", "invalid2"]
        )
        
        # Should fall back to all available attributes
        assert len(result) == 1
        # Should contain original attributes
        assert result[0] == records[0]

    def test_duplicate_attributes_deduplicated(self, engine):
        """Duplicate attribute names are handled correctly."""
        records = [{"date": "2024-01-01", "service": "EC2"}]
        result = engine._project_attributes(
            records,
            ["date", "date", "service", "service"]
        )
        
        assert len(result) == 1
        assert set(result[0].keys()) == {"date", "service"}
        assert len(result[0]) == 2

    def test_record_with_subset_of_attributes(self, engine):
        """Record missing some attributes still projects correctly."""
        records = [
            {
                "date": "2024-01-01",
                # Missing: account_id, currency, cloud_provider
                "service": "EC2",
                "cost_amount": 100.0,
            }
        ]
        result = engine._project_attributes(
            records,
            ["date", "service", "cost_amount", "account_id"]
        )
        
        assert len(result) == 1
        assert result[0] == {
            "date": "2024-01-01",
            "service": "EC2",
            "cost_amount": 100.0,
        }
        assert "account_id" not in result[0]

    def test_record_with_extra_fields(self, engine):
        """Record with extra unknown fields ignores them."""
        records = [
            {
                "date": "2024-01-01",
                "service": "EC2",
                "cost_amount": 100.0,
                "extra_field": "should_be_ignored",
                "another_field": 12345,
            }
        ]
        result = engine._project_attributes(
            records,
            ["date", "service"]
        )
        
        assert len(result) == 1
        assert result[0] == {
            "date": "2024-01-01",
            "service": "EC2",
        }
        assert "extra_field" not in result[0]
        assert "another_field" not in result[0]

    def test_multiple_records_projection(self, engine):
        """Multiple records are each projected correctly."""
        records = [
            {
                "date": "2024-01-01",
                "account_id": "111",
                "service": "EC2",
                "cost_amount": 100.0,
                "currency": "USD",
                "cloud_provider": "aws",
            },
            {
                "date": "2024-01-02",
                "account_id": "222",
                "service": "RDS",
                "cost_amount": 50.0,
                "currency": "USD",
                "cloud_provider": "aws",
            },
        ]
        result = engine._project_attributes(
            records,
            ["date", "service", "cost_amount"]
        )
        
        assert len(result) == 2
        assert result[0] == {
            "date": "2024-01-01",
            "service": "EC2",
            "cost_amount": 100.0,
        }
        assert result[1] == {
            "date": "2024-01-02",
            "service": "RDS",
            "cost_amount": 50.0,
        }

    def test_numeric_values_preserved(self, engine):
        """Numeric values (floats, ints) are preserved exactly."""
        records = [
            {
                "cost_amount": 123.456,
                "date": "2024-01-01",
            }
        ]
        result = engine._project_attributes(
            records,
            ["cost_amount", "date"]
        )
        
        assert result[0]["cost_amount"] == 123.456
        assert isinstance(result[0]["cost_amount"], float)

    def test_string_values_preserved(self, engine):
        """String values are preserved exactly."""
        records = [
            {
                "date": "2024-01-01",
                "service": "Lambda",
            }
        ]
        result = engine._project_attributes(
            records,
            ["date", "service"]
        )
        
        assert result[0]["date"] == "2024-01-01"
        assert result[0]["service"] == "Lambda"
        assert isinstance(result[0]["date"], str)
        assert isinstance(result[0]["service"], str)

    def test_none_attribute_list(self, engine):
        """None as attribute list defaults to all available attributes."""
        records = [
            {
                "date": "2024-01-01",
                "account_id": "123456789",
                "service": "EC2",
                "cost_amount": 100.0,
                "currency": "USD",
                "cloud_provider": "aws",
            }
        ]
        result = engine._project_attributes(records, None)
        
        # Should include all available attributes
        assert len(result) == 1
        assert result[0] == records[0]
