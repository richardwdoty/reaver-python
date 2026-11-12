"""Exercise native Qt editing on representative real images, then compare MATLAB.

Research images, intermediate masks, reports, and screenshots stay in data/tmp.
Run on Windows with the development test dependencies installed.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from scipy.io import loadmat
from generate_editing_reference import ROOT, constants, generate_reference

os.environ.setdefault('QT_QPA_PLATFORM', 'windows' if sys.platform == 'win32' else 'offscreen')
from PySide6.QtCore import Qt, QPointF, QPoint, QEvent
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QMessageBox
from reaver.gui.main_window import ReaverMainWindow
from reaver.core.wire import WIRE_FIELDS


def wait(w, app):
    deadline = time.monotonic()+120
    while w.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert w.worker is None, 'Image processing timed out'


def mouse(canvas, kind, point, button, buttons):
    QApplication.sendEvent(canvas, QMouseEvent(kind, point,
        QPointF(canvas.mapToGlobal(point.toPoint())), button, buttons, Qt.NoModifier))


def drag(canvas, start, end, button):
    mouse(canvas, QEvent.MouseButtonPress, start, button, button)
    mouse(canvas, QEvent.MouseMove, end, Qt.NoButton, button)
    mouse(canvas, QEvent.MouseButtonRelease, end, button, Qt.NoButton)


def image_point(canvas, xy):
    return canvas.origin + QPointF(xy[0]+.5, xy[1]+.5)*canvas.scale_factor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matlab', required=True)
    parser.add_argument('--matlab-root', required=True, type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'data/tmp/gui_editing')
    parser.add_argument('--image-dir', action='append', type=Path, default=[])
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    paths = [ROOT/'data/test_images/example_rgb.tif']
    for directory in args.image_dir:
        candidates = sorted(p for p in directory.iterdir() if p.suffix.lower() in ('.tif','.tiff') and not p.name.startswith('._'))
        assert candidates, f'No TIFF files in {directory}'
        paths.extend(candidates[i] for i in sorted({0,len(candidates)//2,len(candidates)-1}))
    originals = [args.matlab_root/'REAVER GUI'/name for name in ('REAVER_GUI.m','segmentImage.m','updateWire.m')]
    prototype = Path('C:/Users/Richard Doty/Box Sync/Python/REAVER')
    originals.extend(prototype/name for name in ('main.py','morph_luts.py','prototype_GUI.py') if (prototype/name).exists())
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    before_hashes = {str(path):digest(path) for path in paths+originals}
    app = QApplication.instance() or QApplication([])
    w = ReaverMainWindow()
    # Exceptions must fail this unattended verification instead of opening a dialog.
    def fail(*args):
        raise AssertionError(args[-1])
    QMessageBox.critical = fail
    w.show()
    cases, actuals, report = [], [], []
    for i, path in enumerate(paths):
        for s in w.app_state.image_states.values():
            s.dirty = False  # Allow discarding only this verification process's results.
        w.open_directory(path.parent)
        item = next(w.file_list.item(j) for j in range(w.file_list.count()) if w.file_list.item(j).text() == path.name)
        w.load_selected_image(item)
        w.app_state.params.wire_dilation_threshold = 0 if i%2 == 0 else 3
        w.segment_button.click()
        wait(w, app)
        state = w.app_state.active_image
        assert state.image_segmented
        initial = deepcopy(state.derived_layers)
        source = state.base_image.data.copy()
        canvas = w.image_label
        center = QPointF(canvas.width()/2, canvas.height()/2)
        QApplication.sendEvent(canvas, QWheelEvent(center, QPointF(canvas.mapToGlobal(center.toPoint())),
            QPoint(), QPoint(0,120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
        canvas.zoom_at(center, 3)
        drag(canvas, center, center+QPointF(25,15), Qt.MiddleButton)
        zoom = canvas.zoom
        h, width = initial.bw_2.shape
        strokes, masks = [], []
        def record(start, end, add):
            strokes.append([*start,*end,w.brush_size_spinbox.value(),int(add)])
            masks.append(state.derived_layers.bw_2.copy())
        canvas.stroke.connect(record)  # Connected after the GUI's edit handler.
        for size, start, end, button in (
            (8,(width//2-25,h//2),(width//2+25,h//2),Qt.LeftButton),
            (4,(width//2,h//2-25),(width//2,h//2+25),Qt.RightButton),
            (1,(width//2-30,h//2-25),(width//2+30,h//2+25),Qt.LeftButton)):
            w.brush_size_spinbox.setValue(size)
            drag(canvas,image_point(canvas,start),image_point(canvas,end),button)
        canvas.stroke.disconnect(record)
        assert state.wire_update_pending and w.undo_action.isEnabled()
        edited = state.derived_layers.bw_2.copy()
        w.undo_action.trigger()
        for field in WIRE_FIELDS:
            np.testing.assert_array_equal(getattr(state.derived_layers,field),getattr(initial,field))
        # Replay the same pixel events and verify Undo did not change the view.
        assert canvas.zoom == zoom
        for x1,y1,x2,y2,size,add in strokes:
            w.brush_size_spinbox.setValue(size)
            w.paint_stroke((x1,y1),(x2,y2),bool(add))
        np.testing.assert_array_equal(state.derived_layers.bw_2,edited)
        cases.append(dict(name=str(path),binary=initial.bw_2,strokes=np.array(strokes,dtype=float),constants=constants(w.app_state.params)))
        w.update_wire_action.trigger()
        wait(w,app)
        updated = deepcopy(state.derived_layers)
        actuals.append((masks,updated))
        assert not w.update_wire_action.isEnabled() and w.undo_action.isEnabled()
        w.update_current_wire()
        assert w.worker is None
        w.display_mode_combo.setCurrentIndex(w.display_mode_combo.findData('wire_frame'))
        assert not canvas.editable and w.current_display_array is not None
        w.display_mode_combo.setCurrentIndex(w.display_mode_combo.findData('overlay'))
        if i == 0:
            app.processEvents()
            w.grab().save(str(output/'editing_preview.png'))
        w.undo_action.trigger()
        for field in WIRE_FIELDS:
            np.testing.assert_array_equal(getattr(state.derived_layers,field),getattr(initial,field))
        np.testing.assert_array_equal(state.base_image.data,source)
        w.fit_action.trigger()
        assert canvas.zoom == 1
        report.append(dict(image=str(path),shape=list(initial.bw_2.shape),stroke_segments=len(strokes),
            changed_pixels=int(np.count_nonzero(initial.bw_2 != edited)),
            wire_dilation_threshold=w.app_state.params.wire_dilation_threshold,
            binary_pixels_removed_by_update=int(np.count_nonzero(edited & ~updated.bw_2)),
            workflow='passed'))
        print(path.name+': GUI workflow passed',flush=True)
    for s in w.app_state.image_states.values():
        s.dirty = False
    w.close()
    reference = loadmat(generate_reference(cases,output,args.matlab,args.matlab_root),simplify_cells=True)
    for entry,(masks,updated),expected in zip(report,actuals,reference['results']):
        for actual,mask in zip(masks,expected['masks']):
            np.testing.assert_array_equal(actual,mask)
        for py,mat in [('bw_2','BW_2'),('wire','wire'),('dilated_wire','dilated'),('dilated_wire_2','dilated2')]:
            np.testing.assert_array_equal(getattr(updated,py),expected['updated'][mat])
        for name in ('branchpoints','endpoints'):
            np.testing.assert_array_equal(getattr(updated,name),np.asarray(expected['updated'][name]['coords']).reshape(-1,2)-1)
        entry['matlab_parity'] = 'exact for every brush segment, final mask, wire, dilations, and point coordinates'
        print(Path(entry['image']).name+': MATLAB EXACT',flush=True)
    assert before_hashes == {str(path):digest(path) for path in paths+originals}
    (output/'report.json').write_text(json.dumps(dict(matlab_version=reference['matlab_version'],
        cases=report,originals_unchanged=True,source_sha256=before_hashes),indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
