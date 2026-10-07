"""Modular SymPy-powered constraint solver with FreeCAD branch selection."""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Any

import sympy as sp

import draw
from coordinates import get_coordinates

if TYPE_CHECKING:
    # pyrefly: ignore [missing-import]
    import Sketcher  # noqa: F401

_GEO_NONE = -2000
_XAXIS_ID = -1
_YAXIS_ID = -2

DIM_TYPES: tuple[str, ...] = (
    "Distance",
    "DistanceX",
    "DistanceY",
    "Radius",
    "Diameter",
    "Angle",
)


# FreeCAD C++ constant for unassigned geometry (Sketcher::GeoEnum::GeoUndef = -2000)
def _is_geo_none(geo_id: int | None) -> bool:
    """
    Returns True if geo_id represents 'no geometry' (GeoUndef / None).

    FreeCAD Geometry ID Mapping:
      - geo_id >= 0:  Normal sketch geometry (lines, circles, arcs)
      - geo_id == -1: Horizontal sketch axis (X-axis, y = 0)
      - geo_id == -2: Vertical sketch axis (Y-axis, x = 0)
      - geo_id in [-3 .. -1999]: External reference geometry linked from other 3D bodies
      - geo_id <= -2000 or None: Unassigned / GeoUndef (no second/third geometry)
    """
    if geo_id is None:
        return True
    return geo_id <= _GEO_NONE


def sanitize_name(name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    if not clean or clean[0].isdigit():
        clean = f"param_{clean}"
    return clean


def sympy_to_asy(expr: sp.Expr) -> str:
    """Formats SymPy expressions cleanly for Asymptote."""
    s = str(sp.simplify(expr))
    s = re.sub(r"([a-zA-Z0-9_]+)\*\*2", r"(\1)^2", s)
    s = re.sub(r"\((.*?)\)\*\*2", r"((\1))^2", s)
    s = s.replace("**", "^")
    s = re.sub(r"(P\d+)_x", r"\1.x", s)
    s = re.sub(r"(P\d+)_y", r"\1.y", s)
    return s


# ======================================================================
# Solver Context & Disjoint Set
# ======================================================================


class DisjointSet:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        if item not in self.parent:
            self.parent[item] = item
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, a: str, b: str, formulas: dict[str, str] | None = None) -> str:
        ra = self.find(a)
        rb = self.find(b)
        if ra != rb:
            if ra in ("__X_ORIGIN__", "__Y_ORIGIN__"):
                pass
            elif (
                rb in ("__X_ORIGIN__", "__Y_ORIGIN__")
                or formulas is not None
                and rb in formulas
                and ra not in formulas
            ):
                ra, rb = rb, ra

            self.parent[rb] = ra
            if formulas is not None and rb in formulas and ra not in formulas:
                formulas[ra] = formulas.pop(rb)
        return ra


# ======================================================================
# Modular Constraint Handlers
# ======================================================================


class BaseHandler:
    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        pass

    def process_nonlinear(self, model: ParametricModel, c: Any, idx: int) -> None:
        pass


class HorizontalHandler(BaseHandler):
    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        p1 = model._resolve_point_ref(c.First, 1 if c.FirstPos == 0 else c.FirstPos)
        p2 = model._resolve_point_ref(
            c.First if c.FirstPos == 0 else c.Second,
            2 if c.FirstPos == 0 else c.SecondPos,
        )
        if p1 and p2:
            model.y_sets.union(p1, p2, model.y_formulas)


class VerticalHandler(BaseHandler):
    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        p1 = model._resolve_point_ref(c.First, 1 if c.FirstPos == 0 else c.FirstPos)
        p2 = model._resolve_point_ref(
            c.First if c.FirstPos == 0 else c.Second,
            2 if c.FirstPos == 0 else c.SecondPos,
        )
        if p1 and p2:
            model.x_sets.union(p1, p2, model.x_formulas)


class DistanceXHandler(BaseHandler):
    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        param = model.constraint_vars.get(idx)
        if not param:
            return
        p1, p2 = model._get_constraint_pair(c)
        if p1 and p2 and p1 in model.point_coords and p2 in model.point_coords:
            dx = model.point_coords[p2][0] - model.point_coords[p1][0]
            model.x_edges.append(
                (model.x_sets.find(p1), model.x_sets.find(p2), param, dx)
            )


class DistanceYHandler(BaseHandler):
    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        param = model.constraint_vars.get(idx)
        if not param:
            return
        p1, p2 = model._get_constraint_pair(c)
        if p1 and p2 and p1 in model.point_coords and p2 in model.point_coords:
            dy = model.point_coords[p2][1] - model.point_coords[p1][1]
            model.y_edges.append(
                (model.y_sets.find(p1), model.y_sets.find(p2), param, dy)
            )


