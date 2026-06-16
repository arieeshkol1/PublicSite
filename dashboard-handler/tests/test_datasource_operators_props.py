"""Property-based tests for DataSourceQueryEngine operator-type mapping.

Tests the operator mapping logic using hypothesis to verify that:
- Correct operator lists are returned per attribute type
- "text" attributes map to ["equals", "not_equals"]
- "numeric" attributes map to ["equals", "not_equals", "greater_than", "less_than"]
- Unknown attribute types raise appropriate errors
- Empty operator lists are never returned
- Operator order is consistent across multiple calls
- Attributes from DATASOURCE_AVAILABLE_ATTRIBUTES are correctly typed
- Invalid attributes raise errors

Validates: Requirements 5.4
"""

import sys
import os
from unittest.mock import MagicMock

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

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


# Strategy for generating attributes from the available set
def available_attributes():
    """Generate random attributes from DATASOURCE_AVAILABLE_ATTRIBUTES."""
    return st.sampled_from(DATASOURCE_AVAILABLE_ATTRIBUTES)


# Strategy for generating invalid attribute names
def invalid_attributes():
    """Generate attribute names that are NOT in DATASOURCE_AVAILABLE_ATTRIBUTES."""
    return st.text(min_size=1, max_size=50).filter(
        lambda x: x not in DATASOURCE_AVAILABLE_ATTRIBUTES
    )


