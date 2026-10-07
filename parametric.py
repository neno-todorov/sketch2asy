"""SymPy-based symbolic constraint solver for FreeCAD sketches to Asymptote."""

from __future__ import annotations

import math
import re
from typing import Any

import sympy
from coordinates import get_coordinates
import draw


class ParametricModel:
    """Extracts constraints from a FreeCAD sketch and solves them symbolically."""

    def __init__(self, sketch_obj: Any, pairs_dict: dict[str, str]) -> None:
        self.sketch_obj = sketch_obj
        self.pairs_dict = pairs_dict
        self.radius_params: dict[int, str] = {}
        self.parameters: dict[str, float] = {}  # param_name -> default_value
        self.point_solutions: dict[str, tuple[sympy.Expr, sympy.Expr]] = {}
        self._geo_point_map: dict[tuple[int, int], str] = {}

        self._prepopulate_points()
        self._extract_constraints_and_solve()

    def _prepopulate_points(self) -> None:
        """Pre-populates pairs_dict so point names (P0, P1, ...) match draw.py."""
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
            elif geom_name in (
                "ArcOfCircle",
                "ArcOfEllipse",
                "ArcOfHyperbola",
                "ArcOfParabola",
            ):
                p0 = draw._pair(geom.StartPoint, self.pairs_dict)
                p1 = draw._pair(geom.EndPoint, self.pairs_dict)
                c_loc = getattr(geom, "Location", getattr(geom, "Center", None))
                pc = draw._pair(c_loc, self.pairs_dict) if c_loc else None
                self._geo_point_map[(geo_id, 1)] = p0
                self._geo_point_map[(geo_id, 2)] = p1
                if pc:
                    self._geo_point_map[(geo_id, 3)] = pc
            elif geom_name in ("Circle", "Ellipse"):
                c_loc = getattr(geom, "Location", getattr(geom, "Center", None))
                if c_loc:
                    pc = draw._pair(c_loc, self.pairs_dict)
                    self._geo_point_map[(geo_id, 3)] = pc
            elif geom_name == "Point":
                pt_loc = getattr(geom, "Location", geom)
                p0 = draw._pair(pt_loc, self.pairs_dict)
                self._geo_point_map[(geo_id, 1)] = p0

    def _sanitize_name(self, name: str, fallback_prefix: str, idx: int) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip()) if name else ""
        if not clean or clean[0].isdigit():
            clean = f"{fallback_prefix}{idx}"
        # Ensure unique name
        base = clean
        count = 1
        while clean in self.parameters:
            clean = f"{base}_{count}"
            count += 1
        return clean

    def _extract_constraints_and_solve(self) -> None:
        constraints = getattr(self.sketch_obj, "Constraints", [])
        if not constraints:
            return

        equations: list[sympy.Expr] = []
        point_symbols: dict[str, tuple[sympy.Symbol, sympy.Symbol]] = {}

        # Create SymPy symbols and store numeric target values
        numeric_targets: dict[sympy.Symbol, float] = {}
        for coord_str, pt_name in self.pairs_dict.items():
            try:
                coords = coord_str.strip("()").split(",")
                x_val, y_val = float(coords[0]), float(coords[1])
            except (ValueError, IndexError):
                x_val, y_val = 0.0, 0.0

            x_sym = sympy.Symbol(f"x_{pt_name}", real=True)
            y_sym = sympy.Symbol(f"y_{pt_name}", real=True)
            point_symbols[pt_name] = (x_sym, y_sym)
            numeric_targets[x_sym] = x_val
            numeric_targets[y_sym] = y_val

        def get_point_sym(
            geo_id: int, pos_id: int
        ) -> tuple[sympy.Symbol, sympy.Symbol] | tuple[float, float] | None:
            if geo_id == -3 or (geo_id in (-1, -2) and pos_id == 1):
                return (0.0, 0.0)
            pt_name = self._geo_point_map.get((geo_id, pos_id))
            if pt_name and pt_name in point_symbols:
                return point_symbols[pt_name]
            return None

        # Process each constraint
        param_counter = 1
        for con in constraints:
            if not getattr(con, "IsActive", True) or not getattr(
                con, "IsDriving", True
            ):
                continue

            con_type = getattr(con, "Type", "")
            val = float(getattr(con, "Value", 0.0))
            name = getattr(con, "Name", "")

            # Dimensional constraints create parameters
            param_sym = None
            if con_type in (
                "DistanceX",
                "DistanceY",
                "Distance",
                "Radius",
                "Diameter",
                "Angle",
            ):
                param_name = self._sanitize_name(
                    name, con_type[0].lower(), param_counter
                )
                param_counter += 1
                self.parameters[param_name] = val
                param_sym = sympy.Symbol(param_name, positive=True, real=True)

                if con_type == "Radius" and con.First >= 0:
                    self.radius_params[con.First] = param_name
                elif con_type == "Diameter" and con.First >= 0:
                    self.radius_params[con.First] = f"({param_name} / 2)"

            pt1 = get_point_sym(con.First, con.FirstPos)
            pt2 = (
                get_point_sym(con.Second, con.SecondPos)
                if con.Second != -2000
                else None
            )

            # Algebraic modeling
            if con_type == "Horizontal":
                if pt1 and pt2:
                    equations.append(pt1[1] - pt2[1])
                elif con.First >= 0:
                    p_start = get_point_sym(con.First, 1)
                    p_end = get_point_sym(con.First, 2)
                    if p_start and p_end:
                        equations.append(p_start[1] - p_end[1])

            elif con_type == "Vertical":
                if pt1 and pt2:
                    equations.append(pt1[0] - pt2[0])
                elif con.First >= 0:
                    p_start = get_point_sym(con.First, 1)
                    p_end = get_point_sym(con.First, 2)
                    if p_start and p_end:
                        equations.append(p_start[0] - p_end[0])

            elif con_type == "Coincident" and pt1 and pt2:
                equations.append(pt1[0] - pt2[0])
                equations.append(pt1[1] - pt2[1])

            elif con_type == "DistanceX" and param_sym is not None:
                if pt1 and pt2:
                    sign = (
                        1
                        if numeric_targets.get(pt2[0], 0.0)
                        >= numeric_targets.get(pt1[0], 0.0)
                        else -1
                    )
                    equations.append(pt2[0] - pt1[0] - sign * param_sym)
                elif pt1 and con.Second == -2:  # Vertical sketch axis (X = 0)
                    sign = 1 if numeric_targets.get(pt1[0], 0.0) >= 0 else -1
                    equations.append(pt1[0] - sign * param_sym)

            elif con_type == "DistanceY" and param_sym is not None:
                if pt1 and pt2:
                    sign = (
                        1
                        if numeric_targets.get(pt2[1], 0.0)
                        >= numeric_targets.get(pt1[1], 0.0)
                        else -1
                    )
                    equations.append(pt2[1] - pt1[1] - sign * param_sym)
                elif pt1 and con.Second == -1:  # Horizontal sketch axis (Y = 0)
                    sign = 1 if numeric_targets.get(pt1[1], 0.0) >= 0 else -1
                    equations.append(pt1[1] - sign * param_sym)

            elif con_type == "Distance" and param_sym is not None:
                if not pt1 and con.First >= 0:
                    pt1 = get_point_sym(con.First, 1)
                    pt2 = get_point_sym(con.First, 2)

                if pt1 and pt2:
                    dx_num = abs(
                        numeric_targets.get(pt2[0], 0.0)
                        - numeric_targets.get(pt1[0], 0.0)
                    )
                    dy_num = abs(
                        numeric_targets.get(pt2[1], 0.0)
                        - numeric_targets.get(pt1[1], 0.0)
                    )

                    if dy_num < 1e-6:  # Effectively horizontal
                        sign = (
                            1
                            if numeric_targets.get(pt2[0], 0.0)
                            >= numeric_targets.get(pt1[0], 0.0)
                            else -1
                        )
                        equations.append(pt2[0] - pt1[0] - sign * param_sym)
                    elif dx_num < 1e-6:  # Effectively vertical
                        sign = (
                            1
                            if numeric_targets.get(pt2[1], 0.0)
                            >= numeric_targets.get(pt1[1], 0.0)
                            else -1
                        )
                        equations.append(pt2[1] - pt1[1] - sign * param_sym)
                    else:
                        equations.append(
                            (pt2[0] - pt1[0]) ** 2
                            + (pt2[1] - pt1[1]) ** 2
                            - param_sym**2
                        )

        if not equations:
            return

        all_syms = [s for pair in point_symbols.values() for s in pair]

        # Solve system using SymPy
        try:
            solutions = sympy.solve(equations, all_syms, dict=True)
        except Exception:  # noqa: BLE001
            # Fall back to solving linear equations only
            linear_eqs = [
                eq
                for eq in equations
                if eq.is_polynomial()
                and all(sympy.degree(eq, s) <= 1 for s in all_syms)
            ]
            solutions = sympy.solve(linear_eqs, all_syms, dict=True)

        if not solutions:
            return

        # Pick best branch matching the sketch's numeric coordinates
        best_sol = solutions[0]
        if len(solutions) > 1:
            best_error = float("inf")
            subs_params = {sympy.Symbol(k): v for k, v in self.parameters.items()}
            for candidate in solutions:
                curr_error = 0.0
                for sym, target in numeric_targets.items():
                    if sym in candidate:
                        try:
                            val = float(candidate[sym].evalf(subs=subs_params))
                            curr_error += (val - target) ** 2
                        except (TypeError, ValueError):
                            curr_error += 1e6
                if curr_error < best_error:
                    best_error = curr_error
                    best_sol = candidate

        # Store solutions for each point
        for pt_name, (x_sym, y_sym) in point_symbols.items():
            x_sol = best_sol.get(x_sym, sympy.Float(numeric_targets[x_sym]))
            y_sol = best_sol.get(y_sym, sympy.Float(numeric_targets[y_sym]))
            self.point_solutions[pt_name] = (x_sol, y_sol)

    @staticmethod
    def _expr_to_asy(expr: sympy.Expr) -> str:
        """Converts a SymPy expression to Asymptote-compatible syntax."""
        if expr.is_number:
            val = float(expr)
            if abs(val - round(val)) < 1e-6:
                return str(int(round(val)))
            return f"{val:g}"

        s = sympy.sstr(expr)
        s = s.replace("**", "^")
        return s

    def format_asymptote_definitions(self, paths_and_circles_str: str = "") -> str:
        """Formats the parameter declarations and point definitions for Asymptote."""
        point_lines: list[tuple[str, str]] = []  # (pt_name, line)
        referenced_text = paths_and_circles_str

        # Format points
        for coord_str, name in sorted(
            self.pairs_dict.items(),
            key=lambda i: int(i[1][1:]) if i[1][1:].isdigit() else 999999,
        ):
            if name in self.point_solutions:
                x_sym, y_sym = self.point_solutions[name]
                x_str = self._expr_to_asy(x_sym)
                y_str = self._expr_to_asy(y_sym)
                line = f"pair {name} = ({x_str}, {y_str});\n"
            else:
                line = f"pair {name} = {coord_str};\n"

            point_lines.append((name, line))
            referenced_text += f" {line}"

        # Prune unused / dead parameters
        active_params: list[str] = []
        for param_name, default_val in self.parameters.items():
            pattern = rf"\b{re.escape(param_name)}\b"
            if re.search(pattern, referenced_text):
                val_str = f"{default_val:g}"
                active_params.append(f"real {param_name} = {val_str};\n")

        params_section = ""
        if active_params:
            params_section = "// --- Parameters ---\n" + "".join(active_params) + "\n"

        points_section = "// --- Points & Coordinates ---\n" + "".join(
            line for _, line in point_lines
        )
        return f"{params_section}{points_section}"