class DistanceHandler(BaseHandler):
    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        param = model.constraint_vars.get(idx)
        if not param:
            return

        # Axis-pinned distances
        if (c.Second == _XAXIS_ID and c.SecondPos == 0) or (
            c.First == _XAXIS_ID and c.FirstPos == 0
        ):
            tgt_geo = c.First if c.Second == _XAXIS_ID else c.Second
            tgt_pos = c.FirstPos if c.Second == _XAXIS_ID else c.SecondPos
            pt = model._resolve_point_ref(tgt_geo, 1 if tgt_pos == 0 else tgt_pos)
            if pt and pt in model.point_coords:
                root_y = model.y_sets.find(pt)
                sign = "" if model.point_coords[pt][1] >= 0 else "-"
                model.y_formulas[root_y] = f"{sign}{param}"
            return

        if (c.Second == _YAXIS_ID and c.SecondPos == 0) or (
            c.First == _YAXIS_ID and c.FirstPos == 0
        ):
            tgt_geo = c.First if c.Second == _YAXIS_ID else c.Second
            tgt_pos = c.FirstPos if c.Second == _YAXIS_ID else c.SecondPos
            pt = model._resolve_point_ref(tgt_geo, 1 if tgt_pos == 0 else tgt_pos)
            if pt and pt in model.point_coords:
                root_x = model.x_sets.find(pt)
                sign = "" if model.point_coords[pt][0] >= 0 else "-"
                model.x_formulas[root_x] = f"{sign}{param}"
            return

        p1, p2 = model._get_constraint_pair(c)
        if not (p1 and p2 and p1 in model.point_coords and p2 in model.point_coords):
            return

        c1, c2 = model.point_coords[p1], model.point_coords[p2]
        dx = c2[0] - c1[0]
        dy = c2[1] - c1[1]

        # Orthogonal lines
        if abs(dy) < 1e-4:
            model.x_edges.append(
                (model.x_sets.find(p1), model.x_sets.find(p2), param, dx)
            )
        elif abs(dx) < 1e-4:
            model.y_edges.append(
                (model.y_sets.find(p1), model.y_sets.find(p2), param, dy)
            )
        else:
            model.length_lines[c.First] = (p1, p2, param)


class PointOnObjectHandler(BaseHandler):
    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        pt = model._resolve_point_ref(c.First, c.FirstPos)
        target = c.Second
        if not pt:
            pt = model._resolve_point_ref(c.Second, c.SecondPos)
            target = c.First

        if not pt:
            return

        if target == _XAXIS_ID:
            model.y_sets.union(pt, "__Y_ORIGIN__", model.y_formulas)
        elif target == _YAXIS_ID:
            model.x_sets.union(pt, "__X_ORIGIN__", model.x_formulas)
        elif 0 <= target < len(model.sketch.Geometry):
            geom = model.sketch.Geometry[target]
            if hasattr(geom, "StartPoint") and hasattr(geom, "EndPoint"):
                ps = get_coordinates(geom.StartPoint)
                pe = get_coordinates(geom.EndPoint)
                line_ref = model.vertex_map.get((target, 1))
                if line_ref:
                    if abs(ps[1] - pe[1]) < 1e-4:
                        model.y_sets.union(pt, line_ref, model.y_formulas)
                    elif abs(ps[0] - pe[0]) < 1e-4:
                        model.x_sets.union(pt, line_ref, model.x_formulas)


class SymmetricHandler(BaseHandler):
    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        fp = c.FirstPos if c.FirstPos else 1
        sp = c.SecondPos if c.SecondPos else 1
        p1 = model._resolve_point_ref(c.First, fp)
        p2 = model._resolve_point_ref(c.Second, sp)
        if not (p1 and p2 and p1 in model.point_coords and p2 in model.point_coords):
            return

        third = getattr(c, "Third", _GEO_NONE)
        third_pos = getattr(c, "ThirdPos", 0)

        if third == _XAXIS_ID:
            model.x_sets.union(p1, p2, model.x_formulas)
            model.y_reflections.append((p1, p2, "__Y_ORIGIN__"))
        elif third == _YAXIS_ID:
            model.y_sets.union(p1, p2, model.y_formulas)
            model.x_reflections.append((p1, p2, "__X_ORIGIN__"))
        elif not (third <= _GEO_NONE or third < -100) and third_pos != 0:
            p3 = model._resolve_point_ref(third, third_pos)
            if p3 and p3 in model.point_coords:
                model.x_midpoints.append((p1, p2, p3))
                model.y_midpoints.append((p1, p2, p3))


