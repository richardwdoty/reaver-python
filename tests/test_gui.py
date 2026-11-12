import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
import numpy as np
import pytest
import tifffile
from PySide6.QtWidgets import QApplication, QMessageBox
from reaver.gui.main_window import ReaverMainWindow
from reaver.gui.image_viewer import render_view
from copy import deepcopy
from pathlib import Path
from PySide6.QtCore import Qt, QPointF, QPoint, QEvent
from PySide6.QtGui import QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog


def mouse(canvas, kind, position, button, buttons):
    event = QMouseEvent(kind, QPointF(position), QPointF(canvas.mapToGlobal(position.toPoint())),
                        button, buttons, Qt.NoModifier)
    QApplication.sendEvent(canvas, event)


def drag(canvas, start, end, button):
    mouse(canvas, QEvent.MouseButtonPress, start, button, button)
    mouse(canvas, QEvent.MouseMove, end, Qt.NoButton, button)
    mouse(canvas, QEvent.MouseButtonRelease, end, button, Qt.NoButton)


def image_point(canvas, x, y):
    return canvas.origin + QPointF(x+.5, y+.5)*canvas.scale_factor


def wheel(canvas, position, delta=120, modifiers=Qt.NoModifier):
    event = QWheelEvent(position, QPointF(canvas.mapToGlobal(position.toPoint())),
                        QPoint(), QPoint(0,delta), Qt.NoButton, modifiers, Qt.NoScrollPhase, False)
    QApplication.sendEvent(canvas, event)


@pytest.fixture
def window(monkeypatch):
    app = QApplication.instance() or QApplication([])
    w = ReaverMainWindow()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Discard)
    yield w, app
    if w.worker is not None:
        w.worker.wait(30000)
        app.processEvents()
    w.close()
    w.deleteLater()
    app.processEvents()


def wait_for_worker(w, app):
    deadline = time.monotonic() + 30
    while w.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert w.worker is None


def test_gui_segmentation_and_all_views(window, tmp_path):
    w, app = window
    image = np.zeros((96, 128, 3), np.uint8)
    image[20:45, :, 0] = 255
    image[:, 40:70, 0] = 255
    for name in ('a.tif', 'b.tif'):
        tifffile.imwrite(tmp_path/name, image, photometric='rgb')
    w.open_directory(tmp_path)
    w.load_selected_image(w.file_list.item(0))
    w.display_mode_combo.setCurrentIndex(w.display_mode_combo.findData('wire_frame'))
    assert w.current_display_array is None
    w.segment_button.click()
    assert not w.open_action.isEnabled()
    wait_for_worker(w, app)
    state = w.app_state.active_image
    assert state.image_segmented and state.dirty
    layers = state.derived_layers
    for _, mode in w.DISPLAY_MODE_OPTIONS:
        w.display_mode_combo.setCurrentIndex(w.display_mode_combo.findData(mode))
        assert w.current_display_array is not None
        assert w.current_display_array.dtype == np.uint8
        assert not w.image_label.pixmap().isNull()
    for mode, field in [('segmented', 'bw_2'), ('first_binary', 'bw_1')]:
        np.testing.assert_array_equal(render_view(state, mode), getattr(layers, field).astype(np.uint8)*255)
    w.display_channel_checkboxes[0].setChecked(False)
    np.testing.assert_array_equal(state.base_image.data, image)
    w.load_selected_image(w.file_list.item(1))
    w.load_selected_image(w.file_list.item(0))
    assert w.app_state.active_image.derived_layers is layers


def test_grayscale_uint16_and_channel_controls(window, tmp_path):
    w, app = window
    tifffile.imwrite(tmp_path/'gray.tif', np.full((32, 48), 32768, np.uint16))
    w.open_directory(tmp_path)
    w.load_selected_image(w.file_list.item(0))
    assert np.all(w.current_display_array == 128)
    assert not any(c.isEnabled() for c in w.segmentation_channel_checkboxes)
    w.segment_button.click()
    wait_for_worker(w, app)
    assert w.app_state.active_image.derived_layers.gray.shape == (32, 48)


def test_worker_failure_restores_controls(window, tmp_path, monkeypatch):
    w, app = window
    tifffile.imwrite(tmp_path/'gray.tif', np.zeros((32, 48), np.uint8))
    w.open_directory(tmp_path)
    w.load_selected_image(w.file_list.item(0))
    messages = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *args: messages.append(args[-1]))
    w.app_state.params.averaging_filter_size = -1
    w.segment_button.click()
    wait_for_worker(w, app)
    assert messages and w.open_action.isEnabled() and w.sidebar.isEnabled()
    assert not w.app_state.active_image.image_segmented


