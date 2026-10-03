"""FreeCAD sketch to Asymptote exporter macro."""

from __future__ import annotations

import os
import sys

sys.path.append(os.path.dirname(__file__))

from datetime import datetime

import FreeCAD as app
import FreeCADGui as gui

try:
    from PySide2 import QtGui, QtWidgets
except ImportError:
    try:
        from PySide import QtGui, QtWidgets
    except ImportError:
        from PySide6 import QtGui, QtWidgets

import config
import draw


def clear_console_and_report() -> None:
    """Clears previous messages from the Python console and Report view."""
    main_window = gui.getMainWindow()
    if not main_window:
        return

    python_console = main_window.findChild(QtGui.QPlainTextEdit, "Python console")
    report_view = main_window.findChild(QtGui.QTextEdit, "Report view")

    if python_console:
        python_console.clear()
    if report_view:
        report_view.clear()
        report_view.show()


def main() -> None:
    clear_console_and_report()

    doc = gui.activeDocument()
    if not doc or not doc.getInEdit():
        app.Console.PrintError("Please open a document and enter sketch edit mode.\n")
        return

    sketch_obj = doc.getInEdit().Object
    if not hasattr(sketch_obj, "GeometryFacadeList"):
        app.Console.PrintError("Active object in edit mode is not a Sketch.\n")
        return

    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # noqa: DTZ005

    preamble = (
        f"\n// sketch2asy.py {config.version}\n// exported      {date}\n"
        'texpreamble("\n'
        "    \\usepackage[T2A]{fontenc}\n"
        "    \\usepackage[utf8]{inputenc}\n"
        "    \\usepackage[bulgarian]{babel}\n"
        '");\n'
        f"unitsize({config.unitsize});\n"
        "defaultpen(fontsize(12pt));\n"
        "arrowhead arh = HookHead();\n"
        "real ars = 7pt;\n"
        f"pen {config.construction_pen_name} = {config.construction_pen_color};\n\n"
        "import geometry;\n\n"
        "// Helper to draw an exact arc of ellipse using geometry.asy\n"
        "path arc_ellipse(pair Pc, real a, real b, real rot_deg, pair Ps, pair Pe, bool ccw=true) {\n"
        "    ellipse el = ellipse((point)Pc, a, b, rot_deg);\n"
        "    real a1 = degrees(Ps - Pc) - rot_deg;\n"
        "    real a2 = degrees(Pe - Pc) - rot_deg;\n"
        "    path p = (path)arc(el, a1, a2, polarconicroutine=fromCenter, direction=ccw ? CCW : CW);\n"
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
        "    parabola par = parabola((point)Pf, (point)V);\n"
        "    real axis_ang = degrees(Pf - V);\n"
        "    real a1 = degrees(Ps - Pf) - axis_ang;\n"
        "    real a2 = degrees(Pe - Pf) - axis_ang;\n"
        "    path p = arcfromfocus(par, a1, a2, direction=ccw ? CCW : CW);\n"
        "    if (length(point(p, 0) - Ps) > length(point(p, 0) - Pe)) {\n"
        "        p = reverse(p);\n"
        "    }\n"
        "    return p;\n"
        "}\n\n"
    )

    pairs_dict: dict[str, str] = {}
    chainable_elements: list[dict[str, str | None]] = []
    draw_paths = "\n// draw\n"

    for element in sketch_obj.GeometryFacadeList:
        item = draw.extract_chainable_element(element, pairs_dict)
        if item:
            chainable_elements.append(item)
        else:
            draw_paths += draw.draw_elements(element, pairs_dict)

    chains = draw.chain_composite_elements(chainable_elements)
    for subpaths, is_closed, pen in chains:
        draw_paths += draw.format_compact_chain(subpaths, is_closed, pen)

    define_pairs = "\n// pairs\n"
    for k, v in pairs_dict.items():
        define_pairs += f"pair {v} = {k};\n"

    if config.print_dot_labels:
        show_dots = "\n// show dot at each pair\n" + "".join(
            f'dot("${v.replace("P", "")}$", {v});\n' for v in pairs_dict.values()
        )
    else:
        show_dots = ""

    asy_output = f"{preamble}{define_pairs}{show_dots}{draw_paths}"

    app.Console.PrintMessage(asy_output)

    filename, _ = QtWidgets.QFileDialog.getSaveFileName(
        None, "Export Asymptote", "", "Asymptote files (*.asy)"
    )
    if filename:
        if not filename.lower().endswith(".asy"):
            filename += ".asy"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(asy_output)


if __name__ == "__main__":
    main()