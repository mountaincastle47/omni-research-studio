"""Encrypted Vault Backup & Restore Dialog: Zero-Knowledge AES-256-GCM management UI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidTag
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import get_text
from core.vault_sync import VaultSync


class VaultSyncDialog(QDialog):
    """Encrypted Vault management dialog for zero-knowledge AES-256-GCM backup and restoration."""

    restore_completed = pyqtSignal(str)

    def __init__(
        self,
        current_project_path: Optional[Path] = None,
        lang: str = "en",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.current_project_path = current_project_path
        self._lang = lang

        self.setWindowTitle(get_text("vault_dialog_title", self._lang))
        self.resize(540, 360)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header description
        hdr = QLabel(
            "Client-Side Zero-Knowledge Encryption: All projects are encrypted with AES-256-GCM "
            "using keys derived via PBKDF2 (600,000 iterations). Your password is never stored or transmitted.",
            self,
        )
        hdr.setWordWrap(True)
        hdr.setStyleSheet("color: #94A3B8; font-size: 11px;")
        layout.addWidget(hdr)

        # Passphrase Box
        pwd_frame = QFrame(self)
        pwd_frame.setStyleSheet("QFrame { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px; padding: 12px; }")
        pwd_layout = QVBoxLayout(pwd_frame)
        pwd_layout.setSpacing(8)

        lbl_pwd = QLabel(get_text("vault_pwd_label", self._lang), pwd_frame)
        lbl_pwd.setStyleSheet("color: #F1F5F9; font-weight: 700; font-size: 11px;")
        pwd_layout.addWidget(lbl_pwd)

        self.pwd_input = QLineEdit(pwd_frame)
        self.pwd_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_input.setPlaceholderText("Enter master encryption passphrase...")
        self.pwd_input.setStyleSheet("QLineEdit { background-color: #090D16; color: #F8FAFC; border: 1px solid #334155; border-radius: 5px; padding: 6px 10px; font-size: 12px; }")
        pwd_layout.addWidget(self.pwd_input)

        self.pwd_confirm = QLineEdit(pwd_frame)
        self.pwd_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_confirm.setPlaceholderText("Confirm master passphrase (for backup)...")
        self.pwd_confirm.setStyleSheet("QLineEdit { background-color: #090D16; color: #F8FAFC; border: 1px solid #334155; border-radius: 5px; padding: 6px 10px; font-size: 12px; }")
        pwd_layout.addWidget(self.pwd_confirm)

        layout.addWidget(pwd_frame)

        # Status Label
        self.status_label = QLabel("", self)
        self.status_label.setStyleSheet("color: #38BDF8; font-size: 11px;")
        layout.addWidget(self.status_label)

        layout.addStretch(1)

        # Actions
        btn_row = QHBoxLayout()

        self.btn_backup = QPushButton(get_text("vault_backup_btn", self._lang), self)
        self.btn_backup.setStyleSheet("QPushButton { background-color: #0284C7; color: #FFFFFF; font-weight: 700; border-radius: 6px; padding: 8px 16px; font-size: 12px; } QPushButton:hover { background-color: #0369A1; }")
        self.btn_backup.clicked.connect(self._run_backup)
        btn_row.addWidget(self.btn_backup)

        self.btn_restore = QPushButton(get_text("vault_restore_btn", self._lang), self)
        self.btn_restore.setStyleSheet("QPushButton { background-color: #1E293B; color: #38BDF8; border: 1px solid #334155; border-radius: 6px; padding: 8px 16px; font-size: 12px; } QPushButton:hover { background-color: #334155; }")
        self.btn_restore.clicked.connect(self._run_restore)
        btn_row.addWidget(self.btn_restore)

        btn_row.addStretch(1)

        btn_close = QPushButton("Close", self)
        btn_close.setStyleSheet("QPushButton { background-color: #334155; color: #F1F5F9; border-radius: 6px; padding: 8px 16px; font-size: 12px; }")
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def _run_backup(self) -> None:
        pwd = self.pwd_input.text()
        confirm = self.pwd_confirm.text()

        if not pwd or len(pwd) < 6:
            QMessageBox.warning(self, "Passphrase Too Short", "Master passphrase must be at least 6 characters long.")
            return

        if pwd != confirm:
            QMessageBox.warning(self, "Passphrase Mismatch", "Master passphrase and confirmation do not match.")
            return

        if not self.current_project_path or not Path(self.current_project_path).exists():
            QMessageBox.warning(self, "No Saved Project", "Please save the project first before creating an encrypted vault backup.")
            return

        dest_file, _ = QFileDialog.getSaveFileName(
            self,
            "Save Encrypted Project Vault",
            str(Path(self.current_project_path).with_suffix(".omni.vault")),
            "OmniResearch Encrypted Vault (*.omni.vault)",
        )
        if not dest_file:
            return

        try:
            self.status_label.setText("Encrypting with AES-256-GCM (600,000 PBKDF2 iterations)...")
            QApplication.processEvents()

            VaultSync.encrypt_file(self.current_project_path, dest_file, pwd)
            self.status_label.setText(f"✔ Backup successfully encrypted: {Path(dest_file).name}")
            QMessageBox.information(self, "Backup Successful", f"Encrypted vault created:\n{dest_file}")
        except Exception as exc:
            self.status_label.setText(f"Backup failed: {exc}")
            QMessageBox.critical(self, "Backup Failed", str(exc))

    def _run_restore(self) -> None:
        pwd = self.pwd_input.text()
        if not pwd:
            QMessageBox.warning(self, "Passphrase Required", "Please enter the vault master passphrase to decrypt.")
            return

        vault_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select Encrypted Project Vault",
            "",
            "OmniResearch Encrypted Vault (*.omni.vault);;All Files (*.*)",
        )
        if not vault_file:
            return

        dest_file, _ = QFileDialog.getSaveFileName(
            self,
            "Save Restored Project",
            str(Path(vault_file).with_suffix("").with_suffix(".omni")),
            "OmniResearch Project (*.omni)",
        )
        if not dest_file:
            return

        try:
            self.status_label.setText("Decrypting and verifying authentication tag...")
            QApplication.processEvents()

            VaultSync.decrypt_file(vault_file, dest_file, pwd)
            self.status_label.setText(f"✔ Decrypted successfully: {Path(dest_file).name}")
            self.restore_completed.emit(dest_file)
            QMessageBox.information(self, "Restoration Successful", f"Vault decrypted successfully:\n{dest_file}")
            self.accept()
        except InvalidTag:
            self.status_label.setText("❌ Authentication Failed: Incorrect passphrase or tampered file.")
            QMessageBox.critical(self, "Decryption Failed", "Authentication failed: Incorrect passphrase or corrupted vault file.")
        except Exception as exc:
            self.status_label.setText(f"Decryption failed: {exc}")
            QMessageBox.critical(self, "Decryption Failed", str(exc))
