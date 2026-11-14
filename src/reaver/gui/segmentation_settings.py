"""MATLAB threshold mapping and validated GUI-only parameter editing."""
import math
from dataclasses import replace
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMessageBox
from .help import SETTING_HELP

SETTING_LABELS = {
    'averaging_filter_size': 'Averaging filter size (pixels)',
    'min_connected_component_area': 'Minimum connected-component area (pixels)',
    'wire_dilation_threshold': 'Wire dilation radius (pixels)',
    'vessel_thickness_threshold': 'Vessel thickness threshold (pixels)',
}


def round_thousandth(value):
    return math.floor(value * 1000 + .5) / 1000


def threshold_from_slider(position):
    x = position / 1000
    return round_thousandth(x if x <= .2 else 4*x-.6)


def threshold_from_text(text):
    value = float(text)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Enter a threshold from 0 to 1.')
    return round_thousandth(value)


def slider_from_threshold(value):
    return math.floor(1000 * (value if value < .2 else (value+.6)/4) + .5)


def validated_settings(params, values):
    updates = {}
    for name, label in SETTING_LABELS.items():
        value = float(values[name])
        minimum = 1 if name == 'averaging_filter_size' else 0
        integer = name != 'vessel_thickness_threshold'
        if not math.isfinite(value) or value < minimum or (integer and value != math.floor(value)):
            raise ValueError(f'{label}: enter a {"whole " if integer else ""}number of at least {minimum}.')
        updates[name] = int(value) if integer else value
    return replace(params, **updates)


class SegmentationSettingsDialog(QDialog):
    def __init__(self, params, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Segmentation Settings')
        self.params = replace(params)
        layout = QFormLayout(self)
        self.inputs = {}
        for name, label in SETTING_LABELS.items():
            field = QLineEdit(str(getattr(params,name)))
            field.setToolTip(SETTING_HELP[name])
            self.inputs[name] = field
            layout.addRow(label,field)
            layout.labelForField(field).setToolTip(SETTING_HELP[name])
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def accept(self):
        try:
            updated = validated_settings(self.params, {n:f.text() for n,f in self.inputs.items()})
        except ValueError as exc:
            QMessageBox.warning(self,'Invalid setting',str(exc))
            return
        self.params = updated
        super().accept()
