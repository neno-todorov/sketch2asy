"""General SymPy-based symbolic constraint solver for FreeCAD sketches to Asymptote."""

from __future__ import annotations

import math
import re
from typing import Any

import sympy

import draw
from coordinates import get_coordinates


class ParametricModel:
    """Extracts constraints from any FreeCAD sketch and solves them symbolically in closed form."""

    def __init__(self, sketch_obj: Any, pairs_dict: dict[str, str]) -> None:
        self.sketch_obj = sketch_obj
        self.pairs_dict = pairs_dict
        self.radius_params: dict[int, str] = {}
        self.parameters: dict[str, float] = {}  # param_name -> default_value
        self.param_symbols: dict[str, sympy.Symbol] = {}
        self.point_solutions: dict[str, tuple[str, str]] = {}

        self._geo_point_map: dict[tuple[int, int], str] = {}
        self._numeric_coords: dict[str, tuple[float, float]] = {}

        self._prepopulate_points()
        self._solve_general_system()

    def _prepopulate_points(self) -> None:
        """Registers all sketch vertices into pairs_dict and maps (geo_id, pos_id) -> point name."""
        geoms = getattr(self.sketch_obj, "GeometryFacadeList", [])
        if not geoms and hasattr(self.sketch_obj, "Geometry"):
            geoms = self.sketch_obj.Geometry

        for geo_id, elem in enumerate(geoms):
            geom = getattr(elem, "Geometry", elem)
            geom_name = type(geom).__name__.replace("Geom", "")

            if geom_name in ("LineSegment", "BSplineCurve"):
                p0 = draw._pair(geom.StartPoint, self.pairs_dict)
                p1 = draw._pair(geom.EndPoint, self.pairs_dict)
                self._geo_point_map[(geo_id, 1)] = p0
                self._geo_point_map[(geo_id, 2)] = p1
                self._numeric_coords[p0] = get_coordinates(geom.StartPoint)
                self._numeric_coords[p1] = get_coordinates(geom.EndPoint)
            elif geom_name in (
                "ArcOfCircle",
                "ArcOfEllipse",
                "ArcOfHyperbola",
                "ArcOfParabola",
            ):
                p0 = draw._pair(geom.StartPoint, self.pairs_dict)
                p1 = draw._pair(geom.EndPoint, self.pairs_dict)
                c_loc = getattr(geom, "Location", getattr(geom, "Center", None))
                self._geo_point_map[(geo_id, 1)] = p0
                self._geo_point_map[(geo_id, 2)] = p1
                self._numeric_coords[p0] = get_coordinates(geom.StartPoint)
                self._numeric_coords[p1] = get_coordinates(geom.EndPoint)
                if c_loc:
                    pc = draw._pair(c_loc, self.pairs_dict)
                    self._geo_point_map[(geo_id, 3)] = pc
                    self._numeric_coords[pc] = get_coordinates(c_loc)
            elif geom_name in ("Circle", "Ellipse"):
                c_loc = getattr(geom, "Location", getattr(geom, "Center", None))
                if c_loc:
                    pc = draw._pair(c_loc, self.pairs_dict)
                    self._geo_point_map[(geo_id, 3)] = pc
                    self._numeric_coords[pc] = get_coordinates(c_loc)
            elif geom_name == "Point":
                pt_loc = getattr(geom, "Location", geom)
                p0 = draw._pair(pt_loc, self.pairs_dict)
                self._geo_point_map[(geo_id, 1)] = p0
                self._numeric_coords[p0] = get_coordinates(pt_loc)

        for coord_str, name in self.pairs_dict.items():
            if name not in self._numeric_coords:
                try:
                    coords = coord_str.strip("()").split(",")
                    self._numeric_coords[name] = (float(coords[0]), float(coords[1]))
                except (ValueError, IndexError):
                    self._numeric_coords[name] = (0.0, 0.0)

    def _sanitize_name(self, name: str, fallback_prefix: str, idx: int) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip()) if name else ""
        if not clean or clean[0].isdigit():
            clean = f"{fallback_prefix}{idx}"
        base = clean
        count = 1
        while clean in self.parameters:
            clean = f"{base}_{count}"
            count += 1
        return clean

    def _resolve_pt(self, geo_id: int, pos_id: int) -> str | None:
        if geo_id == -3 or (geo_id in (-1, -2) and pos_id == 1):
            return "__ORIGIN__"
        if geo_id == -1 and pos_id == 0:
            return "__HAXIS__"
        if geo_id == -2 and pos_id == 0:
            return "__VAXIS__"
        return self._geo_point_map.get((geo_id, pos_id))

    def _solve_general_system(self) -> None:
        constraints = getattr(self.sketch_obj, "Constraints", [])

        # Step 1: Create symbolic parameters for all dimensional constraints
        con_param_map: dict[int, str] = {}
        param_idx = 1
        for i, con in enumerate(constraints):
            if not getattr(con, "IsActive", True) or not getattr(
                con, "IsDriving", True
            ):
                continue

            con_type = getattr(con, "Type", "")
            raw_val = float(getattr(con, "Value", 0.0))
            name = getattr(con, "Name", "")

            if con_type in (
                "DistanceX",
                "DistanceY",
                "Distance",
                "Radius",
                "Diameter",
                "Angle",
            ):
                prefix = {
                    "DistanceX": "Dx",
                    "DistanceY": "Dy",
                    "Distance": "L",
                    "Radius": "R",
                    "Diameter": "D",
                    "Angle": "A",
                }.get(con_type, "p")

                val = (
                    round(math.degrees(raw_val), 4) if con_type == "Angle" else raw_val
                )
                p_name = self._sanitize_name(name, prefix, param_idx)
                param_idx += 1

                self.parameters[p_name] = val
                self.param_symbols[p_name] = sympy.Symbol(p_name, real=True)
                con_param_map[i] = p_name

                if con_type == "Radius" and con.First >= 0:
                    self.radius_params[con.First] = p_name
                elif con_type == "Diameter" and con.First >= 0:
                    self.radius_params[con.First] = f"({p_name} / 2)"

        # Step 2: Create (X, Y) SymPy symbols for all sketch points
        point_symbols: dict[str, tuple[sympy.Symbol, sympy.Symbol]] = {}
        for pt_name in self.pairs_dict.values():
            x_sym = sympy.Symbol(f"x_{pt_name}", real=True)
            y_sym = sympy.Symbol(f"y_{pt_name}", real=True)
            point_symbols[pt_name] = (x_sym, y_sym)

        def get_pt_sym(pt_id: str | None) -> tuple[Any, Any] | None:
            if pt_id == "__ORIGIN__":
                return (sympy.Integer(0), sympy.Integer(0))
            if pt_id in point_symbols:
                return point_symbols[pt_id]
            return None

        # Step 3: Translate all constraints into general algebraic equations
        equations: list[sympy.Expr] = []

        for i, con in enumerate(constraints):
            if not getattr(con, "IsActive", True) or not getattr(
                con, "IsDriving", True
            ):
                continue

            con_type = getattr(con, "Type", "")
            p_name = con_param_map.get(i)
            param_sym = self.param_symbols.get(p_name) if p_name else None

            pt1_id = self._resolve_pt(con.First, con.FirstPos)
            pt2_id = (
                self._resolve_pt(con.Second, con.SecondPos)
                if con.Second != -2000
                else None
            )

            # Handle constraints applied to whole lines (pos_id == 0)
            if not pt1_id and con.First >= 0:
                pt1_id = self._resolve_pt(con.First, 1)
                pt2_id = self._resolve_pt(con.First, 2)

            pt1 = get_pt_sym(pt1_id)
            pt2 = get_pt_sym(pt2_id)

            if con_type == "Coincident" and pt1 and pt2:
                equations.append(pt1[0] - pt2[0])
                equations.append(pt1[1] - pt2[1])

            elif con_type == "Horizontal":
                if pt1 and pt2:
                    equations.append(pt1[1] - pt2[1])
                elif con.First >= 0:
                    s = get_pt_sym(self._resolve_pt(con.First, 1))
                    e = get_pt_sym(self._resolve_pt(con.First, 2))
                    if s and e:
                        equations.append(s[1] - e[1])

            elif con_type == "Vertical":
                if pt1 and pt2:
                    equations.append(pt1[0] - pt2[0])
                elif con.First >= 0:
                    s = get_pt_sym(self._resolve_pt(con.First, 1))
                    e = get_pt_sym(self._resolve_pt(con.First, 2))
                    if s and e:
                        equations.append(s[0] - e[0])

            elif con_type == "PointOnObject" and pt1:
                if con.Second == -1:  # Horizontal axis (Y = 0)
                    equations.append(pt1[1])
                elif con.Second == -2:  # Vertical axis (X = 0)
                    equations.append(pt1[0])
                elif pt2_id and pt2:
                    # Point on line
                    l_s = get_pt_sym(self._resolve_pt(con.Second, 1))
                    l_e = get_pt_sym(self._resolve_pt(con.Second, 2))
                    if l_s and l_e:
                        equations.append(
                            (pt1[0] - l_s[0]) * (l_e[1] - l_s[1])
                            - (pt1[1] - l_s[1]) * (l_e[0] - l_s[0])
                        )

            elif con_type == "DistanceX" and param_sym is not None and pt1:
                if pt2:
                    sign = (
                        1
                        if self._numeric_coords[pt2_id][0]
                        >= self._numeric_coords[pt1_id][0]
                        else -1
                    )
                    equations.append(pt2[0] - pt1[0] - sign * param_sym)
                elif con.Second == -2:
                    sign = 1 if self._numeric_coords[pt1_id][0] >= 0 else -1
                    equations.append(pt1[0] - sign * param_sym)

            elif con_type == "DistanceY" and param_sym is not None and pt1:
                if pt2:
                    sign = (
                        1
                        if self._numeric_coords[pt2_id][1]
                        >= self._numeric_coords[pt1_id][1]
                        else -1
                    )
                    equations.append(pt2[1] - pt1[1] - sign * param_sym)
                elif con.Second == -1:
                    sign = 1 if self._numeric_coords[pt1_id][1] >= 0 else -1
                    equations.append(pt1[1] - sign * param_sym)

            elif con_type == "Distance" and param_sym is not None and pt1:
                # Perpendicular distance to Vertical Axis (line X = 0)
                if (
                    (pt2_id in ("__VAXIS__", None))
                    and con.Second == -2
                    and con.SecondPos == 0
                ):
                    sign = 1 if self._numeric_coords[pt1_id][0] >= 0 else -1
                    equations.append(pt1[0] - sign * param_sym)
                # Perpendicular distance to Horizontal Axis (line Y = 0)
                elif (
                    (pt2_id in ("__HAXIS__", None))
                    and con.Second == -1
                    and con.SecondPos == 0
                ):
                    sign = 1 if self._numeric_coords[pt1_id][1] >= 0 else -1
                    equations.append(pt1[1] - sign * param_sym)
                elif pt2:
                    dx_num = abs(
                        self._numeric_coords[pt2_id][0]
                        - self._numeric_coords[pt1_id][0]
                    )
                    dy_num = abs(
                        self._numeric_coords[pt2_id][1]
                        - self._numeric_coords[pt1_id][1]
                    )
                    if dy_num < 1e-4:
                        sign = (
                            1
                            if self._numeric_coords[pt2_id][0]
                            >= self._numeric_coords[pt1_id][0]
                            else -1
                        )
                        equations.append(pt2[0] - pt1[0] - sign * param_sym)
                    elif dx_num < 1e-4:
                        sign = (
                            1
                            if self._numeric_coords[pt2_id][1]
                            >= self._numeric_coords[pt1_id][1]
                            else -1
                        )
                        equations.append(pt2[1] - pt1[1] - sign * param_sym)
                    else:
                        equations.append(
                            (pt2[0] - pt1[0]) ** 2
                            + (pt2[1] - pt1[1]) ** 2
                            - param_sym**2
                        )

            elif con_type == "Equal":
                # Equal length of two lines
                if (
                    con.First >= 0
                    and con.Second >= 0
                    and con.FirstPos == 0
                    and con.SecondPos == 0
                ):
                    s1 = get_pt_sym(self._resolve_pt(con.First, 1))
                    e1 = get_pt_sym(self._resolve_pt(con.First, 2))
                    s2 = get_pt_sym(self._resolve_pt(con.Second, 1))
                    e2 = get_pt_sym(self._resolve_pt(con.Second, 2))
                    if s1 and e1 and s2 and e2:
                        equations.append(
                            ((e1[0] - s1[0]) ** 2 + (e1[1] - s1[1]) ** 2)
                            - ((e2[0] - s2[0]) ** 2 + (e2[1] - s2[1]) ** 2)
                        )

            elif con_type == "Angle" and param_sym is not None:
                # Dot product angle formula
                if con.First >= 0 and con.Second >= 0:
                    s1 = get_pt_sym(self._resolve_pt(con.First, 1))
                    e1 = get_pt_sym(self._resolve_pt(con.First, 2))
                    s2 = get_pt_sym(self._resolve_pt(con.Second, 1))
                    e2 = get_pt_sym(self._resolve_pt(con.Second, 2))
                    if s1 and e1 and s2 and e2:
                        # Vector dot product with known lengths / unit directions
                        v1 = (e1[0] - s1[0], e1[1] - s1[1])
                        v2 = (e2[0] - s2[0], e2[1] - s2[1])
                        l1 = sympy.sqrt(v1[0] ** 2 + v1[1] ** 2)
                        l2 = sympy.sqrt(v2[0] ** 2 + v2[1] ** 2)
                        # cos(angle) in degrees for Asymptote Cos
                        cos_term = sympy.cos(param_sym * sympy.pi / 180)
                        equations.append(
                            v1[0] * v2[0] + v1[1] * v2[1] - l1 * l2 * cos_term
                        )

        # Step 4: Staged incremental solving (Linear first -> incremental non-linear)
        solved_vars: dict[sympy.Symbol, sympy.Expr] = {}
        all_var_symbols = [s for pair in point_symbols.values() for s in pair]

        # Phase A: Fast Linear System Solving via linsolve
        linear_eqs = []
        non_linear_eqs = []
        for eq in equations:
            eq_poly = eq.as_poly(*all_var_symbols)
            if eq_poly is not None and eq_poly.total_degree() <= 1:
                linear_eqs.append(eq)
            else:
                non_linear_eqs.append(eq)

        if linear_eqs:
            lin_sol = sympy.linsolve(linear_eqs, all_var_symbols)
            if lin_sol:
                sol_tuple = next(iter(lin_sol))
                for var, expr in zip(all_var_symbols, sol_tuple):
                    # Check if the linear solution resolved to a definite parameter expression
                    free_pts = [s for s in expr.free_symbols if s in all_var_symbols]
                    if not free_pts and expr != var:
                        solved_vars[var] = expr

        # Phase B: Incremental Non-linear solving
        # Substitute already solved variables into non-linear equations
        remaining_eqs = [eq.subs(solved_vars) for eq in non_linear_eqs]
        progress = True
        while progress:
            progress = False
            next_remaining = []
            for eq in remaining_eqs:
                eq_sub = eq.subs(solved_vars)
                unknowns = [
                    s
                    for s in eq_sub.free_symbols
                    if s in all_var_symbols and s not in solved_vars
                ]

                if len(unknowns) == 1:
                    target_var = unknowns[0]
                    target_pt_name = str(target_var).split("_")[1]
                    coord_idx = 0 if str(target_var).startswith("x_") else 1
                    target_num = self._numeric_coords[target_pt_name][coord_idx]

                    try:
                        roots = sympy.solve(eq_sub, target_var)
                        if roots:
                            # Pick root closest to FreeCAD numerical value
                            subs_params = {
                                s: self.parameters[str(s)]
                                for s in self.param_symbols.values()
                                if str(s) in self.parameters
                            }
                            best_root = roots[0]
                            best_err = float("inf")
                            for r in roots:
                                try:
                                    r_val = float(r.evalf(subs=subs_params))
                                    err = abs(r_val - target_num)
                                    if err < best_err:
                                        best_err = err
                                        best_root = r
                                except (TypeError, ValueError):
                                    pass

                            solved_vars[target_var] = best_root
                            progress = True
                            continue
                    except Exception:  # noqa: BLE001, S110
                        pass

                next_remaining.append(eq_sub)
            remaining_eqs = next_remaining

        # Phase C: Fully Back-Substitute all expressions so every point is closed-form
        for _ in range(3):
            for var in list(solved_vars.keys()):
                solved_vars[var] = sympy.simplify(solved_vars[var].subs(solved_vars))

        # Phase D: Fallback unconstrained variables to FreeCAD numerical values
        for pt_name, (x_sym, y_sym) in point_symbols.items():
            num_x, num_y = self._numeric_coords[pt_name]

            if x_sym in solved_vars and not any(
                s in all_var_symbols for s in solved_vars[x_sym].free_symbols
            ):
                x_final = self._expr_to_asy(solved_vars[x_sym])
            else:
                x_final = draw._to_str(num_x)

            if y_sym in solved_vars and not any(
                s in all_var_symbols for s in solved_vars[y_sym].free_symbols
            ):
                y_final = self._expr_to_asy(solved_vars[y_sym])
            else:
                y_final = draw._to_str(num_y)

            self.point_solutions[pt_name] = (x_final, y_final)

    def _expr_to_asy(self, expr: sympy.Expr) -> str:
        """Converts a SymPy expression to valid Asymptote syntax."""
        if expr is None:
            return "0"
        if expr.is_number:
            val = float(expr)
            if abs(val - round(val)) < 1e-5:
                return str(round(val))
            return draw._to_str(val)

        # Capitalize Cos/Sin for Asymptote degrees trig functions
        s = sympy.sstr(sympy.simplify(expr))
        s = s.replace("**", "^")
        s = re.sub(r"\bcos\(", "Cos(", s)
        s = re.sub(r"\bsin\(", "Sin(", s)
        # Clean up pi radians factors if converted to degrees
        s = s.replace("*pi/180", "")
        return s

    def format_asymptote_definitions(self, paths_and_circles_str: str = "") -> str:
        """Formats the parameter declarations and closed-form point definitions."""
        point_lines: list[tuple[str, str]] = []

        for coord_str, name in sorted(
            self.pairs_dict.items(),
            key=lambda i: int(i[1][1:]) if i[1][1:].isdigit() else 999999,
        ):
            if name in self.point_solutions:
                x_str, y_str = self.point_solutions[name]
                line = f"pair {name} = ({x_str}, {y_str});\n"
            else:
                line = f"pair {name} = {coord_str};\n"

            point_lines.append((name, line))

        # Output all driving dimensional constraints
        params_lines: list[str] = []
        for param_name, default_val in self.parameters.items():
            if abs(default_val - round(default_val)) < 1e-5:
                val_str = str(round(default_val))
            else:
                val_str = draw._to_str(default_val)
            params_lines.append(f"real {param_name} = {val_str};\n")

        params_section = ""
        if params_lines:
            params_section = "// --- Parameters ---\n" + "".join(params_lines) + "\n"

        points_section = "// --- Points & Coordinates ---\n" + "".join(
            line for _, line in point_lines
        )
        return f"{params_section}{points_section}"
