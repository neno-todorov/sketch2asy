"""Fast coordinate extraction for FreeCAD geometry elements."""

from __future__ import annotations

from typing import Any


def get_coordinates(pnt: Any) -> tuple[float, float]:
    """Extracts (x, y) coordinates from FreeCAD Vectors, Points, or tuples."""
    if hasattr(pnt, "x") and hasattr(pnt, "y"):
        return float(pnt.x), float(pnt.y)
    if hasattr(pnt, "X") and hasattr(pnt, "Y"):
        return float(pnt.X), float(pnt.Y)
    try:
        return float(pnt[0]), float(pnt[1])
    except (IndexError, TypeError, KeyError):
        return 0.0, 0.0
