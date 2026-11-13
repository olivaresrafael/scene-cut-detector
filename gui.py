#!/usr/bin/env python3
"""Scene Cut Detector — macOS graphical interface.

A thin, friendly layer on top of ``scene_cut_detector.py``: drop a video,
pick a sensitivity, and get an FCPXML timeline, a Resolve marker EDL, a cut
EDL, a CSV and a readable summary.

Run with:  python gui.py
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
import time
import traceback
from pathlib import Path

try:
    from PySide6.QtCore import Qt, QThread, QTimer, Signal
    from PySide6.QtGui import QIcon, QKeySequence, QShortcut
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover - only hit when PySide6 is missing
    sys.exit(
        "PySide6 is not installed.\n\n"
        "Run 'Install Dependencies.command' first, or:\n"
        "  python3 -m pip install -r requirements.txt\n"
    )

import scene_cut_detector as core

APP_NAME = "Scene Cut Detector"
APP_VERSION = core.VERSION
VIDEO_FILTER = (
    "Video files (*.mp4 *.mov *.m4v *.mkv *.avi *.mxf *.mts *.m2ts *.webm "
    "*.wmv *.flv *.mpg *.mpeg *.ts);;All files (*)"
)

STYLESHEET = """
QWidget {
    font-family: -apple-system, "SF Pro Text", "Helvetica Neue", Arial;
    font-size: 13px;
    color: #1d1d1f;
}
QMainWindow, #root, #scrollBody {
    background: #f5f5f7;
}
QGroupBox {
    background: #ffffff;
    border: 1px solid #e5e5ea;
    border-radius: 12px;
    margin-top: 18px;
    padding: 16px 14px 12px 14px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    top: 3px;
    padding: 0 5px;
    color: #6e6e73;
    font-weight: 600;
}
QLabel#appTitle {
    font-size: 24px;
    font-weight: 700;
    letter-spacing: -0.3px;
}
QLabel#appSubtitle {
    color: #6e6e73;
    font-size: 13px;
}
QLabel#sectionHint {
    color: #86868b;
    font-size: 11px;
}
QLabel#summary {
    font-size: 14px;
    font-weight: 600;
}
QLabel#status {
    color: #6e6e73;
}
QLabel#banner {
    background: #fff4e5;
    border: 1px solid #ffd8a8;
    border-radius: 8px;
    padding: 8px 10px;
    color: #8a4b00;
}
QFrame#dropZone {
    background: #fbfbfd;
    border: 2px dashed #c9c9cf;
    border-radius: 12px;
}
QFrame#dropZone[dragging="true"] {
    background: #eef4ff;
    border-color: #3b82f6;
}
QFrame#dropZone[hasFile="true"] {
    background: #f4f8ff;
    border-color: #9dbcff;
}
QLabel#dropIcon {
    font-size: 26px;
}
QLabel#dropTitle {
    font-size: 14px;
    font-weight: 600;
}
QLabel#dropHint {
    color: #86868b;
    font-size: 11px;
}
QLabel#dropDetails {
    color: #4b5563;
    font-size: 11px;
}
QLineEdit, QComboBox, QDoubleSpinBox {
    background: #ffffff;
    border: 1px solid #d6d6dc;
    border-radius: 7px;
    padding: 5px 8px;
    min-height: 21px;
    selection-background-color: #3b82f6;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
    border-color: #3b82f6;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #d6d6dc;
    border-radius: 6px;
    selection-background-color: #eaf1ff;
    selection-color: #1d1d1f;
    outline: none;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #d6d6dc;
    border-radius: 8px;
    padding: 7px 12px;
}
QPushButton:hover {
    background: #f2f2f5;
}
QPushButton:pressed {
    background: #e8e8ec;
}
QPushButton:disabled {
    color: #a1a1a6;
    background: #f7f7f9;
}
QPushButton#primary {
    background: #3b82f6;
    border: 1px solid #2f6fdd;
    color: #ffffff;
    font-weight: 600;
    font-size: 14px;
    padding: 10px 18px;
}
QPushButton#primary:hover {
    background: #2f74ea;
}
QPushButton#primary:pressed {
    background: #2563cd;
}
QPushButton#primary:disabled {
    background: #a8c6f8;
    border-color: #a8c6f8;
    color: #ffffff;
}
QPushButton#danger {
    color: #b42318;
}
QCheckBox {
    spacing: 7px;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid #c7c7cc;
    border-radius: 4px;
    background: #ffffff;
}
QCheckBox::indicator:checked {
    background: #3b82f6;
    border-color: #3b82f6;
}
QProgressBar {
    background: #ececf0;
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: #3b82f6;
    border-radius: 5px;
}
QTabWidget::pane {
    border: 1px solid #e5e5ea;
    border-radius: 10px;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #6e6e73;
    padding: 7px 14px;
    border: none;
}
QTabBar::tab:selected {
    color: #1d1d1f;
    font-weight: 600;
}
QTableWidget {
    background: #ffffff;
    border: none;
    gridline-color: #f0f0f2;
    alternate-background-color: #fafafc;
    selection-background-color: #eaf1ff;
    selection-color: #1d1d1f;
}
QTableWidget::item {
    padding: 4px 6px;
}
QHeaderView::section {
    background: #fafafc;
    border: none;
    border-bottom: 1px solid #e5e5ea;
    padding: 6px 6px;
    color: #6e6e73;
    font-weight: 600;
}
QPlainTextEdit {
    background: #1e1e21;
    color: #e8e8ec;
    border: none;
    border-radius: 8px;
    font-family: "SF Mono", Menlo, monospace;
    font-size: 11px;
    padding: 8px;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #c7c7cc;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QToolTip {
    background: #1d1d1f;
    color: #ffffff;
    border: none;
    padding: 5px 7px;
}
"""


# --------------------------------------------------------------------------- #
# Background workers
# --------------------------------------------------------------------------- #

class ProbeWorker(QThread):
    """Read video metadata without blocking the interface."""

    probed = Signal(object)
    failed = Signal(str)

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    def run(self) -> None:
        try:
            warnings: list[str] = []
            info = core.probe_media(self.path, warn=warnings.append)
            if warnings:
                for warning in warnings:
                    print(warning, file=sys.stderr)
            self.probed.emit(info)
        except Exception as exc:  # noqa: BLE001 - surfaced in the UI
            self.failed.emit(str(exc))


class DetectionWorker(QThread):
    """Run the full detection pipeline off the main thread."""

    progressed = Signal(float)
    logged = Signal(str)
    succeeded = Signal(object)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, video: Path, out_dir: Path, args) -> None:
        super().__init__()
        self.video = video
        self.out_dir = out_dir
        self.args = args
        self._cancel_requested = False
        self._last_emit = 0.0

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def _cancelled(self) -> bool:
        return self._cancel_requested

    def _progress(self, fraction: float) -> None:
        now = time.monotonic()
        if 0.0 < fraction < 1.0 and now - self._last_emit < 0.08:
            return
        self._last_emit = now
        self.progressed.emit(fraction)

    def run(self) -> None:
        try:
            result = core.process_video(
                self.video,
                self.out_dir,
                self.args,
                log=self.logged.emit,
                progress=self._progress,
                cancelled=self._cancelled,
            )
            self.succeeded.emit(result)
        except core.DetectionCancelled:
            self.cancelled.emit()
        except Exception:  # noqa: BLE001 - report the full traceback
            self.failed.emit(traceback.format_exc())


# --------------------------------------------------------------------------- #
# Drop zone
# --------------------------------------------------------------------------- #

class DropZone(QFrame):
    fileDropped = Signal(str)
    browseRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)

        self.icon_label = QLabel("🎞")
        self.icon_label.setObjectName("dropIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel("Drop a video here")
        self.title_label.setObjectName("dropTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.hint_label = QLabel("or click to browse")
        self.hint_label.setObjectName("dropHint")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.details_label = QLabel("")
        self.details_label.setObjectName("dropDetails")
        self.details_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.details_label.setWordWrap(True)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.details_label)

    def _set_dragging(self, active: bool) -> None:
        self.setProperty("dragging", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self.browseRequested.emit()
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_dragging(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._set_dragging(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._set_dragging(False)
        urls = [u for u in event.mimeData().urls() if u.isLocalFile()]
        if urls:
            event.acceptProposedAction()
            self.fileDropped.emit(urls[0].toLocalFile())
        else:
            event.ignore()

    def show_file(self, path: Path, details: str = "Reading video…") -> None:
        self.setProperty("hasFile", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.icon_label.setText("🎬")
        self.title_label.setText(path.name)
        self.hint_label.setText("click to choose a different video")
        self.details_label.setText(details)
        self.setToolTip(str(path))

    def show_empty(self) -> None:
        self.setProperty("hasFile", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.icon_label.setText("🎞")
        self.title_label.setText("Drop a video here")
        self.hint_label.setText("or click to browse")
        self.details_label.setText("")
        self.setToolTip("")


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1060, 700)
        self.resize(1180, 800)
        self.setAcceptDrops(True)

        self.video_path: Path | None = None
        self.output_dir: Path | None = None
        self.result: core.DetectionResult | None = None
        self.worker: DetectionWorker | None = None
        self.probe_worker: ProbeWorker | None = None
        self._started_at = 0.0
        self._auto_output: Path | None = None

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(200)
        self._elapsed_timer.timeout.connect(self._update_elapsed)

        self._build_ui()
        self._apply_style()
        self._wire_shortcuts()
        self._check_dependencies()

        if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
            self.set_video(Path(sys.argv[1]))

    # ------------------------------------------------------------------ UI --

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        # Header -----------------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(12)
        if Path(__file__).parent.joinpath("assets", "icon.svg").is_file():
            logo = QLabel()
            icon = QIcon(str(Path(__file__).parent / "assets" / "icon.svg"))
            logo.setPixmap(icon.pixmap(48, 48))
            header.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        subtitle = QLabel(
            "Find every scene cut and send it to DaVinci Resolve"
        )
        subtitle.setObjectName("appSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        outer.addLayout(header)

        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        outer.addWidget(self.banner)

        # Body -------------------------------------------------------------
        body = QHBoxLayout()
        body.setSpacing(14)
        outer.addLayout(body, 1)

        # Left: settings column inside a scroll area.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll_body = QWidget()
        scroll_body.setObjectName("scrollBody")
        left = QVBoxLayout(scroll_body)
        left.setContentsMargins(0, 0, 8, 0)
        left.setSpacing(0)

        left.addWidget(self._build_video_group())
        left.addWidget(self._build_detection_group())
        left.addWidget(self._build_output_group())

        # Action buttons.
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.detect_button = QPushButton("Detect Cuts")
        self.detect_button.setObjectName("primary")
        self.detect_button.setMinimumHeight(38)
        self.detect_button.clicked.connect(self.start_detection)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("danger")
        self.cancel_button.setMinimumHeight(38)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self.cancel_detection)
        actions.addWidget(self.detect_button, 1)
        actions.addWidget(self.cancel_button)
        left.addSpacing(12)
        left.addLayout(actions)
        left.addStretch(1)

        scroll.setWidget(scroll_body)
        scroll.setMinimumWidth(470)
        scroll.setMaximumWidth(520)
        body.addWidget(scroll, 0)

        # Right: results column.
        right = QVBoxLayout()
        right.setSpacing(10)
        body.addLayout(right, 1)

        result_header = QHBoxLayout()
        self.summary_label = QLabel("No detection yet")
        self.summary_label.setObjectName("summary")
        result_header.addWidget(self.summary_label)
        result_header.addStretch(1)
        self.open_button = QPushButton("Open Output Folder")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_output_folder)
        result_header.addWidget(self.open_button)
        right.addLayout(result_header)

        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("status")
        self.status_label.setMinimumWidth(170)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight
                                       | Qt.AlignmentFlag.AlignVCenter)
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.status_label)
        right.addLayout(progress_row)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.cuts_table = QTableWidget(0, 4)
        self.cuts_table.setHorizontalHeaderLabels(
            ["#", "Timecode", "Seconds", "Frame"]
        )
        self.cuts_table.verticalHeader().setVisible(False)
        self.cuts_table.setAlternatingRowColors(True)
        self.cuts_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.cuts_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.cuts_table.setShowGrid(False)
        header_view = self.cuts_table.horizontalHeader()
        header_view.setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        header_view.setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tabs.addTab(self.cuts_table, "Cuts")

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Detection log will appear here.")
        self.tabs.addTab(self.log_view, "Log")
        right.addWidget(self.tabs, 1)

        hint = QLabel(
            "Tip: drag the video anywhere on this window. The generated files "
            "reference the original video by its absolute path."
        )
        hint.setObjectName("sectionHint")
        hint.setWordWrap(True)
        right.addWidget(hint)

    def _build_video_group(self) -> QGroupBox:
        group = QGroupBox("Video")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self.drop_zone = DropZone()
        self.drop_zone.browseRequested.connect(self.choose_video)
        self.drop_zone.fileDropped.connect(
            lambda path: self.set_video(Path(path))
        )
        layout.addWidget(self.drop_zone)

        output_label = QLabel("Output folder")
        output_label.setObjectName("sectionHint")
        layout.addWidget(output_label)

        output_row = QHBoxLayout()
        output_row.setSpacing(6)
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Same folder as the video")
        self.output_edit.editingFinished.connect(self._commit_output_edit)
        browse_output = QPushButton("Choose…")
        browse_output.clicked.connect(self.choose_output)
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(browse_output)
        layout.addLayout(output_row)

        self.open_when_done = QCheckBox("Open the output folder when finished")
        self.open_when_done.setChecked(True)
        layout.addWidget(self.open_when_done)

        return group

    def _build_detection_group(self) -> QGroupBox:
        group = QGroupBox("Detection")
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        preset_label = QLabel("Sensitivity")
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Normal", "normal")
        self.preset_combo.addItem("Sensitive", "sensitive")
        self.preset_combo.addItem("Strict", "strict")
        self.preset_combo.setItemData(
            1, "Finds more cuts, including soft or fast transitions.",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.preset_combo.setItemData(
            2, "Finds fewer cuts and avoids most false positives.",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.preset_combo.setToolTip(
            "How eagerly cuts are detected. Start with Normal and adjust if "
            "you get too many or too few cuts."
        )

        detector_label = QLabel("Detector")
        self.detector_combo = QComboBox()
        self.detector_combo.addItem("Content", "content")
        self.detector_combo.addItem("Adaptive", "adaptive")
        self.detector_combo.addItem("Hash", "hash")
        self.detector_combo.addItem("Histogram", "histogram")
        self.detector_combo.setToolTip(
            "Algorithm used to compare frames. Content is a good default; "
            "Adaptive handles camera movement better."
        )

        min_shot_label = QLabel("Min shot")
        self.min_shot_spin = QDoubleSpinBox()
        self.min_shot_spin.setRange(0.1, 60.0)
        self.min_shot_spin.setSingleStep(0.1)
        self.min_shot_spin.setValue(0.5)
        self.min_shot_spin.setSuffix(" s")
        self.min_shot_spin.setToolTip(
            "Shots shorter than this are merged into the previous shot."
        )

        downscale_label = QLabel("Speed")
        self.downscale_combo = QComboBox()
        self.downscale_combo.addItem("Auto", "auto")
        self.downscale_combo.addItem("Full res", 1)
        self.downscale_combo.addItem("2×", 2)
        self.downscale_combo.addItem("4×", 4)
        self.downscale_combo.addItem("8×", 8)
        self.downscale_combo.setToolTip(
            "Downscaling the analysis frames makes detection faster with "
            "little impact on hard cuts."
        )

        start_label = QLabel("From")
        self.start_edit = QLineEdit()
        self.start_edit.setPlaceholderText("start, e.g. 0:00")
        self.start_edit.setToolTip(
            "Optional. Seconds (83.5) or HH:MM:SS. Leave blank for the start."
        )

        end_label = QLabel("To")
        self.end_edit = QLineEdit()
        self.end_edit.setPlaceholderText("end, e.g. 21:00")
        self.end_edit.setToolTip(
            "Optional. Seconds (83.5) or HH:MM:SS. Leave blank for the end."
        )

        grid.addWidget(preset_label, 0, 0)
        grid.addWidget(self.preset_combo, 0, 1)
        grid.addWidget(detector_label, 0, 2)
        grid.addWidget(self.detector_combo, 0, 3)
        grid.addWidget(min_shot_label, 1, 0)
        grid.addWidget(self.min_shot_spin, 1, 1)
        grid.addWidget(downscale_label, 1, 2)
        grid.addWidget(self.downscale_combo, 1, 3)
        grid.addWidget(start_label, 2, 0)
        grid.addWidget(self.start_edit, 2, 1)
        grid.addWidget(end_label, 2, 2)
        grid.addWidget(self.end_edit, 2, 3)

        for combo in (
            self.preset_combo, self.detector_combo, self.downscale_combo
        ):
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(10)
        return group

    def _build_output_group(self) -> QGroupBox:
        group = QGroupBox("Output")
        layout = QVBoxLayout(group)
        layout.setSpacing(7)

        self.fcpxml_check = QCheckBox("FCPXML cut timeline")
        self.fcpxml_check.setChecked(True)
        self.fcpxml_check.setToolTip(
            "Import with File → Import → Timeline. One clip per shot."
        )
        self.markers_check = QCheckBox("Marker EDL")
        self.markers_check.setChecked(True)
        self.markers_check.setToolTip(
            "One marker per cut on your current timeline. Import with "
            "right-click → Timelines → Import → Timeline Markers from EDL."
        )
        self.edl_check = QCheckBox("Cut EDL")
        self.edl_check.setChecked(True)
        self.edl_check.setToolTip("Classic CMX3600 cut timeline.")
        self.csv_check = QCheckBox("CSV")
        self.csv_check.setChecked(True)
        self.csv_check.setToolTip("Cut and shot list with timecodes and frames.")
        self.txt_check = QCheckBox("TXT summary")
        self.txt_check.setChecked(True)
        self.txt_check.setToolTip("Readable report with statistics.")

        checks_top = QHBoxLayout()
        checks_top.addWidget(self.fcpxml_check)
        checks_top.addWidget(self.markers_check)
        checks_bottom = QHBoxLayout()
        checks_bottom.addWidget(self.edl_check)
        checks_bottom.addWidget(self.csv_check)
        checks_bottom.addWidget(self.txt_check)
        checks_top.addStretch(1)
        checks_bottom.addStretch(1)
        layout.addLayout(checks_top)
        layout.addLayout(checks_bottom)

        self.markers_only_check = QCheckBox(
            "Keep the FCPXML as one clip with markers (do not split it)"
        )
        self.markers_only_check.setToolTip(
            "Useful to review cuts on a single clip instead of a pre-cut "
            "timeline. Only affects the FCPXML file."
        )
        layout.addWidget(self.markers_only_check)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        color_label = QLabel("Marker color")
        self.marker_color_combo = QComboBox()
        for color in core.RESOLVE_COLORS:
            self.marker_color_combo.addItem(color, color)
        self.marker_color_combo.setToolTip(
            "Color used for markers imported into DaVinci Resolve."
        )

        tc_label = QLabel("Timeline start")
        self.record_tc_edit = QLineEdit("01:00:00:00")
        self.record_tc_edit.setToolTip(
            "Timecode of the first frame of the clip inside your timeline. "
            "DaVinci Resolve timelines normally start at 01:00:00:00; use "
            "00:00:00:00 if yours starts at zero."
        )

        grid.addWidget(color_label, 0, 0)
        grid.addWidget(self.marker_color_combo, 0, 1)
        grid.addWidget(tc_label, 0, 2)
        grid.addWidget(self.record_tc_edit, 0, 3)
        layout.addLayout(grid)

        note = QLabel(
            "The marker EDL assumes the clip starts at the timecode above."
        )
        note.setObjectName("sectionHint")
        note.setWordWrap(True)
        layout.addWidget(note)
        return group

    def _apply_style(self) -> None:
        self.setStyleSheet(STYLESHEET)

    def _wire_shortcuts(self) -> None:
        open_shortcut = QShortcut(QKeySequence.StandardKey.Open, self)
        open_shortcut.activated.connect(self.choose_video)
        run_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        run_shortcut.activated.connect(self.start_detection)
        run_shortcut_mac = QShortcut(QKeySequence("Meta+Return"), self)
        run_shortcut_mac.activated.connect(self.start_detection)

    def _check_dependencies(self) -> None:
        if importlib.util.find_spec("scenedetect") is None:
            self.show_banner(
                "PySceneDetect is not installed. Run "
                "'Install Dependencies.command' in the project folder, then "
                "relaunch this app."
            )
            self.detect_button.setEnabled(False)
        elif not shutil.which("ffprobe"):
            self.show_banner(
                "ffprobe was not found. Detection still works, but embedded "
                "timecode and precise metadata are unavailable. Install it "
                "with: brew install ffmpeg"
            )

    def show_banner(self, text: str) -> None:
        self.banner.setText(text)
        self.banner.show()

    # ---------------------------------------------------------- file input --

    def set_video(self, path: Path) -> None:
        path = path.expanduser().resolve()
        if not path.is_file():
            QMessageBox.warning(self, APP_NAME, f"File not found:\n{path}")
            return

        self.video_path = path
        self.drop_zone.show_file(path)

        default_out = path.parent / f"{path.stem}_cuts"
        current = self.output_edit.text().strip()
        if not current or (self._auto_output is not None
                           and Path(current).expanduser() == self._auto_output):
            self._auto_output = default_out
            self.output_edit.setText(str(default_out))
            self.output_edit.setCursorPosition(0)
        self.output_dir = Path(self.output_edit.text()).expanduser()

        self.result = None
        self.open_button.setEnabled(False)
        self.summary_label.setText("No detection yet")
        self.cuts_table.setRowCount(0)
        self.tabs.setCurrentIndex(0)
        self.progress.setValue(0)
        self.status_label.setText("Ready")

        if self.probe_worker is not None and self.probe_worker.isRunning():
            self.probe_worker.terminate()
            self.probe_worker.wait()
        self.probe_worker = ProbeWorker(path)
        self.probe_worker.probed.connect(
            lambda info: self._show_media_info(path, info)
        )
        self.probe_worker.failed.connect(
            lambda message: self.drop_zone.show_file(
                path, f"Could not read metadata: {message}"
            )
        )
        self.probe_worker.start()
        self.status_label.setText("Video loaded")

    def _show_media_info(self, path: Path, info: core.MediaInfo) -> None:
        if self.video_path != path:
            return
        details = (
            f"{info.width}×{info.height}  ·  {info.fps_label} fps  ·  "
            f"{core.format_duration(info.duration)}  ·  TC "
            f"{core.frames_to_tc(info.start_tc_frames, info.fps, info.drop_frame)}"
        )
        if info.drop_frame:
            details += "  ·  drop frame"
        self.drop_zone.show_file(path, details)

    def choose_video(self) -> None:
        start_dir = str(self.video_path.parent) if self.video_path else str(
            Path.home()
        )
        filename, _ = QFileDialog.getOpenFileName(
            self, "Choose a video", start_dir, VIDEO_FILTER
        )
        if filename:
            self.set_video(Path(filename))

    def choose_output(self) -> None:
        start_dir = (
            str(self.output_dir) if self.output_dir else
            str(self.video_path.parent if self.video_path else Path.home())
        )
        directory = QFileDialog.getExistingDirectory(
            self, "Choose the output folder", start_dir
        )
        if directory:
            self.output_edit.setText(directory)
            self.output_dir = Path(directory)
            self._auto_output = None

    def _commit_output_edit(self) -> None:
        text = self.output_edit.text().strip()
        if text:
            self.output_dir = Path(text).expanduser()
            self._auto_output = None
        elif self.video_path is not None:
            self.output_dir = self.video_path.parent / f"{self.video_path.stem}_cuts"
            self.output_edit.setText(str(self.output_dir))
            self._auto_output = self.output_dir

    # ------------------------------------------------------------ detection --

    def _build_args(self) -> argparse.Namespace:
        formats = []
        if self.fcpxml_check.isChecked():
            formats.append("fcpxml")
        if self.markers_check.isChecked():
            formats.append("markers")
        if self.edl_check.isChecked():
            formats.append("edl")
        if self.csv_check.isChecked():
            formats.append("csv")
        if self.txt_check.isChecked():
            formats.append("txt")

        start_text = self.start_edit.text().strip()
        end_text = self.end_edit.text().strip()
        start = core.parse_time(start_text) if start_text else None
        end = core.parse_time(end_text) if end_text else None
        if start is not None and end is not None and end <= start:
            raise ValueError("The end of the analysis range must be after the start.")

        return argparse.Namespace(
            detector=self.detector_combo.currentData(),
            preset=self.preset_combo.currentData(),
            threshold=None,
            min_scene_len=self.min_shot_spin.value(),
            min_content=None,
            downscale=self.downscale_combo.currentData(),
            start=start,
            end=end,
            fps=None,
            formats=formats,
            record_start=self.record_tc_edit.text().strip() or "01:00:00:00",
            marker_color=self.marker_color_combo.currentData(),
            markers_only=self.markers_only_check.isChecked(),
            quiet=True,
            open=False,
        )

    def start_detection(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        if self.video_path is None or not self.video_path.is_file():
            QMessageBox.information(
                self, APP_NAME, "Choose or drop a video file first."
            )
            return
        try:
            args = self._build_args()
        except Exception as exc:  # noqa: BLE001 - user input
            QMessageBox.warning(self, APP_NAME, str(exc))
            return

        if not args.formats:
            QMessageBox.information(
                self, APP_NAME,
                "Select at least one output format (for example FCPXML).",
            )
            return

        self._commit_output_edit()
        if self.output_dir is None:
            self.output_dir = (
                self.video_path.parent / f"{self.video_path.stem}_cuts"
            )
        self.output_dir = self.output_dir.expanduser()

        self.result = None
        self.open_button.setEnabled(False)
        self.cuts_table.setRowCount(0)
        self.log_view.clear()
        self.progress.setValue(0)
        self.summary_label.setText("Detecting cuts…")
        self.status_label.setText("0:00 elapsed")
        self.detect_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setVisible(True)
        self._started_at = time.monotonic()
        self._elapsed_timer.start()

        self.worker = DetectionWorker(
            self.video_path, self.output_dir, args
        )
        self.worker.progressed.connect(self._on_progress)
        self.worker.logged.connect(self._append_log)
        self.worker.succeeded.connect(self._on_success)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.failed.connect(self._on_failure)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()
        self.tabs.setCurrentIndex(1)

    def cancel_detection(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_cancel()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Cancelling…")

    def _on_progress(self, fraction: float) -> None:
        self.progress.setValue(int(round(fraction * 1000)))

    def _append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _update_elapsed(self) -> None:
        if self.worker is None or not self.worker.isRunning():
            return
        elapsed = time.monotonic() - self._started_at
        minutes, seconds = divmod(int(elapsed), 60)
        self.status_label.setText(f"{minutes}:{seconds:02d} elapsed")

    def _on_success(self, result: core.DetectionResult) -> None:
        self.result = result
        self.progress.setValue(1000)
        elapsed = time.monotonic() - self._started_at
        self.status_label.setText(f"Done in {elapsed:.1f} s")
        self.summary_label.setText(
            f"{len(result.cuts)} cuts  ·  {len(result.shots)} shots  ·  "
            f"{len(result.outputs)} files written"
        )
        self._fill_table(result)
        self.open_button.setEnabled(True)
        self.tabs.setCurrentIndex(0)

        if self.open_when_done.isChecked():
            core.open_in_file_manager(result.out_dir)

    def _on_cancelled(self) -> None:
        self.progress.setValue(0)
        self.summary_label.setText("Detection cancelled")
        self.status_label.setText("Cancelled")

    def _on_failure(self, details: str) -> None:
        self.progress.setValue(0)
        self.summary_label.setText("Detection failed")
        self.status_label.setText("Failed")
        self._append_log(details)
        self.tabs.setCurrentIndex(1)
        QMessageBox.critical(
            self, APP_NAME,
            "Detection failed. See the Log tab for the full details.\n\n"
            + details.strip().splitlines()[-1],
        )

    def _on_worker_finished(self) -> None:
        self._elapsed_timer.stop()
        self.detect_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setVisible(False)

    def _fill_table(self, result: core.DetectionResult) -> None:
        cuts = result.cuts
        self.cuts_table.setRowCount(len(cuts))
        for row, cut in enumerate(cuts):
            values = [
                str(cut["number"]),
                cut["timecode"],
                f"{cut['seconds']:.3f}",
                str(cut["frame"]),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column != 1:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter
                    )
                self.cuts_table.setItem(row, column, item)

    def open_output_folder(self) -> None:
        target = self.result.out_dir if self.result else self.output_dir
        if target is not None:
            core.open_in_file_manager(Path(target))

    # ------------------------------------------------------------ OS events --

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt naming
        urls = [u for u in event.mimeData().urls() if u.isLocalFile()]
        if not urls:
            return
        if len(urls) > 1:
            self.status_label.setText("Only the first dropped file is used")
        event.acceptProposedAction()
        self.set_video(Path(urls[0].toLocalFile()))

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self.worker is not None and self.worker.isRunning():
            answer = QMessageBox.question(
                self, APP_NAME,
                "Detection is still running. Quit anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.request_cancel()
            if not self.worker.wait(2500):
                self.worker.terminate()
                self.worker.wait(1000)
        if self.probe_worker is not None and self.probe_worker.isRunning():
            self.probe_worker.terminate()
            self.probe_worker.wait(1000)
        event.accept()


def main() -> int:
    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationDisplayName(APP_NAME)
    QApplication.setOrganizationName("Scene Cut Detector")
    QApplication.setApplicationVersion(APP_VERSION)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    icon_path = Path(__file__).parent / "assets" / "icon.svg"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