def test_real_image_edit_update_undo_workflow(window):
    w, app = window
    w.show()
    w.open_directory(Path(__file__).resolve().parents[1]/'data/test_images')
    w.load_selected_image(w.file_list.item(0))
    w.segment_button.click()
    wait_for_worker(w, app)
    canvas = w.image_label
    state = w.app_state.active_image
    original = deepcopy(state.derived_layers)
    base = state.base_image.data.copy()
    h, width = original.bw_2.shape
    assert canvas.editable and not w.update_wire_action.isEnabled()
    center = QPointF(canvas.width()/2, canvas.height()/2)
    anchor = canvas.pixel_at(center)
    wheel(canvas, center)
    assert canvas.zoom == pytest.approx(10/9)
    assert canvas.pixel_at(center) == anchor
    canvas.zoom_at(center, 4)
    old_origin = QPointF(canvas.origin)
    drag(canvas, center, center+QPointF(20,10), Qt.MiddleButton)
    assert canvas.origin == old_origin+QPointF(20,10)
    zoom = canvas.zoom
    wheel(canvas, center, modifiers=Qt.ControlModifier)
    assert w.brush_size_spinbox.value() == 2 and canvas.zoom == zoom
    w.brush_size_spinbox.setValue(8)
    start, end = (width//2-20,h//2), (width//2+20,h//2)
    drag(canvas, image_point(canvas,*start), image_point(canvas,*end), Qt.LeftButton)
    mask = state.derived_layers.bw_2
    assert mask[h//2-7:h//2+8,width//2-27:width//2+28].all()
    assert state.wire_update_pending and w.update_wire_action.isEnabled() and w.undo_action.isEnabled()
    assert not w.display_mode_combo.model().item(w.display_mode_combo.findData('wire_frame')).isEnabled()
    np.testing.assert_array_equal(state.derived_layers.wire, original.wire)
    drag(canvas, image_point(canvas,*start), image_point(canvas,*end), Qt.RightButton)
    assert not state.derived_layers.bw_2[h//2-7:h//2+8,width//2-27:width//2+28].any()
    w.undo_action.trigger()
    np.testing.assert_array_equal(state.derived_layers.bw_2, original.bw_2)
    assert not w.update_wire_action.isEnabled() and not w.undo_action.isEnabled()
    drag(canvas, image_point(canvas,*start), image_point(canvas,*end), Qt.LeftButton)
    edited = state.derived_layers.bw_2.copy()
    w.update_wire_action.trigger()
    assert not canvas.editable and not w.undo_action.isEnabled()
    wait_for_worker(w, app)
    np.testing.assert_array_equal(state.derived_layers.bw_2, edited)
    updated = state.derived_layers
    w.update_current_wire()
    assert w.worker is None and state.derived_layers is updated
    assert w.undo_action.isEnabled() and not w.update_wire_action.isEnabled()
    # Keyboard Undo restores the entire batch, including derived wire layers.
    canvas.setFocus()
    QTest.keyClick(w, Qt.Key_Z, Qt.ControlModifier)
    app.processEvents()
    for name in ('bw_2','wire','branchpoints','endpoints','dilated_wire','dilated_wire_2'):
        np.testing.assert_array_equal(getattr(state.derived_layers,name), getattr(original,name))
    np.testing.assert_array_equal(state.base_image.data, base)
    assert canvas.zoom == zoom
    w.fit_action.trigger()
    assert canvas.zoom == 1


def test_edit_guards_failure_and_image_switch(window, tmp_path, monkeypatch):
    w, app = window
    image = np.zeros((96,128), np.uint8)
    for name in ('a.tif','b.tif'):
        tifffile.imwrite(tmp_path/name, image)
    w.open_directory(tmp_path)
    w.load_selected_image(w.file_list.item(0))
    w.segment_button.click()
    wait_for_worker(w, app)
    state = w.app_state.active_image
    original = deepcopy(state.derived_layers)
    # Read-only modes never edit; a no-op does not enable Update Wire.
    w.display_mode_combo.setCurrentIndex(w.display_mode_combo.findData('grey'))
    w.paint_stroke((20,20),(30,30),True)
    assert not state.wire_update_pending
    w.display_mode_combo.setCurrentIndex(w.display_mode_combo.findData('segmented'))
    w.paint_stroke((20,20),(30,30),False)
    assert not state.wire_update_pending
    w.paint_stroke((20,20),(30,30),True)
    edited = state.derived_layers.bw_2.copy()
    messages = []
    monkeypatch.setattr(QMessageBox,'critical',lambda *args: messages.append(args[-1]))
    state.params.thin_iterations = -1  # Force failure in the settings used by this wire.
    w.update_wire_action.trigger()
    wait_for_worker(w, app)
    assert messages and state.wire_update_pending and w.update_wire_action.isEnabled()
    np.testing.assert_array_equal(state.derived_layers.bw_2, edited)
    w.load_selected_image(w.file_list.item(1))
    assert not w.undo_action.isEnabled() and not w.image_label.editable
    w.load_selected_image(w.file_list.item(0))
    assert w.undo_action.isEnabled() and w.update_wire_action.isEnabled()
    w.undo_action.trigger()
    np.testing.assert_array_equal(state.derived_layers.bw_2, original.bw_2)
    assert not w.update_wire_action.isEnabled()


def test_gui_save_reopen_and_continue_editing(window,tmp_path,monkeypatch):
    from reaver.io.results import default_analysis_path
    from dataclasses import fields
    w,app = window
    image = np.zeros((96,128,3),np.uint8)
    image[20:45,:,1] = 255
    tifffile.imwrite(tmp_path/'saved.tif',image,photometric='rgb')
    w.open_directory(tmp_path)
    w.load_selected_image(w.file_list.item(0))
    w.segmentation_channel_checkboxes[0].setChecked(False)
    w.segmentation_channel_checkboxes[1].setChecked(True)
    w.segment_button.click()
    wait_for_worker(w,app)
    assert w.save_analysis_action.isEnabled()
    w.brush_size_spinbox.setValue(8)
    w.paint_stroke((20,50),(90,50),True)
    assert not w.save_analysis_action.isEnabled()
    w.update_wire_action.trigger()
    wait_for_worker(w,app)
    expected = deepcopy(w.app_state.active_image.derived_layers)
    w.save_analysis_action.trigger()
    path = default_analysis_path(tmp_path/'saved.tif')
    assert path.exists() and not w.app_state.active_image.dirty
    assert not w.save_analysis_action.isEnabled()
    # Reopen via directory discovery, using a fresh window and no segmentation.
    other = ReaverMainWindow()
    try:
        other.open_directory(tmp_path)
        other.load_selected_image(other.file_list.item(0))
        loaded = other.app_state.active_image
        assert loaded.image_segmented and not loaded.dirty
        assert loaded.segmented_channels == (1,)
        assert not other.undo_action.isEnabled() and not other.update_wire_action.isEnabled()
        for f in fields(expected):
            np.testing.assert_array_equal(getattr(loaded.derived_layers,f.name),getattr(expected,f.name))
        assert other.display_mode_combo.currentData() == 'overlay'
        other.display_mode_combo.setCurrentIndex(other.display_mode_combo.findData('overlay'))
        other.paint_stroke((20,50),(90,50),False)
        other.undo_action.trigger()
        np.testing.assert_array_equal(loaded.derived_layers.bw_2,expected.bw_2)
        assert loaded.dirty and other.save_analysis_action.isEnabled()
        # Cancel reopening and closing must keep the current analysis.
        monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.Cancel)
        assert not other.open_analysis(path)
        assert other.app_state.active_image is loaded
        assert not other.close()
        # Save-all handles the unsaved analysis before a directory change.
        monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.Save)
        assert other.confirm_unsaved('Test')
        assert not loaded.dirty
    finally:
        for s in other.app_state.image_states.values(): s.dirty = False
        other.close()
        other.deleteLater()


def test_gui_open_save_failures_keep_current_analysis(window,tmp_path,monkeypatch):
    from reaver.io.results import default_analysis_path
    w,app = window
    tifffile.imwrite(tmp_path/'a.tif',np.zeros((48,64),np.uint8))
    w.open_directory(tmp_path)
    w.load_selected_image(w.file_list.item(0))
    w.segment_button.click()
    wait_for_worker(w,app)
    state = w.app_state.active_image
    messages = []
    monkeypatch.setattr(QMessageBox,'critical',lambda *args: messages.append(args[-1]))
    broken = tmp_path/'broken.mat'
    broken.write_bytes(b'not a MAT file')
    assert not w.open_analysis(broken)
    assert w.app_state.active_image is state and state.dirty
    def fail(*args,**kwargs): raise OSError('simulated disk failure')
    monkeypatch.setattr('reaver.gui.main_window.save_analysis',fail)
    assert not w.save_current_analysis()
    assert state.dirty and w.save_analysis_action.isEnabled()
    assert messages and not default_analysis_path(state.path).exists()


def test_measure_resolution_save_verify_export_workflow(window,tmp_path,monkeypatch):
    import csv
    from test_measurement_export import make_state
    from reaver.io.results import save_analysis,load_analysis
    from reaver.core.metrics import METRIC_LABELS
    w,app=window
    source=make_state(tmp_path);save_analysis(source)
    w.open_directory(tmp_path)
    w.load_selected_image(w.file_list.item(0))
    state=w.app_state.active_image
    assert w.resolution_edit.text()=='0.65'
    assert w.measure_action.isEnabled() and not w.verified_checkbox.isChecked()
    w.measure_action.trigger()
    assert not w.image_label.editable and not w.export_results_action.isEnabled()
    wait_for_worker(w,app)
    original=state.measurements.copy()
    assert len(original)==12 and w.measurements_table.item(6,1).text()=='4'
    w.resolution_edit.setText('1.3');w.resolution_changed()
    assert state.dirty and not state.measurements and not w.export_results_action.isEnabled()
    w.measure_action.trigger();wait_for_worker(w,app)
    assert state.measurements['vessel_length_um']==pytest.approx(2*original['vessel_length_um'])
    assert w.save_current_analysis()
    w.verified_checkbox.setChecked(True)
    assert load_analysis(state.analysis_path).verified and not state.dirty
    out=tmp_path/(tmp_path.name+'.csv')
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args,**kwargs:(str(out),'CSV'))
    w.export_results_action.trigger();wait_for_worker(w,app)
    with out.open() as f:row=next(csv.DictReader(f))
    for name in METRIC_LABELS:
        np.testing.assert_allclose(float(row[name]),state.measurements[name],rtol=1e-12)
    w.export_directory_action.trigger();wait_for_worker(w,app)
    assert 'Exported 1 analysis' in w.statusBar().currentMessage()
    w.display_mode_combo.setCurrentIndex(w.display_mode_combo.findData('overlay'))
    w.brush_size_spinbox.setValue(4)
    w.paint_stroke((30,20),(40,20),False)
    assert state.wire_update_pending and not state.measurements
    assert not w.measure_action.isEnabled() and not w.export_results_action.isEnabled()
    assert w.measurements_table.item(6,1).text()=='—'
    w.undo_action.trigger()
    assert w.measure_action.isEnabled() and not state.measurements