class TestOperatorTypeMapping:
    """Property-based tests for operator-type mapping.
    
    **Validates: Requirements 5.4**
    
    Requirement 5.4: Filter operators mapped by attribute type:
    - "text" attributes → ["equals", "not_equals"]
    - "numeric" attributes → ["equals", "not_equals", "greater_than", "less_than"]
    """

    @given(attribute=available_attributes())
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_operators_match_attribute_type(self, engine, attribute):
        """Property: Operator list matches the attribute type from mapping.
        
        For any available attribute, when requesting operators for that attribute,
        the returned list must correspond to the attribute's type in
        DATASOURCE_ATTRIBUTE_TYPES and DATASOURCE_FILTER_OPERATORS.
        """
        # Get the attribute type
        attr_type = DATASOURCE_ATTRIBUTE_TYPES.get(attribute)
        assert attr_type is not None, (
            f"Attribute {attribute} not found in DATASOURCE_ATTRIBUTE_TYPES"
        )
        
        # Get expected operators for this type
        expected_operators = DATASOURCE_FILTER_OPERATORS.get(attr_type)
        assert expected_operators is not None, (
            f"Type {attr_type} not found in DATASOURCE_FILTER_OPERATORS"
        )
        
        # Get operators from engine
        result_operators = engine.get_operators_for_attribute(attribute)
        
        # Must be the exact same list (order and content)
        assert result_operators == expected_operators, (
            f"Operators for attribute '{attribute}' (type: {attr_type}) "
            f"mismatch: got {result_operators}, expected {expected_operators}"
        )

    @given(attribute=st.sampled_from([
        attr for attr in DATASOURCE_AVAILABLE_ATTRIBUTES
        if DATASOURCE_ATTRIBUTE_TYPES.get(attr) == "text"
    ]))
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_text_attributes_have_correct_operators(self, engine, attribute):
        """Property: Text attributes always have exactly ["equals", "not_equals"].
        
        For any attribute with type "text", the returned operator list must be
        exactly ["equals", "not_equals"] with no other operators.
        """
        result = engine.get_operators_for_attribute(attribute)
        expected = ["equals", "not_equals"]
        
        assert result == expected, (
            f"Text attribute '{attribute}' has wrong operators: "
            f"got {result}, expected {expected}"
        )
        
        # Verify count
        assert len(result) == 2, (
            f"Text attribute '{attribute}' should have exactly 2 operators, got {len(result)}"
        )
        
        # Verify no empty or None values
        for op in result:
            assert op, f"Empty operator in text attribute result"
            assert isinstance(op, str), f"Operator must be string, got {type(op)}"

    @given(attribute=st.sampled_from([
        attr for attr in DATASOURCE_AVAILABLE_ATTRIBUTES
        if DATASOURCE_ATTRIBUTE_TYPES.get(attr) == "numeric"
    ]))
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_numeric_attributes_have_correct_operators(self, engine, attribute):
        """Property: Numeric attributes always have exactly 4 comparison operators.
        
        For any attribute with type "numeric", the returned operator list must be
        exactly ["equals", "not_equals", "greater_than", "less_than"] in that order.
        """
        result = engine.get_operators_for_attribute(attribute)
        expected = ["equals", "not_equals", "greater_than", "less_than"]
        
        assert result == expected, (
            f"Numeric attribute '{attribute}' has wrong operators: "
            f"got {result}, expected {expected}"
        )
        
        # Verify count
        assert len(result) == 4, (
            f"Numeric attribute '{attribute}' should have exactly 4 operators, got {len(result)}"
        )
        
        # Verify all operators are non-empty strings
        for op in result:
            assert op, f"Empty operator in numeric attribute result"
            assert isinstance(op, str), f"Operator must be string, got {type(op)}"

    @given(attribute=available_attributes())
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_operators_never_empty_for_valid_attribute(self, engine, attribute):
        """Property: Valid attributes never return empty operator lists.
        
        For any available attribute, the operator list must never be empty.
        """
        result = engine.get_operators_for_attribute(attribute)
        
        assert result, (
            f"Attribute '{attribute}' returned empty operator list"
        )
        assert len(result) > 0, (
            f"Attribute '{attribute}' has no operators"
        )

    @given(attribute=available_attributes())
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_operators_list_no_duplicates(self, engine, attribute):
        """Property: Operator lists never contain duplicate values.
        
        For any attribute, the returned operator list must have unique values.
        """
        result = engine.get_operators_for_attribute(attribute)
        
        # Check no duplicates
        assert len(result) == len(set(result)), (
            f"Attribute '{attribute}' has duplicate operators: {result}"
        )

    @given(attribute=available_attributes())
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_operators_all_strings(self, engine, attribute):
        """Property: All operators are non-empty strings.
        
        For any attribute, every operator in the list must be a non-empty string.
        """
        result = engine.get_operators_for_attribute(attribute)
        
        for i, op in enumerate(result):
            assert isinstance(op, str), (
                f"Operator at index {i} is not string for attribute '{attribute}': "
                f"got {type(op)} value {op}"
            )
            assert len(op) > 0, (
                f"Operator at index {i} is empty string for attribute '{attribute}'"
            )
            assert op.strip() == op, (
                f"Operator at index {i} has leading/trailing whitespace: '{op}'"
            )

    @given(attribute=available_attributes())
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_operators_consistent_across_calls(self, engine, attribute):
        """Property: Calling get_operators multiple times returns same result.
        
        For any attribute, multiple calls to get_operators_for_attribute must
        always return the same operator list (idempotency + determinism).
        """
        result1 = engine.get_operators_for_attribute(attribute)
        result2 = engine.get_operators_for_attribute(attribute)
        result3 = engine.get_operators_for_attribute(attribute)
        
        assert result1 == result2 == result3, (
            f"Inconsistent operators for attribute '{attribute}': "
            f"call1={result1}, call2={result2}, call3={result3}"
        )

    @given(attribute=available_attributes())
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_operators_order_preserved(self, engine, attribute):
        """Property: Operator order is always preserved for an attribute.
        
        The order of operators must be consistent across all calls and
        match the order defined in DATASOURCE_FILTER_OPERATORS.
        """
        result = engine.get_operators_for_attribute(attribute)
        attr_type = DATASOURCE_ATTRIBUTE_TYPES[attribute]
        expected_order = DATASOURCE_FILTER_OPERATORS[attr_type]
        
        # Verify same order
        assert result == expected_order, (
            f"Operator order not preserved for '{attribute}': "
            f"got {result}, expected {expected_order}"
        )
        
        # Verify not just same set but same sequence
        assert list(result) == list(expected_order), (
            f"Operator sequence mismatch for '{attribute}'"
        )

    def test_all_available_attributes_have_defined_type(self, engine):
        """Property: Every available attribute has a type mapping.
        
        For all attributes in DATASOURCE_AVAILABLE_ATTRIBUTES, each must
        have an entry in DATASOURCE_ATTRIBUTE_TYPES.
        """
        for attribute in DATASOURCE_AVAILABLE_ATTRIBUTES:
            assert attribute in DATASOURCE_ATTRIBUTE_TYPES, (
                f"Attribute '{attribute}' missing from DATASOURCE_ATTRIBUTE_TYPES"
            )

    def test_all_attribute_types_have_operators_defined(self, engine):
        """Property: Every attribute type in the mapping has operators defined.
        
        For each type used in DATASOURCE_ATTRIBUTE_TYPES, there must be a
        corresponding entry in DATASOURCE_FILTER_OPERATORS.
        """
        types_used = set(DATASOURCE_ATTRIBUTE_TYPES.values())
        
        for attr_type in types_used:
            assert attr_type in DATASOURCE_FILTER_OPERATORS, (
                f"Type '{attr_type}' used in DATASOURCE_ATTRIBUTE_TYPES "
                f"but not in DATASOURCE_FILTER_OPERATORS"
            )

    def test_operators_only_two_types(self, engine):
        """Property: Only "text" and "numeric" types have operators defined.
        
        DATASOURCE_FILTER_OPERATORS should only have entries for
        "text" and "numeric" types.
        """
        valid_types = {"text", "numeric"}
        
        for op_type in DATASOURCE_FILTER_OPERATORS.keys():
            assert op_type in valid_types, (
                f"Unexpected operator type in mapping: '{op_type}'"
            )


