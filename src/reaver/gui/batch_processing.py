from dataclasses import replace
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QDialogButtonBox
from reaver.core.batch import process_batch


class BatchDialog(QDialog):
    def __init__(self, params, channels, unprocessed, total, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Batch Processing')
        layout = QVBoxLayout(self)
        self.scope = QComboBox()
        self.scope.addItem(f'Unprocessed images only ({unprocessed})', False)
        self.scope.addItem(f'All images ({total}) — replace existing analyses', True)
        layout.addWidget(self.scope)
        channel_text = ', '.join('RGB'[c] for c in channels) or 'none (grayscale only)'
        summary = QLabel(f'Use current settings for every image:\n'
            f'Channels: {channel_text}\nThreshold: {params.grey_to_bw_threshold:g}\n'
            f'Averaging filter: {params.averaging_filter_size}\nMinimum area: {params.min_connected_component_area}\n'
            f'Wire dilation: {params.wire_dilation_threshold}\nVessel thickness: {params.vessel_thickness_threshold:g}\n'
            f'Resolution: {params.image_resolution:g} µm / pixel\n\n'
            'Results are saved as .reaver files and marked unverified. Original images and MAT files stay unchanged.')
        summary.setWordWrap(True)
        layout.addWidget(summary)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('Start Processing')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class BatchWorker(QThread):
    progress = Signal(int, int, str)
    succeeded = Signal(object)

    def __init__(self, items, params, channels, parent=None):
        super().__init__(parent)
        self.items = list(items)
        self.params = replace(params)
        self.channels = tuple(channels)

    def run(self):
        self.succeeded.emit(process_batch(self.items, self.params, self.channels,
            cancelled=self.isInterruptionRequested, progress=self.progress.emit))
