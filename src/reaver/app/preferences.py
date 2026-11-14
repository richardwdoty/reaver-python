"""Per-user defaults, separate from each analysis's saved settings."""
import math
from PySide6.QtCore import QSettings, QByteArray


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


def load_measurement_layout():
    store = settings_store()
    floating = str(store.value('measurements/floating', 'true')).lower() != 'false'
    try:
        area = int(store.value('measurements/dock_area', 2))
        width = int(store.value('measurements/dock_width', 390))
    except (TypeError, ValueError):
        area, width = 2, 390
    geometry = store.value('measurements/floating_geometry', QByteArray())
    return dict(floating=floating, area=area if area in (1,2,4,8) else 2,
                width=max(350,min(width,2000)),
                geometry=geometry if isinstance(geometry,QByteArray) else QByteArray())


def save_measurement_layout(floating, area, width, geometry):
    store = settings_store()
    for key, value in dict(floating=bool(floating), dock_area=int(area),
                           dock_width=int(width), floating_geometry=geometry).items():
        store.setValue('measurements/'+key,value)
    store.sync()
    if store.status() != QSettings.NoError:
        raise OSError('Could not remember the measurements window layout')
