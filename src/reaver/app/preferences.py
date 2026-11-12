"""Per-user defaults, separate from each analysis's saved settings."""
import math
from PySide6.QtCore import QSettings


def settings_store():
    return QSettings(QSettings.IniFormat, QSettings.UserScope, 'REAVER', 'REAVER')


def load_default_resolution():
    try:
        value = float(settings_store().value('calibration/default_um_per_pixel', 1.0))
        return value if math.isfinite(value) and value > 0 else 1.0
    except (TypeError, ValueError):
        return 1.0


def save_default_resolution(value):
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Calibration must be positive and finite')
    store = settings_store()
    store.setValue('calibration/default_um_per_pixel', value)
    store.sync()
    if store.status() != QSettings.NoError:
        raise OSError('Could not remember the default calibration')
