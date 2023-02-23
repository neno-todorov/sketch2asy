"""FreeCAD sketch to asymptote. Open this file with FreeCAD go to View > Panels > Report view to see the output"""

import os
import sys
from datetime import datetime
from typing import Dict

import FreeCAD as app
import FreeCADGui as gui
import Part
import Sketcher

sys.path.append(os.path.dirname(__file__))

import config
import draw

config.accuracy = -1
config.comment_construction = False
config.print_dot_labels = False
config.comments_indent = 30
config.skip_construction = False
config.construction_pen_name = "construction"
config.construction_pen_color = "lightblue"


def draw_elements(element: Sketcher.GeometryFacade, pairs: Dict[str, str]) -> str:
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


def main() -> None:
    date = datetime.now().strftime("%Y-%m-%d - %H:%M:%S")
    preamble = (
        f"\n// sketch2asy.py {config.version}\n// exported      {date}\n"
        'texpreamble("\n'
        "    \\usepackage[T2A]{fontenc}\n"
        "    \\usepackage[utf8]{inputenc}\n"
        "    \\usepackage[bulgarian]{babel}\n"
        '");\n'
        "unitsize(1pt);\n"
        "defaultpen(fontsize(12pt));\n"
        "arrowhead arh = HookHead();\n"
        "real ars = 7pt;\n"
        f"pen {config.construction_pen_name} = {config.construction_pen_color};\n"
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

        if not config.print_dot_labels:
            show_dots = ""

        asy_output = "".join(i for i in [preamble, define_pairs, show_dots, draw_paths])
        app.Console.PrintMessage(asy_output)


if __name__ == "__main__":
    main()