class AngleHandler(BaseHandler):
    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        param = model.constraint_vars.get(idx)
        if not param:
            return
        p_v1 = model._resolve_point_ref(c.First, c.FirstPos)
        p_v2 = model._resolve_point_ref(c.Second, c.SecondPos)
        common = p_v1 if (p_v1 and p_v1 == p_v2) else None
        if common:
            model.angle_constraints.append((c.First, c.Second, param, common))


class EqualHandler(BaseHandler):
    """Handles Equal constraints between lines (lengths) or circles/arcs (radii)."""

    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        g1_id = c.First
        g2_id = c.Second
        if not (
            0 <= g1_id < len(model.sketch.Geometry)
            and 0 <= g2_id < len(model.sketch.Geometry)
        ):
            return

        g1 = model.sketch.Geometry[g1_id]
        g2 = model.sketch.Geometry[g2_id]

        # Case 1: Equal Radii (Circles or Arcs of Circles)
        if hasattr(g1, "Radius") and hasattr(g2, "Radius"):
            model.radius_sets.union(str(g1_id), str(g2_id))

        # Case 2: Equal Lengths (Line Segments)
        elif hasattr(g1, "StartPoint") and hasattr(g2, "StartPoint"):
            model.length_sets.union(str(g1_id), str(g2_id))


class CoincidentHandler(BaseHandler):
    """Unifies points that are coincident with each other or with axes."""

    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        p1 = model._resolve_point_ref(c.First, c.FirstPos)

        # Case 1: Point coincident with coordinate axes
        if p1:
            if c.Second == _XAXIS_ID:
                if c.SecondPos != 0:
                    model.x_sets.union(p1, "__X_ORIGIN__", model.x_formulas)
                model.y_sets.union(p1, "__Y_ORIGIN__", model.y_formulas)
                return
            elif c.Second == _YAXIS_ID:
                if c.SecondPos != 0:
                    model.y_sets.union(p1, "__Y_ORIGIN__", model.y_formulas)
                model.x_sets.union(p1, "__X_ORIGIN__", model.x_formulas)
                return

        # Case 2: Point coincident with another point -> unify both X and Y!
        p2 = (
            model._resolve_point_ref(c.Second, c.SecondPos)
            if not _is_geo_none(c.Second) and c.Second >= 0
            else None
        )
        if p1 and p2:
            model.x_sets.union(p1, p2, model.x_formulas)
            model.y_sets.union(p1, p2, model.y_formulas)
            return

        # Case 3: Point coincident with a curve -> delegate to PointOnObject
        HANDLERS["PointOnObject"].process_linear(model, c, idx)


class ParallelHandler(BaseHandler):
    """Propagates orthogonality and slopes between parallel lines."""

    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        g1_id, g2_id = c.First, c.Second
        if not (
            0 <= g1_id < len(model.sketch.Geometry)
            and 0 <= g2_id < len(model.sketch.Geometry)
        ):
            return

        g1 = model.sketch.Geometry[g1_id]
        g2 = model.sketch.Geometry[g2_id]
        if hasattr(g1, "StartPoint") and hasattr(g2, "StartPoint"):
            p1_s, p1_e = (
                model.vertex_map.get((g1_id, 1)),
                model.vertex_map.get((g1_id, 2)),
            )
            p2_s, p2_e = (
                model.vertex_map.get((g2_id, 1)),
                model.vertex_map.get((g2_id, 2)),
            )
            if not (p1_s and p1_e and p2_s and p2_e):
                return

            # If line 1 is horizontal, line 2 is horizontal (same Y)
            if model._geom_is_horizontal(g1):
                model.y_sets.union(p2_s, p2_e, model.y_formulas)
            elif model._geom_is_horizontal(g2):
                model.y_sets.union(p1_s, p1_e, model.y_formulas)

            # If line 1 is vertical, line 2 is vertical (same X)
            elif model._geom_is_vertical(g1):
                model.x_sets.union(p2_s, p2_e, model.x_formulas)
            elif model._geom_is_vertical(g2):
                model.x_sets.union(p1_s, p1_e, model.x_formulas)


