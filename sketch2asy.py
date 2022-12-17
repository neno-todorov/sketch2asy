"""FreeCAD sketch to asymptote. Open this file with FreeCAD go to View > Panels > Report view to see the output"""

from datetime import datetime

import FreeCAD as app
import FreeCADGui as gui
import Part
import Sketcher

import config
import draw

config.ACCURACY = 1
config.COMMENT_CONSTRUCTION = 0
config.PRINT_DOT_LABELS = 0
config.COMMENTS_INDENT = 25
config.SKIP_CONSTRUCTION = 0
config.CONSTRUCTION_PEN_NAME = "construction"
config.CONSTRUCTION_PEN_COLOR = "lightblue"


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
        f"\n// sketch2asy.py {config.VERSION}\n// exported      "
        f"{date}\nunitsize(1pt);\n"
        f"pen {config.CONSTRUCTION_PEN_NAME} = {config.CONSTRUCTION_PEN_COLOR};\n"
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

        if not config.PRINT_DOT_LABELS:
            show_dots = ""

        asy_output = "".join(i for i in [preamble, define_pairs, show_dots, draw_paths])
        app.Console.PrintMessage(asy_output)


if __name__ == "__main__":
    main()
