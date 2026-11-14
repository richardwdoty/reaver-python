"""Compare GUI regional drawing with a committed full renderer on copied data."""
import argparse
from copy import deepcopy
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np
import tifffile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
os.environ.setdefault('QT_QPA_PLATFORM', 'windows' if sys.platform == 'win32' else 'offscreen')
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox
from reaver.app import preferences
from reaver.gui.main_window import ReaverMainWindow
from reaver.io.results import load_analysis, save_analysis
from reaver.io.image_export import export_displayed_image
from reaver.core.wire import update_wire


def reference(ref, path, package):
    code = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{ref}:{path}'], text=True)
    namespace = {'__package__': package}
    exec(compile(code, path, 'exec'), namespace)
    return namespace


def equal_layers(actual, expected):
    for field in fields(actual):
        np.testing.assert_array_equal(getattr(actual, field.name), getattr(expected, field.name), err_msg=field.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference-ref', default='91ca257', help='Commit before regional rendering')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    preferences.settings_store = lambda: QSettings(str(args.output/'preferences.ini'), QSettings.IniFormat)
    old_render = reference(args.reference_ref, 'src/reaver/gui/image_viewer.py', 'reaver.gui')['render_view']
    old_edit = reference(args.reference_ref, 'src/reaver/core/editing.py', 'reaver.core')
    app = QApplication.instance() or QApplication([])
    errors = []
    QMessageBox.critical = lambda *a: errors.append(a[-1])
    report = []
    for index, path in enumerate(args.analysis):
        loaded = load_analysis(path)
        hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (path, loaded.path)}
        folder = args.output/str(index)
        folder.mkdir()
        source = folder/loaded.path.name
        shutil.copyfile(loaded.path, source)
        loaded = load_analysis(path, source)
        save_analysis(loaded)
        window = ReaverMainWindow()
        window.show()
        window.open_directory(folder)
        window.file_list.setCurrentRow(0)
        state = window.app_state.active_image
        expected = deepcopy(state)
        h, w = state.derived_layers.bw_2.shape
        checks = 0
        for mode, gamma, channels in [('overlay', False, (True,True,True)),
                                      ('overlay', True, (True,False,True)),
                                      ('segmented', False, (True,True,True)),
                                      ('overlay', False, (False,True,True))]:
            window.display_mode_combo.setCurrentIndex(window.display_mode_combo.findData(mode))
            window.gamma_action.setChecked(gamma)
            for checkbox, checked in zip(window.display_channel_checkboxes, channels):
                checkbox.setChecked(checked)
            settings = window.app_state.display_settings
            settings.edge_line_color = (129,0,53)
            settings.center_line_color = (0,130,205)
            window.refresh_current_display_image()
            for step in range(18):
                start, end = [((0,0),(8,8)), ((w-1,h-1),(w-8,h-8)),
                              ((300,300),(320,312)), ((-4,-3),(w+4,h+3))][step%4]
                size = (1,4,16)[step%3]
                add = step%2 == 0
                window.brush_size_spinbox.setValue(size)
                window.paint_stroke(start, end, add)
                old_edit['paint_segment'](expected, start, end, size, add)
                equal_layers(state.derived_layers, expected.derived_layers)
                np.testing.assert_array_equal(window.current_display_array,
                    old_render(expected, mode, channels, settings=settings))
                checks += 1
            exported = export_displayed_image(source, window.current_display_array)
            np.testing.assert_array_equal(tifffile.imread(exported), old_render(expected, mode, channels, settings=settings))
        window.update_current_wire()
        deadline = time.monotonic()+120
        while window.worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        assert window.worker is None and not errors, errors
        update_wire(expected, expected.params)
        equal_layers(state.derived_layers, expected.derived_layers)
        np.testing.assert_array_equal(window.current_display_array, old_render(expected, 'overlay', channels, settings=settings))
        window.undo_current_edit()
        old_edit['undo_edit'](expected)
        equal_layers(state.derived_layers, expected.derived_layers)
        np.testing.assert_array_equal(window.current_display_array, old_render(expected, 'overlay', channels, settings=settings))
        state.dirty = False
        state.wire_update_pending = False
        window.close()
        assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p,digest in hashes.items())
        report.append(dict(image=source.name, comparisons=checks, pixel_parity='exact', exports=4,
                           wire_update_and_undo='exact', originals_unchanged=True))
    (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
