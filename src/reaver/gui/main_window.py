import sys
import random
from pathlib import Path

import numpy as np
import csv
from dataclasses import replace
from copy import deepcopy
from reaver.io.images import load_image_state
from reaver.io.image_export import export_displayed_image, export_saved_masks
from reaver.io.results import load_analysis, save_analysis, find_analysis, default_analysis_path, analysis_verified, remove_saved_analysis
from reaver.core.segmentation import segment_image
from reaver.gui.image_viewer import render_view, update_brush_view
from reaver.gui.canvas import ImageCanvas
from reaver.gui.batch_processing import BatchDialog, BatchWorker
from reaver.gui.segmentation_settings import (SegmentationSettingsDialog, threshold_from_slider,
    threshold_from_text, slider_from_threshold)
from reaver.core.editing import paint_segment, undo_edit
from reaver.core.wire import compute_wire, WIRE_FIELDS
from reaver.core.metrics import measure_state, METRIC_LABELS
from reaver.io.measurement_export import export_saved_analyses, write_results_csv, directory_results_path, update_directory_results

from PySide6.QtCore import Qt, QThread, Signal, QEvent
from PySide6.QtGui import QAction, QImage, QPixmap, QShortcut, QKeySequence, QIcon, QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox, QColorDialog,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpinBox, QSlider, QDialog, QProgressDialog,
    QToolBar, QToolButton, QMenu,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QMessageBox,
    QStyle,
    QLineEdit, QDockWidget, QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
)

from reaver.app.app_state import ReaverAppState
from reaver.app.preferences import load_default_resolution, save_default_resolution
from reaver.app.image_state import ReaverImageState


class SegmentationWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, image, params, channels, parent=None):
        super().__init__(parent)
        self.image, self.params, self.channels = image, params, channels

    def run(self):
        try:
            self.succeeded.emit(segment_image(self.image, self.params, self.channels))
        except Exception as exc:
            self.failed.emit(str(exc))


class WireWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, binary, params, parent=None):
        super().__init__(parent)
        self.binary, self.params = binary.copy(), params

    def run(self):
        try:
            self.succeeded.emit(compute_wire(self.binary, self.params))
        except Exception as exc:
            self.failed.emit(str(exc))


class MeasurementWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, state=None, path=None, items=None, parent=None):
        super().__init__(parent)
        self.state, self.path, self.items = state, path, items

    def run(self):
        try:
            if self.items is not None:
                rows = export_saved_analyses(self.items,self.path,progress=lambda i,n,name:
                    self.progress.emit(f'Measuring {i+1}/{n}: {name}'))
                self.succeeded.emit(rows)
            else:
                result = measure_state(self.state)
                if self.path is not None:
                    if self.state.dirty or self.state.analysis_path is None:
                        raise ValueError('Save the analysis before exporting results')
                    update_directory_results(self.state, result.metrics)
                self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class MaskExportWorker(QThread):
    succeeded = Signal(object)
    progress = Signal(int, int, str)

    def __init__(self, items, directory, parent=None):
        super().__init__(parent)
        self.items, self.directory = items, directory

    def run(self):
        try:
            report = export_saved_masks(self.items, self.directory, self.progress.emit)
        except Exception as exc:
            report = dict(saved=[], failed=[str(exc)])
        self.succeeded.emit(report)