def test_measurement_and_export_failure_leave_no_csv(window,tmp_path,monkeypatch):
    from test_measurement_export import make_state
    from reaver.io.results import save_analysis
    w,app=window
    source=make_state(tmp_path,index=1);save_analysis(source)
    w.open_directory(tmp_path);w.load_selected_image(w.file_list.item(0))
    messages=[]
    monkeypatch.setattr(QMessageBox,'critical',lambda *args:messages.append(args[-1]))
    w.measure_action.trigger();wait_for_worker(w,app)
    assert messages and 'no branchpoints' in messages[0]
    assert w.sidebar.isEnabled() and w.open_action.isEnabled() and not w.app_state.active_image.measurements
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args,**kwargs:('',''))
    w.export_results_action.trigger();wait_for_worker(w,app)
    assert w.worker is None and not list(tmp_path.glob('*.csv'))


def test_verification_save_failure_rolls_back_and_invalid_resolution(window,tmp_path,monkeypatch):
    from test_measurement_export import make_state
    from reaver.io.results import save_analysis
    w,app=window
    source=make_state(tmp_path);save_analysis(source)
    w.open_directory(tmp_path);w.load_selected_image(w.file_list.item(0))
    messages=[]
    monkeypatch.setattr(QMessageBox,'critical',lambda *args:messages.append(args[-1]))
    monkeypatch.setattr(QMessageBox,'warning',lambda *args:messages.append(args[-1]))
    def fail(*args,**kwargs):raise OSError('disk unavailable')
    monkeypatch.setattr('reaver.gui.main_window.save_analysis',fail)
    w.verified_checkbox.setChecked(True)
    assert not w.app_state.active_image.verified and not w.verified_checkbox.isChecked()
    w.resolution_edit.setText('nan');w.resolution_changed()
    assert w.app_state.active_image.params.image_resolution==.65
    assert w.resolution_edit.text()=='0.65' and len(messages)==2


