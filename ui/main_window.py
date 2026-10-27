"""Main 3-pane PyQt6 window for OmniResearch Studio.

Interactive citations & source inspector, neural audio studio with embedded player, grounded follow-up Q&A console,
Tier-2 deep web ingestion, .omni project persistence, and executive HTML/PDF export.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QThread, QTimer, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut, QTextCursor, QTextOption
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.academic_resolver import AcademicResolver, is_academic_identifier
from core.audio_studio import (
    SESSION_CACHE_DIR,
    AudioStudioGenerator,
    PodcastScript,
)
from core.cache_manager import GLOBAL_CACHE, CacheManager
from core.citation_audit import CitationAudit, audit_citations
from core.compute_manager import ComputeManager
from core.flight_recorder import FlightRecorder
from core.config import (
    AVAILABLE_MODELS,
    DEFAULT_DISCOVERY_MODEL,
    DEFAULT_SYNTHESIS_MODEL,
    ConfigManager,
)
from core.document_loader import DocumentCorpus, SourceDocument
from core.media_loader import AUDIO_EXTENSIONS, MediaLoader, is_youtube_url, parse_timestamp_to_seconds
from core.exporter import (
    export_bibtex_report,
    export_pdf_report,
    export_to_marp,
    export_to_obsidian,
    save_html_report,
)
from core.i18n import get_text
from core.markdown_utils import build_dark_html
from core.network_sentinel import NetworkSentinel
from core.notebook_synthesis import CitationMatch, SynthesisResult, create_semantic_anchor_builder
from core.local_llm_client import LocalLLMClient, is_local_model
from core.project_manager import (
    PROJECT_EXTENSION,
    ProjectFormatError,
    ProjectState,
    WorkspaceTabState,
    create_checkpoint,
    list_checkpoints,
    load_project,
    restore_checkpoint,
    save_project,
)
from core.resilience import RATE_LIMIT_USER_MESSAGE, is_rate_limit_error
from core.search_index import CorpusSearchIndex
from core.storm_discovery import (
    GroundingReference,
    OmniSweepDiscoveryResult,
    detect_linguistic_origin_tag,
    format_multilingual_source_tag,
)
from core.knowledge_graph import KnowledgeGraphEngine
from core.server_mirror import MobileMirrorServer
from core.cost_tracker import GLOBAL_COST_TRACKER
from core.token_ledger import GLOBAL_LEDGER, TokenLedger
from ui.chat_drawer import FollowUpChatDrawer
from ui.diagnostic_dialog import DiagnosticDialog
from ui.settings_dialog import SettingsDialog
from ui.components import (
    ApiKeyBanner,
    AudioPlayerWidget,
    CheckpointManagerDialog,
    CitationInspectorWidget,
    DialogueRendererWidget,
    PerspectiveSelectorWidget,
    SourceInspectorDialog,
    SourceListWidget,
    SpendLedgerDialog,
    escape_mnemonic,
)
from ui.balance_radar import EpistemicBalanceWidget
from ui.compute_dialog import ComputeDialog
from ui.diff_viewer import DocumentDiffDialog
from ui.mobile_dialog import MobileServerDialog
from ui.sandbox_dock import SandboxDock
from ui.streaming_renderer import StreamingMarkdownViewer
from ui.search_drawer import SearchDockWidget
from ui.source_dock import SourceInspectorDock
from ui.theme_manager import AVAILABLE_FONTS, THEMES, ThemeManager
from ui.vault_dialog import VaultSyncDialog
from ui.dialogs.timeout_dialog import DiagnosticTimeoutDialog, play_warning_alert
from ui.status_bar import SPINNER_FRAMES
from ui.workspace_tabs import ResearchWorkspaceTabs, WorkspaceReportPane, auto_tab_title
from ui.workers import (
    AudioWorker,
    BaseCancellableWorker,
    FollowUpWorker,
    GapFillWorker,
    OmniSweepWorker,
    SynthesisWorker,
    TranslationWorker,
    VisionAnalysisWorker,
)


def render_markdown_safely(
    widget: QTextBrowser,
    md_text: str,
    documents: Optional[List[SourceDocument]] = None,
    critic_verdicts: Optional[Dict[Tuple[int, Optional[int]], Any]] = None,
) -> None:
    """Convert Markdown to styled dark-mode HTML with interactive cite anchors and semantic alignment audit."""
    if isinstance(widget, StreamingMarkdownViewer):
        widget.set_documents(documents)
        if critic_verdicts is not None:
            widget.set_critic_verdicts(critic_verdicts)
        widget.set_markdown_text(md_text)
        return
    builder = create_semantic_anchor_builder(documents, critic_verdicts=critic_verdicts) if documents else None
    widget.setHtml(build_dark_html(md_text, interactive_citations=True, anchor_builder=builder))


DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0B0F19;
    color: #C9D1D9;
    font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #1E293B;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: 600;
    color: #94A3B8;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QPushButton {
    background-color: #1E293B;
    color: #F8FAFC;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 7px 12px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #334155;
    border-color: #475569;
}
QPushButton:disabled {
    background-color: #0F172A;
    color: #475569;
    border-color: #1E293B;
}
QPushButton#PrimaryActionBtn {
    background-color: #0284C7;
    border-color: #38BDF8;
    color: #FFFFFF;
}
QPushButton#PrimaryActionBtn:hover {
    background-color: #0369A1;
}
QPushButton#OmniSweepActionBtn {
    background-color: #7E22CE;
    border-color: #A855F7;
    color: #FFFFFF;
}
QPushButton#OmniSweepActionBtn:hover {
    background-color: #6B21A8;
}
QPushButton#AudioActionBtn {
    background-color: #059669;
    border-color: #10B981;
    color: #FFFFFF;
}
QPushButton#AudioActionBtn:hover {
    background-color: #047857;
}
QPushButton#CancelTaskBtn {
    background-color: #991B1B;
    border: 1px solid #F43F5E;
    color: #FFFFFF;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 700;
    border-radius: 5px;
}
QPushButton#CancelTaskBtn:hover {
    background-color: #B91C1C;
}
QPushButton#CancelTaskBtn:disabled {
    background-color: #3B181E;
    color: #94A3B8;
    border-color: #475569;
}
QPushButton#ToggleViewBtn {
    background-color: #161B22;
    border: 1px solid #38BDF8;
    color: #58A6FF;
    padding: 4px 10px;
    font-size: 12px;
    border-radius: 5px;
}
QPushButton#ToggleViewBtn:hover {
    background-color: #1E293B;
}
QLineEdit, QPlainTextEdit, QTextBrowser, QListWidget, QComboBox {
    background-color: #0F172A;
    color: #C9D1D9;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px;
}
QTabWidget::pane {
    border: 1px solid #1E293B;
    border-radius: 6px;
    background-color: #0B0F19;
}
QTabBar::tab {
    background-color: #0F172A;
    color: #94A3B8;
    padding: 8px 16px;
    border: 1px solid #1E293B;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 4px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background-color: #1E293B;
    color: #58A6FF;
}
QSplitter::handle {
    background-color: #1E293B;
    width: 4px;
}
QSplitter::handle:hover {
    background-color: #58A6FF;
}
QProgressBar {
    border: 1px solid #334155;
    border-radius: 4px;
    background-color: #0F172A;
    color: #F8FAFC;
    text-align: center;
    font-size: 11px;
    font-weight: 700;
    height: 18px;
}
QProgressBar::chunk {
    background-color: #0284C7;
    border-radius: 3px;
}

/* Custom Dark-Mode Scrollbars */
QScrollBar:vertical {
    background: #161b22;
    width: 8px;
    margin: 0px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #30363d;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #484f58;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    width: 0px;
    border: none;
    background: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    background: #161b22;
    height: 8px;
    margin: 0px;
    border: none;
}
QScrollBar::handle:horizontal {
    background: #30363d;
    min-width: 24px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #484f58;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    height: 0px;
    width: 0px;
    border: none;
    background: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}

/* Menu bar, menus, split export button, sliders, dialogs */
QMenuBar {
    background-color: #0B0F19;
    color: #C9D1D9;
    border-bottom: 1px solid #1E293B;
}
QMenuBar::item:selected {
    background-color: #1E293B;
}
QMenu {
    background-color: #0F172A;
    color: #E6EDF3;
    border: 1px solid #334155;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 14px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #1F6FEB;
    color: #FFFFFF;
}
QToolButton#ExportSplitBtn {
    background-color: #1E293B;
    color: #F8FAFC;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 7px 26px 7px 12px;
    font-weight: 600;
}
QToolButton#ExportSplitBtn:hover {
    background-color: #334155;
}
QToolButton#ExportSplitBtn:disabled {
    background-color: #0F172A;
    color: #475569;
    border-color: #1E293B;
}
QToolButton#ExportSplitBtn::menu-button {
    border-left: 1px solid #334155;
    width: 20px;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #1E293B;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #0284C7;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #58A6FF;
    width: 12px;
    margin: -5px 0;
    border-radius: 6px;
}
QDialog {
    background-color: #0B0F19;
}
"""


