"""Mobile LAN Mirror Server Control Dialog: Displays QR code, LAN IP, and 6-digit access PIN."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import get_text
from core.server_mirror import MobileMirrorServer, QR_CODE_PATH


class MobileServerDialog(QDialog):
    """Presents mobile connection QR code and URL for LAN access."""

    def __init__(
        self,
        server: MobileMirrorServer,
        lang: str = "en",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.server = server
        self._lang = lang

        self.setWindowTitle(get_text("mobile_dialog_title", self._lang))
        self.resize(440, 520)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header instructions
        hdr = QLabel(get_text("mobile_qr_instructions", self._lang), self)
        hdr.setWordWrap(True)
        hdr.setStyleSheet("color: #E2E8F0; font-size: 12px; font-weight: 600;")
        layout.addWidget(hdr)

        # QR Code Container
        qr_frame = QFrame(self)
        qr_frame.setStyleSheet("QFrame { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px; padding: 12px; }")
        qr_layout = QVBoxLayout(qr_frame)
        qr_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.qr_label = QLabel(qr_frame)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        qr_file = self.server._generate_qr_code()
        if qr_file.exists():
            pix = QPixmap(str(qr_file))
            self.qr_label.setPixmap(pix.scaled(220, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.qr_label.setText("QR Generation Error")
        qr_layout.addWidget(self.qr_label)

        layout.addWidget(qr_frame)

        # PIN & URL Info Box
        info_frame = QFrame(self)
        info_frame.setStyleSheet("QFrame { background-color: #0B0E14; border: 1px solid #334155; border-radius: 6px; padding: 10px; }")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(6)

        pin_tmpl = get_text("server_pin_label", self._lang)
        self.lbl_pin = QLabel(pin_tmpl.format(pin=self.server.pin), info_frame)
        self.lbl_pin.setStyleSheet("color: #F59E0B; font-size: 14px; font-weight: 700;")
        info_layout.addWidget(self.lbl_pin)

        self.lbl_url = QLabel(self.server.get_server_url(), info_frame)
        self.lbl_url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_url.setStyleSheet("color: #38BDF8; font-size: 11px; font-family: Consolas, monospace;")
        info_layout.addWidget(self.lbl_url)

        layout.addWidget(info_frame)

        # Bottom Button Row
        btn_row = QHBoxLayout()
        btn_copy = QPushButton("Copy URL", self)
        btn_copy.setStyleSheet("QPushButton { background-color: #1E293B; color: #38BDF8; border: 1px solid #334155; border-radius: 4px; padding: 6px 14px; font-size: 11px; }")
        btn_copy.clicked.connect(self._copy_url)
        btn_row.addWidget(btn_copy)

        btn_row.addStretch(1)

        btn_close = QPushButton("Close", self)
        btn_close.setStyleSheet("QPushButton { background-color: #334155; color: #F1F5F9; border-radius: 4px; padding: 6px 16px; font-size: 11px; }")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def _copy_url(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.server.get_server_url())
