"""Coordinate extraction utilities for FreeCAD geometry objects."""

from __future__ import annotations

from typing import Any


def get_coordinates(pnt: Any) -> tuple[float, float]:
    """
    Extracts (x, y) coordinates from FreeCAD Vectors, Points, tuples, or NumPy arrays.
    Uses direct attribute inspection for maximum performance without creating temporary objects.
    """
    if hasattr(pnt, "x") and hasattr(pnt, "y"):
        return float(pnt.x), float(pnt.y)
    if hasattr(pnt, "X") and hasattr(pnt, "Y"):
        return float(pnt.X), float(pnt.Y)
    try:
        return float(pnt[0]), float(pnt[1])
    except (IndexError, TypeError, KeyError):
        return 0.0, 0.0