def test_status_selection_discard_and_remove(window,tmp_path,monkeypatch):
    from test_measurement_export import make_state
    from reaver.io.results import save_analysis, find_analysis
    from reaver.io.measurement_export import update_directory_results, read_results_csv
    w,app=window
    source=make_state(tmp_path);source.verified=True;save_analysis(source)
    csv_path=update_directory_results(source)
    w.open_directory(tmp_path)
    item=w.file_list.item(0)
    assert 'Saved and verified' in item.toolTip()
    assert not w.app_state.image_states[source.path.name].image_loaded
    assert w.file_button.menu() and w.toolbar.widgetForAction(w.toolbar.actions()[0]) is w.file_button
    assert not w.menuBar().actions()
    w.file_list.setCurrentItem(item)
    assert w.display_mode_combo.currentData()=='overlay'
    w.display_mode_combo.setCurrentIndex(w.display_mode_combo.findData('overlay'))
    w.brush_size_spinbox.setValue(4);w.paint_stroke((30,20),(40,20),False)
    assert not w.app_state.active_image.verified
    assert 'Unsaved changes' in item.toolTip() and w.discard_action.isEnabled()
    monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.Cancel)
    assert not w.discard_current_changes()
    assert w.app_state.active_image.wire_update_pending
    monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.Discard)
    assert w.discard_current_changes()
    assert w.app_state.active_image.verified and not w.app_state.active_image.dirty
    assert w.display_mode_combo.currentData()=='overlay'
    assert 'Saved and verified' in item.toolTip()
    monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.Yes)
    assert w.delete_current_analysis()
    assert not w.app_state.active_image.image_segmented
    assert find_analysis(source.path) is None
    assert 'No saved analysis' in item.toolTip() and item.icon().isNull()
    assert read_results_csv(csv_path)==[]


