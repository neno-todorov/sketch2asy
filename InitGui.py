"""FreeCAD Sketch2Asy Workbench - Init file"""

import os

# pyrefly: ignore [missing-import]
import FreeCAD as App

# pyrefly: ignore [missing-import]
import FreeCADGui as Gui

import sketch2asy

CMD_NAME = "Sketch2Asy_Export"


def auto_inject_to_sketcher() -> None:
    try:
        param_path = "User parameter:BaseApp/Workbench/SketcherWorkbench/Toolbar/Custom_Sketch2Asy"
        p = App.ParamGet(param_path)
        p.SetString(CMD_NAME, "")
        p.SetBool("Active", True)
    except Exception:  # noqa: BLE001, S110
        pass


auto_inject_to_sketcher()


class Sketch2AsyWB(Gui.Workbench):
    def __init__(self):
        self.__class__.MenuText = "Sketch2Asy"
        self.__class__.ToolTip = "Export FreeCAD sketches to Asymptote"
        # Safe icon path using sketch2asy.__file__
        icon_path = os.path.join(os.path.dirname(sketch2asy.__file__), "sketch2asy.svg")
        if os.path.exists(icon_path):
            self.__class__.Icon = icon_path

    def Initialize(self):
        self.command_list = [CMD_NAME]
        self.appendToolbar("Sketch2Asy", self.command_list)
        self.appendMenu("Sketch2Asy", self.command_list)

    def Activated(self):
        return

    def Deactivated(self):
        return

    def ContextMenu(self, recipient):
        self.appendContextMenu("Sketch2Asy", self.command_list)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(Sketch2AsyWB())
