from typing import Dict, Optional

import FreeCAD
import Part
import Sketcher
import numpy

import config
from coordinates import get_coordinates


def draw_line_segment(element: Sketcher.GeometryFacade, pairs: Dict[str, str]) -> str:
    # path pair p1 -- pair p2;
    pen = _get_pen(element)
    p1 = _pair(element.Geometry.StartPoint, pairs)
    p2 = _pair(element.Geometry.EndPoint, pairs)
    path = f"{p1}--{p2}"
    comment = _get_length(element)

    return _draw(path, pen=pen, comment=comment)


def draw_circle(element: Sketcher.GeometryFacade, pairs: Dict[str, str]) -> str:
    # path circle(pair c, real r);
    pen = _get_pen(element)
    c = _pair(element.Geometry.Center, pairs)
    r = _to_str(element.Geometry.Radius)
    path = f"circle({c}, {r})"

    return _draw(path, pen=pen)


def draw_ellipse(element: Sketcher.GeometryFacade, pairs: Dict[str, str]) -> str:
    # path shift(pair c)*rotate(angle)*scale(real a, real b)*unitcircle;
    pen = _get_pen(element)
    c = _pair(element.Geometry.Location, pairs)
    a = _to_str(element.Geometry.MajorRadius)
    b = _to_str(element.Geometry.MinorRadius)
    angle = _to_str(numpy.rad2deg(element.Geometry.AngleXU))
    path = f"shift({c})*rotate({angle})*scale({a}, {b})*unitcircle"

    return _draw(path, pen=pen)


def draw_arc_of_circle(element: Sketcher.GeometryFacade, pairs: Dict[str, str]) -> str:
    # path arc(pair c, real r, real angle1, real angle2);
    # path arc(pair c, explicit pair z1, explicit pair z2, bool direction=CCW)
    pen = _get_pen(element)
    c = _pair(element.Geometry.Location, pairs)
    z1 = _pair(element.Geometry.StartPoint, pairs)
    z2 = _pair(element.Geometry.EndPoint, pairs)
    path = f"arc({c}, {z1}, {z2})"
    comment = _get_length(element)

    return _draw(path, pen=pen, comment=comment)


def draw_b_spline_to_bezier(element: Sketcher.GeometryFacade, pairs: Dict[str, str]) -> str:
    # draw(z0..controls c0 and c1..z1);
    # draw((0,0)..controls (0,100) and (100,100)..(100,0));
    pen = _get_pen(element)
    path = _pair(element.Geometry.StartPoint, pairs)

    for bezier in element.Geometry.toBezier():
        c0, c1, z1 = (_pair(p, pairs) for p in bezier.getPoles()[1:])
        path += f"..controls {c0} and {c1}..{z1}"
    comment = _get_length(element)

    return _draw(path, pen=pen, comment=comment)


def draw_point(element: Sketcher.GeometryFacade, pairs: Dict[str, str]) -> str:
    # pair p;
    pen = _get_pen(element)
    pnt = _pair(element.Geometry, pairs)
    line = f"dot({pnt}, {pen});" if pen is not None else f"dot({pnt});"

    if config.skip_construction and pen == config.construction_pen_name:
        return ""
    if config.comment_construction and pen == config.construction_pen_name:
        return f"// {line}\n"

    return f"{line}\n"


def _draw(path: str, pen: str, comment: str = "") -> str:
    # draw(path p, pen pen); // comment
    comment = f"// {comment}" if comment != "" else ""
    line = f"draw({path}, {pen});" if pen is not None else f"draw({path});"

    if config.skip_construction and pen == config.construction_pen_name:
        return ""
    if config.comment_construction and pen == config.construction_pen_name:
        return f"// {line: <{config.comments_indent}} {comment}\n"

    return f"{line: <{config.comments_indent}} {comment}\n"


def _get_pen(element: Sketcher.GeometryFacade) -> Optional[str]:
    if element.Construction:
        return config.construction_pen_name

    return None


def _pair(
    pnt: FreeCAD.Vector | Part.Point | numpy.ndarray,
    pairs: Optional[Dict[str, str]] = None,
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


def _to_str(x: float | int, n_digits: Optional[int] = config.accuracy) -> str:
    if n_digits > 0:
        return f"{x: .{n_digits}f}"

    return f"{x:g}"
