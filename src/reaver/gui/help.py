"""Offline, image-independent help and shared descriptions for GUI controls."""
from html import escape
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QTextBrowser, QToolTip

THRESHOLD_HELP = ('Brightness cutoff after local-background correction (0–1). Increasing it makes the initial vessel selection more restrictive; later cleanup also affects the final mask. Changes apply only when you click Segment Image.')
AUTO_CONTRAST_HELP = ('Automatically stretches contrast in the segmentation overlay. Does not change segmentation or measurements. Export Displayed Image includes the adjusted appearance.')
SETTING_HELP = {
    'averaging_filter_size': 'Width of the square local averaging window, in pixels. Larger windows estimate background over a broader area. This changes local-background correction, not the displayed zoom.',
    'min_connected_component_area': 'Minimum area of a connected vessel region, measured in pixels. Increasing it removes more small regions during segmentation.',
    'wire_dilation_threshold': 'Radius in pixels around the final wire used to retain vessel-mask pixels. Zero disables this mask restriction. A larger positive radius retains pixels farther from the wire; it does not add new vessel pixels.',
    'vessel_thickness_threshold': 'Distance-to-background cutoff in pixels, not full vessel diameter. Wire segments are removed when more than half their pixels have a distance below this cutoff. Increasing it makes thin-segment removal more aggressive.',
}
TOOLTIP_STYLE = 'QToolTip { background-color: #fffbe6; color: #202020; border: 1px solid #777777; padding: 5px; opacity: 255; }'


def install_tooltip_style(app):
    if TOOLTIP_STYLE not in app.styleSheet():
        app.setStyleSheet(app.styleSheet() + '\n' + TOOLTIP_STYLE)
    palette = QToolTip.palette()
    palette.setColor(QPalette.ToolTipBase, QColor('#fffbe6'))
    palette.setColor(QPalette.ToolTipText, QColor('#202020'))
    QToolTip.setPalette(palette)


def help_pages():
    from .segmentation_settings import SETTING_LABELS
    settings = ''.join(f'<h3>{escape(SETTING_LABELS[key])}</h3><p>{escape(value)}</p>' for key,value in SETTING_HELP.items())
    return {
        'Getting Started': '<p>Use <b>File → Open Directory</b>, select an image, choose segmentation channels, then click <b>Segment Image</b>. Review the overlay, edit the mask, and use <b>Update Wire</b> before saving.</p><p><b>Save Analysis</b> writes a .reaver file beside the image. Selecting the image later reopens it. Mark a saved analysis <b>User verified</b> after review. Edits clear verification.</p>',
        'Segmentation Settings': '<p>Settings are proposals until you click <b>Segment Image</b>. Existing results retain the settings used to generate them. <b>Used for this result</b> shows the original threshold; <b>Restore</b> resets only that control without rerunning segmentation or discarding edits. Update Wire uses the result settings.</p><h3>Threshold</h3><p>'+escape(THRESHOLD_HELP)+'</p>'+settings,
        'Display Modes': '<p><b>Original Image:</b> the original image with selected display channels visible.</p><p><b>Segmentation Input:</b> the currently selected segmentation channels. If these differ from the result channels, segment again to apply them.</p><p><b>Vessel Mask:</b> white vessel pixels on a black background; editable.</p><p><b>Segmentation Overlay:</b> the image with vessel boundaries and centerlines; editable. After an edit, the old wire remains visible until Update Wire.</p><p><b>Wire Frame:</b> the centerline network with branchpoint and endpoint markers. Unavailable while a wire update is pending.</p><p>Display channels and colors change visualization, not segmentation or measurements.</p>',
        'Auto Contrast': '<p>'+escape(AUTO_CONTRAST_HELP)+'</p><p>Available under <b>Display → Auto Contrast</b>. This is the same operation previously called Gamma Adjust: it stretches each image channel between its 1st and 99th intensity percentiles. It is not a variable gamma control; gamma remains 1.</p><p>The original pixels, saved vessel mask, wire and verification are unchanged. Other display modes are unchanged. Displayed-image TIFF exports include the contrast adjustment when viewing the overlay; saved binary-mask exports do not.</p>',
        'Editing and Navigation': '<p>Mouse wheel: zoom. Middle-button drag: pan. <b>Fit Image</b>: fit the entire image in the viewing area.</p><p>In Vessel Mask or Segmentation Overlay, left-drag adds vessel pixels and right-drag erases them. The MATLAB square brush uses width 2 × setting − 1 pixels. Ctrl+wheel or Up/Down changes its size.</p><p><b>Update Wire (U)</b> runs once after changed edits. <b>Undo (Ctrl+Z)</b> restores the entire edit batch, including the wire, before or after an update. It is not a multiple-step history.</p><p>R/G/B toggles display channels when not typing. Space switches to the previous view. Ctrl+S saves; Ctrl+W closes.</p>',
        'Measurements and Saving': '<p>Set the image calibration in µm/pixel before measuring. <b>Measure Vessels</b> calculates area, length, branchpoints, segments, diameter, tortuosity and related statistics using the MATLAB definitions. Edits invalidate existing measurements.</p><p>Results CSV exports use one file named after the directory. Verified-directory export includes saved, verified analyses. Save or discard pending work first. File also provides Discard Changes and Remove Saved Analysis.</p><p><b>Blind Image Names</b> randomizes the review order and shows anonymous labels. Saved analyses and exported filenames retain their original image identities; blinding is a review aid, not an anonymized export.</p>',
    }


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('REAVER Help')
        self.resize(760, 540)
        self.pages = help_pages()
        layout = QHBoxLayout(self)
        self.topics = QListWidget()
        self.topics.addItems(self.pages)
        self.topics.setMaximumWidth(220)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        layout.addWidget(self.topics)
        layout.addWidget(self.browser, 1)
        self.topics.currentTextChanged.connect(self.show_topic)
        self.topics.setCurrentRow(0)

    def show_topic(self, topic):
        if topic in self.pages:
            self.browser.setHtml('<h2>'+escape(topic)+'</h2>'+self.pages[topic])
            self.topics.setCurrentRow(list(self.pages).index(topic))
