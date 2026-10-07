"""Asymptote drawing, formatting, and polyline chaining routines."""

from __future__ import annotations

import math
from typing import Any

try:
    # pyrefly: ignore [missing-import]
    from FreeCAD import Sketcher
except ImportError:
    Sketcher = None

from config import cfg
from coordinates import get_coordinates


class GeometryTracker:
    """Tracks which conic helpers are needed in the Asymptote preamble."""

    def __init__(self) -> None:
        self.has_ellipse_arc: bool = False
        self.has_hyperbola_arc: bool = False
        self.has_parabola_arc: bool = False

    def reset(self) -> None:
        self.has_ellipse_arc = False
        self.has_hyperbola_arc = False
        self.has_parabola_arc = False


tracker = GeometryTracker()


def _to_str(x: float, n_digits: int | None = None) -> str:
    """Formats float to string, normalizing negative zeros (-0.0 -> 0.0)."""
    acc = cfg.accuracy if n_digits is None else n_digits
    if acc > 0:
        val = round(x, acc)
        return f"{0.0 if val == 0 else val:.{acc}f}"
    elif acc == 0:
        val = round(x)
        return str(0 if val == 0 else int(val))

    val = round(x, cfg.decimal_places_to_round)
    return f"{0.0 if val == 0 else val:g}"


def _pair(pnt: Any, pairs: dict[str, str] | None = None) -> str:
    """Registers coordinates and returns Asymptote identifier (e.g. P0)."""
    x, y = get_coordinates(pnt)
    p = f"({_to_str(x)}, {_to_str(y)})"

    if pairs is not None:
        if p not in pairs:
            pairs[p] = f"P{len(pairs)}"
        return pairs[p]
    return p


def _get_pen(element: Any) -> str | None:
    if getattr(element, "Construction", False):
        return cfg.construction_pen_name
    return None


def _get_length(element: Any) -> str:
    try:
        geom = getattr(element, "Geometry", element)
        return f"len = {_to_str(geom.length(), 2)}"
    except Exception:  # noqa: BLE001
        return ""


def _draw(path: str, pen: str | None = None, comment: str = "") -> str:
    comment_str = f"// {comment}" if comment else ""
    line = f"draw({path}, {pen});" if pen is not None else f"draw({path});"

    if cfg.skip_construction and pen == cfg.construction_pen_name:
        return ""
    if cfg.comment_construction and pen == cfg.construction_pen_name:
        return f"// {line: <{cfg.comments_indent}} {comment_str}\n"

    return f"{line: <{cfg.comments_indent}} {comment_str}\n"


def _is_ccw(start: Any, mid: Any, center: Any) -> bool:
    sx, sy = get_coordinates(start)
    mx, my = get_coordinates(mid)
    cx, cy = get_coordinates(center)
    return ((sx - cx) * (my - cy) - (sy - cy) * (mx - cx)) > 0


def _should_skip_element(element: Any) -> bool:
    if getattr(cfg, "skip_construction", False) and getattr(
        element, "Construction", False
    ):
        return True
    if not getattr(cfg, "show_internal_geometry", True):
        int_type = getattr(element, "InternalType", 0)
        if int_type not in (0, "None", "Sketcher::InternalType::None"):
            return True
    return False


def _bspline_to_bezier_path(geom: Any, pairs: dict[str, str]) -> str:
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


def format_ellipse_arc(geom: Any, pairs: dict[str, str]) -> str:
    tracker.has_ellipse_arc = True
    c_pnt = getattr(geom, "Center", getattr(geom, "Location", None))
    c = _pair(c_pnt, pairs)
    a = _to_str(geom.MajorRadius)
    b = _to_str(geom.MinorRadius)
    rot_angle = (
        geom.AngleXU
        if hasattr(geom, "AngleXU")
        else math.atan2(geom.XAxis.y, geom.XAxis.x)
    )
    rot = _to_str(math.degrees(rot_angle))
    p0 = _pair(geom.StartPoint, pairs)
    p1 = _pair(geom.EndPoint, pairs)

    mid = geom.value((geom.FirstParameter + geom.LastParameter) / 2.0)
    ccw = "true" if _is_ccw(geom.StartPoint, mid, c_pnt) else "false"
    return f"arc_ellipse({c}, {a}, {b}, {rot}, {p0}, {p1}, {ccw})"


