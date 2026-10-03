import FreeCAD
import numpy as np
import numpy.typing as npt
import Part
import Sketcher

import config
from coordinates import get_coordinates


def draw_line_segment(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    # path pair p1 -- pair p2;
    pen = _get_pen(element)
    p1 = _pair(element.Geometry.StartPoint, pairs)
    p2 = _pair(element.Geometry.EndPoint, pairs)
    path = f"{p1}--{p2}"
    comment = _get_length(element)

    return _draw(path, pen=pen, comment=comment)


def draw_circle(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    # path circle(pair c, real r);
    pen = _get_pen(element)
    c = _pair(element.Geometry.Center, pairs)
    r = _to_str(element.Geometry.Radius)
    path = f"circle({c}, {r})"

    return _draw(path, pen=pen)


def draw_ellipse(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    # path shift(pair c)*rotate(angle)*scale(real a, real b)*unitcircle;
    pen = _get_pen(element)
    c = _pair(element.Geometry.Location, pairs)
    a = _to_str(element.Geometry.MajorRadius)
    b = _to_str(element.Geometry.MinorRadius)
    angle = _to_str(np.rad2deg(element.Geometry.AngleXU))
    path = f"shift({c})*rotate({angle})*scale({a}, {b})*unitcircle"

    return _draw(path, pen=pen)


def draw_arc_of_circle(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    # path arc(pair c, real r, real angle1, real angle2);
    # path arc(pair c, explicit pair z1, explicit pair z2, bool direction=CCW)
    pen = _get_pen(element)
    c = _pair(element.Geometry.Location, pairs)
    z1 = _pair(element.Geometry.StartPoint, pairs)
    z2 = _pair(element.Geometry.EndPoint, pairs)
    path = f"arc({c}, {z1}, {z2})"
    comment = _get_length(element)

    return _draw(path, pen=pen, comment=comment)


def deprecated_draw_arc_of_ellipse(
    element: Sketcher.GeometryFacade, pairs: dict[str, str]
) -> str:
    pen = _get_pen(element)
    geom = element.Geometry
    c = _pair(geom.Location, pairs)
    a = _to_str(geom.MajorRadius)
    b = _to_str(geom.MinorRadius)
    rot = _to_str(np.degrees(geom.AngleXU))
    start_deg = _to_str(np.degrees(geom.FirstParameter))
    end_deg = _to_str(np.degrees(geom.LastParameter))
    path = f"shift({c})*rotate({rot})*scale({a}, {b})*arc((0,0), 1, {start_deg}, {end_deg})"
    return _draw(path, pen=pen, comment=_get_length(element))


def deprecated_draw_b_spline_to_bezier(
    element: Sketcher.GeometryFacade, pairs: dict[str, str]
) -> str:
    # MAY NOT TAKE INTO ACCOUNT ALL POSSIBLE VARIANTS OF BEZIER CURVE
    # draw(z0..controls c0 and c1..z1);
    # draw((0,0)..controls (0,100) and (100,100)..(100,0));
    pen = _get_pen(element)
    path = _pair(element.Geometry.StartPoint, pairs)

    # geom = element.Geometry.copy()
    # if hasattr(geom, "increaseDegree") and geom.Degree < 3:
    #     geom.increaseDegree(3)

    for bezier in element.Geometry.toBezier():
        c0, c1, z1 = (_pair(p, pairs) for p in bezier.getPoles()[1:])
        path += f"..controls {c0} and {c1}..{z1}"
    comment = _get_length(element)

    return _draw(path, pen=pen, comment=comment)


def draw_b_spline_to_bezier(
    element: Sketcher.GeometryFacade, pairs: dict[str, str]
) -> str:
    # draw(z0..controls c0 and c1..z1);
    # draw((0,0)..controls (0,100) and (100,100)..(100,0));
    pen = _get_pen(element)
    path = _pair(element.Geometry.StartPoint, pairs)

    for bezier in element.Geometry.toBezier():
        try:
            p = [_pair(p, pairs) for p in bezier.getPoles()[1:]]
            if len(p) == 3:
                path += f"..controls {p[0]} and {p[1]}..{p[2]}"
            elif len(p) == 2:
                # Asymptote quadratic Bézier syntax: ..controls C..Z1
                path += f"..controls {p[0]}..{p[1]}"
            else:
                path += f"..{p[0]}"
        except ValueError as ve:
            print(str(ve))
    comment = _get_length(element)

    return _draw(path, pen=pen, comment=comment)


def draw_point(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    # pair p;
    pen = _get_pen(element)
    pnt = _pair(element.Geometry, pairs)
    line = f"dot({pnt}, {pen});" if pen is not None else f"dot({pnt});"

    if config.skip_construction and pen == config.construction_pen_name:
        return ""
    if config.comment_construction and pen == config.construction_pen_name:
        return f"// {line}\n"

    return f"{line}\n"


def _draw(path: str, pen: None | str, comment: str = "") -> str:
    # draw(path p, pen pen); // comment
    comment = f"// {comment}" if comment != "" else ""
    line = f"draw({path}, {pen});" if pen is not None else f"draw({path});"

    if config.skip_construction and pen == config.construction_pen_name:
        return ""
    if config.comment_construction and pen == config.construction_pen_name:
        return f"// {line: <{config.comments_indent}} {comment}\n"

    return f"{line: <{config.comments_indent}} {comment}\n"


def _get_pen(element: Sketcher.GeometryFacade) -> None | str:
    if element.Construction:
        return config.construction_pen_name

    return None


def _pair(
    pnt: FreeCAD.Vector | Part.Point | npt.NDArray[np.float64],
    pairs: None | dict[str, str] = None,
) -> str:
    # тази функция може да не е най-добрият вариант
    x, y = get_coordinates(pnt)
    p = f"({_to_str(x)}, {_to_str(y)})"

    if pairs is not None:
        if p not in pairs:
            pairs[p] = f"P{len(pairs)}"
        return pairs[p]

    return p


def _get_length(element: Sketcher.GeometryFacade) -> str:
    return _to_str(element.Geometry.length())


def _to_str(x: float, n_digits: None | int = None) -> str:
    acc = config.accuracy if n_digits is None else n_digits
    if acc > 0:
        return f"{round(x, acc):.{acc}f}"
    elif acc == 0:
        return str(round(x))
    return f"{round(x, config.decimal_places_to_round):g}"


def _is_ccw(start, mid, center) -> bool:
    """2D cross-product orientation test: returns True if CCW, False if CW."""
    v1 = start - center
    v2 = mid - center
    return (v1.x * v2.y - v1.y * v2.x) > 0


def _should_skip_element(element: Sketcher.GeometryFacade) -> bool:
    """Determines if an element should be ignored based on config."""
    if getattr(config, "skip_construction", False) and element.Construction:
        return True

    # Only hide internal alignment helpers (axes, control nets) if configured
    if not getattr(config, "show_internal_geometry", True):
        int_type = getattr(element, "InternalType", 0)
        if int_type not in (0, "None", "Sketcher::InternalType::None"):
            return True

    return False


def format_parabola_arc(geom, pairs: dict[str, str]) -> str:
    """Formats an ArcOfParabola using arc_parabola."""
    # Compute Focus = Location (vertex) + XAxis * Focal
    focus = FreeCAD.Vector(
        geom.Location.x + geom.XAxis.x * geom.Focal,
        geom.Location.y + geom.XAxis.y * geom.Focal,
        geom.Location.z + geom.XAxis.z * geom.Focal,
    )

    f = _pair(focus, pairs)
    v = _pair(geom.Location, pairs)  # Location is the vertex in FreeCAD
    p0 = _pair(geom.StartPoint, pairs)
    p1 = _pair(geom.EndPoint, pairs)

    # Determine rotation direction from midpoint
    mid_u = (geom.FirstParameter + geom.LastParameter) / 2.0
    mid = geom.value(mid_u)
    ccw = "true" if _is_ccw(geom.StartPoint, mid, focus) else "false"

    return f"arc_parabola({f}, {v}, {p0}, {p1}, {ccw})"


def format_ellipse_arc(geom, pairs: dict[str, str]) -> str:
    """Formats an ArcOfEllipse into arc_ellipse using geometry.asy."""
    c_pnt = getattr(geom, "Center", getattr(geom, "Location", None))
    c = _pair(c_pnt, pairs)
    a = _to_str(geom.MajorRadius)
    b = _to_str(geom.MinorRadius)
    rot_angle = (
        geom.AngleXU
        if hasattr(geom, "AngleXU")
        else np.atan2(geom.XAxis.y, geom.XAxis.x)
    )
    rot = _to_str(np.degrees(rot_angle))
    p0 = _pair(geom.StartPoint, pairs)
    p1 = _pair(geom.EndPoint, pairs)

    # Determine orientation (CCW vs CW)
    mid_u = (geom.FirstParameter + geom.LastParameter) / 2.0
    mid = geom.value(mid_u)
    ccw = "true" if _is_ccw(geom.StartPoint, mid, c_pnt) else "false"

    return f"arc_ellipse({c}, {a}, {b}, {rot}, {p0}, {p1}, {ccw})"


def format_hyperbola_arc(geom, pairs: dict[str, str]) -> str:
    """Formats an ArcOfHyperbola into arc_hyperbola using geometry.asy."""
    c_pnt = getattr(geom, "Center", getattr(geom, "Location", None))
    c = _pair(c_pnt, pairs)
    a = _to_str(geom.MajorRadius)
    b = _to_str(geom.MinorRadius)
    rot = _to_str(np.degrees(geom.AngleXU))
    p0 = _pair(geom.StartPoint, pairs)
    p1 = _pair(geom.EndPoint, pairs)

    # Determine orientation (CCW vs CW)
    mid_u = (geom.FirstParameter + geom.LastParameter) / 2.0
    mid = geom.value(mid_u)
    ccw = "true" if _is_ccw(geom.StartPoint, mid, c_pnt) else "false"

    return f"arc_hyperbola({c}, {a}, {b}, {rot}, {p0}, {p1}, {ccw})"


def draw_arc_of_parabola(
    element: Sketcher.GeometryFacade, pairs: dict[str, str]
) -> str:
    pen = _get_pen(element)
    path = format_parabola_arc(element.Geometry, pairs)
    return _draw(path, pen=pen, comment=_get_length(element))


def draw_arc_of_hyperbola(
    element: Sketcher.GeometryFacade, pairs: dict[str, str]
) -> str:
    pen = _get_pen(element)
    path = format_hyperbola_arc(element.Geometry, pairs)
    return _draw(path, pen=pen, comment=_get_length(element))


def draw_arc_of_ellipse(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    pen = _get_pen(element)
    path = format_ellipse_arc(element.Geometry, pairs)
    return _draw(path, pen=pen, comment=_get_length(element))


def extract_chainable_element(element: Sketcher.GeometryFacade, pairs: dict[str, str]):
    if _should_skip_element(element):
        return None

    geom = element.Geometry
    pen = _get_pen(element)
    geom_name = type(geom).__name__.replace("Geom", "")

    # 1. Line Segment (both regular and construction lines)
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

    # 2. Arc of Circle
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

    # 3. Arc of Ellipse
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

    # 4. Arc of Parabola
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

    # 5. Arc of Hyperbola
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

    # 6. Open B-Spline Curve
    elif geom_name == "BSplineCurve" and not geom.isPeriodic():
        p0 = _pair(geom.StartPoint, pairs)
        p1 = _pair(geom.EndPoint, pairs)
        path = p0
        for bezier in geom.toBezier():
            p = [_pair(pt, pairs) for pt in bezier.getPoles()[1:]]
            if len(p) == 3:
                path += f"..controls {p[0]} and {p[1]}..{p[2]}"
            elif len(p) == 2:
                path += f"..controls {p[0]}..{p[1]}"
            elif len(p) == 1:
                path += f"..{p[0]}"
        return {
            "start": p0,
            "end": p1,
            "fwd": path,
            "rev": f"reverse({path})",
            "pen": pen,
        }

    return None


def chain_composite_elements(elements_data: list[dict]):
    """
    Chains connected curves (lines, arcs, b-splines) into composite paths.
    """
    chains = []
    unvisited = [e for e in elements_data if e is not None]

    while unvisited:
        first = unvisited.pop(0)
        curr_subpaths = [first["fwd"]]
        start_pt = first["start"]
        end_pt = first["end"]
        curr_pen = first["pen"]
        extended = True

        while extended:
            extended = False

            # Check if current chain closed on itself
            if start_pt == end_pt and len(curr_subpaths) > 1:
                break

            for i, cand in enumerate(unvisited):
                if cand["pen"] != curr_pen:
                    continue

                # 1. Forward match at the end: ... -> end_pt == cand.start -> cand.end
                if cand["start"] == end_pt:
                    curr_subpaths.append(cand["fwd"])
                    end_pt = cand["end"]
                    unvisited.pop(i)
                    extended = True
                    break

                # 2. Reverse match at the end: ... -> end_pt == cand.end -> cand.start
                elif cand["end"] == end_pt:
                    curr_subpaths.append(cand["rev"])
                    end_pt = cand["start"]
                    unvisited.pop(i)
                    extended = True
                    break

                # 3. Prepend match at the start: cand.start -> cand.end == start_pt -> ...
                elif cand["end"] == start_pt:
                    curr_subpaths.insert(0, cand["fwd"])
                    start_pt = cand["start"]
                    unvisited.pop(i)
                    extended = True
                    break

                # 4. Prepend reverse match at the start: cand.end -> cand.start == start_pt -> ...
                elif cand["start"] == start_pt:
                    curr_subpaths.insert(0, cand["rev"])
                    start_pt = cand["end"]
                    unvisited.pop(i)
                    extended = True
                    break

        is_closed = (start_pt == end_pt) and (len(curr_subpaths) > 1)
        chains.append((curr_subpaths, is_closed, curr_pen))

    return chains


def format_composite_chain(
    subpaths: list[str], is_closed: bool, pen: None | str
) -> str:
    """Formats chained subpaths using Asymptote's & operator."""
    if not subpaths:
        return ""

    # Wrap each subpath in parentheses so operators don't conflict
    chain_str = " & ".join(f"({sp})" for sp in subpaths)
    if is_closed:
        chain_str += " & cycle"

    return _draw(chain_str, pen=pen)


def format_compact_chain(
    subpaths: list[str], is_closed: bool, pen: None | str = None
) -> str:
    """
    Formats a list of subpath strings into a compact Asymptote path:
    draw(P12 -- P13 -- P14 -- arc(P15, P14, P16, CW) -- P16 -- P12 -- cycle);
    """
    if not subpaths:
        return ""

    tokens = []
    for sp in subpaths:
        if not tokens:
            tokens.append(sp)
            continue

        prev = tokens[-1]

        # Merge consecutive lines: "A -- B" followed by "B -- C" -> "A -- B -- C"
        if " -- " in prev and " -- " in sp:
            prev_end = prev.split(" -- ")[-1]
            sp_start = sp.split(" -- ")[0]
            if prev_end == sp_start:
                sp_rest = " -- ".join(sp.split(" -- ")[1:])
                tokens[-1] = f"{prev} -- {sp_rest}"
                continue

        tokens.append(sp)

    # Join all elements with " -- "
    path_str = " -- ".join(tokens)

    if is_closed:
        path_str += " -- cycle"

    return _draw(path_str, pen=pen)


def draw_elements(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    if hasattr(element, "InternalType") and element.InternalType != "None":
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