def test_discard_all_and_calibration_clears_verification(window,tmp_path,monkeypatch):
    from test_measurement_export import make_state
    from reaver.io.results import save_analysis
    w,app=window
    for name in ('a','b'):
        state=make_state(tmp_path,name);state.verified=True;save_analysis(state)
    w.open_directory(tmp_path)
    for i in range(2):
        w.file_list.setCurrentItem(w.file_list.item(i))
        w.resolution_edit.setText('2');w.resolution_changed()
        assert w.app_state.active_image.dirty and not w.app_state.active_image.verified
    assert w.discard_all_action.isEnabled()
    monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.Discard)
    assert w.discard_all_changes()
    assert all(s.verified and not s.dirty and s.params.image_resolution==.65 for s in w.app_state.image_states.values())


def test_resegment_confirmation_and_simplified_file_controls(window,tmp_path,monkeypatch):
    from test_measurement_export import make_state
    from reaver.io.results import save_analysis, default_analysis_path
    w,app=window
    source=make_state(tmp_path);source.verified=True;save_analysis(source)
    original=source.analysis_path.read_bytes()
    w.open_directory(tmp_path);w.file_list.setCurrentItem(w.file_list.item(0))
    state=w.app_state.active_image
    assert w.display_mode_combo.currentData()=='overlay'
    labels=[a.text() for a in w.file_button.menu().actions()]
    assert not any('Open Analysis' in t or 'Save Analysis As' in t for t in labels)
    assert not hasattr(w,'open_analysis_action') and not hasattr(w,'save_analysis_as_action')
    assert '#fffbe6' in w.file_list.styleSheet() and '#202020' in w.file_list.styleSheet()
    questions=[]
    def cancel(*args):
        questions.append(args);return QMessageBox.Cancel
    monkeypatch.setattr(QMessageBox,'question',cancel)
    w.segment_button.click()
    assert len(questions)==1 and w.worker is None
    assert state.verified and not state.dirty
    monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.Yes)
    w.segment_button.click();wait_for_worker(w,app)
    assert state.dirty and not state.verified
    assert source.analysis_path.read_bytes()==original
    state.save_path=tmp_path/'unexpected.reaver'
    assert w.save_current_analysis()
    assert state.analysis_path==default_analysis_path(state.path)
    assert not (tmp_path/'unexpected.reaver').exists()


def test_unsegmented_selection_shows_channels(window,tmp_path):
    w,app=window
    tifffile.imwrite(tmp_path/'raw.tif',np.zeros((32,32),np.uint8))
    w.open_directory(tmp_path)
    w.file_list.setCurrentItem(w.file_list.item(0))
    assert w.display_mode_combo.currentData()=='displayed_channels'


def test_settings_proposals_segment_save_reopen(window,tmp_path,monkeypatch):
    from dataclasses import replace
    from test_measurement_export import make_state
    from reaver.io.results import save_analysis,load_analysis
    from reaver.core.segmentation import segment_image
    from reaver.gui.segmentation_settings import SegmentationSettingsDialog
    w,app=window
    original=make_state(tmp_path);original.verified=True;save_analysis(original)
    w.open_directory(tmp_path);w.file_list.setCurrentItem(w.file_list.item(0))
    state=w.app_state.active_image;old=replace(state.params)
    w.threshold_edit.setText('0.2005');w.threshold_text_changed()
    assert w.app_state.params.grey_to_bw_threshold==.201
    assert state.params==old and state.verified and not state.dirty
    assert 'differ' in w.settings_note.text()
    def accept(dialog):
        dialog.params=replace(dialog.params,averaging_filter_size=17,min_connected_component_area=5,
            wire_dilation_threshold=2,vessel_thickness_threshold=1.5)
        return dialog.Accepted
    monkeypatch.setattr(SegmentationSettingsDialog,'exec',accept)
    w.settings_button.click()
    proposed=replace(w.app_state.params)
    # Saving the existing result must not mislabel it with proposed settings.
    assert w.save_current_analysis()
    assert load_analysis(state.analysis_path).params==old
    monkeypatch.setattr(QMessageBox,'question',lambda *args: QMessageBox.Yes)
    w.segment_button.click();wait_for_worker(w,app)
    assert state.params==proposed and not state.verified and state.dirty
    assert 'differ' not in w.settings_note.text()
    expected=segment_image(state.base_image.data,proposed,state.segmented_channels)
    np.testing.assert_array_equal(state.derived_layers.bw_2,expected.bw_2)
    assert w.save_current_analysis()
    loaded=load_analysis(state.analysis_path)
    assert loaded.params==proposed
    np.testing.assert_array_equal(loaded.derived_layers.wire,expected.wire)
    w.open_directory(tmp_path);w.file_list.setCurrentItem(w.file_list.item(0))
    assert w.threshold_edit.text()=='0.201' and w.app_state.params==proposed


