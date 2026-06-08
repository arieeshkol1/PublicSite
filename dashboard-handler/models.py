"""
Data models for the Widget Builder Dashboard.

Defines dataclass models for widget configuration, grid positioning,
and layout persistence used across the backend components.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GridPosition:
    """
    Represents a widget's placement on the 12-column grid.

    Attributes:
        x: Column start position (0-indexed, non-negative integer)
        y: Row start position (0-indexed, non-negative integer)
        w: Width in columns (integer >= 1, x + w <= 12)
        h: Height in rows (integer >= 1, y + h <= 48)
    """
    x: int
    y: int
    w: int
    h: int

    def to_dict(self) -> dict:
        """Serialize grid position to a dictionary."""
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}

    @classmethod
    def from_dict(cls, data: dict) -> "GridPosition":
        """Create a GridPosition from a dictionary."""
        return cls(
            x=data.get("x", 0),
            y=data.get("y", 0),
            w=data.get("w", 1),
            h=data.get("h", 1),
        )


@dataclass
class WidgetConfig:
    """
    Represents the full configuration for a single dashboard widget.

    Attributes:
        id: Unique widget identifier (UUID string)
        type: Visualization type (bar, line, pie, table, kpi, gauge)
        title: Display title for the widget
        data_source: Data source configuration dict with source, accountIds, dateRange
        dimensions: List of dimension fields to group by (max 3)
        filters: List of filter configurations (field, operator, value)
        aggregation: Aggregation method (sum, avg, max, min, count)
        display: Display options (colorScheme, showLegend, stacked, threshold)
        grid_position: Widget placement on the grid
    """
    id: str
    type: str
    title: str
    data_source: dict
    aggregation: str
    dimensions: list = field(default_factory=list)
    filters: list = field(default_factory=list)
    display: dict = field(default_factory=dict)
    grid_position: Optional[GridPosition] = None

    def to_dict(self) -> dict:
        """Serialize widget config to a dictionary for persistence."""
        result = {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "dataSource": self.data_source,
            "aggregation": self.aggregation,
            "dimensions": self.dimensions,
            "filters": self.filters,
            "display": self.display,
        }
        if self.grid_position:
            result["gridPosition"] = self.grid_position.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "WidgetConfig":
        """Create a WidgetConfig from a dictionary."""
        grid_pos = None
        if "gridPosition" in data and data["gridPosition"]:
            grid_pos = GridPosition.from_dict(data["gridPosition"])

        return cls(
            id=data.get("id", ""),
            type=data.get("type", ""),
            title=data.get("title", ""),
            data_source=data.get("dataSource", {}),
            aggregation=data.get("aggregation", ""),
            dimensions=data.get("dimensions", []),
            filters=data.get("filters", []),
            display=data.get("display", {}),
            grid_position=grid_pos,
        )


@dataclass
class Layout:
    """
    Represents a dashboard layout containing widgets and their grid positions.

    Attributes:
        layout_id: Unique layout identifier (UUID string)
        layout_name: User-defined name for the layout (1-64 characters)
        member_email: Email of the layout owner (partition key)
        widgets: List of WidgetConfig objects (max 20 per layout)
        created_at: ISO 8601 UTC timestamp of creation
        updated_at: ISO 8601 UTC timestamp of last update
    """
    layout_id: str
    layout_name: str
    member_email: str
    widgets: list = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        """Serialize layout to a dictionary for API responses."""
        return {
            "layout_id": self.layout_id,
            "layout_name": self.layout_name,
            "member_email": self.member_email,
            "widgets": [
                w.to_dict() if isinstance(w, WidgetConfig) else w
                for w in self.widgets
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_dynamo_item(self) -> dict:
        """Serialize layout to a DynamoDB item format."""
        return {
            "pk": self.member_email,
            "sk": f"LAYOUT#{self.layout_id}",
            "layout_name": self.layout_name,
            "widgets": [
                w.to_dict() if isinstance(w, WidgetConfig) else w
                for w in self.widgets
            ],
            "grid_columns": 12,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "Layout":
        """Create a Layout from a DynamoDB item."""
        layout_id = item.get("sk", "").replace("LAYOUT#", "")
        widgets = [
            WidgetConfig.from_dict(w) if isinstance(w, dict) else w
            for w in item.get("widgets", [])
        ]

        return cls(
            layout_id=layout_id,
            layout_name=item.get("layout_name", ""),
            member_email=item.get("pk", ""),
            widgets=widgets,
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
        )
