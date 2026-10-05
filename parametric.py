"""Universal parametric model for FreeCAD sketches to Asymptote exporter."""

from __future__ import annotations

import math
import re
from typing import Any

import draw
from coordinates import get_coordinates

_GEO_NONE = -2000
_XAXIS_ID = -1
_YAXIS_ID = -2


def sanitize_name(name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    if not clean or clean[0].isdigit():
        clean = f"param_{clean}"
    return clean


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


def _is_geo_none(geo_id: int) -> bool:
    return geo_id <= _GEO_NONE or geo_id < -100


def _make_midpoint_formula(f1: str, f2: str) -> str:
    if f1 == f2:
        return f1
    if f1 == "0":
        return f"{f2} / 2"
    if f2 == "0":
        return f"{f1} / 2"
    return f"({f1} + {f2}) / 2"


def _make_reflection_formula(f_mid: str, f1: str) -> str:
    if f_mid == "0":
        return f"-({f1})"
    return f"2 * ({f_mid}) - ({f1})"


class ParametricModel:
    def __init__(self, sketch_obj: Any, pairs_dict: dict[str, str]) -> None:
        self.sketch = sketch_obj
        self.pairs_dict = pairs_dict

        self.vertex_map: dict[tuple[int, int], str] = {}
        self.point_coords: dict[str, tuple[float, float]] = {}

        self.constraint_vars: dict[int, str] = {}
        self.params: dict[str, str] = {}
        self.aux_params: dict[str, str] = {}
        self.radius_params: dict[int, str] = {}

        self._equal_length: dict[int, str] = {}
        self._equal_radius: dict[int, str] = {}

        self.x_sets = DisjointSet()
        self.y_sets = DisjointSet()

        self.x_formulas: dict[str, str] = {}
        self.y_formulas: dict[str, str] = {}

        self.line_angles: dict[int, str] = {}
        self.line_angles_num: dict[int, float] = {}

        self.custom_point_exprs: dict[str, str] = {}
        self.deps: dict[str, set[str]] = {}

        self._build_vertex_map()
        self._extract_parameters()
        self._pass1_resolve_cartesian()
        self._pass2_resolve_line_directions()
        self._pass3_resolve_geometry()

    def x_union(self, a: str, b: str) -> str:
        return self.x_sets.union(a, b, self.x_formulas)

    def y_union(self, a: str, b: str) -> str:
        return self.y_sets.union(a, b, self.y_formulas)

    def _build_vertex_map(self) -> None:
        for geo_id, geom in enumerate(self.sketch.Geometry):
            for pos_id in (1, 2, 3):
                try:
                    pt_vec = self.sketch.getPoint(geo_id, pos_id)
                    name = draw._pair(pt_vec, self.pairs_dict)
                    self.vertex_map[(geo_id, pos_id)] = name
                    self.point_coords[name] = get_coordinates(pt_vec)
                except Exception as e:  # noqa: BLE001
                    print(e)

        origin_name = draw._pair((0.0, 0.0), self.pairs_dict)
        self.vertex_map[(-1, 1)] = origin_name
        self.point_coords[origin_name] = (0.0, 0.0)

    def _extract_parameters(self) -> None:
        dim_types = (
            "Distance",
            "DistanceX",
            "DistanceY",
            "Radius",
            "Diameter",
            "Angle",
        )
        used_names: set[str] = set()

        for idx, c in enumerate(self.sketch.Constraints):
            if c.Type not in dim_types:
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
            val = c.Value

            if c.Type == "Angle":
                if abs(val) <= 2 * math.pi + 1e-4 and val != 0:
                    self.params[var_name] = draw._to_str(math.degrees(val), 2)
                else:
                    self.params[var_name] = draw._to_str(val, 2)
            else:
                self.params[var_name] = draw._to_str(val)

            if c.Type == "Radius":
                self.radius_params[c.First] = var_name
                self._equal_radius[c.First] = var_name
            elif c.Type == "Diameter":
                self.radius_params[c.First] = f"{var_name} / 2"
                self._equal_radius[c.First] = f"{var_name} / 2"
            elif c.Type == "Distance":
                self._equal_length[c.First] = var_name

        # Equal constraints propagation
        changed = True
        while changed:
            changed = False
            for c in self.sketch.Constraints:
                if c.Type != "Equal":
                    continue
                if c.First in self._equal_radius and c.Second not in self._equal_radius:
                    expr = self._equal_radius[c.First]
                    self._equal_radius[c.Second] = expr
                    self.radius_params[c.Second] = expr
                    changed = True
                elif (
                    c.Second in self._equal_radius and c.First not in self._equal_radius
                ):
                    expr = self._equal_radius[c.Second]
                    self._equal_radius[c.First] = expr
                    self.radius_params[c.First] = expr
                    changed = True
                if c.First in self._equal_length and c.Second not in self._equal_length:
                    self._equal_length[c.Second] = self._equal_length[c.First]
                    changed = True
                elif (
                    c.Second in self._equal_length and c.First not in self._equal_length
                ):
                    self._equal_length[c.First] = self._equal_length[c.Second]
                    changed = True

    def _resolve_point_ref(self, geo_id: int, pos_id: int) -> str | None:
        if (geo_id, pos_id) in self.vertex_map:
            return self.vertex_map[(geo_id, pos_id)]
        if geo_id == _XAXIS_ID and pos_id == 1:
            return self.vertex_map.get((-1, 1))
        return None

    def _is_cartesian_solved(self, name: str) -> bool:
        rx = self.x_sets.find(name)
        ry = self.y_sets.find(name)
        return rx in self.x_formulas and ry in self.y_formulas

    def _pass1_resolve_cartesian(self) -> None:
        self.x_formulas["__X_ORIGIN__"] = "0"
        self.y_formulas["__Y_ORIGIN__"] = "0"

        origin_pt = self.vertex_map.get((-1, 1))
        if origin_pt:
            self.x_union(origin_pt, "__X_ORIGIN__")
            self.y_union(origin_pt, "__Y_ORIGIN__")

        # Anchor points on axes
        for name, (px, py) in self.point_coords.items():
            if abs(py) < 1e-4:
                self.y_union(name, "__Y_ORIGIN__")
            if abs(px) < 1e-4:
                self.x_union(name, "__X_ORIGIN__")

        # Geometric alignment with lines
        for name, (px, py) in self.point_coords.items():
            for geo_id, geom in enumerate(self.sketch.Geometry):
                if hasattr(geom, "StartPoint") and hasattr(geom, "EndPoint"):
                    ps = get_coordinates(geom.StartPoint)
                    pe = get_coordinates(geom.EndPoint)
                    line_ref = self.vertex_map.get((geo_id, 1))
                    if line_ref and line_ref != name:
                        if abs(ps[0] - pe[0]) < 1e-4 and abs(px - ps[0]) < 1e-4:
                            self.x_union(name, line_ref)
                        elif abs(ps[1] - pe[1]) < 1e-4 and abs(py - ps[1]) < 1e-4:
                            self.y_union(name, line_ref)

        x_midpoints: list[tuple[str, str, str]] = []
        y_midpoints: list[tuple[str, str, str]] = []
        x_reflections: list[tuple[str, str, str]] = []
        y_reflections: list[tuple[str, str, str]] = []

        # Structural constraints
        for c in self.sketch.Constraints:
            if c.Type == "Horizontal":
                p1 = self._resolve_point_ref(
                    c.First, 1 if c.FirstPos == 0 else c.FirstPos
                )
                p2 = self._resolve_point_ref(
                    c.First if c.FirstPos == 0 else c.Second,
                    2 if c.FirstPos == 0 else c.SecondPos,
                )
                if p1 and p2:
                    self.y_union(p1, p2)

            elif c.Type == "Vertical":
                p1 = self._resolve_point_ref(
                    c.First, 1 if c.FirstPos == 0 else c.FirstPos
                )
                p2 = self._resolve_point_ref(
                    c.First if c.FirstPos == 0 else c.Second,
                    2 if c.FirstPos == 0 else c.SecondPos,
                )
                if p1 and p2:
                    self.x_union(p1, p2)

            elif c.Type == "Coincident":
                p1 = self._resolve_point_ref(c.First, c.FirstPos)
                p2 = (
                    self._resolve_point_ref(c.Second, c.SecondPos)
                    if not _is_geo_none(c.Second) and c.Second >= 0
                    else None
                )
                if p1 and p2:
                    self.x_union(p1, p2)
                    self.y_union(p1, p2)
                elif p1 and c.Second == _XAXIS_ID:
                    if c.SecondPos != 0:
                        self.x_union(p1, "__X_ORIGIN__")
                    self.y_union(p1, "__Y_ORIGIN__")
                elif p1 and c.Second == _YAXIS_ID:
                    if c.SecondPos != 0:
                        self.y_union(p1, "__Y_ORIGIN__")
                    self.x_union(p1, "__X_ORIGIN__")

            elif c.Type in ("PointOnObject", "PointOnCurve"):
                pt = self._resolve_point_ref(c.First, c.FirstPos)
                target = c.Second
                if not pt:
                    pt = self._resolve_point_ref(c.Second, c.SecondPos)
                    target = c.First

                if pt:
                    if target == _XAXIS_ID:
                        self.y_union(pt, "__Y_ORIGIN__")
                    elif target == _YAXIS_ID:
                        self.x_union(pt, "__X_ORIGIN__")

            elif c.Type == "Symmetric":
                p1 = self._resolve_point_ref(c.First, c.FirstPos if c.FirstPos else 1)
                p2 = self._resolve_point_ref(
                    c.Second, c.SecondPos if c.SecondPos else 1
                )
                if not (
                    p1 and p2 and p1 in self.point_coords and p2 in self.point_coords
                ):
                    continue

                third = getattr(c, "Third", _GEO_NONE)
                third_pos = getattr(c, "ThirdPos", 0)

                if not _is_geo_none(third) and third_pos != 0:
                    p3 = self._resolve_point_ref(third, third_pos)
                    if p3 and p3 in self.point_coords:
                        x_midpoints.append((p1, p2, p3))
                        y_midpoints.append((p1, p2, p3))
                else:
                    if third == _YAXIS_ID:
                        self.y_union(p1, p2)
                        x_reflections.append((p1, p2, "__X_ORIGIN__"))
                    elif third == _XAXIS_ID:
                        self.x_union(p1, p2)
                        y_reflections.append((p1, p2, "__Y_ORIGIN__"))

        # 1D Distance constraints
        x_edges: list[tuple[str, str, str, float]] = []
        y_edges: list[tuple[str, str, str, float]] = []

        for idx, c in enumerate(self.sketch.Constraints):
            param = self.constraint_vars.get(idx)
            if not param:
                continue

            # Distance to X-axis -> Y distance
            if c.Second == _XAXIS_ID and c.SecondPos == 0:
                pt = self._resolve_point_ref(
                    c.First, 1 if c.FirstPos == 0 else c.FirstPos
                )
                if pt and pt in self.point_coords:
                    root_y = self.y_sets.find(pt)
                    sign = "" if self.point_coords[pt][1] >= 0 else "-"
                    self.y_formulas[root_y] = f"{sign}{param}"
                continue

            if c.First == _XAXIS_ID and c.FirstPos == 0:
                pt = self._resolve_point_ref(
                    c.Second, 1 if c.SecondPos == 0 else c.SecondPos
                )
                if pt and pt in self.point_coords:
                    root_y = self.y_sets.find(pt)
                    sign = "" if self.point_coords[pt][1] >= 0 else "-"
                    self.y_formulas[root_y] = f"{sign}{param}"
                continue

            # Distance to Y-axis -> X distance
            if c.Second == _YAXIS_ID and c.SecondPos == 0:
                pt = self._resolve_point_ref(
                    c.First, 1 if c.FirstPos == 0 else c.FirstPos
                )
                if pt and pt in self.point_coords:
                    root_x = self.x_sets.find(pt)
                    sign = "" if self.point_coords[pt][0] >= 0 else "-"
                    self.x_formulas[root_x] = f"{sign}{param}"
                continue

            if c.First == _YAXIS_ID and c.FirstPos == 0:
                pt = self._resolve_point_ref(
                    c.Second, 1 if c.SecondPos == 0 else c.SecondPos
                )
                if pt and pt in self.point_coords:
                    root_x = self.x_sets.find(pt)
                    sign = "" if self.point_coords[pt][0] >= 0 else "-"
                    self.x_formulas[root_x] = f"{sign}{param}"
                continue

            p1 = self._resolve_point_ref(c.First, 1 if c.FirstPos == 0 else c.FirstPos)
            if c.First == c.Second and c.FirstPos != c.SecondPos:
                p2 = self._resolve_point_ref(
                    c.First, 2 if c.SecondPos == 0 else c.SecondPos
                )
            elif not _is_geo_none(c.Second):
                p2 = self._resolve_point_ref(
                    c.Second, 2 if c.SecondPos == 0 else c.SecondPos
                )
            else:
                continue

            if (
                not p1
                or not p2
                or p1 not in self.point_coords
                or p2 not in self.point_coords
            ):
                continue

            c1, c2 = self.point_coords[p1], self.point_coords[p2]
            dx = c2[0] - c1[0]
            dy = c2[1] - c1[1]

            if c.Type == "DistanceX" or (c.Type == "Distance" and abs(dy) < 1e-4):
                r1 = self.x_sets.find(p1)
                r2 = self.x_sets.find(p2)
                x_edges.append((r1, r2, param, dx))

            elif c.Type == "DistanceY" or (c.Type == "Distance" and abs(dx) < 1e-4):
                r1 = self.y_sets.find(p1)
                r2 = self.y_sets.find(p2)
                y_edges.append((r1, r2, param, dy))

        # Propagate X formulas
        changed = True
        while changed:
            changed = False
            for r1, r2, param, dx in x_edges:
                r1_curr = self.x_sets.find(r1)
                r2_curr = self.x_sets.find(r2)
                if r1_curr in self.x_formulas and r2_curr not in self.x_formulas:
                    sign = "+" if dx >= 0 else "-"
                    base = self.x_formulas[r1_curr]
                    self.x_formulas[r2_curr] = (
                        f"{param}"
                        if base == "0" and sign == "+"
                        else (f"-{param}" if base == "0" else f"{base} {sign} {param}")
                    )
                    changed = True
                elif r2_curr in self.x_formulas and r1_curr not in self.x_formulas:
                    sign = "-" if dx >= 0 else "+"
                    base = self.x_formulas[r2_curr]
                    self.x_formulas[r1_curr] = (
                        f"{param}"
                        if base == "0" and sign == "+"
                        else (f"-{param}" if base == "0" else f"{base} {sign} {param}")
                    )
                    changed = True

            for p1, p2, p3 in x_midpoints:
                r1, r2, r3 = (
                    self.x_sets.find(p1),
                    self.x_sets.find(p2),
                    self.x_sets.find(p3),
                )
                if (
                    r3 not in self.x_formulas
                    and r1 in self.x_formulas
                    and r2 in self.x_formulas
                ):
                    self.x_formulas[r3] = _make_midpoint_formula(
                        self.x_formulas[r1], self.x_formulas[r2]
                    )
                    changed = True

            for p1, p2, axis_pt in x_reflections:
                r1, r2, ra = (
                    self.x_sets.find(p1),
                    self.x_sets.find(p2),
                    self.x_sets.find(axis_pt),
                )
                if (
                    r2 not in self.x_formulas
                    and ra in self.x_formulas
                    and r1 in self.x_formulas
                ):
                    self.x_formulas[r2] = _make_reflection_formula(
                        self.x_formulas[ra], self.x_formulas[r1]
                    )
                    changed = True

        # Propagate Y formulas
        changed = True
        while changed:
            changed = False
            for r1, r2, param, dy in y_edges:
                r1_curr = self.y_sets.find(r1)
                r2_curr = self.y_sets.find(r2)
                if r1_curr in self.y_formulas and r2_curr not in self.y_formulas:
                    sign = "+" if dy >= 0 else "-"
                    base = self.y_formulas[r1_curr]
                    self.y_formulas[r2_curr] = (
                        f"{param}"
                        if base == "0" and sign == "+"
                        else (f"-{param}" if base == "0" else f"{base} {sign} {param}")
                    )
                    changed = True
                elif r2_curr in self.y_formulas and r1_curr not in self.y_formulas:
                    sign = "-" if dy >= 0 else "+"
                    base = self.y_formulas[r2_curr]
                    self.y_formulas[r1_curr] = (
                        f"{param}"
                        if base == "0" and sign == "+"
                        else (f"-{param}" if base == "0" else f"{base} {sign} {param}")
                    )
                    changed = True

            for p1, p2, p3 in y_midpoints:
                r1, r2, r3 = (
                    self.y_sets.find(p1),
                    self.y_sets.find(p2),
                    self.y_sets.find(p3),
                )
                if (
                    r3 not in self.y_formulas
                    and r1 in self.y_formulas
                    and r2 in self.y_formulas
                ):
                    self.y_formulas[r3] = _make_midpoint_formula(
                        self.y_formulas[r1], self.y_formulas[r2]
                    )
                    changed = True

            for p1, p2, axis_pt in y_reflections:
                r1, r2, ra = (
                    self.y_sets.find(p1),
                    self.y_sets.find(p2),
                    self.y_sets.find(axis_pt),
                )
                if (
                    r2 not in self.y_formulas
                    and ra in self.y_formulas
                    and r1 in self.y_formulas
                ):
                    self.y_formulas[r2] = _make_reflection_formula(
                        self.y_formulas[ra], self.y_formulas[r1]
                    )
                    changed = True

    def _pass2_resolve_line_directions(self) -> None:
        for gid, geom in enumerate(self.sketch.Geometry):
            if hasattr(geom, "StartPoint") and hasattr(geom, "EndPoint"):
                dx = geom.EndPoint.x - geom.StartPoint.x
                dy = geom.EndPoint.y - geom.StartPoint.y
                deg = math.degrees(math.atan2(dy, dx))
                self.line_angles_num[gid] = deg

                if abs(dy) < 1e-4:
                    self.line_angles[gid] = "0" if dx >= 0 else "180"
                elif abs(dx) < 1e-4:
                    self.line_angles[gid] = "90" if dy >= 0 else "-90"

    def _pass3_resolve_geometry(self) -> None:
        """Pass 3: Multi-sweep geometric deductions with true CAD coordinate validation."""
        length_lines: dict[int, tuple[str, str, str]] = {}
        for idx, c in enumerate(self.sketch.Constraints):
            if c.Type != "Distance":
                continue
            param = self.constraint_vars.get(idx)
            if not param:
                continue

            if c.First == c.Second and c.FirstPos != c.SecondPos:
                p1 = self.vertex_map.get(
                    (c.First, 1 if c.FirstPos == 0 else c.FirstPos)
                )
                p2 = self.vertex_map.get(
                    (c.First, 2 if c.SecondPos == 0 else c.SecondPos)
                )
            elif not _is_geo_none(c.Second):
                p1 = self.vertex_map.get(
                    (c.First, 1 if c.FirstPos == 0 else c.FirstPos)
                )
                p2 = self.vertex_map.get(
                    (c.Second, 2 if c.SecondPos == 0 else c.SecondPos)
                )
            else:
                continue

            if p1 and p2 and p1 in self.point_coords and p2 in self.point_coords:
                length_lines[c.First] = (p1, p2, param)

        for geo_id, param in self._equal_length.items():
            if geo_id not in length_lines:
                p1 = self.vertex_map.get((geo_id, 1))
                p2 = self.vertex_map.get((geo_id, 2))
                if p1 and p2 and p1 in self.point_coords and p2 in self.point_coords:
                    length_lines[geo_id] = (p1, p2, param)

        max_sweeps = len(self.point_coords) + 10
        for _ in range(max_sweeps):
            progress = False

            # --- Rule A: Regular Polygon Inscribed on Circle ---
            for cid, geom in enumerate(self.sketch.Geometry):
                if "Circle" not in type(geom).__name__ or "Arc" in type(geom).__name__:
                    continue

                center_name = self.vertex_map.get((cid, 3))
                if not center_name or center_name not in self.point_coords:
                    continue

                verts: list[tuple[str, tuple[int, int]]] = []
                seen_vnames: set[str] = set()
                for c in self.sketch.Constraints:
                    if c.Type in ("PointOnObject", "PointOnCurve"):
                        target_cid = c.Second if c.First >= 0 else c.First
                        pt_geo = c.First if c.First >= 0 else c.Second
                        pt_pos = c.FirstPos if c.First >= 0 else c.SecondPos
                        if target_cid == cid and pt_geo >= 0 and pt_pos in (1, 2, 3):
                            vname = self.vertex_map.get((pt_geo, pt_pos))
                            if (
                                vname
                                and vname not in seen_vnames
                                and vname in self.point_coords
                            ):
                                seen_vnames.add(vname)
                                verts.append((vname, (pt_geo, pt_pos)))

                N = len(verts)
                if N < 3:
                    continue

                c_coord = self.point_coords[center_name]
                v_angles: list[tuple[float, str]] = []
                for vname, _ in verts:
                    v_coord = self.point_coords[vname]
                    ang = (
                        math.degrees(
                            math.atan2(v_coord[1] - c_coord[1], v_coord[0] - c_coord[0])
                        )
                        % 360
                    )
                    v_angles.append((ang, vname))
                v_angles.sort()

                expected_step = 360.0 / N
                is_regular = True
                for i in range(N):
                    step = (v_angles[(i + 1) % N][0] - v_angles[i][0]) % 360
                    if abs(step - expected_step) > 1.0:
                        is_regular = False
                        break

                if not is_regular:
                    continue

                side_len_param = None
                for vname, (g_id, p_id) in verts:
                    if g_id in self._equal_length:
                        side_len_param = self._equal_length[g_id]
                        break

                r_var = f"R_{cid}"
                if side_len_param:
                    sin_arg = 180 // N if 180 % N == 0 else f"180.0 / {N}"
                    self.aux_params[r_var] = f"{side_len_param} / (2 * Sin({sin_arg}))"
                    self.radius_params[cid] = r_var
                elif cid in self.radius_params:
                    r_var = self.radius_params[cid]
                else:
                    self.aux_params[r_var] = draw._to_str(geom.Radius)

                # Only match angles connected to this polygon!
                connected_geos = {cid} | {g_id for _, (g_id, _) in verts}
                for v_ang, vname in v_angles:
                    if vname in self.custom_point_exprs or self._is_cartesian_solved(
                        vname
                    ):
                        continue

                    matched_ang_expr = None
                    for param_idx, c in enumerate(self.sketch.Constraints):
                        if c.Type != "Angle" or (
                            c.First not in connected_geos
                            and c.Second not in connected_geos
                        ):
                            continue
                        aparam = self.constraint_vars.get(param_idx)
                        if not aparam or aparam not in self.params:
                            continue
                        pval = float(self.params[aparam])
                        for s in (1, -1):
                            for off in range(-180, 181, 15):
                                cand = (s * pval + off) % 360
                                if abs(cand - v_ang) < 0.5:
                                    sign_str = "" if s > 0 else "-"
                                    off_str = (
                                        f" + {off}"
                                        if off > 0
                                        else (f" - {-off}" if off < 0 else "")
                                    )
                                    matched_ang_expr = f"{sign_str}{aparam}{off_str}"
                                    break
                            if matched_ang_expr:
                                break
                        if matched_ang_expr:
                            break

                    if matched_ang_expr:
                        self.custom_point_exprs[vname] = (
                            f"{center_name} + dir({matched_ang_expr}) * {r_var}"
                        )
                        self.deps.setdefault(vname, set()).add(center_name)
                        progress = True

            # --- Rule B: Angle-Driven Lines (Validated against true coordinates) ---
            for idx, c in enumerate(self.sketch.Constraints):
                if c.Type != "Angle":
                    continue
                param = self.constraint_vars.get(idx)
                if not param or _is_geo_none(c.Second) or c.Second < 0:
                    continue

                for line_geo, other_geo in [(c.First, c.Second), (c.Second, c.First)]:
                    if line_geo not in length_lines:
                        continue
                    lp1, lp2, len_param = length_lines[line_geo]
                    other_p1 = self.vertex_map.get((other_geo, 1))
                    other_p2 = self.vertex_map.get((other_geo, 2))

                    # Identify common vertex
                    common = (
                        lp1
                        if lp1 in (other_p1, other_p2)
                        else (lp2 if lp2 in (other_p1, other_p2) else None)
                    )
                    if not common:
                        continue

                    target = lp2 if lp1 == common else lp1
                    other_ref = other_p2 if other_p1 == common else other_p1

                    if target in self.custom_point_exprs or self._is_cartesian_solved(
                        target
                    ):
                        continue
                    if not (
                        common in self.point_coords
                        and other_ref in self.point_coords
                        and target in self.point_coords
                    ):
                        continue

                    c_common = self.point_coords[common]
                    c_other = self.point_coords[other_ref]
                    c_target = self.point_coords[target]
                    L_num = float(self.params.get(len_param, 0))
                    ang_num = float(self.params.get(param, 0))

                    # Test candidate angle orientations and validate against true CAD coordinates
                    best_expr = None
                    for ref_mode, ref_name in [
                        ("forward", f"degrees({other_ref} - {common})"),
                        ("backward", f"degrees({common} - {other_ref})"),
                    ]:
                        base_deg = (
                            math.degrees(
                                math.atan2(
                                    c_other[1] - c_common[1], c_other[0] - c_common[0]
                                )
                            )
                            if ref_mode == "forward"
                            else math.degrees(
                                math.atan2(
                                    c_common[1] - c_other[1], c_common[0] - c_other[0]
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
                                math.hypot(test_x - c_target[0], test_y - c_target[1])
                                < 0.05
                            ):
                                best_expr = f"{common} + dir({ref_name} {sign} {param}) * {len_param}"
                                break
                        if best_expr:
                            break

                    if best_expr:
                        self.custom_point_exprs[target] = best_expr
                        self.deps.setdefault(target, set()).update({common, other_ref})
                        progress = True

            # --- Rule C: Circle-Line Intersection (Pythagorean formula) ---
            for line_geo, (p1, p2, len_param) in length_lines.items():
                for base, target in [(p1, p2), (p2, p1)]:
                    if target in self.custom_point_exprs or self._is_cartesian_solved(
                        target
                    ):
                        continue

                    root_x = self.x_sets.find(target)
                    root_y = self.y_sets.find(target)
                    x_solved = root_x in self.x_formulas
                    y_solved = root_y in self.y_formulas

                    base_known = (
                        base in self.custom_point_exprs
                        or self._is_cartesian_solved(base)
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
                        progress = True

                    elif y_solved and not x_solved:
                        y_expr = self.y_formulas[root_y]
                        x_sign = "+" if c_target[0] >= c_base[0] else "-"
                        x_expr = f"{base}.x {x_sign} sqrt(({len_param})^2 - (({y_expr}) - {base}.y)^2)"
                        self.custom_point_exprs[target] = f"({x_expr}, {y_expr})"
                        self.deps.setdefault(target, set()).add(base)
                        progress = True

            # --- Rule D: Trilateration (distance to two known base points) ---
            for target_name in list(self.point_coords.keys()):
                if target_name in self.custom_point_exprs or self._is_cartesian_solved(
                    target_name
                ):
                    continue

                connected_dists: list[tuple[str, str]] = []
                for line_geo, (p1, p2, len_param) in length_lines.items():
                    if p1 == target_name and (
                        p2 in self.custom_point_exprs or self._is_cartesian_solved(p2)
                    ):
                        connected_dists.append((p2, len_param))
                    elif p2 == target_name and (
                        p1 in self.custom_point_exprs or self._is_cartesian_solved(p1)
                    ):
                        connected_dists.append((p1, len_param))

                if len(connected_dists) >= 2:
                    base1, len1 = connected_dists[0]
                    base2, len2 = connected_dists[1]
                    c_b1 = self.point_coords[base1]
                    c_b2 = self.point_coords[base2]
                    c_t = self.point_coords[target_name]

                    d = math.hypot(c_b2[0] - c_b1[0], c_b2[1] - c_b1[1])
                    if d > 1e-4:
                        u = ((c_b2[0] - c_b1[0]) / d, (c_b2[1] - c_b1[1]) / d)
                        v_perp = (-u[1], u[0])
                        v_t = (c_t[0] - c_b1[0], c_t[1] - c_b1[1])
                        perp_dot = v_t[0] * v_perp[0] + v_t[1] * v_perp[1]
                        sign = "+" if perp_dot >= 0 else "-"

                        dx_expr = f"(({len1})^2 - ({len2})^2 + length({base2} - {base1})^2) / (2 * length({base2} - {base1}))"
                        h_expr = f"sqrt(max(0, ({len1})^2 - ({dx_expr})^2))"
                        u_expr = f"unit({base2} - {base1})"
                        v_expr = f"(-({u_expr}).y, ({u_expr}).x)"

                        self.custom_point_exprs[target_name] = (
                            f"{base1} + ({dx_expr}) * {u_expr} {sign} ({h_expr}) * {v_expr}"
                        )
                        self.deps.setdefault(target_name, set()).update({base1, base2})
                        progress = True

            if not progress:
                break

    def format_asymptote_definitions(self) -> str:
        out = ""

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

                # Rule 1: Pure Cartesian solved points
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
                    out += f"pair {name} = {coord_str};\n"
                    declared.add(name)
                    unresolved.pop(i)
                    progress = True
                    break

            if not progress and unresolved:
                name = unresolved.pop(0)
                coord_str = inv_pairs[name]
                out += f"pair {name} = {coord_str};  // unresolved\n"
                declared.add(name)

        return out