def test_settings_dialog_cancel_invalid_and_wire_uses_saved_settings(window,tmp_path,monkeypatch):
    from dataclasses import replace
    from test_measurement_export import make_state
    from reaver.io.results import save_analysis
    from reaver.gui.segmentation_settings import SegmentationSettingsDialog
    w,app=window
    source=make_state(tmp_path);save_analysis(source)
    w.open_directory(tmp_path);w.file_list.setCurrentItem(w.file_list.item(0))
    state=w.app_state.active_image;old=replace(state.params)
    messages=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda *args:messages.append(args[-1]))
    dialog=SegmentationSettingsDialog(old,w)
    dialog.inputs['averaging_filter_size'].setText('1.5');dialog.accept()
    assert dialog.params==old and messages
    monkeypatch.setattr(SegmentationSettingsDialog,'exec',lambda d:d.Rejected)
    w.settings_button.click();assert w.app_state.params==old
    w.threshold_edit.setText('nan');w.threshold_text_changed()
    assert w.app_state.params==old
    w.threshold_slider.setValue(300)
    assert w.app_state.params.grey_to_bw_threshold==.6
    w.brush_size_spinbox.setValue(4);w.paint_stroke((30,20),(40,20),False)
    w.update_wire_action.trigger();wait_for_worker(w,app)
    assert state.params==old and w.settings_differ()


def test_batch_gui_default_confirmation_and_cache_refresh(window,tmp_path,monkeypatch):
    from test_measurement_export import make_state
    from reaver.io.results import save_analysis,load_analysis
    from reaver.gui.batch_processing import BatchDialog
    w,app=window
    old=make_state(tmp_path,'old');old.verified=True;save_analysis(old)
    new=make_state(tmp_path,'new')
    before=old.analysis_path.read_bytes()
    messages=[]
    monkeypatch.setattr(QMessageBox,'information',lambda *args:messages.append(args[-1]))
    def default(dialog):
        assert dialog.scope.currentData() is False
        return 1
    monkeypatch.setattr(BatchDialog,'exec',default)
    w.open_directory(tmp_path);w.file_list.setCurrentItem(w.file_list.item(0))
    w.batch_action.trigger();wait_for_worker(w,app)
    assert old.analysis_path.read_bytes()==before
    assert w.app_state.active_image.image_segmented
    assert len(w.batch_report['saved'])==1 and messages
    def all_images(dialog):
        dialog.scope.setCurrentIndex(1);return 1
    monkeypatch.setattr(BatchDialog,'exec',all_images)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Cancel)
    w.batch_action.trigger();assert w.worker is None
    assert old.analysis_path.read_bytes()==before
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes)
    w.batch_action.trigger();wait_for_worker(w,app)
    assert len(w.batch_report['saved'])==2
    assert not load_analysis(old.analysis_path).verified
    assert len(list((tmp_path/'.reaver-history').iterdir()))==2


def test_batch_default_excludes_unsaved_analysis(window,tmp_path,monkeypatch):
    from test_measurement_export import make_state
    from reaver.gui.batch_processing import BatchDialog
    w,app=window
    state=make_state(tmp_path)
    w.open_directory(tmp_path)
    state.image_id=state.path.name
    w.app_state.image_states[state.image_id]=state
    monkeypatch.setattr(BatchDialog,'exec',lambda d:1)
    messages=[]
    monkeypatch.setattr(QMessageBox,'information',lambda *args:messages.append(args[-1]))
    w.batch_action.trigger()
    assert w.worker is None and state.dirty and messages


def test_blinded_order_save_verification_identity(window,tmp_path,monkeypatch):
    from test_measurement_export import make_state
    from reaver.io.results import save_analysis,load_analysis
    w,app=window
    originals={}
    for name in ('control','treated','other'):
        state=make_state(tmp_path,name);save_analysis(state)
        originals[name]=state.path.read_bytes()
    monkeypatch.setattr('reaver.gui.main_window.random.sample',lambda keys,n:list(reversed(keys)))
    w.open_directory(tmp_path)
    normal=[w.file_list.item(i).data(Qt.UserRole) for i in range(3)]
    w.blind_action.setChecked(True)
    assert [w.file_list.item(i).data(Qt.UserRole) for i in range(3)]==normal[::-1]
    assert [w.file_list.item(i).text() for i in range(3)]==['Image_001','Image_002','Image_003']
    for i in range(3):
        item=w.file_list.item(i);w.file_list.setCurrentItem(item)
        state=w.app_state.active_image
        assert state.image_id==normal[::-1][i]
        assert state.path.name not in item.toolTip()
        assert state.path.name not in w.statusBar().currentMessage()
        w.verified_checkbox.setChecked(i!=1)
        assert load_analysis(state.analysis_path).verified==(i!=1)
        w.resolution_edit.setText(str(i+2));w.resolution_changed()
        assert w.save_current_analysis()
        assert load_analysis(state.analysis_path).params.image_resolution==i+2
    selected=w.app_state.active_image_id
    w.blind_action.setChecked(False)
    assert w.app_state.active_image_id==selected
    assert [w.file_list.item(i).data(Qt.UserRole) for i in range(3)]==normal
    w.blind_action.setChecked(True)
    assert [w.file_list.item(i).data(Qt.UserRole) for i in range(3)]==normal[::-1]
    for name,data in originals.items():assert (tmp_path/(name+'.tif')).read_bytes()==data


