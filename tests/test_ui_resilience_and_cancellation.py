"""Verification tests for UI layout resilience, cancellation hardening, and API key input constraints."""

import sys
import unittest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QSizePolicy, QLineEdit, QLayout

from ui.main_window import MainWindow
from ui.status_bar import StatusEtaWidget, OmniStatusBar
from ui.document_panel import DocumentToolbar
from ui.components import ApiKeyBanner
from ui.dialogs.api_key_dialog import ApiKeyDialog
from ui.dialogs.timeout_dialog import DiagnosticTimeoutDialog
from ui.workers import BaseCancellableWorker
from core.task_runner import TaskCancellationContext, TaskRunner


class TestUiResilienceAndCancellation(unittest.TestCase):
    """Test suite verifying status bar ETA splitting, diff button sizing, worker cancellation, and key modal constraints."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_eta_split_labels_and_font_metrics(self) -> None:
        widget = StatusEtaWidget(lang="en")
        widget.show()

        # In English: ETA: ~43s
        widget.set_eta(43)
        self.app.processEvents()
        self.assertEqual(widget.eta_prefix_label.text(), "ETA:")
        self.assertEqual(widget.eta_value_label.text(), "~43s")
        self.assertEqual(widget.eta_value_label.width(), 55)
        self.assertTrue(widget.eta_prefix_label.width() > 0)

        # In Korean: 남은 시간: ~43s
        widget.set_language("ko")
        widget.set_eta(43)
        self.app.processEvents()
        self.assertEqual(widget.eta_prefix_label.text(), "남은 시간:")
        self.assertEqual(widget.eta_value_label.text(), "~43s")
        self.assertEqual(widget.eta_value_label.width(), 55)
        self.assertTrue(widget.eta_prefix_label.width() > 0)

        # Clear
        widget.clear()
        self.assertEqual(widget.eta_prefix_label.text(), "")
        self.assertEqual(widget.eta_value_label.text(), "")
        widget.close()

    def test_diff_button_flexible_size_policy_and_padding(self) -> None:
        toolbar = DocumentToolbar(lang="en")
        btn = toolbar.btn_diff_compare

        # Check size policy accommodates variable text lengths
        self.assertEqual(btn.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Minimum)
        self.assertEqual(btn.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Fixed)

        # Check stylesheet padding
        ss = btn.styleSheet()
        self.assertIn("padding: 4px 10px;", ss)

        # In Korean
        toolbar.retranslate_ui("ko")
        self.assertEqual(btn.text(), "선택 문서 버전 비교 (Diff)...")

    def test_main_window_task_lifecycle_locks_language_combo(self) -> None:
        win = MainWindow()
        win.show()

        self.assertTrue(win.language_combo.isEnabled())

        # Simulate tracking worker
        worker = BaseCancellableWorker()
        win._track_worker(worker, "Running task...")
        self.assertFalse(win.language_combo.isEnabled())
        self.assertTrue(win.btn_cancel.isVisible())

        # Simulate cancel active task
        win._on_cancel_active_task()
        self.assertTrue(worker.stop_requested.is_set())
        self.assertTrue(worker.is_cancelled())
        self.assertTrue(win.language_combo.isEnabled())
        self.assertFalse(win.btn_cancel.isVisible())

        win.close()

    def test_api_key_banner_constraints(self) -> None:
        banner = ApiKeyBanner(initial_key="", lang="en")
        banner.show()

        # Fixed size policy & no inline QLineEdit in layout
        self.assertEqual(banner.layout().count(), 2)  # badge_label and change_btn
        self.assertTrue(banner.change_btn.isVisible())
        self.assertIn("No Key Configured", banner.badge_label.text())

        # Fixed layout constraint
        layout = banner.layout()
        self.assertEqual(layout.sizeConstraint(), QLayout.SizeConstraint.SetFixedSize)
        banner.close()

    def test_api_key_dialog_constraints(self) -> None:
        dlg = ApiKeyDialog(initial_key="", lang="en")
        # Fixed 440 x 190 sizing
        self.assertEqual(dlg.width(), 440)
        self.assertEqual(dlg.height(), 190)
        self.assertEqual(dlg.windowModality(), Qt.WindowModality.ApplicationModal)
        self.assertEqual(dlg.key_input.echoMode(), QLineEdit.EchoMode.Password)
        self.assertEqual(dlg.key_input.cursorPosition(), 0)
        self.assertEqual(dlg.key_input.placeholderText(), "AIzaSy...")
        dlg.close()

    def test_task_runner_cooperative_cancellation(self) -> None:
        runner = TaskRunner()
        ctx = runner.create_context()
        self.assertFalse(ctx.is_cancelled())
        runner.cancel_active()
        self.assertTrue(ctx.is_cancelled())
        self.assertTrue(ctx.stop_requested.is_set())

    def test_diagnostic_timeout_dialog_rendering(self) -> None:
        dlg = DiagnosticTimeoutDialog(current_stage="omnisweep_phase_2", elapsed_seconds=61.2, lang="en")
        self.assertEqual(dlg.width(), 520)
        self.assertEqual(dlg.height(), 360)
        self.assertEqual(dlg.windowModality(), Qt.WindowModality.ApplicationModal)
        self.assertIn("Timed Out", dlg.windowTitle())
        dlg.close()

        # In Korean
        dlg_ko = DiagnosticTimeoutDialog(current_stage="omnisweep_phase_2", elapsed_seconds=61.2, lang="ko")
        self.assertIn("작업 시간 초과", dlg_ko.windowTitle())
        dlg_ko.close()

    def test_omni_status_bar_spinner_and_reset(self) -> None:
        bar = OmniStatusBar(lang="en")
        bar.show()
        self.assertFalse(bar.spinner_label.isVisible())
        self.assertEqual(bar.progress_bar.minimum(), 0)
        self.assertEqual(bar.progress_bar.maximum(), 100)

        # Start busy
        bar.start_busy("omnisweep_phase_1")
        self.assertTrue(bar.spinner_label.isVisible())
        self.assertTrue(bar.spinner_timer.isActive())
        self.assertEqual(bar.progress_bar.minimum(), 0)
        self.assertEqual(bar.progress_bar.maximum(), 0)
        self.assertTrue(bar.btn_cancel.isVisible())

        # Progress update
        bar.set_progress(45, eta_seconds=12)
        self.assertEqual(bar.progress_bar.minimum(), 0)
        self.assertEqual(bar.progress_bar.maximum(), 100)
        self.assertEqual(bar.progress_bar.value(), 45)

        # Reset
        bar.reset_state()
        self.assertFalse(bar.spinner_label.isVisible())
        self.assertFalse(bar.spinner_timer.isActive())
        self.assertEqual(bar.progress_bar.value(), 0)
        self.assertFalse(bar.btn_cancel.isVisible())
        bar.close()

    def test_base_worker_watchdog_timeout_signal(self) -> None:
        import time
        worker = BaseCancellableWorker()
        worker._watchdog_timeout = 0.15  # fast timeout for testing
        worker._total_stall_limit = 0.5

        received = []
        worker.task_timed_out.connect(lambda stage, elapsed: received.append((stage, elapsed)))

        worker.start_watchdog("test_stage")
        time.sleep(0.35)
        self.app.processEvents()
        worker.stop_watchdog()
        self.app.processEvents()

        self.assertTrue(worker.is_cancelled())
        self.assertTrue(worker.stop_requested.is_set())
        self.assertGreaterEqual(len(received), 1)
        self.assertEqual(received[0][0], "test_stage")


if __name__ == "__main__":
    unittest.main()