class ReaverMainWindow(QMainWindow):
    DISPLAY_MODE_OPTIONS = (
        ("Displayed Channels", "displayed_channels"),
        ("Input Channel", "input_channel"),
        ("Grey", "grey"),
        ("Grey Neighbors", "grey_neighbors"),
        ("First Binary", "first_binary"),
        ("First Binary Neighbors", "first_binary_neighbors"),
        ("Second Binary", "segmented"),
        ("Segmentation Overlay", "overlay"),
        ("Wire Frame", "wire_frame"),
    )

    def __init__(self):
        super().__init__()
        self.worker = None
        self.blind_order = []
        self.blind_names = {}
        self._verification_cache = {}
        # Reused only between brush segments. All other display refreshes clear it.
        self._stroke_render_cache = {}

        self.setWindowTitle("REAVER")
        self.resize(1000, 700)

        self.app_state = ReaverAppState()
        self.default_resolution = load_default_resolution()
        self.app_state.params.image_resolution = self.default_resolution
        self.previous_display_mode = None
        self.current_display_array: np.ndarray | None = None
        self.segmentation_channels = (True, False, False)

        self.select_dir_button = QPushButton("Select Directory")
        self.select_dir_button.clicked.connect(self.select_directory)

        self.save_stats_button = QPushButton("Save Image Stats")
        self.save_stats_button.clicked.connect(self.save_stats)
        self.save_stats_button.setEnabled(False)

        self.file_list = QListWidget()
        self.file_list.setStyleSheet('QToolTip { background-color: #fffbe6; color: #202020; '
                                     'border: 1px solid #999999; padding: 5px; }')
        self.file_list.currentItemChanged.connect(lambda item, previous: self.load_selected_image(item) if item else None)

        self.display_mode_label = QLabel("Display Mode")
        self.display_mode_combo = QComboBox()
        for label, mode in self.DISPLAY_MODE_OPTIONS:
            self.display_mode_combo.addItem(label, mode)
        current_mode = self.app_state.display_settings.display_mode
        current_index = self.display_mode_combo.findData(current_mode)
        if current_index >= 0:
            self.display_mode_combo.setCurrentIndex(current_index)
        self.display_mode_combo.currentIndexChanged.connect(self.display_mode_changed)

        self.display_channel_checkboxes = (
            QCheckBox("R"),
            QCheckBox("G"),
            QCheckBox("B"),
        )
        for checkbox, checked in zip(
            self.display_channel_checkboxes,
            self.app_state.display_settings.selected_colors,
        ):
            checkbox.setChecked(checked)
            checkbox.stateChanged.connect(self.update_display_channels)

        self.segmentation_channel_checkboxes = (
            QCheckBox("R"),
            QCheckBox("G"),
            QCheckBox("B"),
        )
        for checkbox, checked in zip(
            self.segmentation_channel_checkboxes,
            self.segmentation_channels,
        ):
            checkbox.setChecked(checked)
            checkbox.stateChanged.connect(self.update_segmentation_channels)

        self.segment_button = QPushButton("Segment Image")
        self.segment_button.clicked.connect(self.segment_current_image)
        self.segment_button.setEnabled(False)

        self.image_label = ImageCanvas("Select a directory, then choose a TIF image.")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image_label.setStyleSheet("border: 1px solid gray;")

        self.sidebar = self._build_sidebar()

        main_layout = QHBoxLayout()
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.image_label, stretch=1)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
        self._build_toolbar()
        self._build_measurement_panel()
        self.image_label.stroke.connect(self.paint_stroke)
        self.image_label.brush_step.connect(self.step_brush)
        self.image_label.view_changed.connect(self.update_status_bar)
        self.image_label.setToolTip("Wheel: zoom · Middle drag: pan · Left: draw · Right: erase")
        for key, step in (("Up", 1), ("Down", -1)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda step=step: self.step_brush(step))
        self.close_shortcut = QShortcut(QKeySequence('Ctrl+W'), self)
        self.close_shortcut.activated.connect(self.close)
        QApplication.instance().installEventFilter(self)
        self.update_status_bar()

    def eventFilter(self, watched, event):
        # Consume character shortcuts only outside text editors and dialogs.
        if event.type() in (QEvent.ShortcutOverride, QEvent.KeyPress) and isinstance(watched, QWidget) and watched.window() is self:
            focus = QApplication.focusWidget()
            text_input = isinstance(focus, QLineEdit) or (focus is not None and isinstance(focus.parentWidget(), QSpinBox))
            keys = {Qt.Key_R:0, Qt.Key_G:1, Qt.Key_B:2}
            if event.modifiers() == Qt.NoModifier and not text_input and event.key() in (*keys, Qt.Key_Space):
                if event.type() == QEvent.KeyPress and not event.isAutoRepeat():
                    if event.key() == Qt.Key_Space:
                        self.toggle_previous_view()
                    else:
                        self.toggle_display_channel(keys[event.key()])
                event.accept()
                return True
        return super().eventFilter(watched,event)

    def toggle_display_channel(self, channel):
        if self.worker is not None or self.image_label.last_pixel is not None:
            return
        checkbox = self.display_channel_checkboxes[channel]
        if not checkbox.isEnabled():
            return
        if checkbox.isChecked() and sum(c.isChecked() for c in self.display_channel_checkboxes) == 1:
            return
        checkbox.setChecked(not checkbox.isChecked())

    def toggle_previous_view(self):
        if self.worker is not None or self.image_label.last_pixel is not None or self.previous_display_mode is None:
            return
        state = self.app_state.active_image
        if state is None or not state.image_loaded:
            return
        index = self.display_mode_combo.findData(self.previous_display_mode)
        if index >= 0 and self.display_mode_combo.model().item(index).isEnabled():
            self.display_mode_combo.setCurrentIndex(index)

    def _build_toolbar(self):
        toolbar = QToolBar("Application")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.toolbar = toolbar
        file_menu = QMenu('File', self)
        self.file_button = QToolButton()
        self.file_button.setText('File')
        self.file_button.setMinimumWidth(52)
        self.file_button.setPopupMode(QToolButton.InstantPopup)
        self.file_button.setMenu(file_menu)
        toolbar.addWidget(self.file_button)

        self.open_action = QAction("Open Directory", self)
        self.open_action.triggered.connect(self.select_directory)
        toolbar.addAction(self.open_action)

        self.save_analysis_action = QAction('Save Analysis', self)
        self.save_analysis_action.setShortcut(QKeySequence('Ctrl+S'))
        self.save_analysis_action.triggered.connect(self.save_current_analysis)
        self.save_analysis_action.setEnabled(False)
        toolbar.addAction(self.save_analysis_action)
        file_menu.addActions([self.open_action, self.save_analysis_action])
        self.blind_action = QAction('Blind Image Names', self)
        self.blind_action.setCheckable(True)
        self.blind_action.toggled.connect(self.toggle_blinded_review)
        file_menu.addAction(self.blind_action)
        self.batch_action = QAction('Batch Process Images…', self)
        self.batch_action.triggered.connect(self.batch_process_images)
        self.batch_action.setEnabled(False)
        file_menu.addAction(self.batch_action)

        self.discard_action = QAction('Discard Current Changes…', self)
        self.discard_action.triggered.connect(self.discard_current_changes)
        self.discard_all_action = QAction('Discard All Pending Changes…', self)
        self.discard_all_action.triggered.connect(self.discard_all_changes)
        self.delete_analysis_action = QAction('Remove Saved Analysis…', self)
        self.delete_analysis_action.triggered.connect(self.delete_current_analysis)
        file_menu.addSeparator()
        file_menu.addActions([self.discard_action, self.discard_all_action, self.delete_analysis_action])

        self.save_action = QAction("Export Image Statistics", self)
        self.save_action.triggered.connect(self.save_stats)
        self.save_action.setEnabled(False)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        self.export_results_action = QAction('Update Directory CSV with Current Results',self)
        self.export_results_action.triggered.connect(self.export_current_results)
        self.export_results_action.setEnabled(False)
        file_menu.addAction(self.export_results_action)
        self.export_directory_action = QAction('Export All Verified Results to Directory CSV',self)
        self.export_directory_action.triggered.connect(self.export_directory_results)
        self.export_directory_action.setEnabled(False)
        file_menu.addAction(self.export_directory_action)
        file_menu.addSeparator()
        self.export_masks_action = QAction('Export Saved Binary Masks as TIFFs', self)
        self.export_masks_action.triggered.connect(self.export_binary_masks)
        file_menu.addAction(self.export_masks_action)
        self.export_display_action = QAction('Export Displayed Image as TIFF', self)
        self.export_display_action.triggered.connect(self.export_displayed_view)
        file_menu.addAction(self.export_display_action)
        self.export_masks_action.setEnabled(False)
        self.export_display_action.setEnabled(False)

        view_menu = self.menuBar().addMenu('Display')
        self.gamma_action = QAction('Gamma Adjust', self)
        self.gamma_action.setCheckable(True)
        self.gamma_action.setToolTip('MATLAB automatic contrast stretch for the overlay (1%–99%).')
        self.gamma_action.toggled.connect(self.gamma_changed)
        view_menu.addAction(self.gamma_action)
        self.center_color_action = QAction('Center Line Color…',self)
        self.center_color_action.triggered.connect(lambda: self.choose_display_color('center_line_color'))
        self.edge_color_action = QAction('Edge Line Color…',self)
        self.edge_color_action.triggered.connect(lambda: self.choose_display_color('edge_line_color'))
        view_menu.addActions([self.center_color_action,self.edge_color_action])
        # Keep all menus on the toolbar, matching File.
        self.menuBar().removeAction(view_menu.menuAction())
        display_button = QToolButton()
        display_button.setText('Display')
        display_button.setMenu(view_menu)
        display_button.setPopupMode(QToolButton.InstantPopup)
        toolbar.addWidget(display_button)
        toolbar.addSeparator()

        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self.undo_action.triggered.connect(self.undo_current_edit)
        self.undo_action.setEnabled(False)
        toolbar.addAction(self.undo_action)

        self.update_wire_action = QAction("Update Wire", self)
        self.update_wire_action.setShortcut(QKeySequence("U"))
        self.update_wire_action.triggered.connect(self.update_current_wire)
        self.update_wire_action.setEnabled(False)
        toolbar.addAction(self.update_wire_action)
        self.measure_action = QAction('Measure Vessels',self)
        self.measure_action.triggered.connect(self.measure_current_image)
        self.measure_action.setEnabled(False)
        toolbar.addAction(self.measure_action)

        toolbar.addSeparator()

        self.fit_action = QAction("Fit", self)
        self.fit_action.triggered.connect(self.fit_to_window)
        toolbar.addAction(self.fit_action)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Brush:"))

        self.brush_size_spinbox = QSpinBox()
        self.brush_size_spinbox.setEnabled(False)
        self.brush_size_spinbox.setToolTip("MATLAB brush setting: square width = 2 × setting − 1 pixels. Ctrl+wheel or Up/Down to adjust.")
        self.brush_size_spinbox.setRange(1, 16)
        self.brush_size_spinbox.setValue(self.app_state.edit_state.brush_size)
        self.brush_size_spinbox.valueChanged.connect(self.update_brush_size)
        toolbar.addWidget(self.brush_size_spinbox)

    def _build_sidebar(self):
        self.sidebar = QWidget()
        self.sidebar.setMinimumWidth(250)
        self.sidebar.setMaximumWidth(350)

        images_group = QGroupBox("Images")
        images_layout = QVBoxLayout()
        images_layout.addWidget(self.file_list)
        images_group.setLayout(images_layout)

        display_group = self._build_display_controls()
        segmentation_group = self._build_segmentation_controls()

        sidebar_layout = QVBoxLayout()
        sidebar_layout.addWidget(images_group)
        sidebar_layout.addWidget(display_group)
        sidebar_layout.addWidget(segmentation_group)
        measurement_group = QGroupBox('Analysis')
        measurement_layout = QVBoxLayout(measurement_group)
        resolution_row = QHBoxLayout()
        resolution_row.addWidget(QLabel('µm / pixel:'))
        self.resolution_edit = QLineEdit('1')
        self.resolution_edit.setEnabled(False)
        self.resolution_edit.editingFinished.connect(self.resolution_changed)
        resolution_row.addWidget(self.resolution_edit)
        measurement_layout.addLayout(resolution_row)
        self.verified_checkbox = QCheckBox('User verified')
        self.verified_checkbox.setEnabled(False)
        self.verified_checkbox.setToolTip('Verified saved analyses are included in directory result exports.')
        self.verified_checkbox.toggled.connect(self.verification_changed)
        measurement_layout.addWidget(self.verified_checkbox)
        sidebar_layout.addWidget(measurement_group)
        sidebar_layout.addStretch()
        self.sidebar.setLayout(sidebar_layout)
        return self.sidebar

    def _build_display_controls(self):
        group = QGroupBox("Display")
        layout = QVBoxLayout()
        layout.addWidget(self.display_mode_label)
        layout.addWidget(self.display_mode_combo)

        display_channels_layout = QHBoxLayout()
        display_channels_layout.addWidget(QLabel("Display Channels:"))
        for checkbox in self.display_channel_checkboxes:
            display_channels_layout.addWidget(checkbox)
        display_channels_layout.addStretch()
        layout.addLayout(display_channels_layout)

        group.setLayout(layout)
        return group

    def _build_measurement_panel(self):
        self.measurements_dock = QDockWidget('Vessel Measurements',self)
        self.measurements_dock.setMinimumWidth(350)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.measurements_note = QLabel('Click Measure Vessels for the current analysis.')
        self.measurements_note.setWordWrap(True)
        layout.addWidget(self.measurements_note)
        self.measurements_table = QTableWidget(len(METRIC_LABELS),2)
        self.measurements_table.setHorizontalHeaderLabels(['Measurement','Value'])
        self.measurements_table.verticalHeader().hide()
        self.measurements_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.measurements_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.measurements_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)
        self.measurements_table.setWordWrap(True)
        for row,label in enumerate(METRIC_LABELS.values()):
            self.measurements_table.setItem(row,0,QTableWidgetItem(label))
            self.measurements_table.setItem(row,1,QTableWidgetItem('—'))
        layout.addWidget(self.measurements_table)
        self.measurements_dock.setWidget(panel)
        self.addDockWidget(Qt.RightDockWidgetArea,self.measurements_dock)
        self.measurements_dock.hide()

    def refresh_measurements(self):
        state = self.app_state.active_image
        values = state.measurements if state else {}
        for row,key in enumerate(METRIC_LABELS):
            value = values.get(key)
            text = '—' if value is None else ('NaN' if np.isnan(value) else
                ('Inf' if np.isposinf(value) else format(value,'.10g')))
            self.measurements_table.item(row,1).setText(text)
        if state and state.wire_update_pending:
            note = 'Binary edited. Update Wire, then measure again.'
        elif values:
            note = f'{self.review_name(state)} · MATLAB-compatible network measurements'
        else:
            note = 'Click Measure Vessels for the current analysis.'
        self.measurements_note.setText(note)
        self.measurements_table.resizeRowsToContents()

    def resolution_changed(self):
        state = self.app_state.active_image
        if self.worker is not None or state is None:
            return
        old = self.app_state.params.image_resolution
        try:
            value = float(self.resolution_edit.text())
            if not np.isfinite(value) or value <= 0: raise ValueError()
        except ValueError:
            self.resolution_edit.setText(str(float(old)))
            QMessageBox.warning(self,'Image resolution','Enter a positive, finite number of micrometres per pixel.')
            return
        if value != old or self.resolution_edit.isModified():
            try:
                save_default_resolution(value)
            except OSError as exc:
                QMessageBox.warning(self,'Default calibration',self.review_error(exc))
            self.default_resolution = value
        self.resolution_edit.setModified(False)
        if state.params is None and state.proposed_params is None:
            state.proposed_params = replace(self.app_state.params, image_resolution=value)
        if value != old:
            self.app_state.params.image_resolution = value
            if state.params is not None:
                state.params.image_resolution = value
            if state.proposed_params is not None:
                state.proposed_params.image_resolution = value
            if state.image_segmented:
                state.dirty = True
                state.verified = False
                state.measurements.clear()
            self.sync_edit_controls()
            self.refresh_measurements()
            self.update_status_bar()

    def verification_changed(self, checked):
        state = self.app_state.active_image
        if (self.worker is not None or state is None or state.analysis_path is None
                or state.dirty or state.wire_update_pending):
            return
        old = state.verified
        state.verified = checked
        if not self.save_state(state):
            state.verified = old
            self.sync_edit_controls()

    def batch_process_images(self):
        if self.worker is not None or self.app_state.project_dir is None:
            return
        states = [s for s in self.app_state.image_states.values()
                  if s.path.parent.resolve() == self.app_state.project_dir.resolve()]
        saved = {s.image_id: find_analysis(s.path) for s in states}
        unprocessed = [s for s in states if not saved[s.image_id] and not s.image_segmented
                       and not s.dirty and not s.wire_update_pending]
        params = replace(self.app_state.params)
        channels = tuple(i for i, checked in enumerate(self.segmentation_channels) if checked)
        dialog = BatchDialog(params, channels, len(unprocessed), len(states), self)
        if dialog.exec() != QDialog.Accepted:
            return
        selected = states if dialog.scope.currentData() else unprocessed
        if not selected:
            QMessageBox.information(self, 'Batch Processing', 'No images need processing in the selected scope.')
            return
        if any(s.dirty or s.wire_update_pending for s in selected):
            QMessageBox.warning(self, 'Pending Changes', 'Save or discard pending changes before replacing these analyses. Use the discard commands in File.')
            return
        existing = [s for s in selected if saved[s.image_id] or s.image_segmented]
        if existing and QMessageBox.question(self, 'Replace Existing Analyses?',
                f'Replace {len(existing)} existing analysis(es) using the settings shown? '
                'Verification will be cleared. Previous native saves will be copied to .reaver-history; original MAT files remain unchanged.',
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        self.batch_report = None
        self.batch_progress = QProgressDialog('Preparing images…', 'Stop after current image', 0, len(selected), self)
        self.batch_progress.setWindowTitle('Batch Processing')
        self.batch_progress.setAutoClose(False)
        self.batch_progress.setMinimumDuration(0)
        self.worker = BatchWorker([(s.path, saved[s.image_id]) for s in selected], params, channels, self)
        self.batch_progress.canceled.connect(self.worker.requestInterruption)
        self.worker.progress.connect(self.batch_progress_changed)
        self.worker.succeeded.connect(self.batch_completed)
        self.worker.finished.connect(self.batch_finished)
        self.sidebar.setEnabled(False)
        self.open_action.setEnabled(False)
        self.sync_edit_controls()
        self.worker.start()

    def batch_progress_changed(self, index, total, name):
        if self.blind_action.isChecked():
            name = "anonymous image"
        self.batch_progress.setValue(index)
        self.batch_progress.setLabelText(f'Processing {index+1}/{total}: {name}')
        self.statusBar().showMessage(f'Batch processing {index+1}/{total}: {name}')

    def batch_completed(self, report):
        self.batch_report = report
        successful = {Path(p).resolve() for p in report['saved']}
        for key, state in list(self.app_state.image_states.items()):
            if state.path.resolve() in successful:
                self.app_state.image_states[key] = ReaverImageState(image_id=key, path=state.path)

    def batch_finished(self):
        self.batch_progress.close()
        self.batch_progress.deleteLater()
        self.segmentation_finished()
        report = self.batch_report
        if report is None:
            QMessageBox.critical(self, 'Batch Processing', 'Batch processing stopped unexpectedly.')
            return
        state = self.app_state.active_image
        if state is not None and not state.image_loaded:
            self.load_selected_image(self.file_list.currentItem())
        self.mark_saved_files()
        summary = (f"{'Stopped' if report['cancelled'] else 'Finished'}: {len(report['saved'])} saved, "
                   f"{len(report['skipped'])} skipped, {len(report['failed'])} failed.")
        self.statusBar().showMessage(summary)
        message = summary
        if report['failed'] or report['warnings']:
            message += ('\nDetails hidden during blinded review.' if self.blind_action.isChecked() else '\n\n' + '\n'.join(report['failed'] + report['warnings']))
        QMessageBox.information(self, 'Batch Processing', message)

    def export_displayed_view(self):
        state = self.app_state.active_image
        if self.worker is not None or state is None or self.current_display_array is None:
            return
        try:
            path = export_displayed_image(state.path, self.current_display_array.copy())
        except Exception as exc:
            QMessageBox.critical(self, 'Image export error', 'Could not export image.' if self.blind_action.isChecked() else str(exc))
            return
        self.statusBar().showMessage('Displayed image exported.' if self.blind_action.isChecked() else f'Exported: {path}')

    def export_binary_masks(self):
        if self.worker is not None or self.app_state.project_dir is None:
            return
        states = [s for s in self.app_state.image_states.values()
                  if s.path.parent.resolve() == self.app_state.project_dir.resolve()]
        if any(s.dirty or s.wire_update_pending for s in states):
            QMessageBox.warning(self, 'Pending changes', 'Save or discard pending changes before exporting saved binary masks.')
            return
        items = [(s.analysis_path or find_analysis(s.path), s.path) for s in states]
        items = [(a,p) for a,p in items if a is not None]
        if not items:
            QMessageBox.information(self, 'No saved analyses', 'Save an analysis before exporting binary masks.')
            return
        self.image_export_report = None
        self.worker = MaskExportWorker(items, self.app_state.project_dir, self)
        self.worker.progress.connect(lambda i,n,name: self.statusBar().showMessage(
            f'Exporting mask {i+1}/{n}' + ('' if self.blind_action.isChecked() else f': {name}')))
        self.worker.succeeded.connect(self.mask_export_completed)
        self.worker.finished.connect(self.mask_export_finished)
        self.sidebar.setEnabled(False)
        self.open_action.setEnabled(False)
        self.sync_edit_controls()
        self.worker.start()

    def mask_export_completed(self, report):
        self.image_export_report = report

    def mask_export_finished(self):
        self.segmentation_finished()
        report = self.image_export_report
        summary = f"Exported {len(report['saved'])} binary mask(s); {len(report['failed'])} failed."
        self.statusBar().showMessage(summary)
        details = '' if self.blind_action.isChecked() else '\n'.join(report['failed'])
        QMessageBox.information(self, 'Binary mask export', summary + ('\n'+details if details else ''))

    def measure_current_image(self):
        state = self.app_state.active_image
        if self.worker is not None or state is None or not state.image_segmented or state.wire_update_pending:
            return
        self.start_measurement_worker(MeasurementWorker(state=state,parent=self))

    def export_current_results(self):
        state = self.app_state.active_image
        if (self.worker is not None or state is None or not state.image_segmented
                or state.wire_update_pending or state.dirty or state.analysis_path is None):
            return
        path = directory_results_path(state.path.parent)
        self.start_measurement_worker(MeasurementWorker(state=state,path=path,parent=self))

    def export_directory_results(self):
        if self.worker is not None or self.app_state.project_dir is None:
            return
        # Never silently export older on-disk values when a cached result changed.
        if any(s.dirty or s.wire_update_pending for s in self.app_state.image_states.values()
               if s.path.parent.resolve() == self.app_state.project_dir.resolve()):
            QMessageBox.warning(self,'Unsaved analyses','Save pending changes, or use File → Discard Current Changes / Discard All Pending Changes, then export again.')
            return
        items = []
        for state in self.app_state.image_states.values():
            if state.path.parent.resolve() != self.app_state.project_dir.resolve():continue
            analysis = state.analysis_path or find_analysis(state.path)
            if analysis:items.append((analysis,state.path))
        if not items:
            QMessageBox.information(self,'No analyses','Save and verify an analysis before exporting directory results.')
            return
        path = directory_results_path(self.app_state.project_dir)
        self.start_measurement_worker(MeasurementWorker(items=items,path=path,parent=self))

    def start_measurement_worker(self,worker):
        self.worker = worker
        self.measurement_target = self.app_state.active_image
        self.measurement_completion = None
        worker.succeeded.connect(self.measurement_succeeded)
        worker.failed.connect(self.measurement_failed)
        worker.progress.connect(lambda message: self.statusBar().showMessage('Measuring anonymous images…' if self.blind_action.isChecked() else message))
        worker.finished.connect(self.measurement_finished)
        self.sidebar.setEnabled(False)
        self.open_action.setEnabled(False)
        self.sync_edit_controls()
        self.statusBar().showMessage('Measuring vessel network…')
        worker.start()

    def measurement_succeeded(self,result):
        if self.worker.items is None:
            self.measurement_target.measurements = result.metrics
            self.refresh_measurements()
            if not self.measurements_dock.isVisible():
                self.measurements_dock.show()
                self.resizeDocks([self.measurements_dock],[390],Qt.Horizontal)
            self.measurements_table.resizeRowsToContents()
        if self.worker.path:
            count = len(result) if self.worker.items is not None else 1
            self.measurement_completion = f'Exported {count} analysis result(s)' + ('' if self.blind_action.isChecked() else f' to {self.worker.path}')

    def measurement_failed(self,message):
        QMessageBox.critical(self,'Measurement / export error',self.review_error(message))

    def measurement_finished(self):
        self.segmentation_finished()
        if self.measurement_completion:
            self.statusBar().showMessage(self.measurement_completion)

    def _build_segmentation_controls(self):
        group = QGroupBox("Segmentation")
        layout = QVBoxLayout()

        segmentation_channels_layout = QHBoxLayout()
        segmentation_channels_layout.addWidget(QLabel("Segmentation Channels:"))
        for checkbox in self.segmentation_channel_checkboxes:
            segmentation_channels_layout.addWidget(checkbox)
        segmentation_channels_layout.addStretch()
        layout.addLayout(segmentation_channels_layout)

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel('Threshold:'))
        self.threshold_edit = QLineEdit()
        self.threshold_edit.setMaximumWidth(80)
        self.threshold_edit.editingFinished.connect(self.threshold_text_changed)
        threshold_row.addWidget(self.threshold_edit)
        layout.addLayout(threshold_row)
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(0,400)
        self.threshold_slider.setToolTip('MATLAB threshold scale: fine control from 0 to 0.2, then 0.2 to 1.')
        self.threshold_slider.valueChanged.connect(self.threshold_slider_changed)
        layout.addWidget(self.threshold_slider)
        result_threshold_row = QHBoxLayout()
        self.result_threshold_label = QLabel('Used for this result: —')
        self.result_threshold_label.setWordWrap(True)
        result_threshold_row.addWidget(self.result_threshold_label)
        self.restore_threshold_button = QPushButton('Restore')
        self.restore_threshold_button.setToolTip('Restore the threshold used for this result. Does not rerun segmentation or discard edits.')
        self.restore_threshold_button.clicked.connect(self.restore_result_threshold)
        result_threshold_row.addWidget(self.restore_threshold_button)
        layout.addLayout(result_threshold_row)
        self.settings_button = QPushButton('Segmentation Settings…')
        self.settings_button.clicked.connect(self.edit_segmentation_settings)
        layout.addWidget(self.settings_button)
        self.settings_note = QLabel('Settings apply when you click Segment Image.')
        self.settings_note.setWordWrap(True)
        layout.addWidget(self.settings_note)
        self.refresh_parameter_controls()
        layout.addWidget(self.segment_button)
        group.setLayout(layout)
        return group

    def refresh_parameter_controls(self):
        value = self.app_state.params.grey_to_bw_threshold
        self.threshold_slider.blockSignals(True)
        self.threshold_slider.setValue(slider_from_threshold(value))
        self.threshold_slider.blockSignals(False)
        self.threshold_edit.setText(format(value,'.12g'))
        self.refresh_result_threshold()

    def refresh_result_threshold(self):
        state = self.app_state.active_image
        value = state.params.grey_to_bw_threshold if state and state.image_segmented and state.params is not None else None
        self.result_threshold_label.setText('Used for this result: ' + ('—' if value is None else format(value,'.12g')))
        self.restore_threshold_button.setEnabled(self.worker is None and value is not None
            and value != self.app_state.params.grey_to_bw_threshold)

    def restore_result_threshold(self):
        state = self.app_state.active_image
        if self.worker is not None or state is None or not state.image_segmented or state.params is None:
            return
        self.app_state.params.grey_to_bw_threshold = state.params.grey_to_bw_threshold
        self.proposed_settings_changed()

    def proposed_settings_changed(self):
        state = self.app_state.active_image
        if state is not None:
            state.proposed_params = replace(self.app_state.params)
        self.refresh_parameter_controls()
        self.sync_edit_controls()
        self.update_status_bar()

    def threshold_slider_changed(self, position):
        if self.worker is not None:
            return
        self.app_state.params.grey_to_bw_threshold = threshold_from_slider(position)
        self.proposed_settings_changed()

    def threshold_text_changed(self):
        if self.worker is not None:
            return
        # A restored/imported value may have more precision than manual entry.
        # Merely leaving the field must not round that unchanged result value.
        if self.threshold_edit.text() == format(self.app_state.params.grey_to_bw_threshold,'.12g'):
            return
        try:
            value = threshold_from_text(self.threshold_edit.text())
        except ValueError:
            QMessageBox.warning(self,'Threshold','Enter a finite threshold from 0 to 1.')
            self.refresh_parameter_controls()
            return
        self.app_state.params.grey_to_bw_threshold = value
        self.proposed_settings_changed()

    def edit_segmentation_settings(self):
        if self.worker is not None:
            return
        dialog = SegmentationSettingsDialog(self.app_state.params,self)
        if dialog.exec() == QDialog.Accepted:
            self.app_state.params = replace(dialog.params)
            self.proposed_settings_changed()

    def settings_differ(self):
        state = self.app_state.active_image
        return bool(state and state.image_segmented and state.params is not None
                    and state.params != self.app_state.params)

    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Directory")

        if not directory:
            return

        self.open_directory(directory)

    def open_directory(self, directory):
        if self.worker is not None:
            return
        project_dir = Path(directory)
        try:
            tif_files = sorted(p for p in project_dir.iterdir()
                if p.is_file() and not p.name.startswith("._")
                and p.suffix.lower() in (".tif", ".tiff", ".jpg", ".jpeg", ".bmp", ".png"))
        except OSError as exc:
            QMessageBox.critical(self, "Directory error", self.review_error(exc))
            return
        if not self.confirm_unsaved('Change directory'):
            return
        self.app_state.project_dir = project_dir
        self.app_state.image_states.clear()
        self.app_state.active_image_id = None

        self.blind_order = []
        self.blind_names = {}
        self.file_list.clear()

        for path in tif_files:
            image_id = path.name
            self.app_state.image_states[image_id] = ReaverImageState(
                image_id=image_id,
                path=path,
            )
            self.file_list.addItem(image_id)
            self.file_list.item(self.file_list.count()-1).setData(Qt.UserRole, image_id)

        self.image_label.setPixmap(QPixmap())
        self.image_label.setText("Select an image.")
        self.current_display_array = None
        self.save_stats_button.setEnabled(False)
        self.save_action.setEnabled(False)
        self.segment_button.setEnabled(False)
        self.update_display_channel_controls()
        self.sync_edit_controls()
        self.refresh_measurements()
        self.update_status_bar()

        if not tif_files:
            QMessageBox.information(self, "No TIF files", "No .tif or .tiff files found.")
        self.toggle_blinded_review(self.blind_action.isChecked())

    def load_selected_image(self, item):
        if item is None:
            return
        image_id = item.data(Qt.UserRole) or item.text()
        image_state = self.app_state.image_states[image_id]

        if self.worker is not None:
            return
        if not image_state.image_loaded:
            try:
                saved = find_analysis(image_state.path)
                image_state = load_analysis(saved, image_state.path) if saved else load_image_state(image_state.path)
                image_state.image_id = image_id
                self.app_state.image_states[image_id] = image_state
            except Exception as exc:
                QMessageBox.critical(self, "Load error", self.review_error(f"Could not load image:\n{exc}"))
                previous = self.app_state.active_image_id
                self.file_list.blockSignals(True)
                self.file_list.setCurrentRow(-1)
                for row in range(self.file_list.count()):
                    candidate = self.file_list.item(row)
                    if (candidate.data(Qt.UserRole) or candidate.text()) == previous:
                        self.file_list.setCurrentItem(candidate)
                        break
                self.file_list.blockSignals(False)
                return

        changed_image = self.app_state.active_image_id != image_id
        self.app_state.active_image_id = image_id
        if image_state.params is None and image_state.proposed_params is None:
            image_state.proposed_params = replace(self.app_state.params, image_resolution=self.default_resolution)
        selected_params = image_state.proposed_params or image_state.params
        if selected_params is not None:
            self.app_state.params = replace(selected_params)
        self.refresh_parameter_controls()
        self.resolution_edit.setText(str(float(self.app_state.params.image_resolution)))
        self.segmentation_channels = tuple(i in image_state.input_channels for i in range(3))
        for checkbox, checked in zip(self.segmentation_channel_checkboxes, self.segmentation_channels):
            checkbox.blockSignals(True)
            checkbox.setChecked(checked)
            checkbox.blockSignals(False)

        self.update_display_channel_controls()
        mode = 'overlay' if image_state.image_segmented else 'displayed_channels'
        self.display_mode_combo.setCurrentIndex(self.display_mode_combo.findData(mode))
        if changed_image:
            self.previous_display_mode = None
        self.refresh_current_display_image()
        self.image_label.fit()
        self.save_stats_button.setEnabled(True)
        self.save_action.setEnabled(True)
        self.segment_button.setEnabled(True)
        self.update_status_bar()

    def display_mode_changed(self, index):
        mode = self.display_mode_combo.itemData(index)
        if mode is None:
            return

        old_mode = self.app_state.display_settings.display_mode
        if old_mode != mode:
            self.previous_display_mode = old_mode
        self.app_state.display_settings.display_mode = mode
        self.refresh_current_display_image()

    def sync_edit_controls(self):
        state = self.app_state.active_image
        self.refresh_result_threshold()
        self.export_masks_action.setEnabled(self.worker is None and self.app_state.project_dir is not None)
        self.export_display_action.setEnabled(self.worker is None and state is not None and self.current_display_array is not None)
        self.blind_action.setEnabled(self.worker is None)
        ready = self.worker is None and state is not None and state.image_segmented
        pending = ready and state.wire_update_pending
        self.settings_note.setText('Settings differ from this result. Click Segment Image to apply them.'
            if self.settings_differ() else 'Settings apply when you click Segment Image.')
        self.undo_action.setEnabled(bool(ready and state.undo_available))
        self.update_wire_action.setEnabled(bool(pending))
        can_save = bool(ready and not state.wire_update_pending)
        self.measure_action.setEnabled(can_save)
        self.export_results_action.setEnabled(bool(can_save and state.analysis_path and not state.dirty))
        self.export_directory_action.setEnabled(self.worker is None and self.app_state.project_dir is not None)
        self.batch_action.setEnabled(self.worker is None and self.app_state.project_dir is not None)
        self.resolution_edit.setEnabled(self.worker is None and state is not None and state.image_loaded)
        self.verified_checkbox.setEnabled(bool(can_save and state.analysis_path and not state.dirty))
        self.verified_checkbox.blockSignals(True)
        self.verified_checkbox.setChecked(bool(state and state.verified))
        self.verified_checkbox.blockSignals(False)
        self.save_analysis_action.setEnabled(bool(can_save and state.dirty))
        self.discard_action.setEnabled(bool(self.worker is None and state and (state.dirty or state.wire_update_pending)))
        self.discard_all_action.setEnabled(self.worker is None and any(s.dirty or s.wire_update_pending for s in self.app_state.image_states.values()))
        self.delete_analysis_action.setEnabled(bool(self.worker is None and state and (state.analysis_path or find_analysis(state.path))))
        self.mark_saved_files()
        self.brush_size_spinbox.setEnabled(bool(ready))
        self.image_label.editable = bool(ready and self.app_state.display_settings.display_mode in ('segmented', 'overlay'))
        index = self.display_mode_combo.findData('wire_frame')
        self.display_mode_combo.model().item(index).setEnabled(not bool(state and state.wire_update_pending))
        if state and state.wire_update_pending and self.display_mode_combo.currentData() == 'wire_frame':
            self.display_mode_combo.setCurrentIndex(self.display_mode_combo.findData('overlay'))

    def step_brush(self, step):
        if self.brush_size_spinbox.isEnabled():
            self.brush_size_spinbox.setValue(self.brush_size_spinbox.value() + step)

    def paint_stroke(self, start, end, add):
        if not self.image_label.editable:
            return
        already_pending = self.app_state.active_image.wire_update_pending
        if paint_segment(self.app_state.active_image, start, end,
                         self.app_state.edit_state.brush_size, add):
            mode = self.app_state.display_settings.display_mode
            if already_pending and self.current_display_array is not None and mode in ('overlay', 'segmented'):
                update_brush_view(self.app_state.active_image, mode, self.current_display_array,
                    start, end, self.app_state.edit_state.brush_size,
                    self.app_state.display_settings.selected_colors,
                    settings=self.app_state.display_settings, cache=self._stroke_render_cache)
                self.update_display()
            else:
                self.refresh_current_display_image()
            if not already_pending:
                self.update_status_bar()

    def undo_current_edit(self):
        if self.worker is not None or self.image_label.last_pixel is not None:
            return
        state = self.app_state.active_image
        if state is not None and undo_edit(state):
            self.refresh_current_display_image()
            self.update_status_bar()

    def update_current_wire(self):
        state = self.app_state.active_image
        if (self.worker is not None or self.image_label.last_pixel is not None
                or state is None or not state.wire_update_pending):
            return
        self.segmentation_target = state
        self.worker = WireWorker(state.derived_layers.bw_2, replace(state.params), self)
        self.worker.succeeded.connect(self.wire_succeeded)
        self.worker.failed.connect(self.wire_failed)
        self.worker.finished.connect(self.segmentation_finished)
        self.sidebar.setEnabled(False)
        self.open_action.setEnabled(False)
        self.sync_edit_controls()
        self.statusBar().showMessage('Updating wire…')
        self.worker.start()

    def wire_succeeded(self, layers):
        state = self.segmentation_target
        state.derived_layers = replace(state.derived_layers,
            **{name: getattr(layers, name) for name in WIRE_FIELDS})
        state.wire_update_pending = False
        state.edit_backup_locked = False
        state.dirty = True
        state.verified = False
        state.metrics.clear()
        state.measurements.clear()
        state.params = replace(self.worker.params)
        self.refresh_current_display_image()

    def wire_failed(self, message):
        QMessageBox.critical(self, 'Update Wire error', self.review_error(message))

    def gamma_changed(self, checked):
        self.app_state.display_settings.gamma_adjust = checked
        self.refresh_current_display_image()

    def choose_display_color(self, field):
        settings = self.app_state.display_settings
        color = QColorDialog.getColor(QColor(*getattr(settings,field)),self,'Select Display Color')
        if color.isValid():
            setattr(settings,field,(color.red(),color.green(),color.blue()))
            self.refresh_current_display_image()

    def update_display_channels(self):
        self.app_state.display_settings.selected_colors = tuple(
            checkbox.isChecked()
            for checkbox in self.display_channel_checkboxes
        )
        self.refresh_current_display_image()

    def update_segmentation_channels(self):
        self.segmentation_channels = tuple(
            checkbox.isChecked()
            for checkbox in self.segmentation_channel_checkboxes
        )
        state = self.app_state.active_image
        if state is not None:
            state.input_channels = tuple(i for i, selected in enumerate(self.segmentation_channels) if selected)
        self.update_status_bar()
        self.refresh_current_display_image()

    def segment_current_image(self):
        state = self.app_state.active_image
        if self.worker is not None or state is None or state.base_image is None:
            return
        channels = tuple(i for i, selected in enumerate(self.segmentation_channels) if selected)
        if state.base_image.n_channels != 1 and not channels:
            QMessageBox.warning(self, "Input Channel", "Select at least one segmentation channel.")
            return
        if state.image_segmented or state.analysis_path or find_analysis(state.path):
            answer = QMessageBox.question(self, 'Replace Existing Analysis?',
                'Segmenting again will replace the current segmentation, edits, and wire results '
                'and clear verification. The saved file stays unchanged until you save. Continue?',
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if answer != QMessageBox.Yes:
                return
        self.segmentation_target = state
        self.worker = SegmentationWorker(state.base_image.data,
            replace(self.app_state.params), channels, self)
        self.worker.succeeded.connect(self.segmentation_succeeded)
        self.worker.failed.connect(self.segmentation_failed)
        self.worker.finished.connect(self.segmentation_finished)
        self.sidebar.setEnabled(False)
        self.open_action.setEnabled(False)
        self.sync_edit_controls()
        self.statusBar().showMessage("Segmenting image…")
        self.worker.start()

    def segmentation_succeeded(self, layers):
        state = self.segmentation_target
        state.derived_layers = layers
        state.image_segmented = True
        state.segmented_channels = self.worker.channels
        state.params = replace(self.worker.params)
        state.proposed_params = replace(state.params)
        state.wire_update_pending = False
        state.undo_layers = deepcopy(layers)
        state.undo_available = False
        state.edit_backup_locked = True
        state.dirty = True
        state.verified = False
        state.metrics.clear()
        state.measurements.clear()
        self.display_mode_combo.setCurrentIndex(self.display_mode_combo.findData("overlay"))
        self.refresh_current_display_image()

    def segmentation_failed(self, message):
        QMessageBox.critical(self, "Segmentation error", self.review_error(message))

    def segmentation_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.sidebar.setEnabled(True)
        self.open_action.setEnabled(True)
        self.sync_edit_controls()
        self.update_status_bar()

    def closeEvent(self, event):
        if self.worker is not None:
            QMessageBox.information(self, "Processing image", "Wait for image processing to finish before closing.")
            event.ignore()
            return
        if not self.confirm_unsaved('Close REAVER'):
            event.ignore()
            return
        event.accept()

    def confirm_unsaved(self, title, states=None):
        dirty = [s for s in (self.app_state.image_states.values() if states is None else states) if s.dirty]
        if not dirty:
            return True
        answer = QMessageBox.question(self, title,
            f'{len(dirty)} image(s) have unsaved analysis changes. Save them before continuing?\n'
            'Edited images must have their wire updated before they can be saved.',
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer == QMessageBox.Discard:
            return True
        if answer != QMessageBox.Save:
            return False
        if any(s.wire_update_pending for s in dirty):
            QMessageBox.warning(self, 'Update Wire needed', 'Update Wire or Undo for edited images, then save again.')
            return False
        for state in dirty:
            if not self.save_state(state):
                return False
        return True

    def save_state(self, state, path=None):
        changed = state.dirty
        try:
            save_analysis(state, default_analysis_path(state.path))
        except Exception as exc:
            QMessageBox.critical(self, 'Save analysis error', self.review_error(exc))
            return False
        if changed:
            try:
                update_directory_results(state, remove=True)
            except Exception as exc:
                QMessageBox.warning(self, 'Results CSV not updated', 'Analysis saved, but its previous CSV row could not be removed. ' + self.review_error(exc))
        self.sync_edit_controls()
        self.update_status_bar()
        self.mark_saved_files()
        return True

    def save_current_analysis(self):
        state = self.app_state.active_image
        if self.worker is not None or state is None or self.image_label.last_pixel is not None:
            return False
        return self.save_state(state)

    def open_analysis(self, path, image_path=None):
        if self.worker is not None or self.image_label.last_pixel is not None:
            return False
        try:
            try:
                state = load_analysis(path, image_path)
            except FileNotFoundError:
                image_path, _ = QFileDialog.getOpenFileName(self, 'Locate original source image',
                    str(Path(path).parent), 'Images (*.tif *.tiff *.png *.jpg *.jpeg *.bmp)')
                if not image_path:
                    return False
                state = load_analysis(path, image_path)
        except Exception as exc:
            QMessageBox.critical(self, 'Open analysis error', self.review_error(exc))
            return False
        # Fully validate before replacing any cached result. Other images stay cached.
        key = str(state.path.resolve())
        for image_id, existing in self.app_state.image_states.items():
            if existing.path.resolve() == state.path.resolve():
                key = image_id
                if not self.confirm_unsaved('Reopen analysis', [existing]):
                    return False
                # Save-before-reopen must load the just-saved file, not stale data.
                try:
                    state = load_analysis(path, image_path or state.path)
                except Exception as exc:
                    QMessageBox.critical(self, 'Open analysis error', self.review_error(exc))
                    return False
                break
        state.image_id = key
        self.app_state.image_states[key] = state
        item = next((self.file_list.item(i) for i in range(self.file_list.count())
                     if self.file_list.item(i).data(Qt.UserRole) == key or self.file_list.item(i).text() == key), None)
        if item is None:
            self.file_list.addItem(state.path.name)
            item = self.file_list.item(self.file_list.count()-1)
            item.setData(Qt.UserRole, key)
        self.file_list.setCurrentItem(item)
        self.load_selected_image(item)
        self.mark_saved_files()
        return True

    def review_error(self, message):
        if self.blind_action.isChecked():
            return 'The operation could not be completed. Details are hidden during blinded review; turn blinding off and retry to see them.'
        return str(message)

    def review_name(self, state):
        return self.blind_names.get(state.image_id, 'Image') if self.blind_action.isChecked() else state.path.name

    def toggle_blinded_review(self, enabled):
        if self.worker is not None:
            return
        keys = list(self.app_state.image_states)
        if set(self.blind_order) != set(keys):
            self.blind_order = random.sample(keys, len(keys))
            self.blind_names = {key: f'Image_{i+1:03d}' for i,key in enumerate(self.blind_order)}
        selected = self.app_state.active_image_id
        self.file_list.blockSignals(True)
        items = {}
        while self.file_list.count():
            item = self.file_list.takeItem(0)
            items[item.data(Qt.UserRole) or item.text()] = item
        for key in (self.blind_order if enabled else keys):
            item = items[key]
            item.setData(Qt.UserRole, key)
            item.setText(self.blind_names[key] if enabled else self.app_state.image_states[key].path.name)
            self.file_list.addItem(item)
            if key == selected:
                self.file_list.setCurrentItem(item)
        self.file_list.blockSignals(False)
        self.mark_saved_files()
        self.refresh_measurements()
        self.update_status_bar()

    def mark_saved_files(self):
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            state = self.app_state.image_states[item.data(Qt.UserRole) or item.text()]
            saved = state.analysis_path or find_analysis(state.path)
            verified = state.verified
            error = None
            if saved and not state.image_loaded:
                try:
                    stamp = Path(saved).stat()
                    table = state.path.parent/'User Verified Table.mat'
                    table_stamp = table.stat().st_mtime_ns if table.exists() else None
                    key = (str(saved), stamp.st_mtime_ns, stamp.st_size, table_stamp)
                    if key not in self._verification_cache:
                        self._verification_cache[key] = analysis_verified(saved, state.path)
                    verified = self._verification_cache[key]
                except Exception as exc:
                    error = str(exc)
            pending = state.dirty or state.wire_update_pending
            status = ('Unsaved changes — Update Wire needed' if state.wire_update_pending else 'Unsaved changes') if pending else (
                'Saved and verified' if saved and verified else 'Saved, not verified' if saved else 'No saved analysis')
            icon = (QStyle.SP_MessageBoxWarning if pending or error else
                    QStyle.SP_DialogApplyButton if saved and verified else QStyle.SP_DialogSaveButton if saved else None)
            item.setIcon(self.style().standardIcon(icon) if icon is not None else QIcon())
            item.setToolTip(status if self.blind_action.isChecked() else status + ('\n'+str(saved) if saved else '') + ('\n'+error if error else ''))
            item.setData(Qt.UserRole + 1, status)

    def _restore_states(self, states):
        # Load every replacement before discarding any in-memory work.
        replacements = {}
        try:
            for state in states:
                saved = state.analysis_path or find_analysis(state.path)
                restored = load_analysis(saved, state.path) if saved else load_image_state(state.path)
                restored.image_id = state.image_id
                replacements[state.image_id] = restored
        except Exception as exc:
            QMessageBox.critical(self, 'Discard changes error', self.review_error(exc))
            return False
        self.app_state.image_states.update(replacements)
        item = self.file_list.currentItem()
        if item:
            self.load_selected_image(item)
        self.sync_edit_controls()
        return True

    def discard_current_changes(self):
        state = self.app_state.active_image
        if self.worker is not None or state is None or not (state.dirty or state.wire_update_pending):
            return False
        if QMessageBox.question(self, 'Discard Current Changes',
                'Discard unsaved changes and restore the last saved analysis? If none exists, return to the original image.',
                QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Discard:
            return False
        return self._restore_states([state])

    def discard_all_changes(self):
        if self.worker is not None:
            return False
        states = [s for s in self.app_state.image_states.values() if s.dirty or s.wire_update_pending]
        if not states:
            return True
        if QMessageBox.question(self, 'Discard All Pending Changes',
                f'Discard unsaved changes for {len(states)} image(s) and restore their saved analyses?',
                QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Discard:
            return False
        return self._restore_states(states)

    def delete_current_analysis(self):
        state = self.app_state.active_image
        if self.worker is not None or state is None:
            return False
        if QMessageBox.question(self, 'Remove Saved Analysis',
                f'Remove saved data and discard pending changes for {self.review_name(state)}?\n'
                'Native saves move to .reaver-trash. Original images and legacy .mat files remain untouched; '
                'legacy analyses will no longer open automatically. Its directory CSV row will be removed.',
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return False
        try:
            restored = load_image_state(state.path)
            # Validate CSV before removing a save; never replace an unrelated CSV.
            from reaver.io.measurement_export import read_results_csv
            read_results_csv(directory_results_path(state.path.parent))
            remove_saved_analysis(state)
        except Exception as exc:
            QMessageBox.critical(self, 'Remove analysis error', self.review_error(exc))
            return False
        try:
            update_directory_results(state, remove=True)
        except Exception as exc:
            QMessageBox.warning(self, 'Results CSV not updated', 'Analysis removed, but its CSV row could not be removed. ' + self.review_error(exc))
        restored.image_id = state.image_id
        self.app_state.image_states[state.image_id] = restored
        self.load_selected_image(self.file_list.currentItem())
        self.mark_saved_files()
        return True

    def fit_to_window(self):
        self.image_label.fit()

    def update_brush_size(self, value):
        self.app_state.edit_state.brush_size = value
        self.image_label.brush_size = value
        self.image_label.update()
        self.update_status_bar()

    def update_display_channel_controls(self):
        image_state = self.app_state.active_image
        image = None
        if image_state is not None and image_state.base_image is not None:
            image = image_state.base_image.data

        enabled = image is not None and image.ndim == 3 and image.shape[-1] == 3
        for checkbox in (*self.display_channel_checkboxes, *self.segmentation_channel_checkboxes):
            checkbox.setEnabled(enabled)

    def refresh_current_display_image(self):
        self._stroke_render_cache.clear()
        self.sync_edit_controls()
        self.refresh_measurements()
        image_state = self.app_state.active_image

        if image_state is None or image_state.base_image is None:
            return

        image = image_state.base_image.data
        if image is None:
            return

        self.current_display_array = render_view(image_state,
            self.app_state.display_settings.display_mode,
            self.app_state.display_settings.selected_colors,
            tuple(i for i, selected in enumerate(self.segmentation_channels) if selected),
            settings=self.app_state.display_settings, cache=self._stroke_render_cache)
        if self.current_display_array is None:
            self.export_display_action.setEnabled(False)
            self.image_label.clear()
            self.image_label.setText("Segment the image to view this layer.")
            return
        self.update_display()
        self.export_display_action.setEnabled(self.worker is None)

    def update_status_bar(self):
        image_state = self.app_state.active_image
        brush_size = self.app_state.edit_state.brush_size

        if image_state is None:
            filename = "No image loaded"
            save_state = "No analysis"
        else:
            filename = self.review_name(image_state)
            save_state = 'Unsaved analysis changes' if image_state.dirty else (
                ('Saved analysis' if self.blind_action.isChecked() else f'Saved: {image_state.analysis_path.name}') if image_state.analysis_path else 'Image loaded')
            if self.settings_differ():
                save_state += ' | Settings changed: segment again to apply'
            if image_state.wire_update_pending:
                save_state += " | Binary edited: Update Wire needed"
            if image_state.image_segmented and image_state.base_image.n_channels != 1 and image_state.input_channels != image_state.segmented_channels:
                save_state += " | Input changed: segment again to update results"

        self.statusBar().showMessage(
            f"{filename} | Zoom: {self.image_label.zoom:.2f}× fit | Brush: {brush_size} ({2*brush_size-1} px square) | {save_state}"
        )

    def update_display(self):
        if self.current_display_array is None:
            return

        image = np.ascontiguousarray(self.current_display_array)

        if image.ndim == 2:
            height, width = image.shape
            qimage = QImage(
                image.data,
                width,
                height,
                image.strides[0],
                QImage.Format_Grayscale8,
            )
        elif image.ndim == 3 and image.shape[-1] == 3:
            height, width, _ = image.shape
            qimage = QImage(
                image.data,
                width,
                height,
                image.strides[0],
                QImage.Format_RGB888,
            )
        else:
            raise ValueError(f"Unsupported display image shape: {image.shape}")

        pixmap = QPixmap.fromImage(qimage.copy())
        state = self.app_state.active_image
        self.image_label.markers = []
        if state is not None and self.app_state.display_settings.display_mode == 'wire_frame' and not state.wire_update_pending:
            self.image_label.markers = [(state.derived_layers.branchpoints,(255,0,0)),
                                        (state.derived_layers.endpoints,(0,255,255))]
        self.image_label.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_display()

    def save_stats(self):
        image_state = self.app_state.active_image

        if image_state is None or image_state.base_image is None:
            QMessageBox.warning(self, "No image", "No image is currently loaded.")
            return

        image = image_state.base_image.data

        if image is None:
            QMessageBox.warning(self, "No image", "No image data is loaded.")
            return

        stats = {
            "filename": image_state.path.name,
            "height": image.shape[0],
            "width": image.shape[1],
            "ndim": image.ndim,
            "n_channels": image_state.base_image.n_channels,
            "dtype": str(image.dtype),
            "min": float(np.nanmin(image)),
            "max": float(np.nanmax(image)),
            "mean": float(np.nanmean(image)),
            "std": float(np.nanstd(image)),
        }

        if self.blind_action.isChecked():
            QMessageBox.information(self, 'Source statistics', 'Source-statistics export uses original filenames. Turn blinded review off before opening its file dialog.')
            return
        default_path = image_state.path.with_suffix(".summary_stats.csv")

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Summary Stats",
            str(default_path),
            "CSV Files (*.csv)",
        )

        if not save_path:
            return

        try:
            with open(save_path, "w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=stats.keys())
                writer.writeheader()
                writer.writerow(stats)
        except OSError as exc:
            QMessageBox.critical(self, "Export error", self.review_error(exc))
            return

        self.update_status_bar()
        QMessageBox.information(self, "Saved", f"Stats saved to:\n{save_path}")


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    window = ReaverMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
