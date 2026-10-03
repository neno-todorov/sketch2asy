"""Basic configuration for sketch2asy."""

from __future__ import annotations

version: str = "2026-10-03"
accuracy: int = -1
decimal_places_to_round: int = 6
comments_indent: int = 30

unitsize: str = "1pt"
construction_pen_name: str = "construction"
construction_pen_color: str = "lightblue"

print_dot_labels: bool = True
skip_construction: bool = False
comment_construction: bool = False
show_internal_geometry: bool = True