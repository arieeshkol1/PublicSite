"""Grid position validation for the Widget Builder Dashboard.

Validates widget grid positions to ensure:
- x, y are non-negative integers
- w, h are integers >= 1
- x + w <= GRID_COLS (12) and y + h <= MAX_ROWS (48)
- No two widgets occupy the same grid cell (overlap detection)

Requirements: 6.3, 6.4, 6.5
"""

from constants import GRID_COLS, MAX_ROWS


def validate_grid_positions(widgets: list) -> tuple[bool, str | None]:
    """Validate grid positions for a list of widgets.

    Checks that all widget positions are within bounds and that no two
    widgets occupy the same grid cell.

    Args:
        widgets: List of widget dicts, each expected to have a 'gridPosition'
                 dict with keys x, y, w, h.

    Returns:
        Tuple of (is_valid: bool, error_message: str | None).
        Returns (True, None) if all positions are valid and non-overlapping.
        Returns (False, error_message) describing the first violation found.
    """
    if not isinstance(widgets, list):
        return (False, "Widgets must be a list")

    occupied = set()  # set of (col, row) tuples

    for idx, widget in enumerate(widgets):
        if not isinstance(widget, dict):
            return (False, f"Widget at index {idx}: must be an object")

        grid_pos = widget.get("gridPosition")
        if grid_pos is None or not isinstance(grid_pos, dict):
            return (False, f"Widget at index {idx}: missing or invalid gridPosition")

        x = grid_pos.get("x")
        y = grid_pos.get("y")
        w = grid_pos.get("w")
        h = grid_pos.get("h")

        # Reject booleans masquerading as integers (bool is subclass of int in Python)
        if isinstance(x, bool) or isinstance(y, bool) or isinstance(w, bool) or isinstance(h, bool):
            return (False, f"Widget at index {idx}: position values must be integers, not booleans")

        # Validate types: x, y must be integers (non-negative)
        if not isinstance(x, int) or not isinstance(y, int):
            return (False, f"Widget at index {idx}: x and y must be integers")

        # Validate types: w, h must be integers (>= 1)
        if not isinstance(w, int) or not isinstance(h, int):
            return (False, f"Widget at index {idx}: w and h must be integers")

        # Validate non-negative x, y
        if x < 0 or y < 0:
            return (False, f"Widget at index {idx}: x and y must be non-negative (got x={x}, y={y})")

        # Validate w, h >= 1
        if w < 1 or h < 1:
            return (False, f"Widget at index {idx}: w and h must be at least 1 (got w={w}, h={h})")

        # Validate x + w <= GRID_COLS (12)
        if x + w > GRID_COLS:
            return (False, f"Widget at index {idx}: exceeds grid width (x={x} + w={w} = {x + w} > {GRID_COLS})")

        # Validate y + h <= MAX_ROWS (48)
        if y + h > MAX_ROWS:
            return (False, f"Widget at index {idx}: exceeds grid height (y={y} + h={h} = {y + h} > {MAX_ROWS})")

        # Check overlap: ensure no cell is already occupied
        for col in range(x, x + w):
            for row in range(y, y + h):
                if (col, row) in occupied:
                    return (False, f"Widget at index {idx}: overlaps with another widget at cell ({col}, {row})")
                occupied.add((col, row))

    return (True, None)