class TestOperatorTypeErrorHandling:
    """Tests for error handling with invalid attributes.
    
    **Validates: Requirements 5.4**
    """

    @given(attribute=invalid_attributes())
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_unknown_attribute_raises_error(self, engine, attribute):
        """Property: Unknown attributes raise an error.
        
        For any attribute NOT in DATASOURCE_AVAILABLE_ATTRIBUTES,
        get_operators_for_attribute must raise ValueError or KeyError.
        """
        # Skip if by chance the generated string matches an available attribute
        if attribute in DATASOURCE_AVAILABLE_ATTRIBUTES:
            return
        
        with pytest.raises((ValueError, KeyError)) as exc_info:
            engine.get_operators_for_attribute(attribute)
        
        error_msg = str(exc_info.value).lower()
        # Error should mention the attribute or indicate it's unknown
        assert "attribute" in error_msg or "unknown" in error_msg or \
               "not found" in error_msg or "invalid" in error_msg, (
            f"Error message unclear for unknown attribute '{attribute}': {exc_info.value}"
        )

    def test_none_attribute_raises_error(self, engine):
        """None as attribute raises an error."""
        with pytest.raises((ValueError, TypeError, AttributeError)):
            engine.get_operators_for_attribute(None)

    def test_empty_string_attribute_raises_error(self, engine):
        """Empty string as attribute raises an error."""
        with pytest.raises((ValueError, KeyError)):
            engine.get_operators_for_attribute("")

    def test_integer_attribute_raises_error(self, engine):
        """Integer as attribute raises an error."""
        with pytest.raises((ValueError, TypeError)):
            engine.get_operators_for_attribute(12345)

    def test_list_attribute_raises_error(self, engine):
        """List as attribute raises an error."""
        with pytest.raises((ValueError, TypeError)):
            engine.get_operators_for_attribute(["date", "service"])

    def test_dict_attribute_raises_error(self, engine):
        """Dict as attribute raises an error."""
        with pytest.raises((ValueError, TypeError)):
            engine.get_operators_for_attribute({"attr": "date"})


