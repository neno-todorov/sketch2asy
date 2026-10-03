"""FreeCAD sketch to asymptote. Open this file with FreeCAD go to View > Panels > Report view to see the output"""

import os
import sys

sys.path.append(os.path.dirname(__file__))
# Do not move these imports before the line above
from datetime import datetime

import FreeCAD as app
import FreeCADGui as gui
from PySide import QtGui, QtWidgets

import config
import draw

# Clear previous messages from python console and report view
main_window = gui.getMainWindow()
python_console = main_window.findChild(QtGui.QPlainTextEdit, "Python console")
report_view = main_window.findChild(QtGui.QTextEdit, "Report view")

python_console.clear()
report_view.clear()
report_view.show()

config.accuracy = -1
config.comment_construction = False
config.print_dot_labels = False
config.comments_indent = 30
config.skip_construction = False
config.construction_pen_name = "construction"
config.construction_pen_color = "lightblue"


def main() -> None:
    date = datetime.now().strftime("%Y-%m-%d - %H:%M:%S")  # noqa: DTZ005
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
        f"pen {config.construction_pen_name} = {config.construction_pen_color};\n\n"
        "import geometry;\n\n"
        "// Helper to draw an exact arc of ellipse using geometry.asy (without M @ el abort)\n"
        "path arc_ellipse(pair Pc, real a, real b, real rot_deg, pair Ps, pair Pe, bool ccw=true) {\n"
        "    ellipse el = ellipse((point)Pc, a, b, rot_deg);\n"
        "    real a1 = degrees(Ps - Pc) - rot_deg;\n"
        "    real a2 = degrees(Pe - Pc) - rot_deg;\n"
        "    // Explicitly use fromCenter to avoid the fromFocus angle shift\n"
        "    path p = (path)arc(el, a1, a2, polarconicroutine=fromCenter, direction=ccw ? CCW : CW);\n"
        "    // Ensure path starts at Ps and ends at Pe\n"
        "    if (length(point(p, 0) - Ps) > length(point(p, 0) - Pe)) {\n"
        "        p = reverse(p);\n"
        "    }\n"
        "    return p;\n"
        "}\n\n"
        "// Helper to draw an exact arc of hyperbola using geometry.asy\n"
        "path arc_hyperbola(pair Pc, real a, real b, real rot_deg, pair Ps, pair Pe, bool ccw=true) {\n"
        "    hyperbola h = hyperbola((point)Pc, a, b, rot_deg);\n"
        "    real a1 = degrees(Ps - Pc) - rot_deg;\n"
        "    real a2 = degrees(Pe - Pc) - rot_deg;\n"
        "    path p = arcfromcenter(h, a1, a2, direction=ccw ? CCW : CW);\n"
        "    if (length(point(p, 0) - Ps) > length(point(p, 0) - Pe)) {\n"
        "        p = reverse(p);\n"
        "    }\n"
        "    return p;\n"
        "}\n\n"
        "// Helper to draw an exact arc of parabola using geometry.asy\n"
        "path arc_parabola(pair Pf, pair V, pair Ps, pair Pe, bool ccw=true) {\n"
        "    parabola p = parabola((point)Pf, (point)V);\n"
        "    real axis_ang = degrees(Pf - V);\n"
        "    real a1 = degrees(Ps - Pf) - axis_ang;\n"
        "    real a2 = degrees(Pe - Pf) - axis_ang;\n"
        "    path p = arcfromfocus(p, a1, a2, direction=ccw ? CCW : CW);\n"
        "    if (length(point(p, 0) - Ps) > length(point(p, 0) - Pe)) {\n"
        "        p = reverse(p);\n"
        "    }\n"
        "    return p;\n"
        "}\n\n"
    )

    define_pairs = "\n// pairs\n"
    draw_paths = "\n// draw\n"
    show_dots = "\n// show dot at each pair\n/*\n"

    doc = gui.activeDocument()
    if not doc or not doc.getInEdit():
        app.Console.PrintError("Please open a document and enter sketch edit mode.\n")
        return
    else:
        SKETCH = gui.activeDocument().getInEdit().Object
        pairs_dict: dict[str, str] = {}
        draw_paths: str = ""
        chainable_elements = []

        for element in SKETCH.GeometryFacadeList:
            # Try extracting open curve (Line, Arc, open B-Spline)
            item = draw.extract_chainable_element(element, pairs_dict)
            if item:
                chainable_elements.append(item)
            else:
                # Full circles, ellipses, points are drawn directly
                draw_paths += draw.draw_elements(element, pairs_dict)

        # Chain connected curves together and output them
        chains = draw.chain_composite_elements(chainable_elements)
        for subpaths, is_closed, pen in chains:
            # draw_paths += draw.format_composite_chain(subpaths, is_closed, pen)
            draw_paths += draw.format_compact_chain(subpaths, is_closed, pen)

        for k, v in pairs_dict.items():
            define_pairs += f"pair {v} = {k};\n"
            show_dots += f'dot("${v}$", {v});\n'

        show_dots += "*/\n"

        if config.print_dot_labels:
            show_dots = "\n// show dot at each pair\n" + "".join(
                f'dot("${v}$", {v});\n' for v in pairs_dict.values()
            )
        else:
            show_dots = ""

        asy_output = "".join(i for i in [preamble, define_pairs, show_dots, draw_paths])
        app.Console.PrintMessage(asy_output)

        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            None, "Export Asymptote", "", "Asymptote files (*.asy)"
        )
        if filename:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(asy_output)


if __name__ == "__main__":
    main()