class PerpendicularHandler(BaseHandler):
    """Enforces 90-degree relationships between perpendicular lines."""

    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        g1_id, g2_id = c.First, c.Second
        if not (
            0 <= g1_id < len(model.sketch.Geometry)
            and 0 <= g2_id < len(model.sketch.Geometry)
        ):
            return

        g1 = model.sketch.Geometry[g1_id]
        g2 = model.sketch.Geometry[g2_id]
        if hasattr(g1, "StartPoint") and hasattr(g2, "StartPoint"):
            p1_s, p1_e = (
                model.vertex_map.get((g1_id, 1)),
                model.vertex_map.get((g1_id, 2)),
            )
            p2_s, p2_e = (
                model.vertex_map.get((g2_id, 1)),
                model.vertex_map.get((g2_id, 2)),
            )
            if not (p1_s and p1_e and p2_s and p2_e):
                return

            # If line 1 is horizontal, line 2 becomes vertical (same X)
            if model._geom_is_horizontal(g1):
                model.x_sets.union(p2_s, p2_e, model.x_formulas)
            elif model._geom_is_horizontal(g2):
                model.x_sets.union(p1_s, p1_e, model.x_formulas)

            # If line 1 is vertical, line 2 becomes horizontal (same Y)
            elif model._geom_is_vertical(g1):
                model.y_sets.union(p2_s, p2_e, model.y_formulas)
            elif model._geom_is_vertical(g2):
                model.y_sets.union(p1_s, p1_e, model.y_formulas)


class TangentHandler(BaseHandler):
    """Propagates tangency between lines and arcs/circles."""

    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        g1_id, g2_id = c.First, c.Second
        if not (
            0 <= g1_id < len(model.sketch.Geometry)
            and 0 <= g2_id < len(model.sketch.Geometry)
        ):
            return

        g1 = model.sketch.Geometry[g1_id]
        g2 = model.sketch.Geometry[g2_id]

        # Case: Line tangent to Circle / Arc
        line_id = (
            g1_id
            if hasattr(g1, "StartPoint") and not hasattr(g1, "Radius")
            else (
                g2_id
                if hasattr(g2, "StartPoint") and not hasattr(g2, "Radius")
                else None
            )
        )
        circle_id = g2_id if line_id == g1_id else (g1_id if line_id == g2_id else None)

        if line_id is not None and circle_id is not None:
            c_center = model.vertex_map.get((circle_id, 3))
            p_line_s = model.vertex_map.get((line_id, 1))
            p_line_e = model.vertex_map.get((line_id, 2))

            if c_center and p_line_s and p_line_e and c_center in model.point_coords:
                # Find the shared contact point
                contact_pt = (
                    p_line_s
                    if (
                        p_line_s
                        in (
                            model.vertex_map.get((circle_id, 1)),
                            model.vertex_map.get((circle_id, 2)),
                        )
                    )
                    else (
                        p_line_e
                        if (
                            p_line_e
                            in (
                                model.vertex_map.get((circle_id, 1)),
                                model.vertex_map.get((circle_id, 2)),
                            )
                        )
                        else None
                    )
                )
                if contact_pt and contact_pt in model.point_coords:
                    c_pt = model.point_coords[contact_pt]
                    c_cen = model.point_coords[c_center]
                    # If radius vector is vertical, tangent line is horizontal
                    if abs(c_pt[0] - c_cen[0]) < 1e-4:
                        model.y_sets.union(p_line_s, p_line_e, model.y_formulas)
                    # If radius vector is horizontal, tangent line is vertical
                    elif abs(c_pt[1] - c_cen[1]) < 1e-4:
                        model.x_sets.union(p_line_s, p_line_e, model.x_formulas)


class RadiusHandler(BaseHandler):
    """Maps Radius constraint to the geometry's radius parameter."""

    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        param = model.constraint_vars.get(idx)
        if param and 0 <= c.First < len(model.sketch.Geometry):
            model.radius_params[c.First] = param


class DiameterHandler(BaseHandler):
    """Maps Diameter constraint as (param / 2) to the geometry's radius."""

    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        param = model.constraint_vars.get(idx)
        if param and 0 <= c.First < len(model.sketch.Geometry):
            model.radius_params[c.First] = f"{param} / 2"


class BlockHandler(BaseHandler):
    """Fixes a point or line in place by binding its current coordinates."""

    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        pt = model._resolve_point_ref(c.First, 1 if c.FirstPos == 0 else c.FirstPos)
        if pt and pt in model.point_coords:
            px, py = model.point_coords[pt]
            rx = model.x_sets.find(pt)
            ry = model.y_sets.find(pt)
            if rx not in model.x_formulas:
                model.x_formulas[rx] = draw._to_str(px)
            if ry not in model.y_formulas:
                model.y_formulas[ry] = draw._to_str(py)


class InternalAlignmentHandler(BaseHandler):
    """Handles internal ellipse diameters and focus points."""

    def process_linear(self, model: ParametricModel, c: Any, idx: int) -> None:
        # Unifies internal geometry vertices with the host geometry
        p1 = model._resolve_point_ref(c.First, c.FirstPos)
        p2 = model._resolve_point_ref(c.Second, c.SecondPos)
        if p1 and p2:
            model.x_sets.union(p1, p2, model.x_formulas)
            model.y_sets.union(p1, p2, model.y_formulas)


