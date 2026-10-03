"""Asymptote geometry drawing and polyline chaining routines."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import config
from coordinates import get_coordinates

if TYPE_CHECKING:
    import Sketcher


# ----------------------------------------------------------------------
# Internal Helpers
# ----------------------------------------------------------------------

def _to_str(x: float, n_digits: int | None = None) -> str:
    """Formats a float to a clean string, normalizing -0.0 to 0.0."""
    acc = config.accuracy if n_digits is None else n_digits
    if acc > 0:
        val = round(x, acc)
        return f"{0.0 if val == 0 else val:.{acc}f}"
    elif acc == 0:
        val = round(x)
        return str(0 if val == 0 else int(val))

    val = round(x, config.decimal_places_to_round)
    return f"{0.0 if val == 0 else val:g}"


def _pair(pnt: Any, pairs: dict[str, str] | None = None) -> str:
    """Returns an Asymptote coordinate string or an identifier like P0."""
    x, y = get_coordinates(pnt)
    p = f"({_to_str(x)}, {_to_str(y)})"

    if pairs is not None:
        if p not in pairs:
            pairs[p] = f"P{len(pairs)}"
        return pairs[p]

    return p


def _get_pen(element: Sketcher.GeometryFacade) -> str | None:
    """Returns the pen name if construction geometry, otherwise None."""
    if element.Construction:
        return config.construction_pen_name
    return None


def _get_length(element: Sketcher.GeometryFacade) -> str:
    """Calculates element length for code comments."""
    try:
        length = element.Geometry.length()
        return f"len = {_to_str(length, 2)}"
    except Exception:  # noqa: BLE001
        return ""


def _draw(path: str, pen: str | None = None, comment: str = "") -> str:
    """Wraps an Asymptote path into a formatted draw() statement."""
    comment_str = f"// {comment}" if comment else ""
    line = f"draw({path}, {pen});" if pen is not None else f"draw({path});"

    if config.skip_construction and pen == config.construction_pen_name:
        return ""
    if config.comment_construction and pen == config.construction_pen_name:
        return f"// {line: <{config.comments_indent}} {comment_str}\n"

    return f"{line: <{config.comments_indent}} {comment_str}\n"


def _is_ccw(start: Any, mid: Any, center: Any) -> bool:
    """2D cross-product orientation test: returns True if CCW, False if CW."""
    sx, sy = get_coordinates(start)
    mx, my = get_coordinates(mid)
    cx, cy = get_coordinates(center)

    v1_x, v1_y = sx - cx, sy - cy
    v2_x, v2_y = mx - cx, my - cy

    return (v1_x * v2_y - v1_y * v2_x) > 0


def _should_skip_element(element: Sketcher.GeometryFacade) -> bool:
    """Determines if an element should be ignored based on configuration."""
    if getattr(config, "skip_construction", False) and element.Construction:
        return True

    if not getattr(config, "show_internal_geometry", True):
        int_type = getattr(element, "InternalType", 0)
        if int_type not in (0, "None", "Sketcher::InternalType::None"):
            return True

    return False


def _bspline_to_bezier_path(geom: Any, pairs: dict[str, str]) -> str:
    """Converts a B-Spline curve into an Asymptote Bézier path string."""
    path = _pair(geom.StartPoint, pairs)
    for bezier in geom.toBezier():
        try:
            p = [_pair(pt, pairs) for pt in bezier.getPoles()[1:]]
            if len(p) == 3:
                path += f"..controls {p[0]} and {p[1]}..{p[2]}"
            elif len(p) == 2:
                path += f"..controls {p[0]}..{p[1]}"
            elif len(p) == 1:
                path += f"..{p[0]}"
        except ValueError:
            pass
    return path


# ----------------------------------------------------------------------
# Conic Formatters
# ----------------------------------------------------------------------

def format_ellipse_arc(geom: Any, pairs: dict[str, str]) -> str:
    """Formats an ArcOfEllipse into an arc_ellipse helper call."""
    c_pnt = getattr(geom, "Center", getattr(geom, "Location", None))
    c = _pair(c_pnt, pairs)
    a = _to_str(geom.MajorRadius)
    b = _to_str(geom.MinorRadius)

    rot_angle = geom.AngleXU if hasattr(geom, "AngleXU") else math.atan2(geom.XAxis.y, geom.XAxis.x)
    rot = _to_str(math.degrees(rot_angle))

    p0 = _pair(geom.StartPoint, pairs)
    p1 = _pair(geom.EndPoint, pairs)

    mid_u = (geom.FirstParameter + geom.LastParameter) / 2.0
    mid = geom.value(mid_u)
    ccw = "true" if _is_ccw(geom.StartPoint, mid, c_pnt) else "false"

    return f"arc_ellipse({c}, {a}, {b}, {rot}, {p0}, {p1}, {ccw})"


def format_hyperbola_arc(geom: Any, pairs: dict[str, str]) -> str:
    """Formats an ArcOfHyperbola into an arc_hyperbola helper call."""
    c_pnt = getattr(geom, "Center", getattr(geom, "Location", None))
    c = _pair(c_pnt, pairs)
    a = _to_str(geom.MajorRadius)
    b = _to_str(geom.MinorRadius)
    rot = _to_str(math.degrees(geom.AngleXU))

    p0 = _pair(geom.StartPoint, pairs)
    p1 = _pair(geom.EndPoint, pairs)

    mid_u = (geom.FirstParameter + geom.LastParameter) / 2.0
    mid = geom.value(mid_u)
    ccw = "true" if _is_ccw(geom.StartPoint, mid, c_pnt) else "false"

    return f"arc_hyperbola({c}, {a}, {b}, {rot}, {p0}, {p1}, {ccw})"


def format_parabola_arc(geom: Any, pairs: dict[str, str]) -> str:
    """Formats an ArcOfParabola into an arc_parabola helper call."""
    fx = geom.Location.x + geom.XAxis.x * geom.Focal
    fy = geom.Location.y + geom.XAxis.y * geom.Focal
    fz = geom.Location.z + geom.XAxis.z * geom.Focal
    focus = (fx, fy, fz)

    f = _pair(focus, pairs)
    v = _pair(geom.Location, pairs)
    p0 = _pair(geom.StartPoint, pairs)
    p1 = _pair(geom.EndPoint, pairs)

    mid_u = (geom.FirstParameter + geom.LastParameter) / 2.0
    mid = geom.value(mid_u)
    ccw = "true" if _is_ccw(geom.StartPoint, mid, focus) else "false"

    return f"arc_parabola({f}, {v}, {p0}, {p1}, {ccw})"


# ----------------------------------------------------------------------
# Standalone Geometry Drawers
# ----------------------------------------------------------------------

def draw_line_segment(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    p0 = _pair(element.Geometry.StartPoint, pairs)
    p1 = _pair(element.Geometry.EndPoint, pairs)
    path = f"{p0} -- {p1}"
    return _draw(path, pen=pen, comment=_get_length(element))


def draw_point(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    if _should_skip_element(element):
        return ""
    pen = _get_pen(element)
    pnt = _pair(element.Geometry, pairs)
    line = f"dot({pnt}, {pen});" if pen is not None else f"dot({pnt});"
    if config.comment_construction and pen == config.construction_pen_name:
        return f"// {line}\n"
    return f"{line}\n"


def draw_circle(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    c = _pair(element.Geometry.Location, pairs)
    r = _to_str(element.Geometry.Radius)
    path = f"circle({c}, {r})"
    return _draw(path, pen=pen, comment=_get_length(element))


def draw_ellipse(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    c = _pair(element.Geometry.Location, pairs)
    a = _to_str(element.Geometry.MajorRadius)
    b = _to_str(element.Geometry.MinorRadius)
    rot_angle = element.Geometry.AngleXU if hasattr(element.Geometry, "AngleXU") else math.atan2(element.Geometry.XAxis.y, element.Geometry.XAxis.x)
    rot = _to_str(math.degrees(rot_angle))
    path = f"shift({c})*rotate({rot})*scale({a}, {b})*unitcircle"
    return _draw(path, pen=pen, comment=_get_length(element))


def draw_arc_of_circle(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    c = _pair(element.Geometry.Location, pairs)
    p0 = _pair(element.Geometry.StartPoint, pairs)
    p1 = _pair(element.Geometry.EndPoint, pairs)
    path = f"arc({c}, {p0}, {p1})"
    return _draw(path, pen=pen, comment=_get_length(element))


def draw_arc_of_ellipse(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    path = format_ellipse_arc(element.Geometry, pairs)
    return _draw(path, pen=pen, comment=_get_length(element))


def draw_arc_of_parabola(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    path = format_parabola_arc(element.Geometry, pairs)
    return _draw(path, pen=pen, comment=_get_length(element))


def draw_arc_of_hyperbola(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    path = format_hyperbola_arc(element.Geometry, pairs)
    return _draw(path, pen=pen, comment=_get_length(element))


def draw_b_spline_to_bezier(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    path = _bspline_to_bezier_path(element.Geometry, pairs)
    return _draw(path, pen=pen, comment=_get_length(element))


def draw_elements(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    """Dispatches standalone elements to their corresponding drawer function."""
    if _should_skip_element(element):
        return ""

    geom_name = type(element.Geometry).__name__.replace("Geom", "")

    draw_func_by_name = {
        "LineSegment": draw_line_segment,
        "Point": draw_point,
        "Circle": draw_circle,
        "Ellipse": draw_ellipse,
        "ArcOfCircle": draw_arc_of_circle,
        "ArcOfEllipse": draw_arc_of_ellipse,
        "ArcOfParabola": draw_arc_of_parabola,
        "ArcOfHyperbola": draw_arc_of_hyperbola,
        "BSplineCurve": draw_b_spline_to_bezier,
    }

    if geom_name in draw_func_by_name:
        return draw_func_by_name[geom_name](element, pairs)

    return f"// {geom_name} is not implemented yet.\n"


# ----------------------------------------------------------------------
# Polyline / Composite Path Chaining
# ----------------------------------------------------------------------

def extract_chainable_element(
    element: Sketcher.GeometryFacade, pairs: dict[str, str]
) -> dict[str, str | None] | None:
    """Extracts endpoint names and subpaths for elements that participate in polylines."""
    if _should_skip_element(element):
        return None

    geom = element.Geometry
    pen = _get_pen(element)
    geom_name = type(geom).__name__.replace("Geom", "")

    if geom_name == "LineSegment":
        p0 = _pair(geom.StartPoint, pairs)
        p1 = _pair(geom.EndPoint, pairs)
        return {"start": p0, "end": p1, "fwd": f"{p0} -- {p1}", "rev": f"{p1} -- {p0}", "pen": pen}

    elif geom_name == "ArcOfCircle":
        c = _pair(geom.Location, pairs)
        p0 = _pair(geom.StartPoint, pairs)
        p1 = _pair(geom.EndPoint, pairs)
        return {"start": p0, "end": p1, "fwd": f"arc({c}, {p0}, {p1})", "rev": f"arc({c}, {p1}, {p0}, CW)", "pen": pen}

    elif geom_name == "ArcOfEllipse":
        p0 = _pair(geom.StartPoint, pairs)
        p1 = _pair(geom.EndPoint, pairs)
        subpath = format_ellipse_arc(geom, pairs)
        return {"start": p0, "end": p1, "fwd": subpath, "rev": f"reverse({subpath})", "pen": pen}

    elif geom_name == "ArcOfParabola":
        p0 = _pair(geom.StartPoint, pairs)
        p1 = _pair(geom.EndPoint, pairs)
        subpath = format_parabola_arc(geom, pairs)
        return {"start": p0, "end": p1, "fwd": subpath, "rev": f"reverse({subpath})", "pen": pen}

    elif geom_name == "ArcOfHyperbola":
        p0 = _pair(geom.StartPoint, pairs)
        p1 = _pair(geom.EndPoint, pairs)
        subpath = format_hyperbola_arc(geom, pairs)
        return {"start": p0, "end": p1, "fwd": subpath, "rev": f"reverse({subpath})", "pen": pen}

    elif geom_name == "BSplineCurve" and not geom.isPeriodic():
        p0 = _pair(geom.StartPoint, pairs)
        p1 = _pair(geom.EndPoint, pairs)
        path = _bspline_to_bezier_path(geom, pairs)
        return {"start": p0, "end": p1, "fwd": path, "rev": f"reverse({path})", "pen": pen}

    return None


def chain_composite_elements(elements_data: list[dict[str, str | None]]) -> list[tuple[list[str], bool, str | None]]:
    """Groups connected curves into continuous chains by matching endpoints."""
    chains: list[tuple[list[str], bool, str | None]] = []
    unvisited = [e for e in elements_data if e is not None]

    while unvisited:
        first = unvisited.pop(0)
        curr_subpaths = [str(first["fwd"])]
        start_pt = first["start"]
        end_pt = first["end"]
        curr_pen = first["pen"]
        extended = True

        while extended:
            extended = False

            if start_pt == end_pt and len(curr_subpaths) > 1:
                break

            for i, cand in enumerate(unvisited):
                if cand["pen"] != curr_pen:
                    continue

                if cand["start"] == end_pt:
                    curr_subpaths.append(str(cand["fwd"]))
                    end_pt = cand["end"]
                    unvisited.pop(i)
                    extended = True
                    break
                elif cand["end"] == end_pt:
                    curr_subpaths.append(str(cand["rev"]))
                    end_pt = cand["start"]
                    unvisited.pop(i)
                    extended = True
                    break
                elif cand["end"] == start_pt:
                    curr_subpaths.insert(0, str(cand["fwd"]))
                    start_pt = cand["start"]
                    unvisited.pop(i)
                    extended = True
                    break
                elif cand["start"] == start_pt:
                    curr_subpaths.insert(0, str(cand["rev"]))
                    start_pt = cand["end"]
                    unvisited.pop(i)
                    extended = True
                    break

        is_closed = (start_pt == end_pt) and (len(curr_subpaths) > 1)
        chains.append((curr_subpaths, is_closed, curr_pen))

    return chains


def format_compact_chain(subpaths: list[str], is_closed: bool, pen: str | None = None) -> str:
    """Formats connected subpaths into an Asymptote statement, joining segments with '--'."""
    if not subpaths:
        return ""

    tokens: list[str] = []
    for sp in subpaths:
        if not tokens:
            tokens.append(sp)
            continue

        prev = tokens[-1]
        # Merge consecutive line segments: "A -- B" and "B -- C" -> "A -- B -- C"
        if " -- " in prev and " -- " in sp:
            prev_end = prev.split(" -- ")[-1]
            sp_start = sp.split(" -- ")[0]
            if prev_end == sp_start:
                sp_rest = " -- ".join(sp.split(" -- ")[1:])
                tokens[-1] = f"{prev} -- {sp_rest}"
                continue

        tokens.append(sp)

    path_str = " -- ".join(tokens)

    if is_closed:
        # Avoid duplicating the initial vertex before '-- cycle'
        start_pt = tokens[0].split(" -- ")[0] if tokens else ""
        if start_pt and path_str.endswith(f" -- {start_pt}"):
            path_str = path_str[: -len(f" -- {start_pt}")]
        path_str += " -- cycle"

    return _draw(path_str, pen=pen)