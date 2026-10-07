"""Basic configuration for sketch2asy."""

from __future__ import annotations

try:
    import FreeCAD as App
except ImportError:
    App = None

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/sketch2asy"


class Config:
    def __init__(self) -> None:
        self.version: str = "2026-10-07"
        self.accuracy: int = -1
        self.decimal_places_to_round: int = 6
        self.comments_indent: int = 30

        self.unitsize: str = "1mm"
        self.construction_pen_name: str = "construction"
        self.construction_pen_color: str = "dashed + gray(0.5)"

        self.print_dot_labels: bool = False
        self.skip_construction: bool = False
        self.comment_construction: bool = False
        self.show_internal_geometry: bool = True
        self.parametric_output: bool = True
        self.load()

    def load(self) -> None:
        if App is None:
            return
        try:
            p = App.ParamGet(PARAM_PATH)
            self.accuracy = p.GetInt("accuracy", self.accuracy)
            self.unitsize = p.GetString("unitsize", self.unitsize)
            self.construction_pen_color = p.GetString(
                "construction_pen_color", self.construction_pen_color
            )
            self.print_dot_labels = p.GetBool("print_dot_labels", self.print_dot_labels)
            self.skip_construction = p.GetBool(
                "skip_construction", self.skip_construction
            )
            self.comment_construction = p.GetBool(
                "comment_construction", self.comment_construction
            )
            self.show_internal_geometry = p.GetBool(
                "show_internal_geometry", self.show_internal_geometry
            )
            self.parametric_output = p.GetBool(
                "parametric_output", self.parametric_output
            )
        except Exception:  # noqa: BLE001, S110
            pass

    def save(self) -> None:
        if App is None:
            return
        try:
            p = App.ParamGet(PARAM_PATH)
            p.SetInt("accuracy", self.accuracy)
            p.SetString("unitsize", self.unitsize)
            p.SetString("construction_pen_color", self.construction_pen_color)
            p.SetBool("print_dot_labels", self.print_dot_labels)
            p.SetBool("skip_construction", self.skip_construction)
            p.SetBool("comment_construction", self.comment_construction)
            p.SetBool("show_internal_geometry", self.show_internal_geometry)
            p.SetBool("parametric_output", self.parametric_output)
        except Exception:  # noqa: BLE001, S110
            pass


cfg = Config()
