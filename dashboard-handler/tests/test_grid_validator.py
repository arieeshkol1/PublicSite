"""Unit tests for grid position validation.

Tests cover:
- Valid layouts with proper positions
- Bounds checking: x, y non-negative; w, h >= 1
- Boundary enforcement: x + w <= 12 and y + h <= 48
- Overlap detection between widgets
- Edge cases: empty list, missing gridPosition, non-integer values

Requirements: 6.3, 6.4, 6.5
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from grid_validator import validate_grid_positions


def _widget(x, y, w, h, widget_id="widget-1"):
    """Create a widget dict with a gridPosition."""
    return {
        "id": widget_id,
        "type": "bar",
        "gridPosition": {"x": x, "y": y, "w": w, "h": h},
    }


class TestValidPositions:
    """Tests for valid grid layouts."""

    def test_empty_widget_list_is_valid(self):
        valid, error = validate_grid_positions([])
        assert valid is True
        assert error is None

    def test_single_widget_at_origin(self):
        widgets = [_widget(0, 0, 6, 4)]
        valid, error = validate_grid_positions(widgets)
        assert valid is True
        assert error is None

    def test_single_widget_full_width(self):
        widgets = [_widget(0, 0, 12, 1)]
        valid, error = validate_grid_positions(widgets)
        assert valid is True
        assert error is None

    def test_single_widget_full_height(self):
        widgets = [_widget(0, 0, 1, 48)]
        valid, error = validate_grid_positions(widgets)
        assert valid is True
        assert error is None

    def test_single_widget_fills_entire_grid(self):
        widgets = [_widget(0, 0, 12, 48)]
        valid, error = validate_grid_positions(widgets)
        assert valid is True
        assert error is None

    def test_two_non_overlapping_widgets_side_by_side(self):
        widgets = [
            _widget(0, 0, 6, 4, "w1"),
            _widget(6, 0, 6, 4, "w2"),
        ]
        valid, error = validate_grid_positions(widgets)
        assert valid is True
        assert error is None

    def test_two_non_overlapping_widgets_stacked(self):
        widgets = [
            _widget(0, 0, 12, 4, "w1"),
            _widget(0, 4, 12, 4, "w2"),
        ]
        valid, error = validate_grid_positions(widgets)
        assert valid is True
        assert error is None

    def test_multiple_non_overlapping_widgets(self):
        widgets = [
            _widget(0, 0, 4, 4, "w1"),
            _widget(4, 0, 4, 4, "w2"),
            _widget(8, 0, 4, 4, "w3"),
            _widget(0, 4, 6, 3, "w4"),
            _widget(6, 4, 6, 3, "w5"),
        ]
        valid, error = validate_grid_positions(widgets)
        assert valid is True
        assert error is None

    def test_widget_at_max_boundary(self):
        """Widget positioned at the maximum valid corner."""
        widgets = [_widget(11, 47, 1, 1)]
        valid, error = validate_grid_positions(widgets)
        assert valid is True
        assert error is None

    def test_widget_minimum_size(self):
        """Widget with w=1, h=1 is valid."""
        widgets = [_widget(5, 10, 1, 1)]
        valid, error = validate_grid_positions(widgets)
        assert valid is True
        assert error is None


class TestBoundsChecking:
    """Tests for x, y non-negative and w, h >= 1."""

    def test_negative_x_rejected(self):
        widgets = [_widget(-1, 0, 4, 4)]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "non-negative" in error

    def test_negative_y_rejected(self):
        widgets = [_widget(0, -1, 4, 4)]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "non-negative" in error

    def test_zero_width_rejected(self):
        widgets = [_widget(0, 0, 0, 4)]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "at least 1" in error

    def test_zero_height_rejected(self):
        widgets = [_widget(0, 0, 4, 0)]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "at least 1" in error

    def test_negative_width_rejected(self):
        widgets = [_widget(0, 0, -3, 4)]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "at least 1" in error

    def test_negative_height_rejected(self):
        widgets = [_widget(0, 0, 4, -2)]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "at least 1" in error


class TestBoundaryEnforcement:
    """Tests for x + w <= 12 and y + h <= 48."""

    def test_exceeds_grid_width(self):
        widgets = [_widget(10, 0, 4, 4)]  # 10 + 4 = 14 > 12
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "exceeds grid width" in error

    def test_exactly_at_grid_width_boundary(self):
        widgets = [_widget(8, 0, 4, 4)]  # 8 + 4 = 12, exactly at boundary
        valid, error = validate_grid_positions(widgets)
        assert valid is True
        assert error is None

    def test_exceeds_grid_height(self):
        widgets = [_widget(0, 46, 4, 4)]  # 46 + 4 = 50 > 48
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "exceeds grid height" in error

    def test_exactly_at_grid_height_boundary(self):
        widgets = [_widget(0, 44, 4, 4)]  # 44 + 4 = 48, exactly at boundary
        valid, error = validate_grid_positions(widgets)
        assert valid is True
        assert error is None

    def test_one_pixel_beyond_width(self):
        widgets = [_widget(12, 0, 1, 1)]  # 12 + 1 = 13 > 12
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "exceeds grid width" in error

    def test_one_pixel_beyond_height(self):
        widgets = [_widget(0, 48, 1, 1)]  # 48 + 1 = 49 > 48
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "exceeds grid height" in error


class TestOverlapDetection:
    """Tests for overlap detection between widgets."""

    def test_fully_overlapping_widgets(self):
        widgets = [
            _widget(0, 0, 6, 4, "w1"),
            _widget(0, 0, 6, 4, "w2"),  # Same position
        ]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "overlaps" in error

    def test_partially_overlapping_widgets(self):
        widgets = [
            _widget(0, 0, 6, 4, "w1"),
            _widget(3, 2, 6, 4, "w2"),  # Overlaps from column 3-5, row 2-3
        ]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "overlaps" in error

    def test_overlap_at_single_cell(self):
        widgets = [
            _widget(0, 0, 4, 4, "w1"),
            _widget(3, 3, 4, 4, "w2"),  # Overlaps only at cell (3, 3)
        ]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "overlaps" in error

    def test_adjacent_widgets_no_overlap(self):
        """Widgets touching edges but not overlapping."""
        widgets = [
            _widget(0, 0, 6, 4, "w1"),
            _widget(6, 0, 6, 4, "w2"),  # Adjacent horizontally
        ]
        valid, error = validate_grid_positions(widgets)
        assert valid is True
        assert error is None

    def test_third_widget_overlaps_first(self):
        widgets = [
            _widget(0, 0, 4, 4, "w1"),
            _widget(4, 0, 4, 4, "w2"),
            _widget(2, 2, 4, 4, "w3"),  # Overlaps w1 at (2,2), (3,2), etc.
        ]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "overlaps" in error
        assert "index 2" in error


class TestEdgeCases:
    """Tests for edge cases and invalid input types."""

    def test_non_list_input_rejected(self):
        valid, error = validate_grid_positions("not a list")
        assert valid is False
        assert "must be a list" in error

    def test_none_input_rejected(self):
        valid, error = validate_grid_positions(None)
        assert valid is False
        assert "must be a list" in error

    def test_widget_without_grid_position(self):
        widgets = [{"id": "w1", "type": "bar"}]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "missing" in error.lower() or "gridPosition" in error

    def test_widget_with_none_grid_position(self):
        widgets = [{"id": "w1", "type": "bar", "gridPosition": None}]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "missing" in error.lower() or "invalid" in error.lower()

    def test_widget_with_float_positions(self):
        widgets = [{"id": "w1", "gridPosition": {"x": 0.5, "y": 0, "w": 4, "h": 4}}]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "integer" in error.lower()

    def test_widget_with_string_positions(self):
        widgets = [{"id": "w1", "gridPosition": {"x": "0", "y": "0", "w": "4", "h": "4"}}]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "integer" in error.lower()

    def test_widget_is_not_a_dict(self):
        widgets = ["not a dict"]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "must be an object" in error

    def test_grid_position_missing_keys(self):
        widgets = [{"id": "w1", "gridPosition": {"x": 0, "y": 0}}]
        valid, error = validate_grid_positions(widgets)
        assert valid is False
        assert "integer" in error.lower()  # w and h will be None -> not isinstance int