def test_image_exports_gui(window,tmp_path,monkeypatch):
    from test_measurement_export import make_state
    from reaver.io.results import save_analysis
    w,app=window
    source=make_state(tmp_path);save_analysis(source)
    w.open_directory(tmp_path);w.file_list.setCurrentItem(w.file_list.item(0))
    expected=w.current_display_array.copy()
    w.export_display_action.trigger()
    exports=list(tmp_path.glob('vessels - *.tif'))
    assert len(exports)==1
    np.testing.assert_array_equal(tifffile.imread(exports[0]),expected)
    monkeypatch.setattr(QMessageBox,'information',lambda *args:None)
    w.export_masks_action.trigger();wait_for_worker(w,app)
    np.testing.assert_array_equal(tifffile.imread(tmp_path/'bw/vessels.tif'),source.derived_layers.bw_2)
    messages=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda *args:messages.append(args[-1]))
    w.app_state.active_image.dirty=True
    w.export_masks_action.trigger()
    assert messages and w.worker is None


def test_display_controls_markers_preserve_analysis(window,tmp_path,monkeypatch):
    from test_measurement_export import make_state
    from reaver.io.results import save_analysis
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog
    w,app=window
    source=make_state(tmp_path);source.verified=True;save_analysis(source)
    saved=source.analysis_path.read_bytes()
    w.open_directory(tmp_path);w.file_list.setCurrentItem(w.file_list.item(0))
    state=w.app_state.active_image
    before=state.derived_layers.bw_2.copy()
    w.gamma_action.setChecked(True)
    monkeypatch.setattr(QColorDialog,'getColor',lambda *args:QColor(129,0,53))
    w.edge_color_action.trigger()
    assert w.app_state.display_settings.edge_line_color==(129,0,53)
    assert state.verified and not state.dirty and source.analysis_path.read_bytes()==saved
    np.testing.assert_array_equal(state.derived_layers.bw_2,before)
    w.display_mode_combo.setCurrentIndex(w.display_mode_combo.findData('wire_frame'))
    assert len(w.image_label.markers)==2
    np.testing.assert_array_equal(w.image_label.markers[0][0],state.derived_layers.branchpoints)
    assert w.image_label.markers[0][1]==(255,0,0)
    assert w.image_label.markers[1][1]==(0,255,255)
    w.display_mode_combo.setCurrentIndex(w.display_mode_combo.findData('overlay'))
    assert w.image_label.markers==[]


def test_keyboard_channels_view_switch_and_text_focus(window,tmp_path):
    from PySide6.QtTest import QTest
    w,app=window
    tifffile.imwrite(tmp_path/'rgb.tif',np.zeros((32,40,3),np.uint8),photometric='rgb')
    w.show();w.activateWindow();w.open_directory(tmp_path)
    w.file_list.setCurrentItem(w.file_list.item(0));w.file_list.setFocus();app.processEvents()
    QTest.keyClick(w.file_list,Qt.Key_R)
    assert not w.display_channel_checkboxes[0].isChecked()
    QTest.keyClick(w.file_list,Qt.Key_G)
    QTest.keyClick(w.file_list,Qt.Key_B)
    assert w.display_channel_checkboxes[2].isChecked()  # Never disable the last channel.
    w.display_mode_combo.setCurrentIndex(w.display_mode_combo.findData('input_channel'))
    QTest.keyClick(w.file_list,Qt.Key_Space)
    assert w.display_mode_combo.currentData()=='displayed_channels'
    QTest.keyClick(w.file_list,Qt.Key_Space)
    assert w.display_mode_combo.currentData()=='input_channel'
    w.resolution_edit.setFocus();w.resolution_edit.selectAll()
    QTest.keyClick(w.resolution_edit,Qt.Key_R)
    assert w.resolution_edit.text()=='r' and not w.display_channel_checkboxes[0].isChecked()
    w.resolution_edit.setText('1')
    w.image_label.last_pixel=(1,1)
    w.toggle_previous_view();assert w.display_mode_combo.currentData()=='input_channel'
    w.image_label.last_pixel=None


