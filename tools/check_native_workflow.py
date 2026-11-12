"""Exercise compact persistence and GUI editing on isolated copies of real analyses."""
import argparse
from copy import deepcopy
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
os.environ.setdefault('QT_QPA_PLATFORM', 'windows' if sys.platform=='win32' else 'offscreen')
from PySide6.QtWidgets import QApplication, QMessageBox
from reaver.gui.main_window import ReaverMainWindow
from reaver.io.results import load_analysis, save_analysis, find_analysis
from reaver.io.measurement_export import directory_results_path, read_results_csv


def wait(window, app):
    deadline = time.monotonic()+180
    while window.worker is not None and time.monotonic()<deadline:
        app.processEvents(); time.sleep(.01)
    assert window.worker is None, 'Worker timed out'


def equal(a, b):
    for f in fields(a):
        np.testing.assert_array_equal(getattr(a,f.name), getattr(b,f.name), err_msg=f.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', action='append', type=Path, required=True)
    args = parser.parse_args()
    out = ROOT/'data/tmp'/('native_workflow_'+time.strftime('%Y%m%d_%H%M%S'))
    out.mkdir(parents=True)
    app = QApplication.instance() or QApplication([])
    errors = []
    QMessageBox.critical = lambda *args: errors.append(args[-1])
    QMessageBox.warning = lambda *args: errors.append(args[-1])
    hashes = {}; cases = []
    for index, original in enumerate(args.analysis):
        state = load_analysis(original)
        for path in (original, state.path):
            hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        folder = out/str(index); folder.mkdir()
        image = folder/state.path.name
        shutil.copyfile(state.path,image)
        legacy = folder/original.name
        shutil.copyfile(original,legacy)
        state = load_analysis(legacy,image)
        state.verified = False
        target = save_analysis(state)
        expected = deepcopy(state.derived_layers)
        equal(expected,load_analysis(target).derived_layers)
        initial_size = target.stat().st_size
        window = ReaverMainWindow();window.show();window.open_directory(folder)
        item = window.file_list.item(0);window.file_list.setCurrentItem(item)
        assert window.display_mode_combo.currentData() == 'overlay'
        window.verified_checkbox.setChecked(True)
        assert load_analysis(target).verified and 'Saved and verified' in item.toolTip()
        window.export_directory_action.trigger();wait(window,app)
        csv_path = directory_results_path(folder)
        assert len(read_results_csv(csv_path)) == 1 and not errors
        window.display_mode_combo.setCurrentIndex(window.display_mode_combo.findData('overlay'))
        y,x = np.argwhere(expected.bw_2)[int(expected.bw_2.sum())//2]
        window.brush_size_spinbox.setValue(4)
        window.paint_stroke((int(x),int(y)),(int(x),int(y)),False)
        assert window.app_state.active_image.wire_update_pending
        assert not window.app_state.active_image.verified and 'Unsaved changes' in item.toolTip()
        if index == 0:
            app.processEvents();window.grab().save(str(out/'pending_preview.png'))
        QMessageBox.question = lambda *args: QMessageBox.Discard
        assert window.discard_current_changes()
        assert window.app_state.active_image.verified
        equal(expected,window.app_state.active_image.derived_layers)
        window.display_mode_combo.setCurrentIndex(window.display_mode_combo.findData('overlay'))
        window.paint_stroke((int(x),int(y)),(int(x),int(y)),False)
        window.update_wire_action.trigger();wait(window,app)
        edited = deepcopy(window.app_state.active_image.derived_layers)
        assert window.save_current_analysis() and not errors
        assert read_results_csv(csv_path) == []  # Old measurements invalidated on save.
        reopened = load_analysis(target)
        equal(edited,reopened.derived_layers)
        assert not reopened.verified
        window.export_results_action.trigger();wait(window,app)
        assert len(read_results_csv(csv_path)) == 1 and not errors
        window.export_results_action.trigger();wait(window,app)
        assert len(read_results_csv(csv_path)) == 1
        window.verified_checkbox.setChecked(True)
        if index == 0:
            app.processEvents();window.grab().save(str(out/'verified_preview.png'))
        QMessageBox.question = lambda *args: QMessageBox.Yes
        assert window.delete_current_analysis() and not errors
        assert find_analysis(image) is None and legacy.exists()
        assert read_results_csv(csv_path) == []
        assert legacy.read_bytes() == original.read_bytes()
        window.close();window.deleteLater();app.processEvents()
        cases.append(dict(analysis=str(original),original_bytes=original.stat().st_size,
            compact_bytes=initial_size,all_layers_exact=True,edited_roundtrip_exact=True,
            gui_discard_verify_remove='passed',directory_csv='passed'))
        print(original.name, original.stat().st_size, '->', initial_size, 'bytes; workflow PASS', flush=True)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    (out/'report.json').write_text(json.dumps(dict(cases=cases,originals_unchanged=True,
        source_sha256=hashes),indent=2),encoding='utf-8')
    print('Report:',out/'report.json',flush=True)


if __name__ == '__main__':
    main()