class MainWindow(QMainWindow):
    """OmniResearch Studio 3-pane desktop workstation."""

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        cache_manager: Optional[CacheManager] = None,
        restore_autosave: bool = False,
    ) -> None:
        super().__init__()
        self.config_manager = config_manager or ConfigManager()
        self.cache_manager = cache_manager or GLOBAL_CACHE
        self.corpus = DocumentCorpus()
        self.search_index = CorpusSearchIndex()
        self.setAcceptDrops(True)
        self.current_language: str = "en"

        self.last_synthesis_markdown: str = ""
        self.last_citations: List[CitationMatch] = []
        self.last_grounding_refs: List[GroundingReference] = []
        self.last_podcast_script: Optional[PodcastScript] = None
        self.last_synthesis_model: str = ""
        self.last_audit: Optional[CitationAudit] = None
        self.last_audio_path: Optional[str] = None
        self.last_audio_language: str = "en"
        self._audio_render_error: str = ""
        self.current_project_path: Optional[Path] = None
        self._project_created_at: str = ""
        self._followup_worker: Optional[FollowUpWorker] = None

        # Bilingual Original / Translated report buffers and view states
        self._synthesis_original_text: str = ""
        self._synthesis_translated_text: str = ""
        self._synthesis_showing_translation: bool = False
        self.synthesis_is_translating: bool = False

        self._perspective_original_text: str = ""
        self._perspective_translated_text: str = ""
        self._perspective_showing_translation: bool = False
        self.perspective_is_translating: bool = False

        # Live streaming buffers
        self._streaming_buffers: Dict[str, str] = {
            "synthesis": "",
            "perspective": "",
            "audio": "",
        }

        # Active Worker State Management
        self.active_worker: Optional[QThread] = None
        self._research_worker: Optional[OmniSweepWorker] = None
        self._synthesis_worker: Optional[SynthesisWorker] = None
        self._audio_worker: Optional[AudioWorker] = None
        self._translation_workers: Dict[str, TranslationWorker] = {}

        # Phase 7: Master Executive & Intelligence Suite Managers
        self.token_ledger = TokenLedger.get_instance()
        self.theme_manager = ThemeManager.get_instance()
        self.network_sentinel = NetworkSentinel(parent=self)
        self.network_sentinel.connection_lost.connect(self._on_connection_lost)
        self.network_sentinel.connection_restored.connect(self._on_connection_restored)
        self.network_sentinel.start()

        # Phase 11: Sovereign Workflow & Autonomous Mastery Suite
        self.knowledge_graph_engine = KnowledgeGraphEngine(config_manager=self.config_manager)
        self.mobile_server = MobileMirrorServer(port=8484)
        self.mobile_server.workspaces_provider = self._get_mobile_workspaces
        self.mobile_server.report_provider = self._get_mobile_report
        self.mobile_server.followup_handler = self._handle_mobile_followup
        self.mobile_server.start()

        self._init_local_models()

        self.setWindowTitle(get_text("app_title", self.current_language))
        self.resize(1540, 920)
        self.setStyleSheet(self.theme_manager.get_stylesheet())
        self.theme_manager.apply_title_bar(self)

        self._build_ui()
        self._build_menu()
        self._refresh_corpus_ui()
        self._update_window_title()

        # Crash Autosave & Global Shortcuts
        autosave_sec = self.config_manager.get("autosave_interval_s", 60)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(max(5, autosave_sec) * 1000)
        self._autosave_timer.timeout.connect(self._on_autosave_timer)
        self._autosave_timer.start()

        self._setup_global_shortcuts()
        if restore_autosave:
            autosave_file = SESSION_CACHE_DIR / "autosave.omni"
            if autosave_file.exists():
                self._load_project_from_path(autosave_file)
        else:
            self._check_autosave_recovery()

    @property
    def active_workspace_pane(self) -> WorkspaceReportPane:
        return self.workspace_tabs.current_workspace_pane()

    @property
    def synthesis_viewer(self) -> QTextBrowser:
        return self.active_workspace_pane.synthesis_viewer

    @property
    def sweep_report_viewer(self) -> QTextBrowser:
        return self.active_workspace_pane.sweep_report_viewer

    @property
    def chat_drawer(self) -> FollowUpChatDrawer:
        return self.active_workspace_pane.chat_drawer

    @property
    def synthesis_toggle_btn(self) -> QPushButton:
        return self.active_workspace_pane.synthesis_toggle_btn

    @property
    def perspective_toggle_btn(self) -> QPushButton:
        return self.active_workspace_pane.perspective_toggle_btn

    @property
    def synthesis_translation_status(self) -> QLabel:
        return self.active_workspace_pane.synthesis_translation_status

    @property
    def perspective_translation_status(self) -> QLabel:
        return self.active_workspace_pane.perspective_translation_status

    @property
    def center_tabs(self) -> QTabWidget:
        return self.active_workspace_pane.inner_tabs

    @property
    def synthesis_original_text(self) -> str:
        if hasattr(self, "workspace_tabs"):
            return self.active_workspace_pane.synthesis_original_text
        return getattr(self, "_synthesis_original_text", "")

    @synthesis_original_text.setter
    def synthesis_original_text(self, val: str) -> None:
        self._synthesis_original_text = val
        if hasattr(self, "workspace_tabs"):
            self.active_workspace_pane.synthesis_original_text = val

    @property
    def synthesis_translated_text(self) -> str:
        if hasattr(self, "workspace_tabs"):
            return self.active_workspace_pane.synthesis_translated_text
        return getattr(self, "_synthesis_translated_text", "")

    @synthesis_translated_text.setter
    def synthesis_translated_text(self, val: str) -> None:
        self._synthesis_translated_text = val
        if hasattr(self, "workspace_tabs"):
            self.active_workspace_pane.synthesis_translated_text = val

    @property
    def synthesis_showing_translation(self) -> bool:
        if hasattr(self, "workspace_tabs"):
            return self.active_workspace_pane.synthesis_showing_translation
        return getattr(self, "_synthesis_showing_translation", False)

    @synthesis_showing_translation.setter
    def synthesis_showing_translation(self, val: bool) -> None:
        self._synthesis_showing_translation = val
        if hasattr(self, "workspace_tabs"):
            self.active_workspace_pane.synthesis_showing_translation = val

    @property
    def perspective_original_text(self) -> str:
        if hasattr(self, "workspace_tabs"):
            return self.active_workspace_pane.perspective_original_text
        return getattr(self, "_perspective_original_text", "")

    @perspective_original_text.setter
    def perspective_original_text(self, val: str) -> None:
        self._perspective_original_text = val
        if hasattr(self, "workspace_tabs"):
            self.active_workspace_pane.perspective_original_text = val

    @property
    def perspective_translated_text(self) -> str:
        if hasattr(self, "workspace_tabs"):
            return self.active_workspace_pane.perspective_translated_text
        return getattr(self, "_perspective_translated_text", "")

    @perspective_translated_text.setter
    def perspective_translated_text(self, val: str) -> None:
        self._perspective_translated_text = val
        if hasattr(self, "workspace_tabs"):
            self.active_workspace_pane.perspective_translated_text = val

    @property
    def perspective_showing_translation(self) -> bool:
        if hasattr(self, "workspace_tabs"):
            return self.active_workspace_pane.perspective_showing_translation
        return getattr(self, "_perspective_showing_translation", False)

    @perspective_showing_translation.setter
    def perspective_showing_translation(self, val: bool) -> None:
        self._perspective_showing_translation = val
        if hasattr(self, "workspace_tabs"):
            self.active_workspace_pane.perspective_showing_translation = val

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 8, 12, 8)
        root_layout.setSpacing(8)

        # Condensed Top Header Bar (Title + Compact Inline API Key + Model & Language Selectors)
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        self.title_label = QLabel("OmniResearch Studio")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 800; color: #58A6FF;")
        self.subtitle_label = QLabel(get_text("app_subtitle", self.current_language))
        self.subtitle_label.setStyleSheet("color: #94A3B8; font-size: 11px;")

        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(1)
        header_text_layout.addWidget(self.title_label)
        header_text_layout.addWidget(self.subtitle_label)

        self.api_banner = ApiKeyBanner(
            initial_key=self.config_manager.get_api_key(),
            lang=self.current_language,
        )
        self.api_banner.api_key_Saved.connect(self._on_api_key_saved)
        self.api_banner.api_key_Cleared.connect(self._on_api_key_cleared)

        model_bar = QHBoxLayout()
        model_bar.setSpacing(6)

        self.discovery_model_label = QLabel(get_text("label_discovery_model", self.current_language))
        self.discovery_model_combo = QComboBox()
        self.discovery_model_combo.addItems(AVAILABLE_MODELS)
        self.discovery_model_combo.setCurrentText(DEFAULT_DISCOVERY_MODEL)
        self.discovery_model_combo.currentTextChanged.connect(self._on_models_changed)

        self.synthesis_model_label = QLabel(get_text("label_synthesis_model", self.current_language))
        self.synthesis_model_combo = QComboBox()
        self.synthesis_model_combo.addItems(AVAILABLE_MODELS)
        self.synthesis_model_combo.setCurrentText(DEFAULT_SYNTHESIS_MODEL)
        self.synthesis_model_combo.currentTextChanged.connect(self._on_models_changed)

        self.language_label = QLabel(get_text("label_language", self.current_language))
        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("한국어", "ko")
        self.language_combo.setCurrentIndex(0)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)

        self.compression_label = QLabel(get_text("context_compression_label", self.current_language))
        self.compression_combo = QComboBox()
        self.compression_combo.addItems(["Auto", "64k", "128k", "Off"])
        self.compression_combo.setCurrentText("Auto")

        self.airgap_badge = QLabel(get_text("local_llm_badge", self.current_language))
        self.airgap_badge.setStyleSheet(
            "padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; "
            "background: #064E3B; color: #34D399; border: 1px solid #059669;"
        )
        self.airgap_badge.hide()

        model_bar.addWidget(self.discovery_model_label)
        model_bar.addWidget(self.discovery_model_combo)
        model_bar.addWidget(self.synthesis_model_label)
        model_bar.addWidget(self.synthesis_model_combo)
        model_bar.addWidget(self.compression_label)
        model_bar.addWidget(self.compression_combo)
        model_bar.addWidget(self.language_label)
        model_bar.addWidget(self.language_combo)
        model_bar.addWidget(self.airgap_badge)

        self.telemetry_label = QLabel()
        self.telemetry_label.setObjectName("TelemetryBadge")
        self.telemetry_label.setStyleSheet("padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; border: 1px solid #30363D; background: #161B22;")
        self.telemetry_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.telemetry_label.setToolTip(get_text("token_ledger_dialog_title", self.current_language))
        self.telemetry_label.mousePressEvent = lambda event: self._on_telemetry_clicked()
        model_bar.addWidget(self.telemetry_label)

        self.config_manager.config.discovery_model = self.discovery_model_combo.currentText()
        self.config_manager.config.synthesis_model = self.synthesis_model_combo.currentText()

        header_row.addLayout(header_text_layout, stretch=1)
        header_row.addWidget(self.api_banner)
        header_row.addLayout(model_bar)
        root_layout.addLayout(header_row)

        # Offline Status Alert Banner (Phase 7: Network Sentinel)
        self.offline_banner = QFrame()
        self.offline_banner.setStyleSheet(
            "QFrame { background-color: #78350F; border: 1px solid #F59E0B; border-radius: 6px; padding: 4px; }"
        )
        offline_layout = QHBoxLayout(self.offline_banner)
        offline_layout.setContentsMargins(10, 4, 10, 4)
        self.offline_label = QLabel(get_text("network_offline_banner", self.current_language))
        self.offline_label.setStyleSheet("color: #FEF3C7; font-weight: bold; font-size: 12px;")
        offline_layout.addWidget(self.offline_label)
        self.offline_banner.hide()
        root_layout.addWidget(self.offline_banner)

        # 3-Pane Horizontal Splitter (25% Left, 50% Center, 25% Right)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._build_left_pane())
        self.splitter.addWidget(self._build_center_pane())
        self.splitter.addWidget(self._build_right_pane())
        self.splitter.setStretchFactor(0, 25)
        self.splitter.setStretchFactor(1, 50)
        self.splitter.setStretchFactor(2, 25)
        self.splitter.setSizes([385, 770, 385])
        root_layout.addWidget(self.splitter, stretch=1)

        # Bottom Status Strip (status_label + eta_label + 0-100% progress_bar + red btn_cancel)
        status_strip = QFrame()
        status_strip.setStyleSheet(
            "QFrame { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 6px; }"
        )
        strip_layout = QHBoxLayout(status_strip)
        strip_layout.setContentsMargins(10, 5, 10, 5)
        strip_layout.setSpacing(12)

        self.spinner_label = QLabel("")
        self.spinner_label.setObjectName("StatusSpinnerLabel")
        self.spinner_label.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        self.spinner_label.setFixedWidth(16)
        self.spinner_label.setVisible(False)
        strip_layout.addWidget(self.spinner_label)

        self._spinner_idx = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(100)
        self._spinner_timer.timeout.connect(self._on_spinner_tick)

        self.status_label = QLabel(get_text("welcome_step1", self.current_language))
        self.status_label.setStyleSheet("color: #C9D1D9; font-size: 12px; border: none; background: transparent;")

        # Dedicated right-aligned control container to eliminate horizontal element shifting & layout jitter
        self.status_controls_container = QWidget()
        self.status_controls_container.setObjectName("StatusControlsContainer")
        self.status_controls_container.setStyleSheet("background: transparent; border: none;")
        status_controls_layout = QHBoxLayout(self.status_controls_container)
        status_controls_layout.setContentsMargins(0, 0, 0, 0)
        status_controls_layout.setSpacing(8)
        status_controls_layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Split ETA timer into two distinct labels inside an HBoxLayout:
        # eta_prefix_label (dynamic width based on font metrics) + eta_value_label (fixed 55px width, right-aligned)
        self.eta_container = QWidget()
        self.eta_container.setObjectName("StatusEtaContainer")
        self.eta_container.setStyleSheet("background: transparent; border: none;")
        eta_layout = QHBoxLayout(self.eta_container)
        eta_layout.setContentsMargins(0, 0, 0, 0)
        eta_layout.setSpacing(4)
        eta_layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.eta_prefix_label = QLabel("")
        self.eta_prefix_label.setObjectName("StatusEtaPrefixLabel")
        self.eta_prefix_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.eta_prefix_label.setStyleSheet(
            "color: #8B949E; font-size: 12px; font-weight: 500; border: none; background: transparent;"
        )

        self.eta_value_label = QLabel("")
        self.eta_value_label.setObjectName("StatusEtaValueLabel")
        self.eta_value_label.setFixedWidth(55)
        self.eta_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.eta_value_label.setStyleSheet(
            "color: #58A6FF; font-size: 12px; font-weight: 600; border: none; background: transparent;"
        )

        eta_layout.addWidget(self.eta_prefix_label)
        eta_layout.addWidget(self.eta_value_label)

        # Backwards compatibility alias
        self.eta_label = self.eta_value_label

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("StatusProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setFixedWidth(210)
        self.progress_bar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.btn_cancel = QPushButton(get_text("btn_cancel", self.current_language))
        self.btn_cancel.setObjectName("CancelTaskBtn")
        self.btn_cancel.setFixedWidth(90)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._on_cancel_active_task)

        status_controls_layout.addWidget(self.eta_container)
        status_controls_layout.addWidget(self.progress_bar)
        status_controls_layout.addWidget(self.btn_cancel)

        cm = ComputeManager.get_instance()
        self.compute_badge = QPushButton(cm.get_badge_text(self.current_language), self)
        self.compute_badge.setToolTip(cm.get_tooltip_text(self.current_language))
        self.compute_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.compute_badge.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #38BDF8; font-weight: 700; "
            "font-size: 11px; padding: 2px 10px; border-radius: 4px; border: 1px solid #334155; } "
            "QPushButton:hover { background-color: #334155; color: #7DD3FC; border-color: #0284C7; }"
        )
        self.compute_badge.clicked.connect(self._on_open_compute_dialog)

        strip_layout.addWidget(self.status_label, stretch=1)
        strip_layout.addWidget(self.compute_badge)
        self.btn_mobile_server = QPushButton("📱 Mobile LAN", self)
        self.btn_mobile_server.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #38BDF8; font-weight: 700; "
            "font-size: 11px; padding: 2px 8px; border-radius: 4px; border: 1px solid #334155; } "
            "QPushButton:hover { background-color: #334155; }"
        )
        self.btn_mobile_server.clicked.connect(self._on_open_mobile_dialog)
        strip_layout.addWidget(self.btn_mobile_server)
        strip_layout.addWidget(self.status_controls_container)

        root_layout.addWidget(status_strip)

        # Split-screen non-modal dockable Source Document Inspector
        self.source_dock = SourceInspectorDock(lang=self.current_language, parent=self)
        self.source_dock.analyze_figure_requested.connect(self._on_analyze_figure_requested)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.source_dock)
        self.source_dock.hide()

        # Split-screen SQLite FTS5 Full-Text Search Drawer
        self.search_dock = SearchDockWidget(search_index=self.search_index, lang=self.current_language, parent=self)
        self.search_dock.result_selected.connect(self._on_fts_result_selected)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.search_dock)
        self.search_dock.hide()

        # Mathematical Verification Sandbox Dock
        self.sandbox_dock = SandboxDock(lang=self.current_language, parent=self)
        self.sandbox_dock.insert_requested.connect(self._on_sandbox_insert_requested)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.sandbox_dock)
        self.sandbox_dock.hide()

    def _build_left_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(10)

        # Section 1: Reference Documents
        self.corpus_group = QGroupBox(escape_mnemonic(get_text("sec1_title", self.current_language)))
        corpus_layout = QVBoxLayout(self.corpus_group)

        upload_row = QHBoxLayout()
        self.upload_btn = QPushButton(get_text("btn_add_files", self.current_language))
        self.upload_btn.setObjectName("PrimaryActionBtn")
        self.upload_btn.clicked.connect(self._on_upload_files)

        self.btn_diff_compare = QPushButton(get_text("menu_diff_compare", self.current_language))
        self.btn_diff_compare.setObjectName("DiffCompareBtn")
        self.btn_diff_compare.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.btn_diff_compare.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #38BDF8; border: 1px solid #334155; "
            "border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: 600; } "
            "QPushButton:hover { background-color: #0F172A; }"
        )
        self.btn_diff_compare.clicked.connect(lambda: self._on_open_diff_dialog())

        self.clear_corpus_btn = QPushButton(get_text("btn_clear_all", self.current_language))
        self.clear_corpus_btn.clicked.connect(self._on_clear_corpus)

        upload_row.addWidget(self.upload_btn, stretch=1)
        upload_row.addWidget(self.btn_diff_compare)
        upload_row.addWidget(self.clear_corpus_btn)

        self.corpus_stats_label = QLabel()
        self.corpus_stats_label.setStyleSheet("color: #94A3B8; font-size: 12px;")

        self.source_list = SourceListWidget(lang=self.current_language)
        self.source_list.source_Selected.connect(self._on_source_selected)
        self.source_list.source_Toggled.connect(self._on_source_toggled)
        self.source_list.source_Removed.connect(self._on_source_removed)
        self.source_list.source_DoubleClicked.connect(self._open_source_inspector)

        corpus_layout.addLayout(upload_row)
        corpus_layout.addWidget(self.corpus_stats_label)
        corpus_layout.addWidget(self.source_list, stretch=1)

        # Section 2: OmniSweep Multi-Perspective Discovery
        self.sweep_group = QGroupBox(escape_mnemonic(get_text("sec2_title", self.current_language)))
        sweep_layout = QVBoxLayout(self.sweep_group)

        self.select_personas_label = QLabel(get_text("label_select_personas", self.current_language))
        sweep_layout.addWidget(self.select_personas_label)

        self.perspective_selector = PerspectiveSelectorWidget(
            perspectives=self.config_manager.config.perspectives,
            lang=self.current_language,
        )
        sweep_layout.addWidget(self.perspective_selector)

        self.discovery_prompt_label = QLabel(get_text("label_discovery_prompt", self.current_language))
        sweep_layout.addWidget(self.discovery_prompt_label)

        self.sweep_topic_input = QPlainTextEdit()
        self.sweep_topic_input.setMinimumHeight(135)
        self.sweep_topic_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.sweep_topic_input.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.sweep_topic_input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.sweep_topic_input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sweep_topic_input.setPlaceholderText(get_text("placeholder_discovery_prompt", self.current_language))
        sweep_layout.addWidget(self.sweep_topic_input, stretch=1)

        self.run_sweep_btn = QPushButton(get_text("btn_run_discovery", self.current_language))
        self.run_sweep_btn.setObjectName("OmniSweepActionBtn")
        self.run_sweep_btn.clicked.connect(self._on_run_omnisweep_discovery)
        sweep_layout.addWidget(self.run_sweep_btn)

        layout.addWidget(self.corpus_group, stretch=5)
        layout.addWidget(self.sweep_group, stretch=5)
        return pane

    def _build_center_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(10)

        self.query_group = QGroupBox(escape_mnemonic(get_text("sec3_title", self.current_language)))
        query_layout = QVBoxLayout(self.query_group)

        self.query_input = QPlainTextEdit()
        self.query_input.setMinimumHeight(95)
        self.query_input.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.query_input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.query_input.setPlaceholderText(get_text("placeholder_synthesis_query", self.current_language))

        action_row = QHBoxLayout()
        self.synthesize_btn = QPushButton(get_text("btn_synthesize", self.current_language))
        self.synthesize_btn.setObjectName("PrimaryActionBtn")
        self.synthesize_btn.clicked.connect(self._on_run_synthesis)

        self.export_btn = QToolButton()
        self.export_btn.setObjectName("ExportSplitBtn")
        self.export_btn.setText(get_text("btn_export_menu", self.current_language))
        self.export_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.export_menu = QMenu(self.export_btn)
        self.export_md_action = self.export_menu.addAction(get_text("export_as_md", self.current_language))
        self.export_html_action = self.export_menu.addAction(get_text("export_as_html", self.current_language))
        self.export_pdf_action = self.export_menu.addAction(get_text("export_as_pdf", self.current_language))
        self.export_bibtex_action = self.export_menu.addAction(get_text("export_bibtex", self.current_language))
        self.export_obsidian_action = self.export_menu.addAction(get_text("export_obsidian", self.current_language))
        self.export_marp_action = self.export_menu.addAction(get_text("export_marp", self.current_language))
        self.export_md_action.triggered.connect(self._on_export_synthesis)
        self.export_html_action.triggered.connect(self._on_export_html)
        self.export_pdf_action.triggered.connect(self._on_export_pdf)
        self.export_bibtex_action.triggered.connect(self._on_export_bibtex)
        self.export_obsidian_action.triggered.connect(self._on_export_obsidian)
        self.export_marp_action.triggered.connect(self._on_export_marp)
        self.export_btn.setMenu(self.export_menu)
        self.export_btn.clicked.connect(self._on_export_synthesis)
        self.export_btn.setEnabled(False)
        self.export_md_btn = self.export_btn  # backwards-compatible alias

        action_row.addWidget(self.synthesize_btn, stretch=1)
        action_row.addWidget(self.export_btn)

        options_row = QHBoxLayout()
        self.chk_gap_fill = QCheckBox(get_text("btn_gap_fill_toggle", self.current_language), self)
        self.chk_gap_fill.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: 600;")
        options_row.addWidget(self.chk_gap_fill)
        options_row.addStretch(1)

        query_layout.addWidget(self.query_input)
        query_layout.addLayout(action_row)
        query_layout.addLayout(options_row)

        self.output_group = QGroupBox(escape_mnemonic(get_text("workspace_group_title", self.current_language)))
        output_layout = QVBoxLayout(self.output_group)

        self.workspace_tabs = ResearchWorkspaceTabs(lang=self.current_language, parent=self)
        self.workspace_tabs.citation_clicked.connect(self.on_citation_clicked)
        self.workspace_tabs.chat_citation_clicked.connect(self.on_citation_index_clicked)
        self.workspace_tabs.entity_selected.connect(self._on_entity_selected)
        self.workspace_tabs.workspace_changed.connect(self._on_workspace_tab_changed)
        self.workspace_tabs.split_view_toggled.connect(self._on_split_view_state_changed)
        self._hook_workspace_pane(self.workspace_tabs.current_workspace_pane())

        output_layout.addWidget(self.workspace_tabs, stretch=1)

        layout.addWidget(self.query_group)
        layout.addWidget(self.output_group, stretch=1)
        return pane

    def _hook_workspace_pane(self, pane: WorkspaceReportPane) -> None:
        pane.chat_question_submitted.connect(self._on_chat_question_submitted)
        pane.chat_cleared.connect(self._on_chat_cleared)
        pane.toggle_synthesis_requested.connect(self._on_toggle_synthesis_language_view)
        pane.toggle_perspective_requested.connect(self._on_toggle_perspective_language_view)

    def add_new_workspace_tab(self, title: Optional[str] = None, state: Optional[WorkspaceTabState] = None) -> WorkspaceReportPane:
        pane = self.workspace_tabs.add_new_workspace(title=title, state=state)
        self._hook_workspace_pane(pane)
        self.update_telemetry()
        return pane

    def _on_workspace_tab_changed(self, index: int, pane: WorkspaceReportPane) -> None:
        if pane.query:
            self.query_input.setPlainText(pane.query)
        if pane.audio_directive:
            self.audio_focus_input.setPlainText(pane.audio_directive)
        if pane.audio_mp3_path and Path(pane.audio_mp3_path).exists():
            self.audio_player.load_file(pane.audio_mp3_path)
        self.update_telemetry()
        self._refresh_audit()
        has_content = bool(pane.synthesis_original_text or pane.synthesis_translated_text)
        self.export_btn.setEnabled(has_content)

    def _build_right_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.setSpacing(10)

        self.right_tabs = QTabWidget()

        # Tab 1: Grounding Citations Inspector & Epistemic Balance Radar
        citations_tab = QWidget()
        citations_layout = QVBoxLayout(citations_tab)
        citations_layout.setContentsMargins(0, 0, 0, 0)
        citations_layout.setSpacing(6)

        self.balance_radar = EpistemicBalanceWidget(lang=self.current_language, parent=self)
        self.citation_inspector = CitationInspectorWidget(lang=self.current_language)

        citations_layout.addWidget(self.balance_radar)
        citations_layout.addWidget(self.citation_inspector, stretch=1)
        self.right_tabs.addTab(citations_tab, get_text("tab_citations", self.current_language))

        # Tab 2: Audio Briefing Studio
        audio_tab = QWidget()
        audio_layout = QVBoxLayout(audio_tab)
        audio_layout.setContentsMargins(8, 8, 8, 8)
        audio_layout.setSpacing(8)

        self.audio_desc_label = QLabel(get_text("audio_studio_desc", self.current_language))
        self.audio_desc_label.setWordWrap(True)
        self.audio_desc_label.setStyleSheet("color: #94A3B8; font-size: 12px;")

        self.audio_focus_input = QPlainTextEdit()
        self.audio_focus_input.setMinimumHeight(120)
        self.audio_focus_input.setMaximumHeight(165)
        self.audio_focus_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.audio_focus_input.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.audio_focus_input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.audio_focus_input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.audio_focus_input.setPlaceholderText(get_text("placeholder_audio_directive", self.current_language))

        audio_btn_row = QHBoxLayout()
        self.generate_audio_btn = QPushButton(get_text("btn_generate_audio", self.current_language))
        self.generate_audio_btn.setObjectName("AudioActionBtn")
        self.generate_audio_btn.clicked.connect(self._on_generate_audio)

        self.export_audio_btn = QPushButton(get_text("btn_export_audio", self.current_language))
        self.export_audio_btn.setEnabled(False)
        self.export_audio_btn.clicked.connect(self._on_export_audio_script)

        self.render_audio_btn = QPushButton(get_text("btn_render_audio", self.current_language))
        self.render_audio_btn.setObjectName("AudioActionBtn")
        self.render_audio_btn.clicked.connect(self._on_render_audio_clicked)

        audio_btn_row.addWidget(self.generate_audio_btn, stretch=1)

        audio_btn_row2 = QHBoxLayout()
        audio_btn_row2.addWidget(self.render_audio_btn, stretch=1)
        audio_btn_row2.addWidget(self.export_audio_btn)

        self.dialogue_renderer = DialogueRendererWidget(lang=self.current_language)

        audio_layout.addWidget(self.audio_desc_label)
        audio_layout.addWidget(self.audio_focus_input)
        audio_layout.addLayout(audio_btn_row)
        audio_layout.addLayout(audio_btn_row2)
        audio_layout.addWidget(self.dialogue_renderer, stretch=1)

        self.audio_player = AudioPlayerWidget(lang=self.current_language)
        self.audio_player.audio_Saved.connect(
            lambda path: self._set_status(get_text("status_export_saved", self.current_language).format(path=path))
        )
        audio_layout.addWidget(self.audio_player)

        self.right_tabs.addTab(audio_tab, get_text("tab_audio_studio", self.current_language))

        layout.addWidget(self.right_tabs, stretch=1)
        return pane

    def _build_welcome_markdown(self) -> str:
        title = get_text("welcome_title", self.current_language)
        s1 = get_text("welcome_step1", self.current_language)
        s2 = get_text("welcome_step2", self.current_language)
        s3 = get_text("welcome_step3", self.current_language)
        return f"# {title}\n\n{s1}\n\n{s2}\n\n{s3}"

    def _set_viewer_markdown(self, viewer: QTextBrowser, markdown_text: str) -> None:
        """Render Markdown to clean HTML using `render_markdown_safely` with semantic alignment audit."""
        docs = getattr(self.corpus, "documents", None) if hasattr(self, "corpus") else None
        render_markdown_safely(viewer, markdown_text, documents=docs)

    # --- Live Token Streaming Slot ---

    def _on_stream_chunk_received(self, chunk: str, target_pane: str) -> None:
        """Append incoming live token chunks into the target viewer and re-render HTML safely."""
        if target_pane == "chat":
            self.chat_drawer.append_assistant_chunk(chunk)
            self.update_telemetry()
            return

        self._streaming_buffers[target_pane] = self._streaming_buffers.get(target_pane, "") + chunk
        current_buf = self._streaming_buffers[target_pane]

        if target_pane == "synthesis":
            render_markdown_safely(self.synthesis_viewer, current_buf)
            self.synthesis_viewer.moveCursor(QTextCursor.MoveOperation.End)
        elif target_pane == "perspective":
            render_markdown_safely(self.sweep_report_viewer, current_buf)
            self.sweep_report_viewer.moveCursor(QTextCursor.MoveOperation.End)

        self.update_telemetry()

    # --- Dynamic Bilingual Retranslation (English / 한국어) ---

    def _on_language_changed(self, index: int) -> None:
        lang_code = self.language_combo.itemData(index) or "en"
        self.current_language = "ko" if str(lang_code).startswith("ko") else "en"
        self.retranslate_ui()

        if self.current_language == "en":
            if self.synthesis_original_text:
                self.synthesis_showing_translation = False
                self._set_viewer_markdown(self.synthesis_viewer, self.synthesis_original_text)
                self.update_toggle_button_label(self.synthesis_toggle_btn, self.synthesis_showing_translation)
            if self.perspective_original_text:
                self.perspective_showing_translation = False
                self._set_viewer_markdown(self.sweep_report_viewer, self.perspective_original_text)
                self.update_toggle_button_label(self.perspective_toggle_btn, self.perspective_showing_translation)
        elif self.current_language == "ko":
            if self.synthesis_translated_text:
                self.synthesis_showing_translation = True
                self._set_viewer_markdown(self.synthesis_viewer, self.synthesis_translated_text)
                self.update_toggle_button_label(self.synthesis_toggle_btn, self.synthesis_showing_translation)
            elif self.synthesis_original_text and self.active_worker is None:
                self._start_translation(self.synthesis_original_text, target_pane="synthesis")

            if self.perspective_translated_text:
                self.perspective_showing_translation = True
                self._set_viewer_markdown(self.sweep_report_viewer, self.perspective_translated_text)
                self.update_toggle_button_label(self.perspective_toggle_btn, self.perspective_showing_translation)
            elif self.perspective_original_text and self.active_worker is None:
                self._start_translation(self.perspective_original_text, target_pane="perspective")

    def retranslate_ui(self) -> None:
        """Dynamically update all UI labels, group titles, tabs, buttons, and placeholders in real time."""
        lang = self.current_language
        self._update_window_title()
        self._retranslate_menu()
        self.subtitle_label.setText(get_text("app_subtitle", lang))

        self.discovery_model_label.setText(get_text("label_discovery_model", lang))
        self.synthesis_model_label.setText(get_text("label_synthesis_model", lang))
        if hasattr(self, "compression_label"):
            self.compression_label.setText(get_text("context_compression_label", lang))
        if hasattr(self, "airgap_badge"):
            self.airgap_badge.setText(get_text("local_llm_badge", lang))
        self.language_label.setText(get_text("label_language", lang))

        self.api_banner.retranslate_ui(lang)

        # Section 1 & Section 2 (Left pane)
        self.corpus_group.setTitle(escape_mnemonic(get_text("sec1_title", lang)))
        self.upload_btn.setText(get_text("btn_add_files", lang))
        if hasattr(self, "btn_diff_compare"):
            self.btn_diff_compare.setText(get_text("menu_diff_compare", lang))
        self.clear_corpus_btn.setText(get_text("btn_clear_all", lang))
        self.source_list.retranslate_ui(lang)
        self._update_corpus_stats()
        if hasattr(self, "balance_radar"):
            self.balance_radar.retranslate_ui(lang)
        if hasattr(self, "compute_badge"):
            self.compute_badge.setText(ComputeManager.get_instance().get_badge_text(lang))
            self.compute_badge.setToolTip(ComputeManager.get_instance().get_tooltip_text(lang))

        self.sweep_group.setTitle(escape_mnemonic(get_text("sec2_title", lang)))
        self.select_personas_label.setText(get_text("label_select_personas", lang))
        self.perspective_selector.retranslate_ui(lang)
        self.discovery_prompt_label.setText(get_text("label_discovery_prompt", lang))
        self.sweep_topic_input.setPlaceholderText(get_text("placeholder_discovery_prompt", lang))
        self.run_sweep_btn.setText(get_text("btn_run_discovery", lang))

        # Section 3 & Workspace (Center pane)
        self.query_group.setTitle(escape_mnemonic(get_text("sec3_title", lang)))
        self.query_input.setPlaceholderText(get_text("placeholder_synthesis_query", lang))
        self.synthesize_btn.setText(get_text("btn_synthesize", lang))
        self.export_btn.setText(get_text("btn_export_menu", lang))
        self.export_md_action.setText(get_text("export_as_md", lang))
        self.export_html_action.setText(get_text("export_as_html", lang))
        self.export_pdf_action.setText(get_text("export_as_pdf", lang))
        self.output_group.setTitle(escape_mnemonic(get_text("workspace_group_title", lang)))
        self.workspace_tabs.retranslate_ui(lang)
        self.update_telemetry()

        self.update_toggle_button_label(self.synthesis_toggle_btn, self.synthesis_showing_translation)
        self.update_toggle_button_label(self.perspective_toggle_btn, self.perspective_showing_translation)

        if self.synthesis_is_translating:
            self.synthesis_translation_status.setText(get_text("status_translating", lang))
        else:
            self.synthesis_translation_status.setText("")

        if self.perspective_is_translating:
            self.perspective_translation_status.setText(get_text("status_translating", lang))
        else:
            self.perspective_translation_status.setText("")

        if not self.synthesis_original_text and not self.synthesis_translated_text:
            self._set_viewer_markdown(self.synthesis_viewer, self._build_welcome_markdown())
        if not self.perspective_original_text and not self.perspective_translated_text:
            self._set_viewer_markdown(self.sweep_report_viewer, f"*{get_text('web_uris_help', lang)}*")

        # Section 4 (Right pane)
        self.right_tabs.setTabText(0, get_text("tab_citations", lang))
        self.right_tabs.setTabText(1, get_text("tab_audio_studio", lang))
        self.citation_inspector.retranslate_ui(lang)

        self.audio_desc_label.setText(get_text("audio_studio_desc", lang))
        self.audio_focus_input.setPlaceholderText(get_text("placeholder_audio_directive", lang))
        self.generate_audio_btn.setText(get_text("btn_generate_audio", lang))
        self.export_audio_btn.setText(get_text("btn_export_audio", lang))
        self.dialogue_renderer.retranslate_ui(lang)
        self.render_audio_btn.setText(get_text("btn_render_audio", lang))
        self.audio_player.retranslate_ui(lang)

        # Source Document Inspector Dock
        if hasattr(self, "source_dock"):
            self.source_dock.retranslate_ui(lang)

        # Full-Text Search Drawer Dock
        if hasattr(self, "search_dock"):
            self.search_dock.update_language(lang)

        if hasattr(self, "export_bibtex_action"):
            self.export_bibtex_action.setText(get_text("export_bibtex", lang))
        if hasattr(self, "export_obsidian_action"):
            self.export_obsidian_action.setText(get_text("export_obsidian", lang))
        if hasattr(self, "export_marp_action"):
            self.export_marp_action.setText(get_text("export_marp", lang))
        if hasattr(self, "offline_label"):
            self.offline_label.setText(get_text("network_offline_banner", lang))

        # Bottom Status Strip
        self.btn_cancel.setText(get_text("btn_cancel", lang))
        if self.active_worker is None:
            self._set_status(get_text("welcome_step1", lang))

    retranslateUi = retranslate_ui

    # --- Original / Translation Toggle Logic ---

    def update_toggle_button_label(self, button: QPushButton, is_showing_translation: bool) -> None:
        """Update toggle button text dynamically based on view state and active language."""
        key = "btn_show_original" if is_showing_translation else "btn_show_translation"
        button.setText(get_text(key, self.current_language))

    def _on_toggle_synthesis_language_view(self) -> None:
        """Toggle the Grounded Synthesis viewer between original and translated buffers."""
        if self.synthesis_showing_translation:
            self.synthesis_showing_translation = False
            if self.synthesis_original_text:
                self._set_viewer_markdown(self.synthesis_viewer, self.synthesis_original_text)
        else:
            if self.synthesis_translated_text:
                self.synthesis_showing_translation = True
                self._set_viewer_markdown(self.synthesis_viewer, self.synthesis_translated_text)
            elif self.synthesis_original_text and self.config_manager.has_api_key():
                self._start_translation(self.synthesis_original_text, target_pane="synthesis")
        self.update_toggle_button_label(self.synthesis_toggle_btn, self.synthesis_showing_translation)

    def _on_toggle_perspective_language_view(self) -> None:
        """Toggle the OmniSweep Perspective viewer between original and translated buffers."""
        if self.perspective_showing_translation:
            self.perspective_showing_translation = False
            if self.perspective_original_text:
                self._set_viewer_markdown(self.sweep_report_viewer, self.perspective_original_text)
        else:
            if self.perspective_translated_text:
                self.perspective_showing_translation = True
                self._set_viewer_markdown(self.sweep_report_viewer, self.perspective_translated_text)
            elif self.perspective_original_text and self.config_manager.has_api_key():
                self._start_translation(self.perspective_original_text, target_pane="perspective")
        self.update_toggle_button_label(self.perspective_toggle_btn, self.perspective_showing_translation)

    # --- Universal Task Locking, Progress & Cooperative Cancellation ---

    def _on_spinner_tick(self) -> None:
        self._spinner_idx = (self._spinner_idx + 1) % len(SPINNER_FRAMES)
        self.spinner_label.setText(SPINNER_FRAMES[self._spinner_idx])

    def _begin_task(self, worker: BaseCancellableWorker, initial_status: str) -> None:
        """Lock action buttons, reveal the red Cancel button, and connect progress/streaming/cancellation signals."""
        self.active_worker = worker
        self.spinner_label.setText(SPINNER_FRAMES[0])
        self.spinner_label.setVisible(True)
        self._spinner_timer.start()
        self.progress_bar.setRange(0, 0)
        self.run_sweep_btn.setEnabled(False)
        self.synthesize_btn.setEnabled(False)
        self.generate_audio_btn.setEnabled(False)
        self.upload_btn.setEnabled(False)
        self.clear_corpus_btn.setEnabled(False)
        self.synthesis_toggle_btn.setEnabled(False)
        self.perspective_toggle_btn.setEnabled(False)
        self.render_audio_btn.setEnabled(False)
        self.action_new_project.setEnabled(False)
        self.action_open_project.setEnabled(False)
        self.language_combo.setEnabled(False)
        if hasattr(self, "header_bar"):
            self.header_bar.set_task_running(True)
        self.chat_drawer.set_busy(True)

        self.progress_bar.setValue(0)
        self._update_eta_display(0, is_ready=False)
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setVisible(True)
        self._set_status(initial_status)

        worker.progress_Changed.connect(self._set_status)
        worker.progress_Detailed.connect(self._on_worker_detailed_progress)
        worker.chunk_received.connect(self._on_stream_chunk_received)
        if hasattr(worker, "telemetry_live"):
            worker.telemetry_live.connect(self._on_live_telemetry_updated)
        worker.cache_Hit.connect(self._on_worker_cache_hit)
        worker.cancelled.connect(self._on_worker_cancelled)
        if hasattr(worker, "task_canceled"):
            worker.task_canceled.connect(self._on_worker_cancelled)
        if hasattr(worker, "task_timed_out"):
            worker.task_timed_out.connect(self._on_worker_timed_out)

    _track_worker = _begin_task

    def _end_task(self, reset_progress: bool = False) -> None:
        """Unlock UI buttons and hide the Cancel button when a task finishes, fails, or cancels."""
        if hasattr(self, "_spinner_timer") and self._spinner_timer.isActive():
            self._spinner_timer.stop()
        if hasattr(self, "spinner_label"):
            self.spinner_label.setText("")
            self.spinner_label.setVisible(False)
        self.progress_bar.setRange(0, 100)
        if self.active_worker:
            try:
                self.active_worker.wait(1000)
            except Exception:
                pass
        self.active_worker = None
        self.run_sweep_btn.setEnabled(True)
        self.synthesize_btn.setEnabled(True)
        self.generate_audio_btn.setEnabled(True)
        self.upload_btn.setEnabled(True)
        self.clear_corpus_btn.setEnabled(True)
        self.synthesis_toggle_btn.setEnabled(True)
        self.perspective_toggle_btn.setEnabled(True)
        self.render_audio_btn.setEnabled(True)
        self.action_new_project.setEnabled(True)
        self.action_open_project.setEnabled(True)
        self.language_combo.setEnabled(True)
        if hasattr(self, "header_bar"):
            self.header_bar.set_task_running(False)
        self.chat_drawer.set_busy(False)

        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(True)
        if reset_progress:
            self.progress_bar.setValue(0)
            self._update_eta_display(0, is_ready=False)
        self.update_telemetry()

    def _on_live_telemetry_updated(self, _live_data: Optional[Dict[str, Any]] = None) -> None:
        """Handle progressive live cost and token accumulation updates."""
        self.update_telemetry()

    def _update_eta_display(self, eta_seconds: int, is_ready: bool = False) -> None:
        """Update ETA prefix and value labels with font metric adjustments."""
        if is_ready:
            self.eta_prefix_label.setText("")
            self.eta_prefix_label.setFixedWidth(0)
            self.eta_value_label.setText(get_text("eta_ready", self.current_language))
            return

        if eta_seconds > 0:
            prefix_text = "남은 시간:" if self.current_language == "ko" else "ETA:"
            self.eta_prefix_label.setText(prefix_text)
            fm = self.eta_prefix_label.fontMetrics()
            prefix_width = fm.horizontalAdvance(prefix_text) + 4
            self.eta_prefix_label.setFixedWidth(prefix_width)
            self.eta_value_label.setText(f"~{eta_seconds}s")
        else:
            self.eta_prefix_label.setText("")
            self.eta_prefix_label.setFixedWidth(0)
            self.eta_value_label.setText("")

    def _on_cancel_active_task(self) -> None:
        """Cooperatively request interruption of the active QThread worker and restore UI immediately."""
        if self.active_worker is not None:
            self.btn_cancel.setEnabled(False)
            self._set_status(get_text("status_canceling", self.current_language))
            if hasattr(self.active_worker, "stop_requested"):
                self.active_worker.stop_requested.set()
            self.active_worker.requestInterruption()
            if hasattr(self.active_worker, "cancel"):
                self.active_worker.cancel()
            self._on_worker_cancelled()

    def _on_worker_detailed_progress(self, percentage: int, eta_seconds: int, status_text: str) -> None:
        if percentage > 0:
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(max(0, min(100, percentage)))
        else:
            self.progress_bar.setRange(0, 0)
        if status_text == "CACHE_HIT":
            self._update_eta_display(0, is_ready=True)
            self._set_status(get_text("status_cache_hit", self.current_language))
            return

        if eta_seconds > 0:
            self._update_eta_display(eta_seconds)
        elif percentage >= 100:
            self._update_eta_display(0, is_ready=True)
        else:
            self._update_eta_display(0, is_ready=False)

        if status_text:
            self._set_status(status_text)

    def _on_worker_cache_hit(self) -> None:
        self.progress_bar.setValue(100)
        self._update_eta_display(0, is_ready=True)
        self._set_status(get_text("status_cache_hit", self.current_language))

    def _on_worker_cancelled(self) -> None:
        self.chat_drawer.abort_assistant_message()
        self.synthesis_is_translating = False
        self.perspective_is_translating = False
        self.synthesis_translation_status.setText("")
        self.perspective_translation_status.setText("")
        self._end_task(reset_progress=True)
        self._set_status(get_text("status_cancelled", self.current_language))

    def _start_translation(self, source_markdown: str, target_pane: str) -> None:
        """Spawn an asynchronous TranslationWorker for `synthesis` or `perspective`."""
        if not source_markdown.strip():
            return

        self._streaming_buffers[target_pane] = ""
        if target_pane == "synthesis":
            self.synthesis_is_translating = True
            self.synthesis_translation_status.setText(get_text("status_translating", self.current_language))
        else:
            self.perspective_is_translating = True
            self.perspective_translation_status.setText(get_text("status_translating", self.current_language))

        worker = TranslationWorker(
            config_manager=self.config_manager,
            markdown_text=source_markdown,
            target_pane=target_pane,
            target_lang="ko",
            cache_manager=self.cache_manager,
        )
        self._begin_task(worker, get_text("status_translating", self.current_language))
        worker.finished_Success.connect(self._on_translation_finished)
        worker.failed_Error.connect(lambda err, pane=target_pane: self._on_translation_failed(err, pane))
        self._translation_workers[target_pane] = worker
        worker.start()

    def _on_translation_finished(self, translated_text: str, target_pane: str) -> None:
        was_cache_hit = self.status_label.text() == get_text("status_cache_hit", self.current_language)
        self._end_task(reset_progress=False)
        self.progress_bar.setValue(100)

        if target_pane == "synthesis":
            self.synthesis_is_translating = False
            self.synthesis_translated_text = translated_text
            self.synthesis_showing_translation = True
            self._set_viewer_markdown(self.synthesis_viewer, translated_text)
            self.synthesis_translation_status.setText("")
            self.update_toggle_button_label(self.synthesis_toggle_btn, self.synthesis_showing_translation)
        elif target_pane == "perspective":
            self.perspective_is_translating = False
            self.perspective_translated_text = translated_text
            self.perspective_showing_translation = True
            self._set_viewer_markdown(self.sweep_report_viewer, translated_text)
            self.perspective_translation_status.setText("")
            self.update_toggle_button_label(self.perspective_toggle_btn, self.perspective_showing_translation)

        if was_cache_hit:
            self._set_status(get_text("status_cache_hit", self.current_language))

    def _on_translation_failed(self, error_message: str, target_pane: str) -> None:
        if target_pane == "synthesis":
            self.synthesis_is_translating = False
            self.synthesis_translation_status.setText("")
        else:
            self.perspective_is_translating = False
            self.perspective_translation_status.setText("")
        self._end_task(reset_progress=True)
        self._set_status(f"Translation warning: {error_message[:120]}")

    # --- Event Handlers & Slots ---

    def _on_api_key_saved(self, api_key: str) -> None:
        key_clean = api_key.strip()
        if key_clean:
            self.config_manager.save_api_key(key_clean)
            self._set_status("GEMINI_API_KEY saved and active in isolated user storage.")
            self.api_banner.update_state(True)
        else:
            self._on_api_key_cleared()

    def _on_api_key_cleared(self) -> None:
        self.config_manager.clear_api_key()
        self._set_status("GEMINI_API_KEY cleared. Stored credentials purged from QSettings and user storage.")
        self.api_banner.update_state(False)
        self.update_telemetry()

    def _on_models_changed(self) -> None:
        disc = self.discovery_model_combo.currentText()
        synth = self.synthesis_model_combo.currentText()
        self.config_manager.config.discovery_model = disc
        self.config_manager.config.synthesis_model = synth
        self.config_manager.config.audio_model = disc
        self.config_manager.save()
        if hasattr(self, "airgap_badge"):
            if is_local_model(disc) or is_local_model(synth):
                self.airgap_badge.show()
            else:
                self.airgap_badge.hide()

    def _on_upload_files(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Research Documents or Media",
            str(Path.home()),
            "All Supported Files (*.pdf *.docx *.txt *.md *.markdown *.mp3 *.wav *.m4a);;Documents (*.pdf *.docx *.txt *.md *.markdown);;Audio Media (*.mp3 *.wav *.m4a);;All Files (*.*)",
        )
        if not file_paths:
            return

        added = 0
        errors: List[str] = []
        for path in file_paths:
            try:
                ext = Path(path).suffix.lower()
                if ext in AUDIO_EXTENSIONS:
                    self._set_status(get_text("status_transcribing_audio", self.current_language))
                self.corpus.ingest_file(path)
                added += 1
            except Exception as exc:
                errors.append(f"{Path(path).name}: {exc}")

        self._refresh_corpus_ui()
        if errors:
            QMessageBox.warning(
                self,
                "Document Ingestion Warnings",
                f"Ingested {added} file(s).\n\nErrors:\n" + "\n".join(errors),
            )

    def _on_clear_corpus(self) -> None:
        self.corpus.clear()
        self.last_citations.clear()
        self.last_grounding_refs.clear()
        self._refresh_corpus_ui()
        self.citation_inspector.show_empty_state()

    def _on_open_diff_dialog(self, doc_a: Optional[Any] = None, doc_b: Optional[Any] = None) -> None:
        docs = self.corpus.documents
        if len(docs) < 2:
            QMessageBox.information(
                self,
                get_text("diff_dialog_title", self.current_language),
                "Please index at least two documents in the corpus to perform side-by-side text comparison."
                if self.current_language == "en"
                else "문서 비교를 수행하려면 코퍼스에 2개 이상의 문서를 먼저 등록하십시오.",
            )
            return

        dlg = DocumentDiffDialog(
            documents=docs,
            doc_a=doc_a or (docs[0] if len(docs) > 0 else None),
            doc_b=doc_b or (docs[1] if len(docs) > 1 else None),
            lang=self.current_language,
            parent=self,
        )
        dlg.exec()

    def _on_source_selected(self, cite_id: int) -> None:
        doc = self.corpus.get_by_cite_id(cite_id)
        if doc is not None:
            self.right_tabs.setCurrentIndex(0)
            self.citation_inspector.inspect_document(doc)
            self._set_status(f"Inspecting Source [{doc.cite_id}]: {doc.title}")

    def _on_source_toggled(self, cite_id: int, enabled: bool) -> None:
        self.corpus.set_enabled(cite_id, enabled)
        self._update_corpus_stats()

    def _on_source_removed(self, cite_id: int) -> None:
        if self.corpus.remove_document(cite_id):
            self._refresh_corpus_ui()
            self._set_status(f"Removed source [{cite_id}].")

    def _refresh_corpus_ui(self) -> None:
        self.source_list.refresh_sources(self.corpus.documents)
        if hasattr(self, "search_index"):
            self.search_index.index_corpus(self.corpus.documents)
        self._update_corpus_stats()

    def _update_corpus_stats(self) -> None:
        all_docs = self.corpus.documents
        enabled_docs = self.corpus.enabled_documents
        total_words = sum(d.word_count for d in enabled_docs)
        self.corpus_stats_label.setText(
            get_text("sources_count_label", self.current_language).format(
                active=len(enabled_docs),
                total=len(all_docs),
                words=f"{total_words:,}",
            )
        )
        if hasattr(self, "citation_inspector"):
            self._refresh_audit()
        if hasattr(self, "balance_radar"):
            self.balance_radar.update_balance(self.corpus.documents, audit=getattr(self, "last_audit", None))
        self.update_telemetry()

    def _ensure_api_key_ready(self, model_name: Optional[str] = None) -> bool:
        if model_name and is_local_model(model_name):
            return True
        if self.config_manager.has_api_key():
            return True
        from ui.dialogs.api_key_dialog import ApiKeyDialog
        dlg = ApiKeyDialog(lang=self.current_language, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and self.config_manager.has_api_key():
            self.api_banner.update_state(True)
            return True
        return False

    def _on_worker_timed_out(self, stage: str, idle_seconds: float) -> None:
        """Handle background worker inactivity watchdog timeout."""
        play_warning_alert()
        self._end_task(reset_progress=True)
        self._set_status(get_text("status_cancelled", self.current_language))
        dlg = DiagnosticTimeoutDialog(
            current_stage=stage,
            elapsed_seconds=idle_seconds,
            lang=self.current_language,
            parent=self,
        )
        dlg.exec()

    def _set_status(self, message: str) -> None:
        token = message.strip()
        if token in ("omnisweep_phase_1", "omnisweep_phase_2", "omnisweep_phase_3", "omnisweep_phase_4", "status_ready"):
            message = get_text(token, self.current_language)
        self.status_label.setText(message)

    # --- OmniSweep Discovery Execution ---

    def _on_run_omnisweep_discovery(self) -> None:
        if not self._ensure_api_key_ready():
            return

        topic = self.sweep_topic_input.toPlainText().strip()
        if not topic:
            topic = self.query_input.toPlainText().strip()
            if topic:
                self.sweep_topic_input.setPlainText(topic[:240])

        if not topic:
            QMessageBox.information(
                self,
                "Discovery Topic Required",
                "Please enter a research topic in the OmniSweep Discovery field before launching search.",
            )
            self.sweep_topic_input.setFocus()
            return

        perspectives = self.perspective_selector.get_selected_perspectives()
        if not perspectives:
            QMessageBox.information(
                self,
                "Select Perspectives",
                "Please check at least one expert perspective for OmniSweep discovery.",
            )
            return

        corpus_summary = "\n".join(
            f"- [{d.cite_id}] {d.title}: {d.summary_snippet}" for d in self.corpus.enabled_documents[:10]
        )

        active_discovery_model = self.discovery_model_combo.currentText()
        self._research_worker = OmniSweepWorker(
            config_manager=self.config_manager,
            topic=topic,
            perspectives=perspectives,
            corpus_summary=corpus_summary,
            model_override=active_discovery_model,
            cache_manager=self.cache_manager,
            scrape_status_text=get_text("status_scraping_web", self.current_language),
        )
        self._begin_task(
            self._research_worker,
            f"Running OmniSweep Web Discovery for '{topic[:60]}' ({active_discovery_model})...",
        )
        self._research_worker.finished_Success.connect(self._on_omnisweep_finished)
        self._research_worker.failed_Error.connect(self._on_worker_failed)
        self._research_worker.start()

    def _on_omnisweep_finished(self, result: OmniSweepDiscoveryResult) -> None:
        was_cache_hit = self.status_label.text() == get_text("status_cache_hit", self.current_language)
        self._end_task(reset_progress=False)
        self.progress_bar.setValue(100)

        md_sections: List[str] = [
            f"# OmniSweep Multi-Perspective Discovery: {result.topic}\n",
            f"*Model: `{result.model_used}` | Perspectives Investigated: **{len(result.perspective_reports)}** | "
            f"Verified Web Grounding URIs: **{len(result.all_grounding_references)}***\n",
        ]

        existing_titles = {d.title for d in self.corpus.documents}
        for report in result.perspective_reports:
            grounding_links_dicts = [
                {
                    "title": ref.tagged_title,
                    "uri": ref.uri,
                    "origin_tag": ref.origin_tag,
                }
                for ref in report.grounding_references
            ]
            primary_uri = (
                report.grounding_references[0].uri
                if report.grounding_references
                else f"omnisweep://{report.perspective_id}"
            )
            combined_query_text = " ".join(report.search_queries_executed) + " " + report.analysis_markdown
            report_origin = (
                report.grounding_references[0].origin_tag
                if report.grounding_references
                else detect_linguistic_origin_tag(
                    combined_query_text,
                    uri=primary_uri,
                    perspective_name=report.perspective_name,
                )
            )
            doc_title = format_multilingual_source_tag(
                report.perspective_name,
                report_origin,
                result.topic[:60],
            )
            if doc_title not in existing_titles:
                doc = self.corpus.add_web_document(
                    title=doc_title,
                    uri=primary_uri,
                    content=report.analysis_markdown,
                    perspective_name=report.perspective_name,
                    grounding_links=grounding_links_dicts,
                    origin_tag=report_origin,
                )
                cite_id = doc.cite_id
                existing_titles.add(doc_title)
            else:
                matched = next((d for d in self.corpus.documents if d.title == doc_title), None)
                cite_id = matched.cite_id if matched else 1

            # Ingest Tier-2 Scraped Articles / Snippets into reference corpus
            for scraped in getattr(report, "scraped_sources", []):
                tag = "[WEB FULL-TEXT]" if scraped.full_text else "[WEB SNIPPET]"
                scraped_title = f"{tag} [{report.perspective_name}] {scraped.title}"
                if scraped_title not in existing_titles:
                    self.corpus.add_web_document(
                        title=scraped_title,
                        uri=scraped.uri,
                        content=scraped.text,
                        perspective_name=report.perspective_name,
                        origin_tag=scraped.origin_tag,
                        extra_metadata={"full_text": scraped.full_text},
                    )
                    existing_titles.add(scraped_title)

            md_sections.append(f"---\n## [{cite_id}] {report.perspective_name} `[{report_origin}]`\n")
            md_sections.append(f"**Role Mandate:** *{report.perspective_role}*\n\n")
            if report.search_queries_executed:
                queries_str = ", ".join(f"`{q}`" for q in report.search_queries_executed)
                md_sections.append(f"**Google Search Queries Executed:** {queries_str}\n\n")
            md_sections.append(f"{report.analysis_markdown}\n\n")
            if report.grounding_references:
                md_sections.append("### Grounded Web Sources\n")
                for ref in report.grounding_references:
                    md_sections.append(f"- [{ref.tagged_title}]({ref.uri})\n")

        self.last_grounding_refs = result.all_grounding_references
        self._refresh_corpus_ui()

        combined_sweep_md = "\n".join(md_sections)
        self.perspective_original_text = combined_sweep_md
        self.perspective_translated_text = ""
        self.perspective_showing_translation = False
        self.perspective_translation_status.setText("")
        self.update_toggle_button_label(self.perspective_toggle_btn, self.perspective_showing_translation)

        self._set_viewer_markdown(self.sweep_report_viewer, combined_sweep_md)
        self.center_tabs.setCurrentIndex(1)

        self.citation_inspector.update_grounding_and_citations(
            citations=self.last_citations,
            web_references=self.last_grounding_refs,
        )
        self.right_tabs.setCurrentIndex(0)

        if not self.query_input.toPlainText().strip():
            self.query_input.setPlainText(
                f"Synthesize a comprehensive, critically grounded report on: {result.topic}. "
                f"Compare the findings across all perspectives and cite every factual claim."
            )

        if was_cache_hit:
            self._set_status(get_text("status_cache_hit", self.current_language))
        else:
            self._set_status(
                f"OmniSweep Discovery complete: added {len(result.perspective_reports)} perspective reports "
                f"and {len(result.all_grounding_references)} grounded web sources."
            )

        if self.current_language == "ko":
            self._start_translation(combined_sweep_md, target_pane="perspective")

    # --- Grounded Synthesis Execution ---

    def _on_run_synthesis(self) -> None:
        if not self._ensure_api_key_ready():
            return

        query = self.query_input.toPlainText().strip()
        if not query:
            topic_fallback = self.sweep_topic_input.toPlainText().strip()
            if topic_fallback:
                query = f"Provide a comprehensive grounded synthesis on: {topic_fallback}"
                self.query_input.setPlainText(query)
            else:
                QMessageBox.information(
                    self,
                    "Synthesis Query Required",
                    "Please enter a synthesis query in the center workspace.",
                )
                self.query_input.setFocus()
                return

        if not self.corpus.enabled_documents:
            QMessageBox.warning(
                self,
                "No Active Sources",
                "No enabled reference documents.\n\n"
                "Please upload local files (.pdf, .txt, .md) or run OmniSweep Web Discovery first.",
            )
            return

        active_synthesis_model = self.synthesis_model_combo.currentText()
        header = (
            f"# Grounded Synthesis Report\n"
            f"*Model: `{active_synthesis_model}` (Temperature = `0.0`) | "
            f"Active Sources: **{len(self.corpus.enabled_documents)}***\n\n---\n\n"
        )
        self._streaming_buffers["synthesis"] = header
        self.center_tabs.setCurrentIndex(0)

        comp_mode = self.compression_combo.currentText() if hasattr(self, "compression_combo") else "Auto"
        self._synthesis_worker = SynthesisWorker(
            config_manager=self.config_manager,
            query=query,
            documents=self.corpus.enabled_documents,
            model_override=active_synthesis_model,
            cache_manager=self.cache_manager,
            compression_mode=comp_mode,
        )
        self._begin_task(
            self._synthesis_worker,
            f"Executing zero-temperature grounded synthesis ({active_synthesis_model})...",
        )
        self._synthesis_worker.finished_Success.connect(self._on_synthesis_finished)
        self._synthesis_worker.failed_Error.connect(self._on_worker_failed)
        self._synthesis_worker.start()

    def _on_synthesis_finished(self, result: SynthesisResult) -> None:
        was_cache_hit = result.from_cache or (
            self.status_label.text() == get_text("status_cache_hit", self.current_language)
        )
        self._end_task(reset_progress=False)
        self.progress_bar.setValue(100)

        self.last_synthesis_markdown = result.markdown_report
        self.last_citations = result.citations_used
        self.last_synthesis_model = result.model_used
        self.export_btn.setEnabled(True)
        self._refresh_audit()

        header = (
            f"# Grounded Synthesis Report\n"
            f"*Model: `{result.model_used}` (Temperature = `0.0`) | "
            f"Active Sources: **{result.total_sources_provided}** | "
            f"Verified Citations: **{len(result.citations_used)}***\n\n---\n\n"
        )
        full_markdown = header + result.markdown_report
        self.synthesis_original_text = full_markdown
        self.synthesis_translated_text = ""
        self.synthesis_showing_translation = False
        self.synthesis_translation_status.setText("")
        self.update_toggle_button_label(self.synthesis_toggle_btn, self.synthesis_showing_translation)

        if hasattr(result, "critic_verdicts") and result.critic_verdicts:
            if isinstance(self.synthesis_viewer, StreamingMarkdownViewer):
                self.synthesis_viewer.set_critic_verdicts(result.critic_verdicts)
        self._set_viewer_markdown(self.synthesis_viewer, full_markdown)
        if hasattr(self, "active_workspace_pane"):
            self.active_workspace_pane.update_synthesis_views(full_markdown)
        self.center_tabs.setCurrentIndex(0)

        self.citation_inspector.update_grounding_and_citations(
            citations=self.last_citations,
            web_references=self.last_grounding_refs,
        )
        self.right_tabs.setCurrentIndex(0)

        if was_cache_hit:
            self._set_status(get_text("status_cache_hit", self.current_language))
        else:
            self._set_status(
                f"Synthesis complete: {len(result.citations_used)} unique sources cited across report."
            )

        if hasattr(self, "workspace_tabs"):
            self.workspace_tabs.auto_name_active_tab(self.query_input.toPlainText() or result.query or "Research Workspace")
        self.update_telemetry()

        # Phase 11: Update Knowledge Graph
        if hasattr(self, "knowledge_graph_engine"):
            self.knowledge_graph_engine.build_from_documents(self.corpus.get_all_documents())
            if hasattr(self, "active_workspace_pane") and hasattr(self.active_workspace_pane, "knowledge_graph_viewer"):
                self.active_workspace_pane.knowledge_graph_viewer.load_graph(self.knowledge_graph_engine)

        if self.current_language == "ko":
            self._start_translation(full_markdown, target_pane="synthesis")

        # Phase 11: Recursive Gap-Filling (Auto-Deepening Loop)
        if hasattr(self, "chk_gap_fill") and self.chk_gap_fill.isChecked():
            self._trigger_gap_fill(full_markdown, result.query)

    # --- Phase 11: Sovereign Workflow Handlers ---

    def _trigger_gap_fill(self, report_markdown: str, topic: str) -> None:
        """Trigger autonomous deepening loop to fill empirical gaps."""
        self._begin_task(None, "Running Recursive Autonomous Gap-Filler (Deepening Loop)...")
        active_model = self._get_active_synthesis_model()
        self._gap_fill_worker = GapFillWorker(
            report_markdown=report_markdown,
            corpus=self.corpus,
            base_topic=topic or self.query_input.toPlainText().strip(),
            lang=self.current_language,
            config_manager=self.config_manager,
            model_name=active_model,
            parent=self,
        )
        self.active_worker = self._gap_fill_worker
        self._gap_fill_worker.status_changed.connect(self._set_status)
        self._gap_fill_worker.gap_fill_finished.connect(self._on_gap_fill_finished)
        self._gap_fill_worker.failed_Error.connect(self._on_gap_fill_failed)
        self._gap_fill_worker.start()

    def _on_gap_fill_finished(self, addendum: str, new_docs: list) -> None:
        self._end_task()
        if addendum:
            updated = self.synthesis_original_text + addendum
            self.synthesis_original_text = updated
            self._set_viewer_markdown(self.synthesis_viewer, updated)
            if hasattr(self, "active_workspace_pane"):
                self.active_workspace_pane.update_synthesis_views(updated)
            self._refresh_corpus_ui()
            self._refresh_audit()
            if hasattr(self, "knowledge_graph_engine"):
                self.knowledge_graph_engine.build_from_documents(self.corpus.get_all_documents())
                if hasattr(self, "active_workspace_pane") and hasattr(self.active_workspace_pane, "knowledge_graph_viewer"):
                    self.active_workspace_pane.knowledge_graph_viewer.load_graph(self.knowledge_graph_engine)
            self._set_status(f"Autonomous Gap-Filling complete: +{len(new_docs)} primary source(s) ingested.")
        else:
            self._set_status("Autonomous Gap-Filling complete (No unresolved gaps detected).")

    def _on_gap_fill_failed(self, err_msg: str) -> None:
        self._end_task()
        self._set_status(f"Gap-fill error: {err_msg}")

    def _on_sandbox_insert_requested(self, md: str) -> None:
        """Append mathematical verification output & plot markdown to the active report."""
        if hasattr(self, "active_workspace_pane"):
            updated = self.synthesis_original_text + "\n\n" + md
            self.synthesis_original_text = updated
            self._set_viewer_markdown(self.synthesis_viewer, updated)
            self.active_workspace_pane.update_synthesis_views(updated)
            self._set_status("Appended mathematical verification to report.")

    def _toggle_sandbox_dock(self) -> None:
        if self.sandbox_dock.isVisible():
            self.sandbox_dock.hide()
        else:
            self.sandbox_dock.show()
            self.sandbox_dock.raise_()

    def _on_open_mobile_dialog(self) -> None:
        dlg = MobileServerDialog(server=self.mobile_server, lang=self.current_language, parent=self)
        dlg.exec()

    def _on_open_vault_dialog(self) -> None:
        dlg = VaultSyncDialog(current_project_path=self.current_project_path, lang=self.current_language, parent=self)
        dlg.restore_completed.connect(self._load_project_from_path)
        dlg.exec()

    def _on_entity_selected(self, entity_name: str) -> None:
        """Search corpus via FTS5 when entity node is double-clicked in Knowledge Graph."""
        if hasattr(self, "search_dock"):
            self.search_dock.show()
            self.search_dock.raise_()
            self.search_dock.search_input.setText(entity_name)
            self.search_dock._run_search()
        self._set_status(f"FTS5 Search for entity: {entity_name}")

    def _get_mobile_workspaces(self) -> list:
        workspaces = []
        if hasattr(self, "workspace_tabs"):
            for i in range(self.workspace_tabs.count()):
                pane = self.workspace_tabs.widget(i)
                if isinstance(pane, WorkspaceReportPane):
                    workspaces.append({
                        "id": pane.tab_id,
                        "title": pane.title,
                        "has_audio": bool(pane.audio_mp3_path),
                    })
        if not workspaces:
            workspaces.append({"id": "active", "title": "Active Workspace", "has_audio": False})
        return workspaces

    def _get_mobile_report(self, workspace_id: str) -> dict:
        pane = self.active_workspace_pane
        raw_text = pane.synthesis_original_text or self.synthesis_original_text or "# Grounded Synthesis Report\n\nNo report generated yet."
        import markdown
        html = markdown.markdown(raw_text, extensions=["tables", "fenced_code"])
        return {
            "workspace_id": workspace_id,
            "title": pane.title,
            "html": html,
        }

    def _handle_mobile_followup(self, question: str) -> str:
        from core.followup_engine import FollowUpEngine
        engine = FollowUpEngine(config_manager=self.config_manager)
        report_text = self.synthesis_original_text or ""
        corpus_docs = self.corpus.get_all_documents()
        return engine.answer_question(question=question, report_markdown=report_text, corpus_documents=corpus_docs)

    # --- Audio Studio Execution ---

    def _on_generate_audio(self) -> None:
        if not self._ensure_api_key_ready():
            return

        if not self.last_synthesis_markdown and not self.corpus.enabled_documents:
            QMessageBox.warning(
                self,
                "Source Material Required",
                "Please run a Grounded Synthesis or index documents before generating an Audio Briefing.",
            )
            return

        topic = (
            self.sweep_topic_input.toPlainText().strip()
            or self.query_input.toPlainText().strip()[:120]
            or "OmniResearch Deep-Dive Briefing"
        )

        self._streaming_buffers["audio"] = ""
        self.audio_player.release()
        active_discovery_model = self.discovery_model_combo.currentText()
        self._audio_worker = AudioWorker(
            config_manager=self.config_manager,
            topic_or_query=topic,
            synthesis_markdown=self.last_synthesis_markdown,
            documents=self.corpus.enabled_documents,
            focus_instructions=self.audio_focus_input.toPlainText().strip(),
            model_override=active_discovery_model,
            cache_manager=self.cache_manager,
            language=self.current_language,
            render_audio=True,
        )
        self._begin_task(
            self._audio_worker,
            f"Generating two-host conversational Audio Overview ({active_discovery_model})...",
        )
        self._audio_worker.script_ready.connect(self._on_audio_script_ready)
        self._audio_worker.audio_ready.connect(self._on_audio_rendered)
        self._audio_worker.audio_failed.connect(self._on_audio_render_failed)
        self._audio_worker.finished_Success.connect(self._on_audio_finished)
        self._audio_worker.failed_Error.connect(self._on_worker_failed)
        self._audio_worker.start()

    def _on_render_audio_clicked(self) -> None:
        """Render the existing dialogue script into neural speech without regenerating text."""
        if not self.last_podcast_script:
            self._set_status(get_text("audio_script_need_first", self.current_language))
            return

        self.audio_player.release()
        active_discovery_model = self.discovery_model_combo.currentText()
        self._audio_worker = AudioWorker(
            config_manager=self.config_manager,
            topic_or_query=self.last_podcast_script.title,
            synthesis_markdown=self.last_synthesis_markdown,
            documents=self.corpus.enabled_documents,
            focus_instructions=self.audio_focus_input.toPlainText().strip(),
            model_override=active_discovery_model,
            cache_manager=self.cache_manager,
            language=self.current_language,
            render_audio=True,
            existing_script=self.last_podcast_script,
        )
        self._begin_task(
            self._audio_worker,
            get_text("btn_render_audio", self.current_language) + "...",
        )
        self._audio_worker.audio_ready.connect(self._on_audio_rendered)
        self._audio_worker.audio_failed.connect(self._on_audio_render_failed)
        self._audio_worker.finished_Success.connect(self._on_audio_finished)
        self._audio_worker.failed_Error.connect(self._on_worker_failed)
        self._audio_worker.start()

    def _on_audio_script_ready(self, script: PodcastScript) -> None:
        self.last_podcast_script = script
        self.dialogue_renderer.render_script(script)
        self.export_audio_btn.setEnabled(True)
        self.render_audio_btn.setEnabled(True)
        self.right_tabs.setCurrentIndex(1)

    def _on_audio_rendered(self, mp3_path: str) -> None:
        self.last_audio_path = mp3_path
        self.audio_player.load_file(mp3_path)
        self._set_status(get_text("status_audio_ready", self.current_language))

    def _on_audio_render_failed(self, err: str) -> None:
        self._audio_render_error = err
        self._set_status(get_text("status_audio_failed", self.current_language).format(error=err))

    def _on_audio_finished(self, script: PodcastScript) -> None:
        was_cache_hit = script.from_cache or (
            self.status_label.text() == get_text("status_cache_hit", self.current_language)
        )
        self._end_task(reset_progress=False)
        self.progress_bar.setValue(100)

        self.last_podcast_script = script
        self.export_audio_btn.setEnabled(True)
        self.render_audio_btn.setEnabled(True)
        self.dialogue_renderer.render_script(script)
        self.right_tabs.setCurrentIndex(1)

        if was_cache_hit:
            self._set_status(get_text("status_cache_hit", self.current_language))
        elif self.last_audio_path and Path(self.last_audio_path).exists():
            self._set_status(get_text("status_audio_ready", self.current_language))
        else:
            self._set_status(
                f"Audio Briefing generated: '{script.title}' ({len(script.turns)} conversational turns)."
            )

    def _on_worker_failed(self, error_detail: str) -> None:
        self._end_task(reset_progress=True)
        if error_detail.strip() == RATE_LIMIT_USER_MESSAGE or is_rate_limit_error(Exception(error_detail)):
            self._set_status("API Rate Limit Exceeded (429). Please wait or adjust quota settings.")
            QMessageBox.warning(
                self,
                "API Rate Limit Exceeded (429)",
                RATE_LIMIT_USER_MESSAGE,
            )
            return

        self._set_status("Operation failed. See error dialog for details.")
        short_err = error_detail.splitlines()[0] if error_detail else "Unknown error"
        QMessageBox.critical(
            self,
            "Execution Error",
            f"An error occurred while communicating with Gemini:\n\n{short_err}\n\nDetails:\n{error_detail[:1200]}",
        )

    # --- Export Actions ---

    def _on_export_synthesis(self) -> None:
        active_text = (
            self.synthesis_translated_text
            if (self.synthesis_showing_translation and self.synthesis_translated_text)
            else self.synthesis_original_text or self.last_synthesis_markdown
        )
        if not active_text:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Report (.md)",
            str(Path.home() / "omniresearch_synthesis.md"),
            "Markdown Files (*.md);;Text Files (*.txt)",
        )
        if save_path:
            Path(save_path).write_text(active_text, encoding="utf-8")
            self._set_status(f"Saved report to {save_path}")

    def _on_export_audio_script(self) -> None:
        if not self.last_podcast_script:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Script (.txt)",
            str(Path.home() / "omniresearch_audio_script.txt"),
            "Text Files (*.txt);;Markdown Files (*.md)",
        )
        if save_path:
            lines = [f"# {self.last_podcast_script.title}\n"]
            for turn in self.last_podcast_script.turns:
                lines.append(f"**{turn.speaker} ({turn.role_tag}):** {turn.text}\n")
            Path(save_path).write_text("\n".join(lines), encoding="utf-8")
            self._set_status(f"Saved script to {save_path}")

    # --- Source Inspection & Citation Navigation ---

    def _open_source_inspector(self, cite_id: int) -> None:
        doc = self.corpus.get_document(cite_id)
        if doc is not None:
            self.source_dock.inspect_document(doc, self.current_language)
            self.source_dock.show()
            self.source_dock.raise_()

    def on_citation_clicked(self, url: QUrl) -> None:
        url_str = url.toString() if isinstance(url, QUrl) else str(url)
        if not url_str.startswith("cite:"):
            QDesktopServices.openUrl(QUrl(url_str))
            return
        parts = url_str.split(":")
        if len(parts) >= 2:
            try:
                cite_id = int(parts[1])
                if len(parts) >= 4 and parts[2] == "time":
                    time_str = ":".join(parts[3:])
                    self._handle_timestamp_citation_clicked(cite_id, time_str)
                    return
                page_num = int(parts[2]) if (len(parts) >= 3 and parts[2].isdigit()) else None
                self.on_citation_index_clicked(cite_id, page_num=page_num)
            except ValueError:
                pass

    def _handle_timestamp_citation_clicked(self, cite_id: int, time_str: str) -> None:
        doc = self.corpus.get_document(cite_id)
        sec = parse_timestamp_to_seconds(time_str)
        if doc is not None:
            raw_uri = str(doc.path_or_uri)
            if is_youtube_url(raw_uri) or "youtube.com" in raw_uri or "youtu.be" in raw_uri:
                sep = "&" if "?" in raw_uri else "?"
                seek_url = f"{raw_uri}{sep}t={sec}s"
                QDesktopServices.openUrl(QUrl(seek_url))
                self._set_status(f"Opening YouTube video at [{time_str}] ({sec}s)...")
            else:
                self.source_dock.inspect_document(doc, self.current_language)
                self.source_dock.show()
                self.source_dock.raise_()
                self._set_status(f"Inspecting Source [{cite_id}] at timestamp [{time_str}]...")
        else:
            self._set_status(get_text("status_citation_missing", self.current_language).format(n=cite_id))

    def _on_analyze_figure_requested(self, figure_path: str, figure_title: str) -> None:
        """Triggered from SourceInspectorDock to analyze a technical figure with Gemini Vision."""
        if not self._ensure_api_key_ready():
            return

        self._set_status(get_text("vision_status_analyzing", self.current_language))
        self.progress_bar.setValue(25)

        worker = VisionAnalysisWorker(
            figure_path=figure_path,
            figure_title=figure_title,
            query=self.query_input.toPlainText() or self.sweep_topic_input.toPlainText(),
            model_name=self.synthesis_model_combo.currentText(),
            config_manager=self.config_manager,
            parent=self,
        )
        self._vision_worker = worker
        worker.finished_Success.connect(self._on_figure_vision_finished)
        worker.failed_Error.connect(self._on_figure_vision_failed)
        worker.start()

    def _on_figure_vision_finished(self, fig_path: str, fig_title: str, analysis_markdown: str) -> None:
        self.progress_bar.setValue(100)
        self._set_status(f"Vision analysis complete for {fig_title}.")

        # Inject into active workspace pane report / notes
        note = (
            f"\n\n---\n\n"
            f"### 📐 {get_text('vision_note_title', self.current_language)}: {fig_title}\n\n"
            f"![{fig_title}]({fig_path})\n\n"
            f"{analysis_markdown}\n\n---\n"
        )
        current_report = self.synthesis_original_text or self.last_synthesis_markdown or ""
        updated_report = current_report + note
        self.synthesis_original_text = updated_report
        self._set_viewer_markdown(self.synthesis_viewer, updated_report)
        if hasattr(self, "active_workspace_pane"):
            self.active_workspace_pane.update_synthesis_views(updated_report)

    def _on_figure_vision_failed(self, error_msg: str) -> None:
        self._set_status(f"Vision analysis failed: {error_msg}")
        QMessageBox.warning(self, "Vision Analysis Error", error_msg[:1000])

    def on_citation_index_clicked(self, cite_id: int, page_num: Optional[int] = None) -> None:
        doc = self.corpus.get_document(cite_id)
        if page_num is not None:
            if doc is not None:
                self.source_dock.inspect_document(doc, self.current_language, target_page=page_num)
                self.source_dock.show()
                self.source_dock.raise_()
                self._set_status(f"Navigated to source [{cite_id}] page {page_num}.")
            else:
                self._set_status(get_text("status_citation_missing", self.current_language).format(n=cite_id))
            return

        self.right_tabs.setCurrentIndex(0)
        found = self.citation_inspector.focus_citation(cite_id)
        if not found:
            if doc is not None:
                self.source_dock.inspect_document(doc, self.current_language)
                self.source_dock.show()
                self.source_dock.raise_()
                self._set_status(get_text("status_citation_focused", self.current_language).format(n=cite_id))
            else:
                self._set_status(get_text("status_citation_missing", self.current_language).format(n=cite_id))
        else:
            self._set_status(get_text("status_citation_focused", self.current_language).format(n=cite_id))

    def _refresh_audit(self) -> None:
        active_text = (
            self.synthesis_translated_text
            if (self.synthesis_showing_translation and self.synthesis_translated_text)
            else self.synthesis_original_text or self.last_synthesis_markdown
        )
        if not active_text:
            self.last_audit = None
            if hasattr(self, "citation_inspector"):
                self.citation_inspector.set_audit(None)
            return
        self.last_audit = audit_citations(active_text, self.corpus.get_all_documents())
        if hasattr(self, "citation_inspector"):
            self.citation_inspector.set_audit(self.last_audit)
        if hasattr(self, "balance_radar"):
            self.balance_radar.update_balance(self.corpus.documents, audit=self.last_audit)

    # --- Menus, Project Persistence & Exporters ---

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        self.file_menu = menubar.addMenu(get_text("menu_file", self.current_language))

        self.action_new_project = QAction(get_text("action_new_project", self.current_language), self)
        self.action_new_project.setShortcut(QKeySequence.StandardKey.New)
        self.action_new_project.triggered.connect(self._on_new_project)
        self.file_menu.addAction(self.action_new_project)

        self.action_open_project = QAction(get_text("action_open_project", self.current_language), self)
        self.action_open_project.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open_project.triggered.connect(self._on_open_project)
        self.file_menu.addAction(self.action_open_project)

        self.action_save_project = QAction(get_text("action_save_project", self.current_language), self)
        self.action_save_project.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save_project.triggered.connect(self._on_save_project)
        self.file_menu.addAction(self.action_save_project)

        self.action_save_as_project = QAction(get_text("action_save_as_project", self.current_language), self)
        self.action_save_as_project.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.action_save_as_project.triggered.connect(self._on_save_as_project)
        self.file_menu.addAction(self.action_save_as_project)

        self.action_checkpoints = QAction(get_text("menu_checkpoints", self.current_language), self)
        self.action_checkpoints.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self.action_checkpoints.triggered.connect(self._on_manage_checkpoints)
        self.file_menu.addAction(self.action_checkpoints)

        self.action_vault_backup = QAction(get_text("menu_vault_backup", self.current_language), self)
        self.action_vault_backup.triggered.connect(self._on_open_vault_dialog)
        self.file_menu.addAction(self.action_vault_backup)

        # Edit Menu (Phase 12: Workstation Preferences)
        self.edit_menu = menubar.addMenu(get_text("menu_edit", self.current_language))
        self.action_preferences = QAction(get_text("menu_preferences", self.current_language), self)
        self.action_preferences.setShortcut(QKeySequence("Ctrl+,"))
        self.action_preferences.triggered.connect(self._on_open_preferences)
        self.edit_menu.addAction(self.action_preferences)

        # View Menu (Phase 7: Split View, Themes, Typography)
        self.view_menu = menubar.addMenu(get_text("menu_view", self.current_language))

        self.action_split_view = QAction(get_text("menu_split_view", self.current_language), self)
        self.action_split_view.setShortcut(QKeySequence("Ctrl+Shift+D"))
        self.action_split_view.setCheckable(True)
        self.action_split_view.toggled.connect(self._on_menu_split_view_toggled)
        self.view_menu.addAction(self.action_split_view)

        # Tools Menu (Phase 11: Mobile LAN Server, Mathematical Sandbox)
        self.tools_menu = menubar.addMenu("Tools" if self.current_language == "en" else "도구")

        self.action_mobile_server = QAction(get_text("menu_mobile_server", self.current_language), self)
        self.action_mobile_server.triggered.connect(self._on_open_mobile_dialog)
        self.tools_menu.addAction(self.action_mobile_server)

        self.action_sandbox = QAction(get_text("dock_sandbox_title", self.current_language), self)
        self.action_sandbox.triggered.connect(self._toggle_sandbox_dock)
        self.tools_menu.addAction(self.action_sandbox)

        self.view_menu.addSeparator()

        # Theme Submenu
        self.theme_menu = self.view_menu.addMenu(get_text("menu_theme", self.current_language))
        self.theme_action_dark = QAction(get_text("theme_dark", self.current_language), self)
        self.theme_action_dark.setCheckable(True)
        self.theme_action_dark.setChecked(self.theme_manager.current_theme == "dark")
        self.theme_action_dark.triggered.connect(lambda: self._on_theme_selected("dark"))
        self.theme_menu.addAction(self.theme_action_dark)

        self.theme_action_oled = QAction(get_text("theme_oled", self.current_language), self)
        self.theme_action_oled.setCheckable(True)
        self.theme_action_oled.setChecked(self.theme_manager.current_theme == "oled")
        self.theme_action_oled.triggered.connect(lambda: self._on_theme_selected("oled"))
        self.theme_menu.addAction(self.theme_action_oled)

        self.theme_action_light = QAction(get_text("theme_light", self.current_language), self)
        self.theme_action_light.setCheckable(True)
        self.theme_action_light.setChecked(self.theme_manager.current_theme == "light")
        self.theme_action_light.triggered.connect(lambda: self._on_theme_selected("light"))
        self.theme_menu.addAction(self.theme_action_light)

        # Typography Submenu
        self.typography_menu = self.view_menu.addMenu(get_text("menu_typography", self.current_language))
        self.fonts_menu = self.typography_menu.addMenu("Font Family" if self.current_language == "en" else "글꼴 선택")
        self.font_actions: List[QAction] = []
        for font_name in AVAILABLE_FONTS:
            act = QAction(font_name, self)
            act.setCheckable(True)
            act.setChecked(self.theme_manager.current_font == font_name)
            act.triggered.connect(lambda checked, fn=font_name: self._on_font_selected(fn))
            self.fonts_menu.addAction(act)
            self.font_actions.append(act)

        self.typography_menu.addSeparator()
        self.action_zoom_in = QAction(get_text("zoom_in", self.current_language), self)
        self.action_zoom_in.setShortcut(QKeySequence("Ctrl+="))
        self.action_zoom_in.triggered.connect(self._on_zoom_in)
        self.typography_menu.addAction(self.action_zoom_in)

        self.action_zoom_out = QAction(get_text("zoom_out", self.current_language), self)
        self.action_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        self.action_zoom_out.triggered.connect(self._on_zoom_out)
        self.typography_menu.addAction(self.action_zoom_out)

        self.action_zoom_reset = QAction(get_text("zoom_reset", self.current_language), self)
        self.action_zoom_reset.setShortcut(QKeySequence("Ctrl+0"))
        self.action_zoom_reset.triggered.connect(self._on_zoom_reset)
        self.typography_menu.addAction(self.action_zoom_reset)

        # Help Menu (Phase 9: Diagnostics)
        self.help_menu = menubar.addMenu(get_text("menu_help", self.current_language))
        self.action_diagnostics = QAction(get_text("menu_diagnostics", self.current_language), self)
        self.action_diagnostics.triggered.connect(self._on_open_diagnostics)
        self.help_menu.addAction(self.action_diagnostics)

    def _on_open_preferences(self) -> None:
        dlg = SettingsDialog(config_manager=self.config_manager, lang=self.current_language, parent=self)
        dlg.settings_applied.connect(self._on_settings_applied)
        dlg.exec()

    def _on_settings_applied(self, new_settings: Dict[str, Any]) -> None:
        if "discovery_model" in new_settings and hasattr(self, "discovery_model_combo"):
            idx = self.discovery_model_combo.findText(new_settings["discovery_model"])
            if idx >= 0:
                self.discovery_model_combo.setCurrentIndex(idx)
        if "synthesis_model" in new_settings and hasattr(self, "synthesis_model_combo"):
            idx = self.synthesis_model_combo.findText(new_settings["synthesis_model"])
            if idx >= 0:
                self.synthesis_model_combo.setCurrentIndex(idx)
        if "autosave_interval_s" in new_settings and hasattr(self, "_autosave_timer"):
            interval_ms = max(5000, int(new_settings["autosave_interval_s"]) * 1000)
            self._autosave_timer.setInterval(interval_ms)
        self._on_models_changed()

    def _on_open_diagnostics(self) -> None:
        dlg = DiagnosticDialog(config_manager=self.config_manager, lang=self.current_language, parent=self)
        dlg.exec()

    def _on_open_compute_dialog(self) -> None:
        dlg = ComputeDialog(lang=self.current_language, parent=self)
        dlg.provider_changed.connect(self._on_compute_provider_changed)
        dlg.exec()

    def _on_compute_provider_changed(self, provider_id: str) -> None:
        if hasattr(self, "compute_badge"):
            cm = ComputeManager.get_instance()
            self.compute_badge.setText(cm.get_badge_text(self.current_language))
            self.compute_badge.setToolTip(cm.get_tooltip_text(self.current_language))

    def _retranslate_menu(self) -> None:
        lang = self.current_language
        if hasattr(self, "file_menu"):
            self.file_menu.setTitle(get_text("menu_file", lang))
            self.action_new_project.setText(get_text("action_new_project", lang))
            self.action_open_project.setText(get_text("action_open_project", lang))
            self.action_save_project.setText(get_text("action_save_project", lang))
            if hasattr(self, "action_save_as_project"):
                self.action_save_as_project.setText(get_text("action_save_as_project", lang))
            if hasattr(self, "action_checkpoints"):
                self.action_checkpoints.setText(get_text("menu_checkpoints", lang))
            if hasattr(self, "action_vault_backup"):
                self.action_vault_backup.setText(get_text("menu_vault_backup", lang))
        if hasattr(self, "edit_menu"):
            self.edit_menu.setTitle(get_text("menu_edit", lang))
            if hasattr(self, "action_preferences"):
                self.action_preferences.setText(get_text("menu_preferences", lang))
        if hasattr(self, "tools_menu"):
            self.tools_menu.setTitle("Tools" if lang == "en" else "도구")
            if hasattr(self, "action_mobile_server"):
                self.action_mobile_server.setText(get_text("menu_mobile_server", lang))
            if hasattr(self, "action_sandbox"):
                self.action_sandbox.setText(get_text("dock_sandbox_title", lang))
        if hasattr(self, "chk_gap_fill"):
            self.chk_gap_fill.setText(get_text("btn_gap_fill_toggle", lang))
        if hasattr(self, "sandbox_dock"):
            self.sandbox_dock.retranslate_ui(lang)
        if hasattr(self, "view_menu"):
            self.view_menu.setTitle(get_text("menu_view", lang))
            self.action_split_view.setText(get_text("menu_split_view", lang))
            self.theme_menu.setTitle(get_text("menu_theme", lang))
            self.theme_action_dark.setText(get_text("theme_dark", lang))
            self.theme_action_oled.setText(get_text("theme_oled", lang))
            self.theme_action_light.setText(get_text("theme_light", lang))
            self.typography_menu.setTitle(get_text("menu_typography", lang))
            self.fonts_menu.setTitle("Font Family" if lang == "en" else "글꼴 선택")
            self.action_zoom_in.setText(get_text("zoom_in", lang))
            self.action_zoom_out.setText(get_text("zoom_out", lang))
            self.action_zoom_reset.setText(get_text("zoom_reset", lang))
        if hasattr(self, "help_menu"):
            self.help_menu.setTitle(get_text("menu_help", lang))
            if hasattr(self, "action_diagnostics"):
                self.action_diagnostics.setText(get_text("menu_diagnostics", lang))

    def _setup_global_shortcuts(self) -> None:
        """Bind productivity accelerators across the application."""
        # Ctrl+Return / Ctrl+Enter: Start Grounded Synthesis
        self.shortcut_synth1 = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.shortcut_synth1.activated.connect(self._on_shortcut_synthesize)
        self.shortcut_synth2 = QShortcut(QKeySequence("Ctrl+Enter"), self)
        self.shortcut_synth2.activated.connect(self._on_shortcut_synthesize)

        # Ctrl+T: New Workspace Tab
        self.shortcut_new_tab = QShortcut(QKeySequence("Ctrl+T"), self)
        self.shortcut_new_tab.activated.connect(self._on_shortcut_new_tab)

        # Ctrl+W: Close Active Workspace Tab
        self.shortcut_close_tab = QShortcut(QKeySequence("Ctrl+W"), self)
        self.shortcut_close_tab.activated.connect(self._on_shortcut_close_tab)

        # Ctrl+F: In-Page Find Bar
        self.shortcut_find = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_find.activated.connect(self._on_shortcut_find)

        # Ctrl+Shift+F: Global SQLite FTS5 Full-Text Search Drawer
        self.shortcut_search_fts = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        self.shortcut_search_fts.activated.connect(self._on_shortcut_search_fts)

        # Ctrl+Shift+D: Toggle Split Comparison View
        self.shortcut_split_view = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        self.shortcut_split_view.activated.connect(self._on_shortcut_toggle_split_view)

        # Ctrl++ / Ctrl+=: Zoom In
        self.shortcut_zoom_in1 = QShortcut(QKeySequence("Ctrl++"), self)
        self.shortcut_zoom_in1.activated.connect(self._on_zoom_in)
        self.shortcut_zoom_in2 = QShortcut(QKeySequence("Ctrl+="), self)
        self.shortcut_zoom_in2.activated.connect(self._on_zoom_in)

        # Ctrl+-: Zoom Out
        self.shortcut_zoom_out = QShortcut(QKeySequence("Ctrl+-"), self)
        self.shortcut_zoom_out.activated.connect(self._on_zoom_out)

        # Ctrl+0: Reset Zoom
        self.shortcut_zoom_reset = QShortcut(QKeySequence("Ctrl+0"), self)
        self.shortcut_zoom_reset.activated.connect(self._on_zoom_reset)

        # Escape: Cooperative cancellation or drawer dismissal
        self.shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        self.shortcut_esc.activated.connect(self._on_shortcut_escape)

        # Space: Audio play/pause toggle when active focus is not in an editable field
        self.shortcut_space = QShortcut(QKeySequence("Space"), self)
        self.shortcut_space.activated.connect(self._on_shortcut_space)

    def _on_shortcut_synthesize(self) -> None:
        if hasattr(self, "synthesize_btn") and self.synthesize_btn.isEnabled():
            self.synthesize_btn.click()

    def _on_shortcut_new_tab(self) -> None:
        self.add_new_workspace_tab()

    def _on_shortcut_close_tab(self) -> None:
        if hasattr(self, "workspace_tabs"):
            idx = self.workspace_tabs.currentIndex()
            if idx >= 0:
                self.workspace_tabs._on_tab_close_requested(idx)

    def _on_shortcut_find(self) -> None:
        if hasattr(self, "workspace_tabs"):
            self.active_workspace_pane.open_find_bar()

    def _on_shortcut_search_fts(self) -> None:
        if hasattr(self, "search_dock"):
            if self.search_dock.isVisible():
                self.search_dock.focus_search()
            else:
                self.search_dock.show()
                self.search_dock.raise_()
                self.search_dock.focus_search()

    def _on_fts_result_selected(self, doc_id: int, page_num: int) -> None:
        doc = self.corpus.get_by_cite_id(doc_id)
        if doc is None:
            return
        self.source_dock.inspect_document(doc, self.current_language, target_page=page_num)
        self.source_dock.show()
        self.source_dock.raise_()

    def _on_shortcut_escape(self) -> None:
        # 1. Close in-page find bar if visible
        if hasattr(self, "workspace_tabs") and hasattr(self.active_workspace_pane, "find_bar"):
            if self.active_workspace_pane.find_bar.isVisible():
                self.active_workspace_pane.find_bar.hide_bar()
                return

        # 2. Hide search dock if visible
        if hasattr(self, "search_dock") and self.search_dock.isVisible():
            self.search_dock.hide()
            return

        # 3. Cancel background task if active
        if hasattr(self, "btn_cancel") and self.btn_cancel.isVisible() and self.btn_cancel.isEnabled():
            self._on_cancel_active_task()

    def _on_shortcut_space(self) -> None:
        focused = self.focusWidget()
        if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return
        if hasattr(self, "audio_player") and hasattr(self.audio_player, "play_btn"):
            self.audio_player.play_btn.click()

    def update_telemetry(self) -> None:
        """Calculate and display real-time API spend and token metrics."""
        if not hasattr(self, "telemetry_label"):
            return

        corpus_tokens = sum(doc.estimated_tokens for doc in self.corpus.get_all_documents() if doc.enabled)
        active_pane = self.active_workspace_pane
        synth_chars = len(active_pane.synthesis_original_text or "")
        persp_chars = len(active_pane.perspective_original_text or "")
        chat_chars = sum(len(m.get("text", "")) for m in active_pane.chat_drawer.history)
        total_context_tokens = corpus_tokens + (synth_chars + persp_chars + chat_chars) // 4

        totals = GLOBAL_COST_TRACKER.get_live_totals()
        if totals and (totals.prompt_tokens > 0 or totals.candidate_tokens > 0 or totals.cached_tokens > 0 or totals.total_cost_usd > 0):
            indicator = " ⚡" if totals.is_live else ""
            text = (
                f"Spend: ${totals.total_cost_usd:.4f} USD{indicator} | "
                f"Prompt: {totals.prompt_tokens:,} | "
                f"Output: {totals.candidate_tokens:,} | "
                f"Cached: {totals.cached_tokens:,}"
            )
        else:
            limit_tokens = 1_000_000
            pct = (total_context_tokens / limit_tokens) * 100
            est_cost = (total_context_tokens / 1_000_000) * 0.15
            fmt = get_text("telemetry_label", self.current_language)
            text = fmt.format(tokens=f"{total_context_tokens:,}", pct=f"{pct:.1f}%", cost=f"{est_cost:.4f}")

        if totals and totals.is_live:
            color = "#38BDF8"  # Active streaming cyan
            border = "#0284C7"
        elif total_context_tokens < 200_000:
            color = "#3FB950"  # Green
            border = "#238636"
        elif total_context_tokens <= 600_000:
            color = "#38BDF8"  # Cyan / Blue
            border = "#0284C7"
        else:
            color = "#F59E0B"  # Amber / Warning
            border = "#D97706"

        self.telemetry_label.setStyleSheet(
            f"color: {color}; border: 1px solid {border}; background: #161B22; "
            "border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
        )
        self.telemetry_label.setText(text)

        FlightRecorder.update_flight_state("project_path", str(self.current_project_path) if getattr(self, "current_project_path", None) else "")
        FlightRecorder.update_flight_state("synthesis_model", self.synthesis_model_combo.currentText() if hasattr(self, "synthesis_model_combo") else "")
        FlightRecorder.update_flight_state("active_sources_count", len(self.corpus.enabled_documents) if hasattr(self, "corpus") else 0)
        FlightRecorder.update_flight_state("workspace_count", self.workspace_tabs.count() if hasattr(self, "workspace_tabs") else 1)

    def _on_telemetry_clicked(self) -> None:
        dialog = SpendLedgerDialog(ledger=self.token_ledger, lang=self.current_language, parent=self)
        dialog.exec()
        self.update_telemetry()

    def _on_connection_lost(self) -> None:
        if hasattr(self, "offline_banner"):
            self.offline_banner.show()
        if hasattr(self, "run_sweep_btn"):
            self.run_sweep_btn.setEnabled(False)
        if hasattr(self, "synthesize_btn"):
            self.synthesize_btn.setEnabled(False)
        self._set_status(get_text("network_offline_banner", self.current_language))

    def _on_connection_restored(self) -> None:
        if hasattr(self, "offline_banner"):
            self.offline_banner.hide()
        if self.active_worker is None:
            if hasattr(self, "run_sweep_btn"):
                self.run_sweep_btn.setEnabled(True)
            if hasattr(self, "synthesize_btn"):
                self.synthesize_btn.setEnabled(True)
        self._set_status("Online: Google GenAI connectivity active.")

    def _on_export_obsidian(self) -> None:
        active_text = (
            self.synthesis_translated_text
            if (self.synthesis_showing_translation and self.synthesis_translated_text)
            else self.synthesis_original_text or self.last_synthesis_markdown
        )
        if not active_text:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            get_text("export_obsidian", self.current_language),
            str(Path.home() / "omniresearch_obsidian.md"),
            "Markdown Files (*.md)",
        )
        if save_path:
            topic = self.query_input.toPlainText().strip() or self.sweep_topic_input.toPlainText().strip() or "OmniResearch Report"
            score = getattr(self.last_audit, "groundedness_score", 100) if self.last_audit else 100
            export_to_obsidian(
                output_path=save_path,
                report_md=active_text,
                sources_list=self.corpus.enabled_documents,
                metadata={"topic": topic, "groundedness_score": score},
            )
            self._set_status(get_text("status_export_saved", self.current_language).format(path=save_path))

    def _on_export_marp(self) -> None:
        active_text = (
            self.synthesis_translated_text
            if (self.synthesis_showing_translation and self.synthesis_translated_text)
            else self.synthesis_original_text or self.last_synthesis_markdown
        )
        if not active_text:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            get_text("export_marp", self.current_language),
            str(Path.home() / "omniresearch_presentation.marp.md"),
            "Markdown Slides (*.marp.md *.md)",
        )
        if save_path:
            topic = self.query_input.toPlainText().strip() or self.sweep_topic_input.toPlainText().strip() or "OmniResearch Executive Briefing"
            export_to_marp(
                output_path=save_path,
                report_md=active_text,
                metadata={"title": topic},
            )
            self._set_status(get_text("status_export_saved", self.current_language).format(path=save_path))

    def _on_theme_selected(self, theme_key: str) -> None:
        qss = self.theme_manager.set_theme(theme_key)
        self.setStyleSheet(qss)
        self.theme_manager.apply_title_bar(self)
        if hasattr(self, "theme_action_dark"):
            self.theme_action_dark.setChecked(theme_key == "dark")
        if hasattr(self, "theme_action_oled"):
            self.theme_action_oled.setChecked(theme_key == "oled")
        if hasattr(self, "theme_action_light"):
            self.theme_action_light.setChecked(theme_key == "light")

    def _on_font_selected(self, family: str) -> None:
        qss = self.theme_manager.set_font_family(family)
        self.setStyleSheet(qss)
        if hasattr(self, "font_actions"):
            for act in self.font_actions:
                act.setChecked(act.text() == family)

    def _on_zoom_in(self) -> None:
        qss = self.theme_manager.zoom_in()
        self.setStyleSheet(qss)

    def _on_zoom_out(self) -> None:
        qss = self.theme_manager.zoom_out()
        self.setStyleSheet(qss)

    def _on_zoom_reset(self) -> None:
        qss = self.theme_manager.reset_zoom()
        self.setStyleSheet(qss)

    def _on_menu_split_view_toggled(self, checked: bool) -> None:
        if hasattr(self, "workspace_tabs"):
            self.workspace_tabs.enable_split_view(checked)

    def _on_shortcut_toggle_split_view(self) -> None:
        if hasattr(self, "action_split_view"):
            self.action_split_view.setChecked(not self.action_split_view.isChecked())

    def _on_split_view_state_changed(self, enabled: bool) -> None:
        if hasattr(self, "action_split_view") and self.action_split_view.isChecked() != enabled:
            self.action_split_view.blockSignals(True)
            self.action_split_view.setChecked(enabled)
            self.action_split_view.blockSignals(False)

    def _on_autosave_timer(self) -> None:
        """Autosave active workspace state snapshot every 60 seconds into session_cache/autosave.omni."""
        try:
            has_docs = bool(self.corpus.get_all_documents())
            has_content = any(
                p.synthesis_original_text or p.perspective_original_text or bool(p.chat_drawer.history)
                for p in self.workspace_tabs.get_all_panes()
            )
            if not has_docs and not has_content:
                return

            SESSION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            autosave_file = SESSION_CACHE_DIR / "autosave.omni"

            panes = self.workspace_tabs.get_all_panes()
            active_pane = self.active_workspace_pane
            active_pane.query = self.query_input.toPlainText()
            active_pane.audio_directive = self.audio_focus_input.toPlainText()
            workspace_states = [p.export_state() for p in panes]

            state = ProjectState(
                documents=self.corpus.get_all_documents(),
                active_tab_index=self.workspace_tabs.currentIndex(),
                workspaces=workspace_states,
                topic=active_pane.topic or active_pane.title,
                query=active_pane.query,
                language=self.current_language,
                discovery_model=self.discovery_model_combo.currentText(),
                synthesis_model=self.synthesis_model_combo.currentText(),
                synthesis_original=active_pane.synthesis_original_text,
                synthesis_translated=active_pane.synthesis_translated_text,
                synthesis_showing_translation=active_pane.synthesis_showing_translation,
                perspective_original=active_pane.perspective_original_text,
                perspective_translated=active_pane.perspective_translated_text,
                perspective_showing_translation=active_pane.perspective_showing_translation,
                audio_title=active_pane.audio_title,
                audio_directive=active_pane.audio_directive,
                audio_script_raw=active_pane.audio_script,
                audio_mp3_path=active_pane.audio_mp3_path,
                chat_history=list(active_pane.chat_drawer.history),
                created_at=self._project_created_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                saved_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            save_project(state, autosave_file)
        except Exception:
            pass

    def _check_autosave_recovery(self) -> None:
        """Prompt user on launch if an unsaved session autosave exists."""
        autosave_file = SESSION_CACHE_DIR / "autosave.omni"
        if not autosave_file.exists():
            return
        try:
            mtime = datetime.datetime.fromtimestamp(autosave_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            reply = QMessageBox.question(
                self,
                get_text("autosave_recovery_title", self.current_language),
                get_text("autosave_recovery_msg", self.current_language).format(time=mtime),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._load_project_from_path(autosave_file)
            else:
                autosave_file.unlink(missing_ok=True)
        except Exception:
            pass

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Deterministic shutdown: terminates background server subprocess, stops QThreads, releases audio locks, flushes DBs."""
        # 1. Terminate the isolated Uvicorn server subprocess
        if hasattr(self, "mobile_server") and self.mobile_server:
            try:
                self.mobile_server.stop()
            except Exception:
                pass

        # 2. Stop and join all background QThread workers
        if hasattr(self, "active_worker") and self.active_worker and self.active_worker.isRunning():
            try:
                if hasattr(self.active_worker, "cancel"):
                    self.active_worker.cancel()
                self.active_worker.quit()
                self.active_worker.wait(1500)
            except Exception:
                pass

        if hasattr(self, "_followup_worker") and self._followup_worker and self._followup_worker.isRunning():
            try:
                if hasattr(self._followup_worker, "cancel"):
                    self._followup_worker.cancel()
                self._followup_worker.quit()
                self._followup_worker.wait(1500)
            except Exception:
                pass

        # 3. Release QMediaPlayer audio file locks via setSource(QUrl())
        if hasattr(self, "audio_player_widget") and self.audio_player_widget:
            try:
                if hasattr(self.audio_player_widget, "player") and self.audio_player_widget.player:
                    self.audio_player_widget.player.stop()
                    self.audio_player_widget.player.setSource(QUrl())
            except Exception:
                pass

        # 4. Flush and close all SQLite database connections
        if hasattr(self, "search_index") and self.search_index:
            try:
                self.search_index.close()
            except Exception:
                pass

        try:
            GLOBAL_LEDGER.close()
        except Exception:
            pass

        # 5. Clean up autosave snapshot
        try:
            autosave_file = SESSION_CACHE_DIR / "autosave.omni"
            if autosave_file.exists():
                autosave_file.unlink(missing_ok=True)
        except Exception:
            pass

        super().closeEvent(event)

    def _update_window_title(self) -> None:
        base_title = get_text("app_title", self.current_language)
        if self.current_project_path:
            self.setWindowTitle(f"{self.current_project_path.name} — {base_title}")
        else:
            self.setWindowTitle(base_title)

    def _on_new_project(self) -> None:
        reply = QMessageBox.question(
            self,
            get_text("project_new_confirm_title", self.current_language),
            get_text("project_new_confirm_text", self.current_language),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.corpus.clear()
        self._refresh_corpus_ui()
        while self.workspace_tabs.count() > 0:
            self.workspace_tabs.removeTab(0)
        self.add_new_workspace_tab(title="Research Workspace 1")
        self.query_input.clear()
        self.sweep_topic_input.clear()
        self.audio_focus_input.clear()
        self.dialogue_renderer.show_placeholder()
        self.audio_player.clear()
        self.source_dock.clear()
        self.current_project_path = None
        self._project_created_at = ""
        self._update_window_title()
        self.update_telemetry()
        self._set_status(get_text("status_project_new", self.current_language))

    def _on_save_project(self) -> None:
        if self.current_project_path is None:
            self._on_save_as_project()
            return
        self._save_project_to_path(self.current_project_path)

    def _on_save_as_project(self) -> None:
        dest, _ = QFileDialog.getSaveFileName(
            self,
            get_text("project_save_dialog", self.current_language),
            str(Path.home() / f"research_project{PROJECT_EXTENSION}"),
            f"OmniResearch Project (*{PROJECT_EXTENSION})",
        )
        if not dest:
            return
        target_path = Path(dest)
        self._save_project_to_path(target_path)

    def _build_project_state(self) -> ProjectState:
        panes = self.workspace_tabs.get_all_panes()
        active_pane = self.active_workspace_pane
        active_pane.query = self.query_input.toPlainText()
        active_pane.audio_directive = self.audio_focus_input.toPlainText()
        if self.last_audio_path and Path(self.last_audio_path).exists():
            active_pane.audio_mp3_path = self.last_audio_path

        workspace_states = [p.export_state() for p in panes]

        return ProjectState(
            documents=self.corpus.get_all_documents(),
            active_tab_index=self.workspace_tabs.currentIndex(),
            workspaces=workspace_states,
            topic=active_pane.topic or active_pane.title,
            query=active_pane.query,
            language=self.current_language,
            discovery_model=self.discovery_model_combo.currentText(),
            synthesis_model=self.synthesis_model_combo.currentText(),
            synthesis_original=active_pane.synthesis_original_text,
            synthesis_translated=active_pane.synthesis_translated_text,
            synthesis_showing_translation=active_pane.synthesis_showing_translation,
            perspective_original=active_pane.perspective_original_text,
            perspective_translated=active_pane.perspective_translated_text,
            perspective_showing_translation=active_pane.perspective_showing_translation,
            citations=list(active_pane.citations),
            grounding_refs=list(active_pane.grounding_refs),
            audio_title=active_pane.audio_title,
            audio_directive=active_pane.audio_directive,
            audio_model=self.discovery_model_combo.currentText(),
            audio_language=self.current_language,
            audio_script_raw=active_pane.audio_script,
            audio_mp3_path=active_pane.audio_mp3_path,
            chat_history=list(active_pane.chat_drawer.history),
            created_at=self._project_created_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            saved_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _save_project_to_path(self, target_path: Path) -> Path:
        state = self._build_project_state()
        audio_abs = self.last_audio_path if (self.last_audio_path and Path(self.last_audio_path).exists()) else None
        saved_path = save_project(state, target_path, audio_file_path=audio_abs)
        self.current_project_path = saved_path
        self._update_window_title()
        self._set_status(get_text("status_project_saved", self.current_language).format(path=saved_path.name))
        return saved_path

    def _on_open_project(self) -> None:
        src, _ = QFileDialog.getOpenFileName(
            self,
            get_text("project_open_dialog", self.current_language),
            str(Path.home()),
            f"OmniResearch Project (*{PROJECT_EXTENSION})",
        )
        if not src:
            return
        self._load_project_from_path(Path(src))

    def _load_project_from_state(self, state: ProjectState, extracted_audio: Optional[str] = None) -> None:
        self.corpus.clear()
        self.corpus.restore_documents(state.documents)
        self._refresh_corpus_ui()

        # Clear existing tabs
        while self.workspace_tabs.count() > 0:
            self.workspace_tabs.removeTab(0)

        if state.workspaces:
            for ws_state in state.workspaces:
                self.add_new_workspace_tab(title=ws_state.title, state=ws_state)
            idx = min(max(0, state.active_tab_index), self.workspace_tabs.count() - 1)
            self.workspace_tabs.setCurrentIndex(idx)
        else:
            pane = self.add_new_workspace_tab(title=state.topic or "Research Workspace 1")
            pane.topic = state.topic
            pane.query = state.query
            pane.synthesis_original_text = state.synthesis_original
            pane.synthesis_translated_text = state.synthesis_translated
            pane.synthesis_showing_translation = state.synthesis_showing_translation
            pane.perspective_original_text = state.perspective_original
            pane.perspective_translated_text = state.perspective_translated
            pane.perspective_showing_translation = state.perspective_showing_translation
            pane.audio_directive = state.audio_directive
            pane.audio_script = state.audio_script_raw
            pane.audio_title = state.audio_title
            pane.audio_mp3_path = state.audio_mp3_path
            pane.chat_drawer.load_history(state.chat_history)

        self._project_created_at = state.created_at
        self._update_window_title()

        active_pane = self.active_workspace_pane
        self.query_input.setPlainText(active_pane.query or active_pane.topic)
        self.audio_focus_input.setPlainText(active_pane.audio_directive)

        if extracted_audio and Path(extracted_audio).exists():
            self.last_audio_path = str(extracted_audio)
            self.audio_player.load_file(str(extracted_audio))
        else:
            self.audio_player.clear()

        self.update_telemetry()
        self._refresh_audit()

    def _load_project_from_path(self, project_path: Path) -> None:
        try:
            state, extracted_audio = load_project(project_path)
        except Exception as exc:
            QMessageBox.critical(self, get_text("project_error_title", self.current_language), str(exc))
            return

        self._load_project_from_state(state, extracted_audio)
        self.current_project_path = project_path
        self._update_window_title()
        self._set_status(get_text("status_project_loaded", self.current_language).format(path=project_path.name))

    def _init_local_models(self) -> None:
        try:
            client = LocalLLMClient()
            local_models = client.list_local_models(timeout_sec=0.5)
            for m in local_models:
                if self.discovery_model_combo.findText(m) == -1:
                    self.discovery_model_combo.addItem(m)
                if self.synthesis_model_combo.findText(m) == -1:
                    self.synthesis_model_combo.addItem(m)
        except Exception:
            pass

    def _get_active_project_target(self) -> Path:
        if self.current_project_path:
            return self.current_project_path
        cache_dir = Path("session_cache/active_project")
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def _on_manage_checkpoints(self) -> None:
        target_path = self._get_active_project_target()
        checkpoints = list_checkpoints(target_path)
        dialog = CheckpointManagerDialog(checkpoints=checkpoints, lang=self.current_language, parent=self)
        dialog.create_requested.connect(self._on_create_checkpoint)
        dialog.restore_requested.connect(self._on_restore_checkpoint)
        dialog.fork_requested.connect(self._on_fork_checkpoint)
        dialog.exec()

    def _on_create_checkpoint(self, name: str, description: str) -> None:
        target_path = self._get_active_project_target()
        state = self._build_project_state()
        cp_id = create_checkpoint(target_path, state, name=name, description=description)
        self._set_status(f"Checkpoint '{name}' created ({cp_id}).")

    def _on_restore_checkpoint(self, checkpoint_id: str) -> None:
        target_path = self._get_active_project_target()
        try:
            restored_state = restore_checkpoint(target_path, checkpoint_id)
            self._load_project_from_state(restored_state)
            self._set_status(f"Restored checkpoint: {checkpoint_id}")
        except Exception as exc:
            QMessageBox.critical(self, get_text("project_error_title", self.current_language), str(exc))

    def _on_fork_checkpoint(self, checkpoint_id: str) -> None:
        target_path = self._get_active_project_target()
        try:
            restored_state = restore_checkpoint(target_path, checkpoint_id)
            active_idx = min(max(0, restored_state.active_tab_index), len(restored_state.workspaces) - 1)
            tab_state = restored_state.workspaces[active_idx] if restored_state.workspaces else None
            fork_title = f"{tab_state.title if tab_state else 'Research'} (Fork)"
            self.add_new_workspace_tab(title=fork_title, state=tab_state)
            self._set_status(f"Forked checkpoint into new tab: {fork_title}")
        except Exception as exc:
            QMessageBox.critical(self, get_text("project_error_title", self.current_language), str(exc))

    def _on_export_html(self) -> None:
        active_text = (
            self.synthesis_translated_text
            if (self.synthesis_showing_translation and self.synthesis_translated_text)
            else self.synthesis_original_text or self.last_synthesis_markdown
        )
        if not active_text:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            get_text("export_as_html", self.current_language),
            str(Path.home() / "omniresearch_report.html"),
            "HTML Files (*.html)",
        )
        if save_path:
            title = self.query_input.toPlainText().strip() or self.sweep_topic_input.toPlainText().strip() or "OmniResearch Report"
            save_html_report(
                output_path=save_path,
                title=title,
                report_markdown=active_text,
                documents=self.corpus.enabled_documents,
                script=self.last_podcast_script,
                audio_path=self.last_audio_path,
                language=self.current_language,
            )
            self._set_status(get_text("status_export_saved", self.current_language).format(path=save_path))

    def _on_export_pdf(self) -> None:
        active_text = (
            self.synthesis_translated_text
            if (self.synthesis_showing_translation and self.synthesis_translated_text)
            else self.synthesis_original_text or self.last_synthesis_markdown
        )
        if not active_text:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            get_text("export_as_pdf", self.current_language),
            str(Path.home() / "omniresearch_report.pdf"),
            "PDF Files (*.pdf)",
        )
        if save_path:
            title = self.query_input.toPlainText().strip() or self.sweep_topic_input.toPlainText().strip() or "OmniResearch Report"
            export_pdf_report(
                output_path=save_path,
                title=title,
                report_markdown=active_text,
                documents=self.corpus.enabled_documents,
                language=self.current_language,
            )
            self._set_status(get_text("status_export_saved", self.current_language).format(path=save_path))

    def _on_export_bibtex(self) -> None:
        active_text = (
            self.synthesis_translated_text
            if (self.synthesis_showing_translation and self.synthesis_translated_text)
            else self.synthesis_original_text or self.last_synthesis_markdown
        )
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            get_text("export_bibtex", self.current_language),
            str(Path.home() / "omniresearch_bibliography.bib"),
            "BibTeX Files (*.bib)",
        )
        if save_path:
            export_bibtex_report(
                output_path=save_path,
                markdown_text=active_text,
                documents=self.corpus.enabled_documents,
            )
            self._set_status(get_text("status_export_saved", self.current_language).format(path=save_path))

    # --- Follow-Up Q&A Console Handlers ---

    def _on_chat_question_submitted(self, question: str) -> None:
        active_report = (
            self.synthesis_translated_text
            if (self.synthesis_showing_translation and self.synthesis_translated_text)
            else self.synthesis_original_text or self.last_synthesis_markdown
        )
        active_docs = self.corpus.enabled_documents
        if not active_report and not active_docs:
            self._set_status(get_text("chat_need_material", self.current_language))
            QMessageBox.information(
                self,
                get_text("chat_drawer_toggle", self.current_language),
                get_text("chat_need_material", self.current_language),
            )
            return

        self.chat_drawer.start_assistant_message()
        worker = FollowUpWorker(
            config_manager=self.config_manager,
            question=question,
            report_markdown=active_report,
            documents=active_docs,
            history=self.chat_drawer.history[:-1],
            model_override=self.synthesis_model_combo.currentText(),
            language=self.current_language,
        )
        self._followup_worker = worker
        worker.chunk_received.connect(lambda ch, pane: self._on_stream_chunk_received(ch, pane))
        worker.finished_Success.connect(self._on_chat_finished)
        worker.failed_Error.connect(self._on_chat_failed)
        self.chat_drawer.set_busy(True)
        self._set_status(get_text("status_chat_answering", self.current_language))
        worker.start()

    def _on_chat_finished(self, full_answer: str) -> None:
        self.chat_drawer.finish_assistant_message(full_answer)
        self.chat_drawer.set_busy(False)
        self._followup_worker = None
        self._set_status(f"Answer generated ({len(full_answer)} chars).")
        self.update_telemetry()

    def _on_chat_failed(self, error_detail: str) -> None:
        self.chat_drawer.abort_assistant_message()
        self.chat_drawer.set_busy(False)
        self._followup_worker = None
        self._set_status("Follow-up Q&A failed.")
        QMessageBox.warning(self, "Q&A Error", error_detail[:1000])

    def _on_chat_cleared(self) -> None:
        self._set_status("Follow-up conversation cleared.")
        self.update_telemetry()

    def dragEnterEvent(self, event: Any) -> None:
        """Accept drag events if dropping supported documents, audio, YouTube/Academic URLs, or project files."""
        if event.mimeData().hasUrls():
            valid_exts = {
                ".pdf", ".docx", ".txt", ".md", ".markdown", ".omni",
                ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"
            }
            has_valid = any(
                Path(url.toLocalFile()).suffix.lower() in valid_exts
                for url in event.mimeData().urls()
                if url.isLocalFile()
            ) or any(
                is_youtube_url(url.toString()) or is_academic_identifier(url.toString())
                for url in event.mimeData().urls()
                if not url.isLocalFile()
            )
            if has_valid:
                event.acceptProposedAction()
                return
        elif event.mimeData().hasText():
            txt = event.mimeData().text().strip()
            if is_youtube_url(txt) or is_academic_identifier(txt):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: Any) -> None:
        """Handle dropping of supported document files, audio files, YouTube/Academic links, or project (.omni)."""
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        doc_paths: List[Path] = []
        omni_path: Optional[Path] = None
        remote_urls: List[str] = []

        for u in urls:
            if u.isLocalFile():
                p = Path(u.toLocalFile())
                ext = p.suffix.lower()
                if ext == ".omni":
                    omni_path = p
                elif ext in {".pdf", ".docx", ".txt", ".md", ".markdown"} or ext in AUDIO_EXTENSIONS:
                    doc_paths.append(p)
            else:
                remote_urls.append(u.toString())

        if omni_path is not None:
            self._load_project_from_path(omni_path)
            event.acceptProposedAction()
            return

        # Check for dropped text (e.g. pasted/dragged YouTube or DOI link)
        if event.mimeData().hasText():
            text_str = event.mimeData().text().strip()
            for line in text_str.splitlines():
                clean_l = line.strip()
                if is_youtube_url(clean_l) or is_academic_identifier(clean_l):
                    if clean_l not in remote_urls:
                        remote_urls.append(clean_l)

        added = 0
        if doc_paths:
            for dp in doc_paths:
                try:
                    ext = dp.suffix.lower()
                    if ext in AUDIO_EXTENSIONS:
                        self._set_status(get_text("status_transcribing_audio", self.current_language))
                    self.corpus.ingest_file(dp)
                    added += 1
                except Exception as exc:
                    self._set_status(f"Failed to ingest {dp.name}: {exc}")

        if remote_urls:
            for r_url in remote_urls:
                try:
                    if is_youtube_url(r_url):
                        self._set_status("Fetching YouTube transcript...")
                        self.corpus.ingest_youtube_url(r_url)
                        added += 1
                    elif is_academic_identifier(r_url):
                        self._set_status(get_text("status_resolving_academic", self.current_language))
                        self.corpus.ingest_academic(r_url)
                        added += 1
                except Exception as exc:
                    self._set_status(f"Failed to ingest link {r_url}: {exc}")

        if added:
            self._refresh_corpus_ui()
            self._set_status(f"Ingested {added} source(s) via drag-and-drop.")
        event.acceptProposedAction()
