"""Settings Dialog for sketch2asy."""

from __future__ import annotations

try:
    # pyrefly: ignore [missing-import]
    from PySide2 import QtWidgets
except ImportError:
    try:
        # pyrefly: ignore [missing-import]
        from PySide import QtWidgets
    except ImportError:
        from PySide6 import QtWidgets

from config import cfg


class SettingsDialog(QtWidgets.QDialog):
    """Configuration dialog for sketch2asy export options."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("sketch2asy Settings")
        self.resize(360, 320)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.spin_accuracy = QtWidgets.QSpinBox()
        self.spin_accuracy.setRange(-1, 12)
        self.spin_accuracy.setValue(cfg.accuracy)
        self.spin_accuracy.setToolTip(
            "-1 for auto (:g format), >= 0 for fixed precision"
        )
        form.addRow("Accuracy:", self.spin_accuracy)

        self.edit_unitsize = QtWidgets.QLineEdit(cfg.unitsize)
        form.addRow("Unit size:", self.edit_unitsize)

        self.edit_pen_color = QtWidgets.QLineEdit(cfg.construction_pen_color)
        form.addRow("Construction pen:", self.edit_pen_color)

        self.chk_parametric = QtWidgets.QCheckBox("Enable Parametric Output (SymPy)")
        self.chk_parametric.setChecked(cfg.parametric_output)
        form.addRow(self.chk_parametric)

        self.chk_dot_labels = QtWidgets.QCheckBox("Print Dot Labels")
        self.chk_dot_labels.setChecked(cfg.print_dot_labels)
        form.addRow(self.chk_dot_labels)

        self.chk_skip_construction = QtWidgets.QCheckBox("Skip Construction Lines")
        self.chk_skip_construction.setChecked(cfg.skip_construction)
        form.addRow(self.chk_skip_construction)

        self.chk_comment_construction = QtWidgets.QCheckBox(
            "Comment Out Construction Lines"
        )
        self.chk_comment_construction.setChecked(cfg.comment_construction)
        form.addRow(self.chk_comment_construction)

        self.chk_show_internal = QtWidgets.QCheckBox("Show Internal Geometry")
        self.chk_show_internal.setChecked(cfg.show_internal_geometry)
        form.addRow(self.chk_show_internal)

        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save_and_accept(self) -> None:
        cfg.accuracy = self.spin_accuracy.value()
        cfg.unitsize = self.edit_unitsize.text()
        cfg.construction_pen_color = self.edit_pen_color.text()
        cfg.parametric_output = self.chk_parametric.isChecked()
        cfg.print_dot_labels = self.chk_dot_labels.isChecked()
        cfg.skip_construction = self.chk_skip_construction.isChecked()
        cfg.comment_construction = self.chk_comment_construction.isChecked()
        cfg.show_internal_geometry = self.chk_show_internal.isChecked()
        cfg.save()
        self.accept()
