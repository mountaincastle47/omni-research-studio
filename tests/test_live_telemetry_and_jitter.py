"""Integration and regression test suite for Live Cost Telemetry and Status Bar Jitter Prevention."""

import os
import sys
import unittest
from pathlib import Path

# Headless Qt environment setup
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from core.cost_tracker import LiveCostTracker, LiveTotals
from core.token_ledger import TokenLedger


class TestLiveCostTracker(unittest.TestCase):
    """Verify progressive pre-flight, streaming chunk accumulation, and post-flight reconciliation."""

    def setUp(self) -> None:
        self.ledger = TokenLedger(db_path=":memory:")
        self.tracker = LiveCostTracker(ledger=self.ledger)

    def test_initial_totals(self) -> None:
        totals = self.tracker.get_live_totals()
        self.assertEqual(totals.prompt_tokens, 0)
        self.assertEqual(totals.candidate_tokens, 0)
        self.assertEqual(totals.total_cost_usd, 0.0)
        self.assertFalse(totals.is_live)
        self.assertEqual(totals.active_tasks, 0)

    def test_preflight_input_cost(self) -> None:
        # Prompt: 10,000 chars -> ~2500 tokens on gemini-3.8-flash ($0.15 / 1M tokens)
        sample_prompt = "A" * 10000
        totals = self.tracker.start_task(
            task_id="task_1",
            model="gemini-3.8-flash",
            prompt_text_or_tokens=sample_prompt,
            session_id="test_session",
        )
        self.assertTrue(totals.is_live)
        self.assertEqual(totals.active_tasks, 1)
        self.assertEqual(totals.prompt_tokens, 2500)
        self.assertEqual(totals.candidate_tokens, 0)
        self.assertGreater(totals.total_cost_usd, 0.0)

    def test_progressive_streaming_accumulation(self) -> None:
        self.tracker.start_task(
            task_id="task_2",
            model="gemini-3.8-flash",
            prompt_text_or_tokens=1000,
            session_id="test_session",
        )
        initial_cost = self.tracker.get_live_totals().total_cost_usd

        # Stream chunks
        self.tracker.accumulate_chunk("task_2", "Chunk one text of length twenty. ")
        t1 = self.tracker.get_live_totals()
        self.assertGreater(t1.candidate_tokens, 0)
        self.assertGreaterEqual(t1.total_cost_usd, initial_cost)

        self.tracker.accumulate_chunk("task_2", "A" * 400)
        t2 = self.tracker.get_live_totals()
        self.assertGreater(t2.candidate_tokens, t1.candidate_tokens)
        self.assertGreater(t2.total_cost_usd, t1.total_cost_usd)

    def test_postflight_reconciliation(self) -> None:
        self.tracker.start_task(
            task_id="task_3",
            model="gemini-3.8-flash",
            prompt_text_or_tokens=5000,
            session_id="test_session",
        )
        self.tracker.accumulate_chunk("task_3", "Output chunk")

        # Reconcile exact counts
        self.tracker.reconcile_task(
            task_id="task_3",
            record_to_ledger=True,
            prompt_tokens=5120,
            candidate_tokens=850,
            cached_tokens=0,
        )

        reconciled = self.tracker.get_live_totals()
        self.assertFalse(reconciled.is_live)
        self.assertEqual(reconciled.active_tasks, 0)
        self.assertEqual(reconciled.prompt_tokens, 5120)
        self.assertEqual(reconciled.candidate_tokens, 850)
        self.assertGreater(reconciled.total_cost_usd, 0.0)

        # Verify SQLite audit store contains the transaction
        records = self.ledger.get_all_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].prompt_tokens, 5120)
        self.assertEqual(records[0].candidate_tokens, 850)


class TestStatusBarLayoutJitter(unittest.TestCase):
    """Verify geometry constraints and anti-jitter layout structures."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_status_bar_geometry_and_alignment(self) -> None:
        from ui.main_window import MainWindow

        win = MainWindow()
        win.show()

        # 1. ETA Label constraints
        self.assertEqual(win.eta_label.maximumWidth(), 85)
        self.assertEqual(win.eta_label.minimumWidth(), 85)
        align = win.eta_label.alignment()
        self.assertTrue(bool(align & Qt.AlignmentFlag.AlignRight))

        # 2. Progress Bar constraints
        self.assertEqual(win.progress_bar.maximumWidth(), 210)
        self.assertEqual(win.progress_bar.minimumWidth(), 210)

        # 3. Cancel Button constraints
        self.assertEqual(win.btn_cancel.maximumWidth(), 90)
        self.assertEqual(win.btn_cancel.minimumWidth(), 90)

        # 4. Container existence and child membership
        self.assertIsNotNone(win.status_controls_container)
        container_layout = win.status_controls_container.layout()
        self.assertIsNotNone(container_layout)
        self.assertEqual(container_layout.spacing(), 8)
        self.assertEqual(container_layout.contentsMargins().left(), 0)
        self.assertEqual(container_layout.contentsMargins().right(), 0)

        # 5. Jitter resistance test: Changing ETA label text must not change widget width
        for sample_text in ["ETA: ~142s", "ETA: ~88s", "ETA: ~9s", "Ready", ""]:
            win.eta_label.setText(sample_text)
            self.app.processEvents()
            self.assertEqual(win.eta_label.maximumWidth(), 85)
            self.assertEqual(win.eta_label.minimumWidth(), 85)
            self.assertEqual(win.progress_bar.maximumWidth(), 210)
            self.assertEqual(win.progress_bar.minimumWidth(), 210)
            self.assertEqual(win.btn_cancel.maximumWidth(), 90)
            self.assertEqual(win.btn_cancel.minimumWidth(), 90)

        # 6. Live telemetry updates text and live badge
        from core.cost_tracker import GLOBAL_COST_TRACKER
        GLOBAL_COST_TRACKER.reset()
        GLOBAL_COST_TRACKER.start_task("test_ui_task", "gemini-3.8-flash", 12000)
        win.update_telemetry()
        badge_text = win.telemetry_label.text()
        self.assertIn("Spend: $", badge_text)
        self.assertIn("⚡", badge_text)

        GLOBAL_COST_TRACKER.reconcile_task("test_ui_task", record_to_ledger=False)
        win.update_telemetry()
        win.close()


if __name__ == "__main__":
    unittest.main()
