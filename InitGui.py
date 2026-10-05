"""FreeCAD Sketch2Asy Workbench - Init file"""

CMD_NAME = "Sketch2Asy_Export"
MENU_TEXT = "Sketch2Asy"
TOOLTIP_TEXT = "Export FreeCAD sketches to Asymptote"

# pyrefly: ignore [missing-import]
import FreeCAD as App

# pyrefly: ignore [missing-import]
import FreeCADGui as Gui

# pyrefly: ignore [missing-import]
from FreeCADGui import Workbench


def auto_inject_to_sketcher() -> None:
    """Automatically adds the button to the Sketcher workbench toolbar in user.cfg."""
    try:
        param_path = "User parameter:BaseApp/Workbench/SketcherWorkbench/Toolbar/Custom_Sketch2Asy"
        p = App.ParamGet(param_path)
        p.SetString(CMD_NAME, "")
        p.SetBool("Active", True)
    except Exception as e:  # noqa: BLE001
        print(e)


# 1. Inject the toolbar button into Sketcher
auto_inject_to_sketcher()


class Sketch2AsyWB(Workbench):
    """Sketch2Asy Workbench definition."""

    def __init__(self):
        import os

        import sketch2asy

        self.__class__.MenuText = MENU_TEXT
        self.__class__.ToolTip = TOOLTIP_TEXT

        icon_path = os.path.join(os.path.dirname(sketch2asy.__file__), "sketch2asy.svg")
        if os.path.exists(icon_path):
            self.__class__.Icon = icon_path

    def Initialize(self):
        """Executed when the workbench is activated."""
        # import sketch2asy

        self.command_list = [CMD_NAME]
        self.appendToolbar(MENU_TEXT, self.command_list)
        self.appendMenu(MENU_TEXT, self.command_list)

    def Activated(self):
        return

    def Deactivated(self):
        return

    def ContextMenu(self, recipient):
        self.appendContextMenu(MENU_TEXT, self.command_list)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(Sketch2AsyWB())
