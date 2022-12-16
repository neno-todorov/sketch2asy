"""FreeCAD sketch to asymptote.
Open this file with FreeCAD go to View > Panels > Report view to see the output"""

import draw
import Sketcher
import Part
import FreeCAD as app
import FreeCADGui as gui
from datetime import datetime
from config import SETTINGS


SETTINGS.accuracy = 2
SETTINGS.comment_construction = 1
SETTINGS.print_dot_labels = 1
SETTINGS.comments_indent = 35
SETTINGS.construction_pen_name = "construction"
SETTINGS.skip_construction = 1


def draw_elements(element: Sketcher.GeometryFacade, pairs: dict[str, str]) -> str:
    draw_func_by_type = {
        Part.LineSegment: draw.draw_line_segment,
        Part.Point: draw.draw_point,
        Part.Circle: draw.draw_circle,
        Part.Ellipse: draw.draw_ellipse,
        Part.ArcOfCircle: draw.draw_arc_of_circle,
        Part.BSplineCurve: draw.draw_b_spline_to_bezier,
    }
    draw_func = draw_func_by_type.get(type(element.Geometry))

    if draw_func:
        return draw_func(element, pairs)

    return f"// {type(element.Geometry).__name__} is not implemented yet.\n"


def main():
    date = datetime.now().strftime("%Y-%m-%d - %H:%M:%S")
    preamble = (
        f"// sketch2asy.py {SETTINGS.version}\n// exported      "
        f"{date}\nunitsize(1pt);\n"
        f"pen {SETTINGS.construction_pen_name} = invisible;\n"
    )

    define_pairs = "\n// pairs\n"
    draw_paths = "\n// draw\n"
    show_dots = "\n// show dot at each pair\n/*\n"

    if not gui.activeDocument().getInEdit():
        msg = "A sketch needs to be in edit mode"
        app.Console.PrintError(msg)
    else:
        SKETCH = gui.activeDocument().getInEdit().Object
        pairs_dict: dict[str, str] = {}
        for element in SKETCH.GeometryFacadeList:
            draw_paths += draw_elements(element, pairs_dict)

        for k, v in pairs_dict.items():
            define_pairs += f"pair {v} = {k};\n"
            show_dots += f'dot("${v}$", {v});\n'

        show_dots += "*/\n"

        if not SETTINGS.print_dot_labels:
            show_dots = ""

        for text in [preamble, define_pairs, show_dots, draw_paths]:
            app.Console.PrintMessage(text)


if __name__ == "__main__":
    main()