class TestOperatorTypeEdgeCases:
    """Edge case unit tests for operator-type mapping."""

    def test_date_attribute_is_text_type(self, engine):
        """Edge case: 'date' attribute has type 'text'."""
        assert DATASOURCE_ATTRIBUTE_TYPES["date"] == "text"
        result = engine.get_operators_for_attribute("date")
        assert result == ["equals", "not_equals"]

    def test_account_id_attribute_is_text_type(self, engine):
        """Edge case: 'account_id' attribute has type 'text'."""
        assert DATASOURCE_ATTRIBUTE_TYPES["account_id"] == "text"
        result = engine.get_operators_for_attribute("account_id")
        assert result == ["equals", "not_equals"]

    def test_service_attribute_is_text_type(self, engine):
        """Edge case: 'service' attribute has type 'text'."""
        assert DATASOURCE_ATTRIBUTE_TYPES["service"] == "text"
        result = engine.get_operators_for_attribute("service")
        assert result == ["equals", "not_equals"]

    def test_cost_amount_attribute_is_numeric_type(self, engine):
        """Edge case: 'cost_amount' attribute has type 'numeric'."""
        assert DATASOURCE_ATTRIBUTE_TYPES["cost_amount"] == "numeric"
        result = engine.get_operators_for_attribute("cost_amount")
        assert result == ["equals", "not_equals", "greater_than", "less_than"]

    def test_currency_attribute_is_text_type(self, engine):
        """Edge case: 'currency' attribute has type 'text'."""
        assert DATASOURCE_ATTRIBUTE_TYPES["currency"] == "text"
        result = engine.get_operators_for_attribute("currency")
        assert result == ["equals", "not_equals"]

    def test_cloud_provider_attribute_is_text_type(self, engine):
        """Edge case: 'cloud_provider' attribute has type 'text'."""
        assert DATASOURCE_ATTRIBUTE_TYPES["cloud_provider"] == "text"
        result = engine.get_operators_for_attribute("cloud_provider")
        assert result == ["equals", "not_equals"]

    def test_text_operators_in_expected_order(self, engine):
        """Text operators are in specific order: equals, not_equals."""
        result = DATASOURCE_FILTER_OPERATORS["text"]
        assert result[0] == "equals"
        assert result[1] == "not_equals"

    def test_numeric_operators_in_expected_order(self, engine):
        """Numeric operators are in specific order."""
        result = DATASOURCE_FILTER_OPERATORS["numeric"]
        assert result[0] == "equals"
        assert result[1] == "not_equals"
        assert result[2] == "greater_than"
        assert result[3] == "less_than"

    def test_numeric_operators_includes_comparison_operators(self, engine):
        """Numeric operators include comparison operators."""
        operators = DATASOURCE_FILTER_OPERATORS["numeric"]
        assert "greater_than" in operators
        assert "less_than" in operators

    def test_case_sensitivity_in_attribute_names(self, engine):
        """Attribute names are case-sensitive."""
        with pytest.raises((ValueError, KeyError)):
            engine.get_operators_for_attribute("Date")  # Wrong case

    def test_case_sensitivity_in_operator_names(self, engine):
        """Operator names preserve their case."""
        result = engine.get_operators_for_attribute("date")
        # All operators should be lowercase (following existing pattern)
        for op in result:
            assert op.islower() or "_" in op, (
                f"Operator '{op}' should be lowercase: {result}"
            )

    def test_all_required_attributes_present(self, engine):
        """All required attributes are in DATASOURCE_AVAILABLE_ATTRIBUTES."""
        required_attrs = {"date", "account_id", "service", "cost_amount", "currency", "cloud_provider"}
        available_attrs = set(DATASOURCE_AVAILABLE_ATTRIBUTES)
        
        missing = required_attrs - available_attrs
        assert not missing, f"Missing required attributes: {missing}"

    def test_attribute_type_mapping_completeness(self, engine):
        """All available attributes have type mappings."""
        for attr in DATASOURCE_AVAILABLE_ATTRIBUTES:
            assert attr in DATASOURCE_ATTRIBUTE_TYPES, (
                f"Attribute '{attr}' has no type mapping"
            )
            
            attr_type = DATASOURCE_ATTRIBUTE_TYPES[attr]
            assert attr_type in DATASOURCE_FILTER_OPERATORS, (
                f"Type '{attr_type}' for attribute '{attr}' has no operators"
            )

    def test_no_extra_attributes_in_type_mapping(self, engine):
        """No extra attributes in type mapping beyond available attributes."""
        extra = set(DATASOURCE_ATTRIBUTE_TYPES.keys()) - set(DATASOURCE_AVAILABLE_ATTRIBUTES)
        assert not extra, (
            f"Extra attributes in DATASOURCE_ATTRIBUTE_TYPES: {extra}"
        )

    def test_numeric_operators_superset_of_text_operators(self, engine):
        """Numeric operators include all text operators plus comparisons."""
        text_ops = set(DATASOURCE_FILTER_OPERATORS["text"])
        numeric_ops = set(DATASOURCE_FILTER_OPERATORS["numeric"])
        
        # All text operators should be in numeric
        assert text_ops.issubset(numeric_ops), (
            f"Numeric operators should include text operators: "
            f"text={text_ops}, numeric={numeric_ops}"
        )
        
        # Numeric should have more than text
        assert len(numeric_ops) > len(text_ops), (
            f"Numeric should have more operators than text"
        )


class TestOperatorTypeDocumentation:
    """Tests that verify documented behavior of operator mapping."""

    def test_text_type_has_equality_operators_only(self, engine):
        """Documentation: Text type operators are equality-based only."""
        ops = DATASOURCE_FILTER_OPERATORS["text"]
        
        # Should have equals and not_equals
        assert "equals" in ops
        assert "not_equals" in ops
        
        # Should NOT have comparison operators
        assert "greater_than" not in ops
        assert "less_than" not in ops
        assert "gte" not in ops
        assert "lte" not in ops

    def test_numeric_type_has_all_comparison_operators(self, engine):
        """Documentation: Numeric type has equality + comparison operators."""
        ops = DATASOURCE_FILTER_OPERATORS["numeric"]
        
        # Should have equality operators
        assert "equals" in ops
        assert "not_equals" in ops
        
        # Should have comparison operators
        assert "greater_than" in ops
        assert "less_than" in ops

    def test_mapping_consistency_across_all_attributes(self, engine):
        """All attributes of same type have same operators."""
        # Group attributes by type
        type_to_attrs = {}
        for attr, attr_type in DATASOURCE_ATTRIBUTE_TYPES.items():
            if attr_type not in type_to_attrs:
                type_to_attrs[attr_type] = []
            type_to_attrs[attr_type].append(attr)
        
        # For each type, all attributes should have same operators
        for attr_type, attrs in type_to_attrs.items():
            expected_ops = DATASOURCE_FILTER_OPERATORS[attr_type]
            
            for attr in attrs:
                actual_ops = engine.get_operators_for_attribute(attr)
                assert actual_ops == expected_ops, (
                    f"Operators for attribute '{attr}' ({attr_type}) "
                    f"differ from expected: {actual_ops} != {expected_ops}"
                )
