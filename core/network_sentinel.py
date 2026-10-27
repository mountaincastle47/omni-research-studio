"""Network sentinel monitoring Google Cloud/GenAI connectivity and signaling offline state transitions."""

from __future__ import annotations

import socket
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

GOOGLE_API_HOST = "generativelanguage.googleapis.com"
CONNECT_TIMEOUT_SEC = 2.5


class NetworkSentinel(QObject):
    """Monitors live internet and API connectivity, alerting UI components upon degradation."""

    connection_lost = pyqtSignal()
    connection_restored = pyqtSignal()
    status_changed = pyqtSignal(bool)

    def __init__(
        self,
        check_interval_ms: int = 10000,
        target_host: str = GOOGLE_API_HOST,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.target_host = target_host
        self._is_online = True
        self._timer = QTimer(self)
        self._timer.setInterval(check_interval_ms)
        self._timer.timeout.connect(self.check_now)

    @property
    def is_online(self) -> bool:
        return self._is_online

    def start(self) -> None:
        """Begin periodic network health polling."""
        self.check_now()
        self._timer.start()

    def stop(self) -> None:
        """Halt periodic polling."""
        self._timer.stop()

    def check_now(self) -> bool:
        """Perform immediate network verification check."""
        previously_online = self._is_online
        currently_online = self._probe_connectivity()

        if previously_online != currently_online:
            self._is_online = currently_online
            self.status_changed.emit(currently_online)
            if not currently_online:
                self.connection_lost.emit()
            else:
                self.connection_restored.emit()

        return currently_online

    def _probe_connectivity(self) -> bool:
        """Attempt DNS resolution and lightweight socket handshake."""
        try:
            # 1. DNS Resolution
            ip = socket.gethostbyname(self.target_host)
            # 2. Socket Handshake
            s = socket.create_connection((ip, 443), timeout=CONNECT_TIMEOUT_SEC)
            s.close()
            return True
        except Exception:
            # Fallback check against Google public DNS if API DNS temporarily failed
            try:
                s = socket.create_connection(("8.8.8.8", 53), timeout=CONNECT_TIMEOUT_SEC)
                s.close()
                return True
            except Exception:
                return False
