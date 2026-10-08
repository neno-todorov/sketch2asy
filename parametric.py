"""Hybrid symbolic constraint solver for FreeCAD sketches -> Asymptote.

The FreeCAD solver remains the numerical oracle for selecting branches. SymPy is
used only for local symbolic elimination, rather than trying to solve the whole
sketch globally. This keeps the symbolic part lightweight and prevents UI freezes.
"""

from __future__ import annotations

import math
import re
from typing import Any

import sympy

import draw
from coordinates import get_coordinates

_GEO_NONE = -2000
_XAXIS_ID = -1
_YAXIS_ID = -2
_TOL = 1e-7

DIM_TYPES = (
    "Distance",
    "DistanceX",
    "DistanceY",
    "Radius",
    "Diameter",
    "Angle",
)


def _is_none(g: int | None) -> bool:
    return g is None or g <= _GEO_NONE


class ParametricModel:
    """Build symbolic point expressions while FreeCAD supplies branch choices."""

    def __init__(self, sketch_obj: Any, pairs_dict: dict[str, str]) -> None:
        self.sketch_obj = sketch_obj
        self.pairs_dict = pairs_dict

        self.radius_params: dict[int, str] = {}
        self.parameters: dict[str, float] = {}
        self.param_symbols: dict[str, sympy.Symbol] = {}
        self.point_solutions: dict[str, tuple[str, str]] = {}

        self._geo_point_map: dict[tuple[int, int], str] = {}
        self._numeric_coords: dict[str, tuple[float, float]] = {}

        self.constraint_vars: dict[int, str] = {}
        self.used_parameters: set[str] = set()
        self.unused_parameters: set[str] = set()
        self.unsolved_points: set[str] = set()

        self._prepopulate_points()
        self._solve_general_system()

    # ------------------------------------------------------------------
    # Geometry / Names
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_name(
        name: str, fallback_prefix: str, idx: int, existing: set[str]
    ) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip()) if name else ""
        if not clean or clean[0].isdigit():
            clean = f"{fallback_prefix}{idx}"

        base = clean
        n = 1
        while clean in existing:
            clean = f"{base}_{n}"
            n += 1
        return clean

    def _prepopulate_points(self) -> None:
        geoms = getattr(self.sketch_obj, "GeometryFacadeList", [])
        if not geoms and hasattr(self.sketch_obj, "Geometry"):
            geoms = self.sketch_obj.Geometry

        for geo_id, elem in enumerate(geoms):
            geom = getattr(elem, "Geometry", elem)
            kind = type(geom).__name__.replace("Geom", "")

            try:
                if kind in ("LineSegment", "BSplineCurve"):
                    self._add_point(geo_id, 1, geom.StartPoint)
                    self._add_point(geo_id, 2, geom.EndPoint)

                elif kind in (
                    "ArcOfCircle",
                    "ArcOfEllipse",
                    "ArcOfHyperbola",
                    "ArcOfParabola",
                ):
                    self._add_point(geo_id, 1, geom.StartPoint)
                    self._add_point(geo_id, 2, geom.EndPoint)
                    center = getattr(geom, "Location", getattr(geom, "Center", None))
                    if center is not None:
                        self._add_point(geo_id, 3, center)

                elif kind in ("Circle", "Ellipse"):
                    center = getattr(geom, "Location", getattr(geom, "Center", None))
                    if center is not None:
                        self._add_point(geo_id, 3, center)

                elif kind == "Point":
                    point = getattr(geom, "Location", geom)
                    self._add_point(geo_id, 1, point)
            except Exception:  # noqa: BLE001, S112
                continue

        for coord_str, name in self.pairs_dict.items():
            if name in self._numeric_coords:
                continue
            try:
                x, y = coord_str.strip("()").split(",")[:2]
                self._numeric_coords[name] = (float(x), float(y))
            except (ValueError, IndexError):
                self._numeric_coords[name] = (0.0, 0.0)

    def _add_point(self, geo_id: int, pos_id: int, point: Any) -> None:
        name = draw._pair(point, self.pairs_dict)
        self._geo_point_map[(geo_id, pos_id)] = name
        self._numeric_coords[name] = get_coordinates(point)

    def _resolve_pt(self, geo_id: int, pos_id: int) -> str | None:
        if geo_id == -3 or (geo_id in (-1, -2) and pos_id == 1):
            return "__ORIGIN__"
        if geo_id == _XAXIS_ID and pos_id == 0:
            return "__HAXIS__"
        if geo_id == _YAXIS_ID and pos_id == 0:
            return "__VAXIS__"
        return self._geo_point_map.get((geo_id, pos_id))

    # ------------------------------------------------------------------
    # Constraint -> Equation Translation
    # ------------------------------------------------------------------

    def _make_parameters(self, constraints: list[Any]) -> dict[int, str]:
        result: dict[int, str] = {}
        used: set[str] = set()
        serial = 1

        prefixes = {
            "DistanceX": "X",
            "DistanceY": "Y",
            "Distance": "L",
            "Radius": "R",
            "Diameter": "D",
            "Angle": "A",
        }

        for idx, c in enumerate(constraints):
            if not getattr(c, "IsActive", True) or not getattr(c, "IsDriving", True):
                continue
            ctype = getattr(c, "Type", "")
            if ctype not in DIM_TYPES:
                continue

            raw = float(getattr(c, "Value", 0.0))
            if ctype == "Angle":
                value = math.degrees(raw)
            else:
                value = abs(raw)

            name = self._sanitize_name(
                getattr(c, "Name", ""),
                prefixes.get(ctype, "p"),
                serial,
                used,
            )
            serial += 1
            used.add(name)

            self.parameters[name] = value
            self.param_symbols[name] = sympy.Symbol(name, real=True)
            self.constraint_vars[idx] = name
            result[idx] = name

            if ctype == "Radius" and c.First >= 0:
                self.radius_params[c.First] = name
            elif ctype == "Diameter" and c.First >= 0:
                self.radius_params[c.First] = f"({name} / 2)"

        return result

    def _point_symbols(self) -> dict[str, tuple[sympy.Symbol, sympy.Symbol]]:
        result: dict[str, tuple[sympy.Symbol, sympy.Symbol]] = {}
        for name in self.pairs_dict.values():
            result[name] = (
                sympy.Symbol(f"x_{name}", real=True),
                sympy.Symbol(f"y_{name}", real=True),
            )
        return result

    @staticmethod
    def _point_expr(
        name: str | None,
        symbols: dict[str, tuple[sympy.Symbol, sympy.Symbol]],
    ) -> tuple[Any, Any] | None:
        if name == "__ORIGIN__":
            return sympy.Integer(0), sympy.Integer(0)
        return symbols.get(name)

    def _constraint_points(
        self,
        c: Any,
        symbols: dict[str, tuple[sympy.Symbol, sympy.Symbol]],
    ) -> tuple[
        str | None,
        str | None,
        tuple[Any, Any] | None,
        tuple[Any, Any] | None,
    ]:
        p1_id = self._resolve_pt(c.First, c.FirstPos)

        if _is_none(getattr(c, "Second", None)):
            p2_id = None
        else:
            p2_id = self._resolve_pt(c.Second, c.SecondPos)

        if p1_id is None and c.First >= 0:
            p1_id = self._resolve_pt(c.First, 1)
            p2_id = self._resolve_pt(c.First, 2)

        return (
            p1_id,
            p2_id,
            self._point_expr(p1_id, symbols),
            self._point_expr(p2_id, symbols),
        )

    def _equations(
        self,
        constraints: list[Any],
        symbols: dict[str, tuple[sympy.Symbol, sympy.Symbol]],
        con_param_map: dict[int, str],
    ) -> list[sympy.Expr]:
        equations: list[sympy.Expr] = []

        def append(eq: Any) -> None:
            if eq is None:
                return
            if eq != 0:
                equations.append(eq)

        for idx, c in enumerate(constraints):
            if not getattr(c, "IsActive", True) or not getattr(c, "IsDriving", True):
                continue

            typ = getattr(c, "Type", "")
            param_name = con_param_map.get(idx)
            param = self.param_symbols.get(param_name) if param_name else None

            p1_id, p2_id, p1, p2 = self._constraint_points(c, symbols)

            if typ == "Coincident" and p1 and p2:
                append(p1[0] - p2[0])
                append(p1[1] - p2[1])

            elif typ in ("Horizontal", "Vertical"):
                if c.First >= 0:
                    s = self._point_expr(self._resolve_pt(c.First, 1), symbols)
                    e = self._point_expr(self._resolve_pt(c.First, 2), symbols)
                    if s and e:
                        append((s[1] - e[1]) if typ == "Horizontal" else (s[0] - e[0]))
                elif p1 and p2:
                    append((p1[1] - p2[1]) if typ == "Horizontal" else (p1[0] - p2[0]))

            elif typ in ("PointOnObject", "PointOnCurve") and p1:
                if c.Second == _XAXIS_ID:
                    append(p1[1])
                elif c.Second == _YAXIS_ID:
                    append(p1[0])
                else:
                    ls = self._point_expr(self._resolve_pt(c.Second, 1), symbols)
                    le = self._point_expr(self._resolve_pt(c.Second, 2), symbols)
                    if ls and le:
                        append(
                            (p1[0] - ls[0]) * (le[1] - ls[1])
                            - (p1[1] - ls[1]) * (le[0] - ls[0])
                        )

            elif typ == "DistanceX" and param is not None and p1:
                if p2 and p1_id and p2_id:
                    sign = (
                        1
                        if self._numeric_coords[p2_id][0]
                        >= self._numeric_coords[p1_id][0]
                        else -1
                    )
                    append(p2[0] - p1[0] - sign * param)
                elif c.Second == _YAXIS_ID:
                    sign = 1 if self._numeric_coords[p1_id][0] >= 0 else -1
                    append(p1[0] - sign * param)

            elif typ == "DistanceY" and param is not None and p1:
                if p2 and p1_id and p2_id:
                    sign = (
                        1
                        if self._numeric_coords[p2_id][1]
                        >= self._numeric_coords[p1_id][1]
                        else -1
                    )
                    append(p2[1] - p1[1] - sign * param)
                elif c.Second == _XAXIS_ID:
                    sign = 1 if self._numeric_coords[p1_id][1] >= 0 else -1
                    append(p1[1] - sign * param)

            elif typ == "Distance" and param is not None and p1:
                if c.Second == _YAXIS_ID and c.SecondPos == 0:
                    sign = 1 if self._numeric_coords[p1_id][0] >= 0 else -1
                    append(p1[0] - sign * param)
                elif c.Second == _XAXIS_ID and c.SecondPos == 0:
                    sign = 1 if self._numeric_coords[p1_id][1] >= 0 else -1
                    append(p1[1] - sign * param)
                elif p2 and p1_id and p2_id:
                    dx = self._numeric_coords[p2_id][0] - self._numeric_coords[p1_id][0]
                    dy = self._numeric_coords[p2_id][1] - self._numeric_coords[p1_id][1]

                    if abs(dy) < 1e-4:
                        sign = 1 if dx >= 0 else -1
                        append(p2[0] - p1[0] - sign * param)
                    elif abs(dx) < 1e-4:
                        sign = 1 if dy >= 0 else -1
                        append(p2[1] - p1[1] - sign * param)
                    else:
                        append((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2 - param**2)

            elif typ == "Equal" and c.First >= 0 and c.Second >= 0:
                s1 = self._point_expr(self._resolve_pt(c.First, 1), symbols)
                e1 = self._point_expr(self._resolve_pt(c.First, 2), symbols)
                s2 = self._point_expr(self._resolve_pt(c.Second, 1), symbols)
                e2 = self._point_expr(self._resolve_pt(c.Second, 2), symbols)
                if s1 and e1 and s2 and e2:
                    append(
                        (e1[0] - s1[0]) ** 2
                        + (e1[1] - s1[1]) ** 2
                        - (e2[0] - s2[0]) ** 2
                        - (e2[1] - s2[1]) ** 2
                    )

            elif typ == "Symmetric" and p1 and p2:
                third = getattr(c, "Third", _GEO_NONE)
                third_pos = getattr(c, "ThirdPos", 0)
                if third in (_XAXIS_ID, _YAXIS_ID):
                    if third == _XAXIS_ID:
                        append(p1[1] + p2[1])
                        append(p1[0] - p2[0])
                    else:
                        append(p1[0] + p2[0])
                        append(p1[1] - p2[1])
                elif third_pos:
                    p3 = self._point_expr(self._resolve_pt(third, third_pos), symbols)
                    if p3:
                        append(2 * p3[0] - p1[0] - p2[0])
                        append(2 * p3[1] - p1[1] - p2[1])

            elif typ == "Angle" and param is not None:
                # Fast linear/quadratic angle projection:
                # v1 . v2 - |v1|_num * |v2|_num * cos(theta) = 0
                if c.First >= 0 and c.Second >= 0:
                    s1 = self._point_expr(self._resolve_pt(c.First, 1), symbols)
                    e1 = self._point_expr(self._resolve_pt(c.First, 2), symbols)
                    s2 = self._point_expr(self._resolve_pt(c.Second, 1), symbols)
                    e2 = self._point_expr(self._resolve_pt(c.Second, 2), symbols)

                    s1_id = self._resolve_pt(c.First, 1)
                    e1_id = self._resolve_pt(c.First, 2)
                    s2_id = self._resolve_pt(c.Second, 1)
                    e2_id = self._resolve_pt(c.Second, 2)

                    if s1 and e1 and s2 and e2 and s1_id and e1_id and s2_id and e2_id:
                        v1_num = (
                            self._numeric_coords[e1_id][0]
                            - self._numeric_coords[s1_id][0],
                            self._numeric_coords[e1_id][1]
                            - self._numeric_coords[s1_id][1],
                        )
                        v2_num = (
                            self._numeric_coords[e2_id][0]
                            - self._numeric_coords[s2_id][0],
                            self._numeric_coords[e2_id][1]
                            - self._numeric_coords[s2_id][1],
                        )
                        l1_val = math.hypot(*v1_num)
                        l2_val = math.hypot(*v2_num)

                        if l1_val > 1e-6 and l2_val > 1e-6:
                            dot_num = v1_num[0] * v2_num[0] + v1_num[1] * v2_num[1]
                            sign_cos = 1 if dot_num >= 0 else -1

                            v1 = (e1[0] - s1[0], e1[1] - s1[1])
                            v2 = (e2[0] - s2[0], e2[1] - s2[1])
                            dot_expr = v1[0] * v2[0] + v1[1] * v2[1]

                            # Degree 2 instead of degree 8: solves instantly
                            append(
                                dot_expr
                                - sign_cos
                                * (l1_val * l2_val)
                                * sympy.cos(param * sympy.pi / 180)
                            )

        return equations

    # ------------------------------------------------------------------
    # Hybrid Elimination
    # ------------------------------------------------------------------
    def _choose_root(
        self,
        roots: list[Any],
        target: sympy.Symbol,
        substitutions: dict[sympy.Symbol, Any],
    ) -> Any:
        """Use FreeCAD's solved coordinate to select the symbolic branch."""
        name = str(target)
        axis, point = name.split("_", 1)
        coord_index = 0 if axis == "x" else 1
        target_num = self._numeric_coords.get(
            point,
            (0.0, 0.0),
        )[coord_index]

        best = roots[0]
        best_err = float("inf")

        param_subs = {
            symbol: self.parameters[name]
            for name, symbol in self.param_symbols.items()
            if name in self.parameters
        }

        for root in roots:
            try:
                value_expr = root.subs(substitutions)

                # Only substitute dimensional parameters here.
                value_expr = value_expr.subs(param_subs)

                value = float(value_expr.evalf())
                err = abs(value - target_num)

                if err < best_err:
                    best = root
                    best_err = err

            except Exception:  # noqa: BLE001, S112
                continue

        return best

    @staticmethod
    def _unknowns(expr: Any, point_vars: set[sympy.Symbol]) -> list[sympy.Symbol]:
        return [s for s in expr.free_symbols if s in point_vars]

    # ------------------------------------------------------------------
    # Hybrid Elimination
    # ------------------------------------------------------------------
    def _build_components(
        self,
        equations: list[Any],
        point_vars: set[sympy.Symbol],
    ) -> list[set[sympy.Symbol]]:
        """Build connected variable components without symbolic solving.

        Variables are connected when they occur in the same equation.
        This lets SymPy work on small independent systems instead of the
        complete sketch.
        """
        parent: dict[sympy.Symbol, sympy.Symbol] = {v: v for v in point_vars}

        def find(v: sympy.Symbol) -> sympy.Symbol:
            root = v
            while parent[root] != root:
                root = parent[root]

            while parent[v] != v:
                nxt = parent[v]
                parent[v] = root
                v = nxt

            return root

        def union(a: sympy.Symbol, b: sympy.Symbol) -> None:
            ra = find(a)
            rb = find(b)
            if ra != rb:
                parent[rb] = ra

        for eq in equations:
            vars_in_eq = [s for s in eq.free_symbols if s in point_vars]

            if len(vars_in_eq) > 1:
                first = vars_in_eq[0]
                for other in vars_in_eq[1:]:
                    union(first, other)

        components: dict[sympy.Symbol, set[sympy.Symbol]] = {}

        for var in point_vars:
            root = find(var)
            components.setdefault(root, set()).add(var)

        return list(components.values())

    @staticmethod
    def _equations_for_component(
        equations: list[Any],
        component: set[sympy.Symbol],
        point_vars: set[sympy.Symbol],
    ) -> list[Any]:
        """Return only equations that actually touch this component."""
        result: list[Any] = []

        for eq in equations:
            vars_in_eq = {s for s in eq.free_symbols if s in point_vars}

            if vars_in_eq & component:
                result.append(eq)

        return result

    def _anchor_component(
        self,
        component: set[sympy.Symbol],
        solved: dict[sympy.Symbol, Any],
    ) -> None:
        """Anchor one unresolved coordinate using FreeCAD's numeric solution."""
        unresolved = [v for v in component if v not in solved]

        if not unresolved:
            return

        # Prefer an x coordinate as the anchor because it tends to give
        # simpler propagation for horizontal/vertical constraints.
        unresolved.sort(key=lambda v: (0 if str(v).startswith("x_") else 1, str(v)))

        target = unresolved[0]
        name = str(target)

        try:
            axis, point = name.split("_", 1)
        except ValueError:
            return

        coord_index = 0 if axis == "x" else 1
        numeric = self._numeric_coords.get(point, (0.0, 0.0))

        # Keep a modest precision. The value is only an anchor used by
        # symbolic elimination, not the final numeric geometry.
        solved[target] = sympy.Float(round(numeric[coord_index], 6))

    def _solve_component(
        self,
        equations: list[Any],
        component: set[sympy.Symbol],
        point_vars: set[sympy.Symbol],
        solved: dict[sympy.Symbol, Any],
    ) -> None:
        """Solve one connected symbolic component conservatively."""
        if not component:
            return

        component_eqs = self._equations_for_component(
            equations,
            component,
            point_vars,
        )

        if not component_eqs:
            return

        component_solved: dict[sympy.Symbol, Any] = {}

        # --------------------------------------------------------------
        # 1. Local linear solve
        #
        # IMPORTANT:
        # Only variables in this component are passed to linsolve.
        # --------------------------------------------------------------
        linear_eqs: list[Any] = []

        for eq in component_eqs:
            eq_sub = eq.subs(solved)

            vars_in_eq = {
                s for s in eq_sub.free_symbols if s in component and s not in solved
            }

            if not vars_in_eq:
                continue

            try:
                poly = eq_sub.as_poly(*list(vars_in_eq))
                if poly is not None and poly.total_degree() <= 1:
                    linear_eqs.append(eq_sub)
            except Exception:  # noqa: BLE001, S112
                continue

        if linear_eqs:
            local_vars = sorted(
                {
                    s
                    for eq in linear_eqs
                    for s in eq.free_symbols
                    if s in component and s not in solved
                },
                key=str,
            )

            if local_vars:
                try:
                    result = sympy.linsolve(
                        linear_eqs,
                        local_vars,
                    )

                    if result:
                        sol_tuple = next(iter(result))

                        for var, expr in zip(local_vars, sol_tuple):
                            if expr == var:
                                continue

                            # Never keep SymPy-generated free parameters
                            # such as tau0. They cannot be emitted to ASY.
                            invalid_symbols = [
                                s
                                for s in expr.free_symbols
                                if s not in point_vars
                                and s not in self.param_symbols.values()
                            ]

                            if invalid_symbols:
                                continue

                            # Do not introduce an immediate cycle.
                            if var in expr.free_symbols:
                                continue

                            component_solved[var] = expr

                except Exception:  # noqa: BLE001, S110
                    pass

        if component_solved:
            solved.update(component_solved)

        # --------------------------------------------------------------
        # 2. Incremental one-variable elimination
        #
        # Only equations in this component are considered.
        # No expand() here.
        # --------------------------------------------------------------
        max_iterations = max(4, len(component) * 2)

        for _ in range(max_iterations):
            progress = False

            for eq in component_eqs:
                try:
                    eq_sub = eq.subs(solved)

                    unknowns = [
                        s
                        for s in eq_sub.free_symbols
                        if s in component and s not in solved
                    ]

                    if len(unknowns) != 1:
                        continue

                    target = unknowns[0]

                    poly = eq_sub.as_poly(target)

                    if poly is None:
                        continue

                    degree = poly.degree()

                    # Never hand high-degree equations to solve().
                    if degree is None or degree > 2:
                        continue

                    roots = sympy.solve(
                        eq_sub,
                        target,
                        dict=False,
                        simplify=False,
                        check=False,
                    )

                    if not roots:
                        continue

                    chosen = self._choose_root(
                        roots,
                        target,
                        solved,
                    )

                    if chosen is None:
                        continue

                    if target in chosen.free_symbols:
                        continue

                    solved[target] = chosen
                    progress = True

                except Exception:  # noqa: BLE001, S112
                    continue

            if not progress:
                break

        # --------------------------------------------------------------
        # 3. If still unresolved, anchor ONE variable and propagate.
        #
        # FreeCAD provides the correct branch/orientation. The anchor
        # supplies the missing numerical datum without asking SymPy to
        # solve the complete nonlinear system.
        # --------------------------------------------------------------
        unresolved = component - set(solved)

        if unresolved:
            self._anchor_component(
                component,
                solved,
            )

        # --------------------------------------------------------------
        # 4. Propagate again after anchoring.
        # --------------------------------------------------------------
        if component - set(solved):
            max_iterations = max(4, len(component) * 2)

            for _ in range(max_iterations):
                progress = False

                for eq in component_eqs:
                    try:
                        eq_sub = eq.subs(solved)

                        unknowns = [
                            s
                            for s in eq_sub.free_symbols
                            if s in component and s not in solved
                        ]

                        if len(unknowns) != 1:
                            continue

                        target = unknowns[0]

                        poly = eq_sub.as_poly(target)

                        if poly is None or poly.degree() > 2:
                            continue

                        roots = sympy.solve(
                            eq_sub,
                            target,
                            dict=False,
                            simplify=False,
                            check=False,
                        )

                        if not roots:
                            continue

                        chosen = self._choose_root(
                            roots,
                            target,
                            solved,
                        )

                        if chosen is None:
                            continue

                        if target in chosen.free_symbols:
                            continue

                        solved[target] = chosen
                        progress = True

                    except Exception:  # noqa: BLE001, S112
                        continue

                if not progress:
                    break

    def _solve_general_system(self) -> None:
        constraints = list(getattr(self.sketch_obj, "Constraints", []))

        con_param_map = self._make_parameters(constraints)
        symbols = self._point_symbols()

        point_vars = {v for pair in symbols.values() for v in pair}

        equations = self._equations(
            constraints,
            symbols,
            con_param_map,
        )

        solved: dict[sympy.Symbol, Any] = {}

        # --------------------------------------------------------------
        # Phase 1:
        # Build connected components BEFORE doing any expensive solving.
        # --------------------------------------------------------------
        components = self._build_components(
            equations,
            point_vars,
        )

        # --------------------------------------------------------------
        # Phase 2:
        # Solve each independent component locally.
        # --------------------------------------------------------------
        for component in components:
            self._solve_component(
                equations,
                component,
                point_vars,
                solved,
            )

        # --------------------------------------------------------------
        # Phase 3:
        # A few cheap global substitutions.
        #
        # No simplify(), expand(), or global solve().
        # --------------------------------------------------------------
        for _ in range(3):
            changed = False

            for var in list(solved):
                expr = solved[var]

                try:
                    new_expr = expr.subs(solved)
                except Exception:  # noqa: BLE001, S112
                    continue

                if new_expr == expr:
                    continue

                # Avoid introducing cyclic substitutions.
                if var in new_expr.free_symbols:
                    continue

                solved[var] = new_expr
                changed = True

            if not changed:
                break

        # --------------------------------------------------------------
        # Phase 4:
        # Emit closed-form coordinate expressions.
        # --------------------------------------------------------------
        for point, (xs, ys) in symbols.items():
            x = self._closed_expression(
                solved.get(xs),
                point_vars,
            )
            y = self._closed_expression(
                solved.get(ys),
                point_vars,
            )

            if x is None:
                self.unsolved_points.add(point)
                x_str = draw._to_str(self._numeric_coords[point][0])
            else:
                x_str = self._expr_to_asy(x)

            if y is None:
                self.unsolved_points.add(point)
                y_str = draw._to_str(self._numeric_coords[point][1])
            else:
                y_str = self._expr_to_asy(y)

            self.point_solutions[point] = (
                x_str,
                y_str,
            )

        # --------------------------------------------------------------
        # Phase 5:
        # Parameter usage tracking.
        # --------------------------------------------------------------
        for name in self.param_symbols:
            used = False

            pattern = re.compile(rf"\b{re.escape(name)}\b")

            for x_str, y_str in self.point_solutions.values():
                if pattern.search(x_str) or pattern.search(y_str):
                    used = True
                    break

            if not used:
                for value in self.radius_params.values():
                    if pattern.search(value):
                        used = True
                        break

            if used:
                self.used_parameters.add(name)
            else:
                self.unused_parameters.add(name)

    @staticmethod
    def _closed_expression(expr: Any, point_vars: set[sympy.Symbol]) -> Any | None:
        if expr is None:
            return None
        remaining = [s for s in expr.free_symbols if s in point_vars]
        return None if remaining else expr

    # ------------------------------------------------------------------
    # Asymptote Output Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _expr_to_asy(expr: Any) -> str:
        if expr is None:
            return "0"
        if getattr(expr, "is_number", False):
            value = float(expr)
            if abs(value - round(value)) < 1e-8:
                return str(round(value))
            return draw._to_str(value)

        s = sympy.sstr(expr)
        s = s.replace("**", "^")
        s = re.sub(r"\bcos\(", "Cos(", s)
        s = re.sub(r"\bsin\(", "Sin(", s)
        s = re.sub(r"\*\s*pi\s*/\s*180", "", s)
        s = re.sub(r"\bpi\s*/\s*180\s*\*", "", s)
        return s

    def format_asymptote_definitions(self, paths_and_circles_str: str = "") -> str:
        point_lines: list[str] = []

        for coord_str, name in sorted(
            self.pairs_dict.items(),
            key=lambda item: int(item[1][1:]) if item[1][1:].isdigit() else 999999,
        ):
            if name in self.point_solutions:
                x, y = self.point_solutions[name]
                point_lines.append(f"pair {name} = ({x}, {y});\n")
            else:
                point_lines.append(f"pair {name} = {coord_str};\n")

        params: list[str] = []
        for name, value in self.parameters.items():
            if abs(value - round(value)) < 1e-8:
                value_str = str(round(value))
            else:
                value_str = draw._to_str(value)

            if name in self.unused_parameters:
                params.append(
                    f"// WARNING: FreeCAD constraint parameter '{name}' "
                    "is not used by reconstructed geometry.\n"
                )
            params.append(f"real {name} = {value_str};\n")

        parameter_section = ""
        if params:
            parameter_section = "// --- Parameters ---\n" + "".join(params) + "\n"

        points_section = "// --- Points & Coordinates ---\n" + "".join(point_lines)

        return parameter_section + points_section