def test_remembered_calibration_preserves_saved_analysis(window,tmp_path):
    from test_measurement_export import make_state
    from reaver.io.results import save_analysis,load_analysis
    from reaver.app.preferences import load_default_resolution
    w,app=window
    saved=make_state(tmp_path,'saved');save_analysis(saved)
    before=saved.analysis_path.read_bytes()
    tifffile.imwrite(tmp_path/'raw.tif',np.zeros((32,32),np.uint8))
    w.open_directory(tmp_path);w.file_list.setCurrentItem(w.file_list.item(0))
    w.resolution_edit.setText('2.75');w.resolution_changed()
    assert load_default_resolution()==2.75
    w.file_list.setCurrentItem(w.file_list.item(1))
    assert w.app_state.params.image_resolution==.65
    w.resolution_changed()  # Leaving an unchanged saved calibration must not change the default.
    assert load_default_resolution()==2.75 and saved.analysis_path.read_bytes()==before
    fresh=ReaverMainWindow()
    try:
        assert fresh.app_state.params.image_resolution==2.75
        fresh.open_directory(tmp_path);fresh.file_list.setCurrentItem(fresh.file_list.item(1))
        assert fresh.resolution_edit.text()=='0.65'
        fresh.file_list.setCurrentItem(fresh.file_list.item(0))
        assert fresh.resolution_edit.text()=='2.75'
        assert load_analysis(saved.analysis_path).params.image_resolution==.65
    finally:
        fresh.close();fresh.deleteLater()


def test_ctrl_w_uses_unsaved_close_guard(window,tmp_path,monkeypatch):
    from PySide6.QtTest import QTest
    from test_measurement_export import make_state
    w,app=window
    state=make_state(tmp_path)
    w.open_directory(tmp_path);state.image_id=state.path.name
    w.app_state.image_states[state.image_id]=state
    w.show();w.activateWindow();w.file_list.setFocus();app.processEvents()
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Cancel)
    QTest.keyClick(w.file_list,Qt.Key_W,Qt.ControlModifier);app.processEvents()
    assert w.isVisible() and state.dirty
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Discard)
    QTest.keyClick(w.file_list,Qt.Key_W,Qt.ControlModifier);app.processEvents()
    assert not w.isVisible()


def test_blinded_error_paths_and_statistics_dialog_do_not_leak(window,tmp_path,monkeypatch):
    from test_measurement_export import make_state
    from reaver.io.results import save_analysis
    w,app=window
    source=make_state(tmp_path,'SECRET_TREATMENT');save_analysis(source)
    w.open_directory(tmp_path);w.file_list.setCurrentItem(w.file_list.item(0))
    w.blind_action.setChecked(True)
    messages=[]
    for kind in ('critical','warning','information'):
        monkeypatch.setattr(QMessageBox,kind,lambda *args:messages.append(args[-1]))
    detail=str(source.path)+' private condition'
    for callback in (w.measurement_failed,w.wire_failed,w.segmentation_failed):callback(detail)
    def fail(*args,**kwargs):raise OSError(detail)
    monkeypatch.setattr('reaver.gui.main_window.save_analysis',fail)
    assert not w.save_current_analysis()
    monkeypatch.setattr('reaver.gui.main_window.load_analysis',fail)
    assert not w._restore_states([w.app_state.active_image])
    def forbidden(*args,**kwargs):raise AssertionError('Filename-bearing dialog opened')
    monkeypatch.setattr(QFileDialog,'getSaveFileName',forbidden)
    w.save_stats()
    assert len(messages)==6
    assert all('SECRET' not in m and 'private condition' not in m and str(tmp_path) not in m for m in messages)
    w.blind_action.setChecked(False)
    w.measurement_failed(detail)
    assert detail in messages[-1]


def test_failed_blinded_load_restores_active_selection(window,tmp_path,monkeypatch):
    w,app=window
    tifffile.imwrite(tmp_path/'good.tif',np.zeros((32,32),np.uint8))
    (tmp_path/'SECRET_bad.tif').write_bytes(b'not a TIFF')
    w.open_directory(tmp_path)
    good=next(w.file_list.item(i) for i in range(2) if w.file_list.item(i).text()=='good.tif')
    w.file_list.setCurrentItem(good);active=w.app_state.active_image
    w.blind_action.setChecked(True)
    messages=[]
    monkeypatch.setattr(QMessageBox,'critical',lambda *args:messages.append(args[-1]))
    bad=next(w.file_list.item(i) for i in range(2) if w.file_list.item(i).data(Qt.UserRole)=='SECRET_bad.tif')
    w.file_list.setCurrentItem(bad)
    assert w.app_state.active_image is active
    assert w.file_list.currentItem().data(Qt.UserRole)=='good.tif'
    assert len(messages)==1 and 'SECRET' not in messages[0]
