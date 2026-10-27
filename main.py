"""Application entry point and Windows production runtime initializer for OmniResearch Studio."""

from __future__ import annotations

# 1. Multiprocessing Freeze Support (Must run before anything else on Windows)
import multiprocessing
multiprocessing.freeze_support()

import os
import sys
from pathlib import Path

# 2. Dual SSL Certificate Anchoring
try:
    import certifi
    ca_path = certifi.where()
    os.environ["SSL_CERT_FILE"] = ca_path
    os.environ["REQUESTS_CA_BUNDLE"] = ca_path
except Exception:
    pass

# 3. Windows Keyring Explicit Backend Registration
try:
    import keyring
    import keyring.backends.Windows
    keyring.set_keyring(keyring.backends.Windows.WinVaultKeyring())
except Exception:
    pass

# 4. Universal Paths
from core.paths import get_logs_dir, get_cache_dir

# 5. Guard --noconsole stdout / stderr streams
class RuntimeStreamLogger:
    """Thread-safe fallback stream for GUI / --noconsole execution."""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self._fp = None
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._fp = open(self.log_path, "a", encoding="utf-8", errors="replace")
        except Exception:
            self._fp = None

    def write(self, message: str) -> int:
        if self._fp:
            try:
                self._fp.write(message)
                self._fp.flush()
            except Exception:
                pass
        return len(message)

    def flush(self) -> None:
        if self._fp:
            try:
                self._fp.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return False


if sys.stdout is None or sys.stderr is None:
    _runtime_log = get_logs_dir() / "omni_runtime.log"
    _logger_stream = RuntimeStreamLogger(_runtime_log)
    if sys.stdout is None:
        sys.stdout = _logger_stream
    if sys.stderr is None:
        sys.stderr = _logger_stream

# 6. High-DPI Display Configuration & Desktop OpenGL Acceleration
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

try:
    from PyQt6.QtCore import Qt, QCoreApplication, QTimer
    from PyQt6.QtGui import QFont, QGuiApplication
    from PyQt6.QtWidgets import QApplication
except ImportError:
    from PySide6.QtCore import Qt, QCoreApplication, QTimer
    from PySide6.QtGui import QFont, QGuiApplication
    from PySide6.QtWidgets import QApplication

# Hardware-Accelerated Qt Rendering
try:
    if hasattr(Qt, "ApplicationAttribute"):
        if hasattr(Qt.ApplicationAttribute, "AA_UseDesktopOpenGL"):
            QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseDesktopOpenGL)
        if hasattr(Qt.ApplicationAttribute, "AA_ShareOpenGLContexts"):
            QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
except Exception:
    pass

QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

# 7. Non-Admin Session-Safe Mutex (Local\ namespace)
_GLOBAL_MUTEX_HANDLE = None
if sys.platform == "win32":
    try:
        import ctypes
        from ctypes import wintypes

        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        mutex_name = "Local\\OmniResearchStudio_SingleInstance_Mutex"
        if "--smoke-test" in sys.argv:
            mutex_name += "_SmokeTest"
        _GLOBAL_MUTEX_HANDLE = kernel32.CreateMutexW(None, False, mutex_name)
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            sys.exit(0)
    except Exception:
        pass

# 8. First-Run Runtime Bootstrap
from core.bootstrap import bootstrap_runtime
bootstrap_runtime()

from core.config import ConfigManager
from core.flight_recorder import CrashRecoveryDialog, FlightRecorder
from ui.main_window import MainWindow


def main() -> int:
    """Initialize QApplication and execute OmniResearch Studio workstation."""
    FlightRecorder.install()

    app = QApplication(sys.argv)
    app.setApplicationName("OmniResearch Studio")
    app.setOrganizationName("OmniResearch")
    app.setFont(QFont("Segoe UI", 10))

    # Automated Smoke Test Hook
    if "--smoke-test" in sys.argv:
        # Verify SQLite DB connections and offscreen boot
        from core.search_index import CorpusSearchIndex
        idx = CorpusSearchIndex()
        idx.close()
        from core.token_ledger import TokenLedger
        ledger = TokenLedger()
        ledger.close()

        cfg_mgr = ConfigManager()
        test_window = MainWindow(config_manager=cfg_mgr)
        test_window.hide()
        QTimer.singleShot(250, app.quit)
        return app.exec()

    restore_requested = False
    if FlightRecorder.has_crash_dump():
        dump_data = FlightRecorder.read_crash_dump()
        if dump_data:
            diag = CrashRecoveryDialog(dump_data)
            if diag.exec():
                restore_requested = diag.should_restore

    config_manager = ConfigManager()
    window = MainWindow(config_manager=config_manager, restore_autosave=restore_requested)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
