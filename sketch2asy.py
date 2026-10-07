"""FreeCAD Sketch to Asymptote Exporter Macro / Command."""

from __future__ import annotations

import os
import sys

sys.path.append(os.path.dirname(__file__))

from datetime import datetime

# pyrefly: ignore [missing-import]
import FreeCAD as App

# pyrefly: ignore [missing-import]
import FreeCADGui as Gui

try:
    # pyrefly: ignore [missing-import]
    from PySide2 import QtWidgets
except ImportError:
    try:
        # pyrefly: ignore [missing-import]
        from PySide import QtWidgets
    except ImportError:
        from PySide6 import QtWidgets

from typing import Any

import draw
from config import cfg
from parametric import ParametricModel
from settings_dialog import SettingsDialog


def get_target_sketch() -> Any | None:
    """Finds active sketch in edit mode or selected in the tree."""
    doc = Gui.activeDocument()
    if doc and doc.getInEdit():
        obj = doc.getInEdit().Object
        if hasattr(obj, "GeometryFacadeList"):
            return obj

    # Fallback to selected object in the tree view
    selection = Gui.Selection.getSelection()
    if selection:
        for sel in selection:
            if hasattr(sel, "GeometryFacadeList"):
                return sel

    return None


def build_preamble(date_str: str) -> str:
    """Builds preamble, conditionally adding Asymptote helpers only if needed."""
    preamble = (
        f"// sketch2asy.py {cfg.version}\n"
        f"// exported      {date_str}\n\n"
        'texpreamble("\n'
        "    \\usepackage[T2A]{fontenc}\n"
        "    \\usepackage[utf8]{inputenc}\n"
        "    \\usepackage[bulgarian]{babel}\n"
        '");\n\n'
        f"unitsize({cfg.unitsize});\n"
        "defaultpen(fontsize(12pt));\n"
        "arrowhead arh = HookHead();\n"
        "real ars = 7pt;\n"
        f"pen {cfg.construction_pen_name} = {cfg.construction_pen_color};\n\n"
    )

    needs_geometry = (
        draw.tracker.has_ellipse_arc
        or draw.tracker.has_hyperbola_arc
        or draw.tracker.has_parabola_arc
    )

    if needs_geometry:
        preamble += "import geometry;\n\n"

    if draw.tracker.has_ellipse_arc:
        preamble += (
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
        )

    if draw.tracker.has_hyperbola_arc:
        preamble += (
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
        )

    if draw.tracker.has_parabola_arc:
        preamble += (
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

    return preamble


def export_sketch(sketch_obj: Any) -> None:
    draw.tracker.reset()

    pairs_dict: dict[str, str] = {}
    chainable_elements: list[dict[str, str | None]] = []
    standalone_paths = ""

    # Check if user enabled parametric export
    is_parametric = getattr(cfg, "parametric_output", True)

    model = None
    radius_params = {}
    if is_parametric:
        try:
            model = ParametricModel(sketch_obj, pairs_dict)
            radius_params = model.radius_params
        except Exception as e:  # noqa: BLE001
            App.Console.PrintError(f"Parametric solver fallback: {e}\n")
            model = None
            radius_params = {}

    # Process sketch geometry
    for geo_id, element in enumerate(sketch_obj.GeometryFacadeList):
        item = draw.extract_chainable_element(element, pairs_dict)
        if item:
            chainable_elements.append(item)
        else:
            standalone_paths += draw.draw_elements(
                element, pairs_dict, radius_params=radius_params, geo_id=geo_id
            )

    # Chain polylines
    chained_paths = ""
    chains = draw.chain_composite_elements(chainable_elements)
    for subpaths, is_closed, pen in chains:
        chained_paths += draw.format_compact_chain(subpaths, is_closed, pen)

    # Generate point block and prune dead parameters
    if is_parametric and model:
        draw_section = (
            "\n// --- Geometry Paths ---\n" + chained_paths + standalone_paths
        )
        define_section = model.format_asymptote_definitions(
            paths_and_circles_str=draw_section
        )
    else:
        define_section = "// --- Points & Coordinates ---\n"
        for coord_str, name in sorted(
            pairs_dict.items(),
            key=lambda i: int(i[1][1:]) if i[1][1:].isdigit() else 999999,
        ):
            define_section += f"pair {name} = {coord_str};\n"
        draw_section = (
            "\n// --- Geometry Paths ---\n" + chained_paths + standalone_paths
        )

    # Dot labels
    show_dots = ""
    if cfg.print_dot_labels:
        show_dots = "\n// --- Dots & Labels ---\n"
        for name in pairs_dict.values():
            show_dots += f'dot("${name}$", {name});\n'

    # Preamble & Paths
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # noqa: DTZ005
    preamble = build_preamble(date_str)
    draw_section = "\n// --- Geometry Paths ---\n" + chained_paths + standalone_paths

    asy_output = f"{preamble}\n{define_section}{show_dots}\n{draw_section}"
    App.Console.PrintMessage(asy_output)

    # Save Dialog
    doc = sketch_obj.Document
    doc_dir = (
        os.path.dirname(doc.FileName)
        if doc and doc.FileName
        else os.path.expanduser("~")
    )
    sketch_name = getattr(sketch_obj, "Label", getattr(sketch_obj, "Name", "Sketch"))
    default_filename = os.path.join(doc_dir, f"{sketch_name}.asy")

    filename, _ = QtWidgets.QFileDialog.getSaveFileName(
        None, "Export Asymptote", default_filename, "Asymptote files (*.asy)"
    )

    if filename:
        if not filename.lower().endswith(".asy"):
            filename += ".asy"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(asy_output)
        App.Console.PrintMessage(f"\nSuccessfully exported to {filename}\n")


def main() -> None:
    sketch_obj = get_target_sketch()
    if not sketch_obj:
        App.Console.PrintError("Please edit or select a Sketch before exporting.\n")
        return

    # Show Settings Dialog
    dlg = SettingsDialog()
    if dlg.exec_() == QtWidgets.QDialog.Accepted:
        export_sketch(sketch_obj)


# FreeCAD Command Registration
class Sketch2AsyCommand:
    """FreeCAD GUI Command to run sketch2asy."""

    def GetResources(self) -> dict[str, str]:
        icon_path = os.path.join(os.path.dirname(__file__), "sketch2asy.svg")
        return {
            "Pixmap": icon_path if os.path.exists(icon_path) else "",
            "MenuText": "Export Sketch to Asymptote",
            "ToolTip": "Exports the active or selected Sketch to Asymptote (.asy) format",
        }

    def Activated(self) -> None:
        main()

    def IsActive(self) -> bool:
        return get_target_sketch() is not None


# Register the command into FreeCAD's command manager
if hasattr(Gui, "addCommand"):
    Gui.addCommand("Sketch2Asy_Export", Sketch2AsyCommand())

if __name__ == "__main__":
    main()