# Register all modular handlers
HANDLERS: dict[str, BaseHandler] = {
    # Orthogonal
    "Horizontal": HorizontalHandler(),
    "Vertical": VerticalHandler(),
    # Dimensions
    "DistanceX": DistanceXHandler(),
    "DistanceY": DistanceYHandler(),
    "Distance": DistanceHandler(),
    "Radius": RadiusHandler(),
    "Diameter": DiameterHandler(),
    # Angles & Orientations
    "Angle": AngleHandler(),
    "Parallel": ParallelHandler(),
    "Perpendicular": PerpendicularHandler(),
    "Tangent": TangentHandler(),
    # Positions & Alignments
    "Coincident": CoincidentHandler(),
    "PointOnObject": PointOnObjectHandler(),
    "PointOnCurve": PointOnObjectHandler(),
    "Symmetric": SymmetricHandler(),
    "Equal": EqualHandler(),
    # Miscellaneous FreeCAD Constraints
    "Block": BlockHandler(),
    "InternalAlignment": InternalAlignmentHandler(),
}


# ======================================================================
# Main Parametric Solver Engine
# ======================================================================


class ParametricModel:
    def __init__(self, sketch_obj: Any, pairs_dict: dict[str, str]) -> None:
        self.sketch = sketch_obj
        self.pairs_dict = pairs_dict
        self.aux_params: dict[str, str] = {}

        # Disjoint sets for Equal constraints
        self.length_sets = DisjointSet()
        self.radius_sets = DisjointSet()

        self.vertex_map: dict[tuple[int, int], str] = {}
        self.point_coords: dict[str, tuple[float, float]] = {}

        self.constraint_vars: dict[int, str] = {}
        self.params: dict[str, str] = {}
        self.radius_params: dict[int, str] = {}

        self.fixed_x: set[str] = set()
        self.fixed_y: set[str] = set()

        self.x_sets = DisjointSet()
        self.y_sets = DisjointSet()

        self.x_formulas: dict[str, str] = {}
        self.y_formulas: dict[str, str] = {}

        self.x_edges: list[tuple[str, str, str, float]] = []
        self.y_edges: list[tuple[str, str, str, float]] = []
        self.x_midpoints: list[tuple[str, str, str]] = []
        self.y_midpoints: list[tuple[str, str, str]] = []
        self.x_reflections: list[tuple[str, str, str]] = []
        self.y_reflections: list[tuple[str, str, str]] = []

        self.length_lines: dict[int, tuple[str, str, str]] = {}
        self.angle_constraints: list[tuple[int, int, str, str]] = []

        self.custom_point_exprs: dict[str, str] = {}
        self.deps: dict[str, set[str]] = {}

        self._build_vertex_map()
        self._extract_parameters()
        self._solve_geometry()

    @staticmethod
    def _geom_is_horizontal(geom: Any) -> bool:
        """Returns True if geometry is a horizontal line segment."""
        if not (hasattr(geom, "StartPoint") and hasattr(geom, "EndPoint")):
            return False
        ps = get_coordinates(geom.StartPoint)
        pe = get_coordinates(geom.EndPoint)
        return abs(ps[1] - pe[1]) < 1e-4

    @staticmethod
    def _geom_is_vertical(geom: Any) -> bool:
        """Returns True if geometry is a vertical line segment."""
        if not (hasattr(geom, "StartPoint") and hasattr(geom, "EndPoint")):
            return False
        ps = get_coordinates(geom.StartPoint)
        pe = get_coordinates(geom.EndPoint)
        return abs(ps[0] - pe[0]) < 1e-4

    def _build_vertex_map(self) -> None:
        for geo_id, geom in enumerate(self.sketch.Geometry):
            for pos_id in (1, 2, 3):
                try:
                    pt_vec = self.sketch.getPoint(geo_id, pos_id)
                    name = draw._pair(pt_vec, self.pairs_dict)
                    self.vertex_map[(geo_id, pos_id)] = name
                    self.point_coords[name] = get_coordinates(pt_vec)
                except Exception:  # noqa: BLE001, S110
                    pass

        origin_name = draw._pair((0.0, 0.0), self.pairs_dict)
        self.vertex_map[(-1, 1)] = origin_name
        self.point_coords[origin_name] = (0.0, 0.0)

    def _extract_parameters(self) -> None:
        used_names: set[str] = set()

        for idx, c in enumerate(self.sketch.Constraints):
            if c.Type not in DIM_TYPES:
                continue

            base_name = (
                sanitize_name(c.Name)
                if (c.Name and c.Name.strip())
                else f"{c.Type.lower()}_{idx}"
            )
            var_name = base_name
            count = 1
            while var_name in used_names:
                var_name = f"{base_name}_{count}"
                count += 1
            used_names.add(var_name)

            self.constraint_vars[idx] = var_name
            val = float(c.Value)

            # Ensure distance/radius magnitudes are positive
            if c.Type != "Angle":
                val = abs(val)

            if c.Type == "Angle":
                if abs(val) <= 2 * math.pi + 1e-4 and val != 0:
                    self.params[var_name] = draw._to_str(math.degrees(val), 2)
                else:
                    self.params[var_name] = draw._to_str(val, 2)
            else:
                self.params[var_name] = draw._to_str(val)

            if c.Type == "Radius":
                self.radius_params[c.First] = var_name
            elif c.Type == "Diameter":
                self.radius_params[c.First] = f"{var_name} / 2"

    def _resolve_point_ref(self, geo_id: int, pos_id: int) -> str | None:
        if (geo_id, pos_id) in self.vertex_map:
            return self.vertex_map[(geo_id, pos_id)]
        if geo_id == _XAXIS_ID and pos_id == 1:
            return self.vertex_map.get((-1, 1))
        return None

    def _get_constraint_pair(self, c: Any) -> tuple[str | None, str | None]:
        p1 = self._resolve_point_ref(c.First, 1 if c.FirstPos == 0 else c.FirstPos)
        p2 = self._resolve_point_ref(
            c.First
            if (c.First == c.Second and c.FirstPos != c.SecondPos)
            else c.Second,
            2 if c.SecondPos == 0 else c.SecondPos,
        )
        return p1, p2

    def _is_cartesian_solved(self, name: str) -> bool:
        rx = self.x_sets.find(name)
        ry = self.y_sets.find(name)
        return rx in self.x_formulas and ry in self.y_formulas

    def _solve_geometry(self) -> None:
        # 1. Initialize Axis Anchors
        self.x_formulas["__X_ORIGIN__"] = "0"
        self.y_formulas["__Y_ORIGIN__"] = "0"

        origin_pt = self.vertex_map.get((-1, 1))
        if origin_pt:
            self.x_sets.union(origin_pt, "__X_ORIGIN__", self.x_formulas)
            self.y_sets.union(origin_pt, "__Y_ORIGIN__", self.y_formulas)

        for name, (px, py) in self.point_coords.items():
            if abs(py) < 1e-4:
                self.y_sets.union(name, "__Y_ORIGIN__", self.y_formulas)
            if abs(px) < 1e-4:
                self.x_sets.union(name, "__X_ORIGIN__", self.x_formulas)

        # 2. Execute Linear Handlers (Horizontal, Vertical, Distances, Equal, etc.)
        for idx, c in enumerate(self.sketch.Constraints):
            handler = HANDLERS.get(c.Type)
            if handler:
                handler.process_linear(self, c, idx)

        # -------------------------------------------------------------
        # 3. Propagate Equal Constraints
        # -------------------------------------------------------------
        # A. Propagate Equal Radii
        for geo_id in range(len(self.sketch.Geometry)):
            root_r = self.radius_sets.find(str(geo_id))
            # If any member in this equal group has a radius param, share it
            for other_id in range(len(self.sketch.Geometry)):
                if self.radius_sets.find(str(other_id)) == root_r and (
                    other_id in self.radius_params and geo_id not in self.radius_params
                ):
                    self.radius_params[geo_id] = self.radius_params[other_id]

        # B. Propagate Equal Lengths to length_lines & orthogonal edges
        equal_length_param: dict[str, str] = {}
        for geo_id, (p1, p2, len_param) in list(self.length_lines.items()):
            root_l = self.length_sets.find(str(geo_id))
            equal_length_param[root_l] = len_param

        for geo_id, geom in enumerate(self.sketch.Geometry):
            if hasattr(geom, "StartPoint") and hasattr(geom, "EndPoint"):
                root_l = self.length_sets.find(str(geo_id))
                len_param = equal_length_param.get(root_l)
                if not len_param:
                    continue

                p1 = self.vertex_map.get((geo_id, 1))
                p2 = self.vertex_map.get((geo_id, 2))
                if not (
                    p1 and p2 and p1 in self.point_coords and p2 in self.point_coords
                ):
                    continue

                c1, c2 = self.point_coords[p1], self.point_coords[p2]
                dx = c2[0] - c1[0]
                dy = c2[1] - c1[1]

                # If this equal line is horizontal, propagate to X edges
                if abs(dy) < 1e-4:
                    self.x_edges.append(
                        (self.x_sets.find(p1), self.x_sets.find(p2), len_param, dx)
                    )
                # If this equal line is vertical, propagate to Y edges
                elif abs(dx) < 1e-4:
                    self.y_edges.append(
                        (self.y_sets.find(p1), self.y_sets.find(p2), len_param, dy)
                    )
                # If angled, add to length_lines for polar vectors & intersections
                else:
                    self.length_lines[geo_id] = (p1, p2, len_param)

        # 4. Pass 2: Angle Vectors with FreeCAD Branch Selection
        for g1, g2, ang_param, common in self.angle_constraints:
            for line_geo, other_geo in [(g1, g2), (g2, g1)]:
                if line_geo in self.length_lines:
                    lp1, lp2, len_param = self.length_lines[line_geo]
                    target = lp2 if lp1 == common else lp1
                    if target in self.custom_point_exprs:
                        continue

                    other_p1 = self.vertex_map.get((other_geo, 1))
                    other_p2 = self.vertex_map.get((other_geo, 2))
                    other_ref = other_p2 if other_p1 == common else other_p1

                    if (
                        target
                        and other_ref
                        and common in self.point_coords
                        and other_ref in self.point_coords
                        and target in self.point_coords
                    ):
                        c_common = self.point_coords[common]
                        c_other = self.point_coords[other_ref]
                        c_target = self.point_coords[target]
                        L_num = float(self.params[len_param])
                        ang_num = float(self.params[ang_param])

                        # Evaluate candidate orientations against FreeCAD's true coordinates
                        best_expr = None
                        for ref_mode, ref_name in [
                            ("fwd", f"degrees({other_ref} - {common})"),
                            ("bwd", f"degrees({common} - {other_ref})"),
                        ]:
                            base_deg = (
                                math.degrees(
                                    math.atan2(
                                        c_other[1] - c_common[1],
                                        c_other[0] - c_common[0],
                                    )
                                )
                                if ref_mode == "fwd"
                                else math.degrees(
                                    math.atan2(
                                        c_common[1] - c_other[1],
                                        c_common[0] - c_other[0],
                                    )
                                )
                            )
                            for sign, s_val in [("+", 1), ("-", -1)]:
                                test_ang = base_deg + s_val * ang_num
                                test_x = c_common[0] + L_num * math.cos(
                                    math.radians(test_ang)
                                )
                                test_y = c_common[1] + L_num * math.sin(
                                    math.radians(test_ang)
                                )

                                if (
                                    math.hypot(
                                        test_x - c_target[0], test_y - c_target[1]
                                    )
                                    < 0.05
                                ):
                                    best_expr = f"{common} + dir({ref_name} {sign} {ang_param}) * {len_param}"
                                    break
                            if best_expr:
                                break

                        if best_expr:
                            self.custom_point_exprs[target] = best_expr
                            self.deps.setdefault(target, set()).update(
                                {common, other_ref}
                            )

        # 5. Pass 3: Distance/Circle Intersections
        for line_geo, (p1, p2, len_param) in self.length_lines.items():
            for base, target in [(p1, p2), (p2, p1)]:
                if target in self.custom_point_exprs:
                    continue

                root_x = self.x_sets.find(target)
                root_y = self.y_sets.find(target)
                x_solved = root_x in self.x_formulas
                y_solved = root_y in self.y_formulas

                base_known = (
                    base in self.custom_point_exprs or self._is_cartesian_solved(base)
                )
                if not base_known:
                    continue

                c_base = self.point_coords[base]
                c_target = self.point_coords[target]

                if x_solved and not y_solved:
                    x_expr = self.x_formulas[root_x]
                    y_sign = "+" if c_target[1] >= c_base[1] else "-"
                    y_expr = f"{base}.y {y_sign} sqrt(({len_param})^2 - (({x_expr}) - {base}.x)^2)"
                    self.custom_point_exprs[target] = f"({x_expr}, {y_expr})"
                    self.deps.setdefault(target, set()).add(base)

                elif y_solved and not x_solved:
                    y_expr = self.y_formulas[root_y]
                    x_sign = "+" if c_target[0] >= c_base[0] else "-"
                    x_expr = f"{base}.x {x_sign} sqrt(({len_param})^2 - (({y_expr}) - {base}.y)^2)"
                    self.custom_point_exprs[target] = f"({x_expr}, {y_expr})"
                    self.deps.setdefault(target, set()).add(base)

    def _coordinate_expr(
        self,
        point: str,
        axis: str,
    ) -> str | None:
        if axis == "x":
            root = self.x_sets.find(point)
            return self.x_formulas.get(root)

        root = self.y_sets.find(point)
        return self.y_formulas.get(root)

    def point_expression(self, name: str) -> str:
        """Return the best symbolic Asymptote expression for a point.

        The returned expression may reference other named pair variables.
        Numeric FreeCAD coordinates are only used as a last-resort fallback.
        """
        if name in self.custom_point_exprs:
            return self.custom_point_exprs[name]

        rx = self.x_sets.find(name)
        ry = self.y_sets.find(name)

        x_expr = self.x_formulas.get(rx)
        y_expr = self.y_formulas.get(ry)

        if x_expr is not None and y_expr is not None:
            return f"({x_expr}, {y_expr})"

        if x_expr is not None or y_expr is not None:
            x = x_expr if x_expr is not None else self._fallback_coordinate(name, 0)
            y = y_expr if y_expr is not None else self._fallback_coordinate(name, 1)
            return f"({x}, {y})"

        return self._fallback_point(name)

    def _fallback_coordinate(self, name: str, index: int) -> str:
        coords = self.point_coords.get(name)
        if coords is None:
            raise KeyError(f"No coordinates known for point {name}")
        return draw._to_str(coords[index])

    def _fallback_point(self, name: str) -> str:
        coords = self.point_coords.get(name)
        if coords is None:
            raise KeyError(f"No coordinates known for point {name}")
        return f"({draw._to_str(coords[0])}, {draw._to_str(coords[1])})"

    def format_asymptote_definitions(self, paths_and_circles_str: str = "") -> str:
        out = ""

        # Always output all extracted sketch parameters when parametric mode is on
        if self.params or self.aux_params:
            out += "// --- Predefined Parameters ---\n"
            for name, val in self.params.items():
                out += f"real {name} = {val};\n"
            for name, val in self.aux_params.items():
                out += f"real {name} = {val};\n"
            out += "\n"

        out += "// --- Points & Coordinates ---\n"

        inv_pairs = {name: coord for coord, name in self.pairs_dict.items()}
        sorted_names = sorted(
            inv_pairs.keys(),
            key=lambda item: int(item[1:]) if item[1:].isdigit() else 999999,
        )

        declared: set[str] = set()
        unresolved = list(sorted_names)

        while unresolved:
            progress = False
            for i, name in enumerate(unresolved):
                coord_str = inv_pairs[name]
                x_fallback, y_fallback = coord_str.strip("()").split(",")
                x_fallback, y_fallback = x_fallback.strip(), y_fallback.strip()

                rx = self.x_sets.find(name)
                ry = self.y_sets.find(name)
                both_cartesian = rx in self.x_formulas and ry in self.y_formulas

                # Rule 1: Points with both Cartesian coordinates solved stay Cartesian
                if both_cartesian and name not in self.custom_point_exprs:
                    out += f"pair {name} = ({self.x_formulas[rx]}, {self.y_formulas[ry]});\n"
                    declared.add(name)
                    unresolved.pop(i)
                    progress = True
                    break

                # Rule 2: Custom vector / intersection expressions
                if name in self.custom_point_exprs:
                    deps = self.deps.get(name, set())
                    if deps.issubset(declared):
                        out += f"pair {name} = {self.custom_point_exprs[name]};\n"
                        declared.add(name)
                        unresolved.pop(i)
                        progress = True
                        break

                # Rule 3: Partially solved Cartesian
                elif name not in self.custom_point_exprs and (
                    rx in self.x_formulas or ry in self.y_formulas
                ):
                    x_expr = self.x_formulas.get(rx, x_fallback)
                    y_expr = self.y_formulas.get(ry, y_fallback)
                    out += f"pair {name} = ({x_expr}, {y_expr});\n"
                    declared.add(name)
                    unresolved.pop(i)
                    progress = True
                    break

                # Rule 4: No constraints resolved - emit as-is
                elif name not in self.custom_point_exprs:
                    out += "// --- Points & Coordinates ---\n"
                    inv_pairs = {name: coord for coord, name in self.pairs_dict.items()}
                    sorted_names = sorted(
                        inv_pairs.keys(),
                        key=lambda item: (
                            int(item[1:]) if item[1:].isdigit() else 999999
                        ),
                    )

                    declared: set[str] = set()
                    unresolved = list(sorted_names)

                    while unresolved:
                        progress = False

                        for name in list(unresolved):
                            deps = self.deps.get(name, set())

                            # Do not emit an expression until the points it references
                            # have already been declared.
                            if not deps.issubset(declared):
                                continue

                            expr = self.point_expression(name)

                            out += f"pair {name} = {expr};\n"
                            declared.add(name)
                            unresolved.remove(name)
                            progress = True

                        if not progress:
                            # There is a cyclic or otherwise unresolved dependency.
                            # Do not silently turn it into a frozen coordinate.
                            name = unresolved.pop(0)
                            expr = self._fallback_point(name)

                            out += (
                                f"// WARNING: unresolved symbolic dependencies for {name}\n"
                                f"pair {name} = {expr};\n"
                            )
                            declared.add(name)

            if not progress and unresolved:
                name = unresolved.pop(0)
                coord_str = inv_pairs[name]
                out += f"pair {name} = {coord_str};\n"
                declared.add(name)

        return out