def format_hyperbola_arc(geom: Any, pairs: dict[str, str]) -> str:
    tracker.has_hyperbola_arc = True
    c_pnt = getattr(geom, "Center", getattr(geom, "Location", None))
    c = _pair(c_pnt, pairs)
    a = _to_str(geom.MajorRadius)
    b = _to_str(geom.MinorRadius)
    rot_angle = (
        geom.AngleXU
        if hasattr(geom, "AngleXU")
        else math.atan2(geom.XAxis.y, geom.XAxis.x)
    )
    rot = _to_str(math.degrees(rot_angle))
    p0 = _pair(geom.StartPoint, pairs)
    p1 = _pair(geom.EndPoint, pairs)

    mid = geom.value((geom.FirstParameter + geom.LastParameter) / 2.0)
    ccw = "true" if _is_ccw(geom.StartPoint, mid, c_pnt) else "false"
    return f"arc_hyperbola({c}, {a}, {b}, {rot}, {p0}, {p1}, {ccw})"


def format_parabola_arc(geom: Any, pairs: dict[str, str]) -> str:
    tracker.has_parabola_arc = True
    focus = (
        geom.Location.x + geom.XAxis.x * geom.Focal,
        geom.Location.y + geom.XAxis.y * geom.Focal,
        geom.Location.z + geom.XAxis.z * geom.Focal,
    )
    f = _pair(focus, pairs)
    v = _pair(geom.Location, pairs)
    p0 = _pair(geom.StartPoint, pairs)
    p1 = _pair(geom.EndPoint, pairs)

    mid = geom.value((geom.FirstParameter + geom.LastParameter) / 2.0)
    ccw = "true" if _is_ccw(geom.StartPoint, mid, focus) else "false"
    return f"arc_parabola({f}, {v}, {p0}, {p1}, {ccw})"


