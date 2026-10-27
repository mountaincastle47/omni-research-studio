"""Centralized Workstation Preferences Dialog:
Categorized tabs for API keys, local models, audio voices, network mirror, and vault settings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import AVAILABLE_MODELS
from core.config_manager import ConfigManager
from core.i18n import get_text


class SettingsDialog(QDialog):
    """Categorized preference settings modal dialog."""

    settings_applied = pyqtSignal(dict)

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        lang: str = "en",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager or ConfigManager.get_instance()
        self._lang = lang

        self.setWindowTitle(get_text("settings_dialog_title", self._lang))
        self.resize(620, 480)
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #1E293B; border-radius: 6px; background-color: #0F172A; } "
            "QTabBar::tab { background-color: #090D16; color: #94A3B8; padding: 6px 14px; font-size: 11px; } "
            "QTabBar::tab:selected { background-color: #1E293B; color: #38BDF8; font-weight: 700; }"
        )

        # Tab 1: General / API
        tab_general = QWidget()
        form_general = QFormLayout(tab_general)
        form_general.setSpacing(12)
        form_general.setContentsMargins(14, 14, 14, 14)

        key_row = QHBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Enter Google Gemini API Key...")
        self.btn_clear_key = QPushButton(get_text("btn_clear_key", self._lang))
        self.btn_clear_key.setFixedHeight(26)
        self.btn_clear_key.setStyleSheet(
            "QPushButton { padding: 2px 8px; font-size: 11px; background-color: #3F1B24; color: #F87171; "
            "border: 1px solid #7F1D1D; border-radius: 4px; font-weight: 600; } "
            "QPushButton:hover { background-color: #7F1D1D; color: #FECACA; }"
        )
        self.btn_clear_key.clicked.connect(lambda: self.api_key_input.clear())
        key_row.addWidget(self.api_key_input, stretch=1)
        key_row.addWidget(self.btn_clear_key)
        form_general.addRow(QLabel("Gemini API Key:"), key_row)

        self.autosave_interval = QSpinBox()
        self.autosave_interval.setRange(10, 600)
        self.autosave_interval.setSuffix(" sec")
        form_general.addRow(QLabel("Crash Autosave Interval:"), self.autosave_interval)

        self.cache_retention = QSpinBox()
        self.cache_retention.setRange(1, 365)
        self.cache_retention.setSuffix(" days")
        form_general.addRow(QLabel("Cache Retention Ceiling:"), self.cache_retention)

        self.tabs.addTab(tab_general, get_text("tab_settings_general", self._lang))

        # Tab 2: Models & Local LLM
        tab_models = QWidget()
        form_models = QFormLayout(tab_models)
        form_models.setSpacing(12)
        form_models.setContentsMargins(14, 14, 14, 14)

        self.discovery_model_combo = QComboBox()
        self.discovery_model_combo.addItems(AVAILABLE_MODELS)
        form_models.addRow(QLabel("Default Discovery Model:"), self.discovery_model_combo)

        self.synthesis_model_combo = QComboBox()
        self.synthesis_model_combo.addItems(AVAILABLE_MODELS)
        form_models.addRow(QLabel("Default Synthesis Model:"), self.synthesis_model_combo)

        self.local_endpoint_input = QLineEdit()
        self.local_endpoint_input.setPlaceholderText("http://localhost:11434/v1")
        form_models.addRow(QLabel("Local LLM Endpoint (Ollama/vLLM):"), self.local_endpoint_input)

        self.local_model_input = QLineEdit()
        self.local_model_input.setPlaceholderText("e.g., qwen2.5:7b, mistral:7b")
        form_models.addRow(QLabel("Default Local Model Tag:"), self.local_model_input)

        self.tabs.addTab(tab_models, get_text("tab_settings_models", self._lang))

        # Tab 3: Audio & Media
        tab_audio = QWidget()
        form_audio = QFormLayout(tab_audio)
        form_audio.setSpacing(12)
        form_audio.setContentsMargins(14, 14, 14, 14)

        self.playback_rate_combo = QComboBox()
        self.playback_rate_combo.addItems(["0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
        form_audio.addRow(QLabel("Default Playback Rate:"), self.playback_rate_combo)

        self.host_a_voice_input = QLineEdit()
        self.host_a_voice_input.setPlaceholderText("en-US-GuyNeural")
        form_audio.addRow(QLabel("Host A Voice (Edge-TTS):"), self.host_a_voice_input)

        self.host_b_voice_input = QLineEdit()
        self.host_b_voice_input.setPlaceholderText("en-US-JennyNeural")
        form_audio.addRow(QLabel("Host B Voice (Edge-TTS):"), self.host_b_voice_input)

        self.silence_padding = QSpinBox()
        self.silence_padding.setRange(50, 1000)
        self.silence_padding.setSuffix(" ms")
        form_audio.addRow(QLabel("Turn Silence Buffer:"), self.silence_padding)

        self.tabs.addTab(tab_audio, get_text("tab_settings_audio", self._lang))

        # Tab 4: Network & LAN Mirror
        tab_network = QWidget()
        form_network = QFormLayout(tab_network)
        form_network.setSpacing(12)
        form_network.setContentsMargins(14, 14, 14, 14)

        self.lan_port = QSpinBox()
        self.lan_port.setRange(1024, 65535)
        form_network.addRow(QLabel("LAN Mirror Server Port:"), self.lan_port)

        self.auto_start_server = QCheckBox("Auto-launch Mobile Mirror daemon on workstation startup")
        form_network.addRow("", self.auto_start_server)

        self.network_timeout = QSpinBox()
        self.network_timeout.setRange(1, 30)
        self.network_timeout.setSuffix(" sec")
        form_network.addRow(QLabel("Network Sentinel Probe Timeout:"), self.network_timeout)

        self.tabs.addTab(tab_network, get_text("tab_settings_network", self._lang))

        # Tab 5: Storage & Vault Backup
        tab_storage = QWidget()
        form_storage = QFormLayout(tab_storage)
        form_storage.setSpacing(12)
        form_storage.setContentsMargins(14, 14, 14, 14)

        vault_row = QHBoxLayout()
        self.vault_path_input = QLineEdit()
        self.vault_path_input.setPlaceholderText("session_cache/backups")
        vault_row.addWidget(self.vault_path_input)

        btn_browse_vault = QPushButton("Browse...")
        btn_browse_vault.clicked.connect(self._browse_vault_path)
        vault_row.addWidget(btn_browse_vault)
        form_storage.addRow(QLabel("Encrypted Vault Backup Directory:"), vault_row)

        self.webdav_input = QLineEdit()
        self.webdav_input.setPlaceholderText("https://nas.local:5005/vault/")
        form_storage.addRow(QLabel("Remote WebDAV Sync Endpoint:"), self.webdav_input)

        self.contested_matrix_chk = QCheckBox("Enforce Contested Claims & Empirical Anomalies Matrix")
        form_storage.addRow("", self.contested_matrix_chk)

        self.bm25_threshold = QSpinBox()
        self.bm25_threshold.setRange(8000, 200000)
        self.bm25_threshold.setSingleStep(4000)
        self.bm25_threshold.setSuffix(" tokens")
        form_storage.addRow(QLabel("BM25 Context Compression Threshold:"), self.bm25_threshold)

        self.tabs.addTab(tab_storage, get_text("tab_settings_storage", self._lang))

        layout.addWidget(self.tabs, stretch=1)

        # Bottom Button Strip
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self.btn_cancel = QPushButton(get_text("btn_cancel", self._lang), self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_apply = QPushButton(get_text("btn_apply", self._lang), self)
        self.btn_apply.clicked.connect(self._apply_settings)
        btn_row.addWidget(self.btn_apply)

        self.btn_save = QPushButton(get_text("btn_save", self._lang), self)
        self.btn_save.setObjectName("PrimaryActionBtn")
        self.btn_save.setStyleSheet(
            "QPushButton { background-color: #0284C7; color: #FFFFFF; font-weight: 700; "
            "border-radius: 5px; padding: 6px 18px; font-size: 11px; } QPushButton:hover { background-color: #0369A1; }"
        )
        self.btn_save.clicked.connect(self._save_and_close)
        btn_row.addWidget(self.btn_save)

        layout.addLayout(btn_row)

    def _load_values(self) -> None:
        cfg = self.config_manager.get_all()

        self.api_key_input.setText(cfg.get("gemini_api_key", ""))
        self.autosave_interval.setValue(cfg.get("autosave_interval_s", 60))
        self.cache_retention.setValue(cfg.get("cache_retention_days", 14))

        disc = cfg.get("discovery_model", "gemini-3.8-flash")
        idx_disc = self.discovery_model_combo.findText(disc)
        if idx_disc >= 0:
            self.discovery_model_combo.setCurrentIndex(idx_disc)

        synth = cfg.get("synthesis_model", "gemini-4-argon")
        idx_synth = self.synthesis_model_combo.findText(synth)
        if idx_synth >= 0:
            self.synthesis_model_combo.setCurrentIndex(idx_synth)

        self.local_endpoint_input.setText(cfg.get("local_llm_endpoint", "http://localhost:11434/v1"))
        self.local_model_input.setText(cfg.get("default_local_model", "qwen2.5:7b"))

        rate_str = f"{cfg.get('audio_playback_rate', 1.0):.1f}x"
        idx_rate = self.playback_rate_combo.findText(rate_str)
        if idx_rate >= 0:
            self.playback_rate_combo.setCurrentIndex(idx_rate)

        self.host_a_voice_input.setText(cfg.get("host_a_voice", "en-US-GuyNeural"))
        self.host_b_voice_input.setText(cfg.get("host_b_voice", "en-US-JennyNeural"))
        self.silence_padding.setValue(cfg.get("silence_padding_duration_ms", 200))

        self.lan_port.setValue(cfg.get("lan_server_port", 8484))
        self.auto_start_server.setChecked(cfg.get("auto_start_lan_server", True))
        self.network_timeout.setValue(cfg.get("network_check_timeout_s", 5))

        self.vault_path_input.setText(cfg.get("vault_backup_path", "session_cache/backups"))
        self.webdav_input.setText(cfg.get("webdav_endpoint", ""))
        self.contested_matrix_chk.setChecked(cfg.get("contested_matrix_enforcement", True))
        self.bm25_threshold.setValue(cfg.get("bm25_compression_threshold_tokens", 64000))

    def _collect_values(self) -> Dict[str, Any]:
        rate_val = 1.0
        try:
            rate_val = float(self.playback_rate_combo.currentText().replace("x", ""))
        except ValueError:
            rate_val = 1.0

        return {
            "gemini_api_key": self.api_key_input.text().strip(),
            "autosave_interval_s": self.autosave_interval.value(),
            "cache_retention_days": self.cache_retention.value(),
            "discovery_model": self.discovery_model_combo.currentText(),
            "synthesis_model": self.synthesis_model_combo.currentText(),
            "local_llm_endpoint": self.local_endpoint_input.text().strip(),
            "default_local_model": self.local_model_input.text().strip(),
            "audio_playback_rate": rate_val,
            "host_a_voice": self.host_a_voice_input.text().strip(),
            "host_b_voice": self.host_b_voice_input.text().strip(),
            "silence_padding_duration_ms": self.silence_padding.value(),
            "lan_server_port": self.lan_port.value(),
            "auto_start_lan_server": self.auto_start_server.isChecked(),
            "network_check_timeout_s": self.network_timeout.value(),
            "vault_backup_path": self.vault_path_input.text().strip(),
            "webdav_endpoint": self.webdav_input.text().strip(),
            "contested_matrix_enforcement": self.contested_matrix_chk.isChecked(),
            "bm25_compression_threshold_tokens": self.bm25_threshold.value(),
        }

    def _apply_settings(self) -> None:
        values = self._collect_values()
        self.config_manager.update_bulk(values)
        self.settings_applied.emit(values)

    def _save_and_close(self) -> None:
        self._apply_settings()
        self.accept()

    def _browse_vault_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Vault Backup Directory", self.vault_path_input.text())
        if folder:
            self.vault_path_input.setText(folder)
