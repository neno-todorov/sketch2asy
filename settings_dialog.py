"""GUI Settings Dialog for sketch2asy."""

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
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Asymptote - Settings")
        self.resize(360, 280)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()

        # Unitsize
        self.unit_edit = QtWidgets.QLineEdit(cfg.unitsize)
        form.addRow("Unit size (e.g. 1mm, 1pt):", self.unit_edit)

        # Accuracy
        self.acc_spin = QtWidgets.QSpinBox()
        self.acc_spin.setRange(-1, 10)
        self.acc_spin.setValue(cfg.accuracy)
        self.acc_spin.setSpecialValueText("Auto (-1)")
        form.addRow("Decimal places:", self.acc_spin)

        # Construction pen color/style
        self.pen_edit = QtWidgets.QLineEdit(cfg.construction_pen_color)
        form.addRow("Construction pen:", self.pen_edit)

        # Checkboxes
        self.cb_dots = QtWidgets.QCheckBox("Show point dots and labels ($P0$, $P1$)")
        self.cb_dots.setChecked(cfg.print_dot_labels)

        self.cb_skip_const = QtWidgets.QCheckBox("Skip construction geometry")
        self.cb_skip_const.setChecked(cfg.skip_construction)

        self.cb_comment_const = QtWidgets.QCheckBox("Comment out construction geometry")
        self.cb_comment_const.setChecked(cfg.comment_construction)

        self.cb_internal = QtWidgets.QCheckBox(
            "Show internal solver geometry (axes, hulls)"
        )
        self.cb_internal.setChecked(cfg.show_internal_geometry)

        self.cb_parametric = QtWidgets.QCheckBox(
            "Generate parametric variables and relations (experimental - may fail on complex sketches)"
        )
        self.cb_parametric.setChecked(cfg.parametric_output)

        layout.addLayout(form)
        layout.addWidget(self.cb_dots)
        layout.addWidget(self.cb_skip_const)
        layout.addWidget(self.cb_comment_const)
        layout.addWidget(self.cb_internal)
        layout.addWidget(self.cb_parametric)

        layout.addStretch()

        # Action Buttons
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.button(QtWidgets.QDialogButtonBox.Ok).setText("Export...")
        btn_box.accepted.connect(self._save_and_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _save_and_accept(self) -> None:
        cfg.unitsize = self.unit_edit.text().strip() or "1mm"
        cfg.accuracy = self.acc_spin.value()
        cfg.construction_pen_color = (
            self.pen_edit.text().strip() or "dashed + gray(0.5)"
        )
        cfg.print_dot_labels = self.cb_dots.isChecked()
        cfg.skip_construction = self.cb_skip_const.isChecked()
        cfg.comment_construction = self.cb_comment_const.isChecked()
        cfg.show_internal_geometry = self.cb_internal.isChecked()
        cfg.parametric_output = self.cb_parametric.isChecked()
        cfg.save()
        self.accept()