def draw_line_segment(element: Any, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    geom = getattr(element, "Geometry", element)
    p0 = _pair(geom.StartPoint, pairs)
    p1 = _pair(geom.EndPoint, pairs)
    return _draw(f"{p0} -- {p1}", pen=pen, comment=_get_length(element))


def draw_point(element: Any, pairs: dict[str, str]) -> str:
    if _should_skip_element(element):
        return ""
    pen = _get_pen(element)
    geom = getattr(element, "Geometry", element)
    pnt = _pair(geom, pairs)
    line = f"dot({pnt}, {pen});" if pen is not None else f"dot({pnt});"
    if cfg.comment_construction and pen == cfg.construction_pen_name:
        return f"// {line}\n"
    return f"{line}\n"


def draw_circle(
    element: Any,
    pairs: dict[str, str],
    radius_param: str | None = None,
) -> str:
    pen = _get_pen(element)
    geom = getattr(element, "Geometry", element)
    c = _pair(geom.Location, pairs)
    r = radius_param if radius_param else _to_str(geom.Radius)
    return _draw(f"circle({c}, {r})", pen=pen, comment=_get_length(element))


def draw_ellipse(element: Any, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    geom = getattr(element, "Geometry", element)
    c = _pair(geom.Location, pairs)
    a = _to_str(geom.MajorRadius)
    b = _to_str(geom.MinorRadius)
    rot_angle = (
        geom.AngleXU
        if hasattr(geom, "AngleXU")
        else math.atan2(geom.XAxis.y, geom.XAxis.x)
    )
    rot = _to_str(math.degrees(rot_angle))
    return _draw(
        f"shift({c})*rotate({rot})*scale({a}, {b})*unitcircle",
        pen=pen,
        comment=_get_length(element),
    )


def draw_arc_of_circle(element: Any, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    geom = getattr(element, "Geometry", element)
    c = _pair(geom.Location, pairs)
    p0 = _pair(geom.StartPoint, pairs)
    p1 = _pair(geom.EndPoint, pairs)
    return _draw(f"arc({c}, {p0}, {p1})", pen=pen, comment=_get_length(element))


def draw_arc_of_ellipse(element: Any, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    geom = getattr(element, "Geometry", element)
    return _draw(
        format_ellipse_arc(geom, pairs),
        pen=pen,
        comment=_get_length(element),
    )


def draw_arc_of_parabola(element: Any, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    geom = getattr(element, "Geometry", element)
    return _draw(
        format_parabola_arc(geom, pairs),
        pen=pen,
        comment=_get_length(element),
    )


def draw_arc_of_hyperbola(element: Any, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    geom = getattr(element, "Geometry", element)
    return _draw(
        format_hyperbola_arc(geom, pairs),
        pen=pen,
        comment=_get_length(element),
    )


def draw_b_spline_to_bezier(element: Any, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    geom = getattr(element, "Geometry", element)
    return _draw(
        _bspline_to_bezier_path(geom, pairs),
        pen=pen,
        comment=_get_length(element),
    )


def draw_elements(
    element: Any,
    pairs: dict[str, str],
    radius_params: dict[int, str] | None = None,
    geo_id: int | None = None,
) -> str:
    if _should_skip_element(element):
        return ""

    geom = getattr(element, "Geometry", element)
    geom_name = type(geom).__name__.replace("Geom", "")

    rad_param = (
        radius_params.get(geo_id) if (radius_params and geo_id is not None) else None
    )

    if geom_name == "Circle":
        return draw_circle(element, pairs, radius_param=rad_param)

    draw_map = {
        "LineSegment": draw_line_segment,
        "Point": draw_point,
        "Ellipse": draw_ellipse,
        "ArcOfCircle": draw_arc_of_circle,
        "ArcOfEllipse": draw_arc_of_ellipse,
        "ArcOfParabola": draw_arc_of_parabola,
        "ArcOfHyperbola": draw_arc_of_hyperbola,
        "BSplineCurve": draw_b_spline_to_bezier,
    }

    if geom_name in draw_map:
        return draw_map[geom_name](element, pairs)

    return f"// {geom_name} is not implemented yet.\n"


def extract_chainable_element(
    element: Any, pairs: dict[str, str]
) -> dict[str, str | None] | None:
    if _should_skip_element(element):
        return None

    geom = getattr(element, "Geometry", element)
    pen = _get_pen(element)
    geom_name = type(geom).__name__.replace("Geom", "")

    if geom_name == "LineSegment":
        p0 = _pair(geom.StartPoint, pairs)
        p1 = _pair(geom.EndPoint, pairs)
        return {
            "start": p0,
            "end": p1,
            "fwd": f"{p0} -- {p1}",
            "rev": f"{p1} -- {p0}",
            "pen": pen,
        }

    elif geom_name == "ArcOfCircle":
        c = _pair(geom.Location, pairs)
        p0 = _pair(geom.StartPoint, pairs)
        p1 = _pair(geom.EndPoint, pairs)
        return {
            "start": p0,
            "end": p1,
            "fwd": f"arc({c}, {p0}, {p1})",
            "rev": f"arc({c}, {p1}, {p0}, CW)",
            "pen": pen,
        }

    elif geom_name == "ArcOfEllipse":
        p0 = _pair(geom.StartPoint, pairs)
        p1 = _pair(geom.EndPoint, pairs)
        subpath = format_ellipse_arc(geom, pairs)
        return {
            "start": p0,
            "end": p1,
            "fwd": subpath,
            "rev": f"reverse({subpath})",
            "pen": pen,
        }

    elif geom_name == "ArcOfParabola":
        p0 = _pair(geom.StartPoint, pairs)
        p1 = _pair(geom.EndPoint, pairs)
        subpath = format_parabola_arc(geom, pairs)
        return {
            "start": p0,
            "end": p1,
            "fwd": subpath,
            "rev": f"reverse({subpath})",
            "pen": pen,
        }

    elif geom_name == "ArcOfHyperbola":
        p0 = _pair(geom.StartPoint, pairs)
        p1 = _pair(geom.EndPoint, pairs)
        subpath = format_hyperbola_arc(geom, pairs)
        return {
            "start": p0,
            "end": p1,
            "fwd": subpath,
            "rev": f"reverse({subpath})",
            "pen": pen,
        }

    elif geom_name == "BSplineCurve" and not geom.isPeriodic():
        p0 = _pair(geom.StartPoint, pairs)
        p1 = _pair(geom.EndPoint, pairs)
        path = _bspline_to_bezier_path(geom, pairs)
        return {
            "start": p0,
            "end": p1,
            "fwd": path,
            "rev": f"reverse({path})",
            "pen": pen,
        }

    return None


def chain_composite_elements(
    elements_data: list[dict[str, str | None]],
) -> list[tuple[list[str], bool, str | None]]:
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


def format_compact_chain(
    subpaths: list[str], is_closed: bool, pen: str | None = None
) -> str:
    if not subpaths:
        return ""

    tokens: list[str] = []
    for sp in subpaths:
        if not tokens:
            tokens.append(sp)
            continue

        prev = tokens[-1]
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
        start_pt = tokens[0].split(" -- ")[0] if tokens else ""
        if start_pt and path_str.endswith(f" -- {start_pt}"):
            path_str = path_str[: -len(f" -- {start_pt}")]
        path_str += " -- cycle"

    return _draw(path_str, pen=pen)
