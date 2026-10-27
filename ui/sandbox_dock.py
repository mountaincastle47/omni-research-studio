"""Mathematical Verification Sandbox Dock (QDockWidget):
Interactive Python REPL, telemetry calculation runner, and Matplotlib plot preview.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.i18n import get_text
from core.math_sandbox import MathSandbox, SandboxResult

DEFAULT_SANDBOX_TEMPLATE = """# Empirical Telemetry Modeling & Verification
import numpy as np
import matplotlib.pyplot as plt

# 1. Define model parameters
time_s = np.linspace(0, 10, 200)
baseline_thrust_kn = 450.0 * np.exp(-0.05 * time_s)
observed_telemetry = baseline_thrust_kn + np.random.normal(0, 8.0, len(time_s))

# 2. Compute variance & divergence metrics
rmse = np.sqrt(np.mean((observed_telemetry - baseline_thrust_kn) ** 2))
print(f"Calculated Thrust RMSE: {rmse:.3f} kN")
print(f"Peak Divergence: {np.max(np.abs(observed_telemetry - baseline_thrust_kn)):.3f} kN")

# 3. Render telemetry verification plot
fig, ax = plt.subplots(figsize=(6, 3), dpi=120)
ax.plot(time_s, baseline_thrust_kn, label="Baseline Model", color="#38BDF8", linewidth=1.8)
ax.scatter(time_s[::8], observed_telemetry[::8], label="Telemetry Sensor", color="#F87171", s=15, alpha=0.8)
ax.set_title("Propulsion Telemetry Verification Curve", fontsize=10, color="#F1F5F9")
ax.set_xlabel("Time (s)", fontsize=8, color="#94A3B8")
ax.set_ylabel("Thrust (kN)", fontsize=8, color="#94A3B8")
ax.grid(True, linestyle="--", alpha=0.3)
ax.legend(loc="upper right", fontsize=8)
fig.patch.set_facecolor("#0F172A")
ax.set_facecolor("#0B0E14")
ax.tick_params(colors="#94A3B8")
for spine in ax.spines.values():
    spine.set_color("#334155")
"""


class SandboxDock(QDockWidget):
    """Dockable panel with Python REPL, terminal console, and Matplotlib plot viewer."""

    insert_requested = pyqtSignal(str)

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self.sandbox = MathSandbox(timeout_seconds=5.0)
        self.last_result: Optional[SandboxResult] = None

        self.setWindowTitle(get_text("dock_sandbox_title", self._lang))
        self.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self._build_ui()

    def _build_ui(self) -> None:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Splitter between Editor and Output
        splitter = QSplitter(Qt.Orientation.Vertical, container)

        # Top Section: Code Editor & Run Strip
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(4)

        btn_row = QHBoxLayout()
        self.btn_run = QPushButton(get_text("btn_run_sandbox", self._lang), self)
        self.btn_run.setStyleSheet(
            "QPushButton { background-color: #0284C7; color: #FFFFFF; font-weight: 700; "
            "border-radius: 5px; padding: 5px 14px; font-size: 11px; } QPushButton:hover { background-color: #0369A1; }"
        )
        self.btn_run.clicked.connect(self._run_code)
        btn_row.addWidget(self.btn_run)

        self.btn_insert = QPushButton(get_text("btn_insert_plot", self._lang), self)
        self.btn_insert.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #38BDF8; border: 1px solid #334155; "
            "border-radius: 5px; padding: 5px 12px; font-size: 11px; } QPushButton:hover { background-color: #334155; }"
        )
        self.btn_insert.clicked.connect(self._insert_to_report)
        self.btn_insert.setEnabled(False)
        btn_row.addWidget(self.btn_insert)

        btn_row.addStretch(1)
        self.status_label = QLabel("Sandbox Ready (5s ceiling, sandboxed filesystem)", self)
        self.status_label.setStyleSheet("color: #64748B; font-size: 10px;")
        btn_row.addWidget(self.status_label)

        editor_layout.addLayout(btn_row)

        self.code_editor = QPlainTextEdit(editor_widget)
        self.code_editor.setFont(QFont("Consolas", 10))
        self.code_editor.setStyleSheet(
            "QPlainTextEdit { background-color: #090D16; color: #E2E8F0; border: 1px solid #1E293B; "
            "border-radius: 6px; padding: 6px; }"
        )
        self.code_editor.setPlainText(DEFAULT_SANDBOX_TEMPLATE)
        editor_layout.addWidget(self.code_editor)

        splitter.addWidget(editor_widget)

        # Bottom Section: Terminal Output + Plot Preview
        output_widget = QWidget()
        output_layout = QHBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(6)

        # Terminal
        term_box = QVBoxLayout()
        term_title = QLabel(get_text("sandbox_terminal_title", self._lang), output_widget)
        term_title.setStyleSheet("color: #94A3B8; font-weight: 700; font-size: 10px;")
        term_box.addWidget(term_title)

        self.terminal_view = QTextEdit(output_widget)
        self.terminal_view.setReadOnly(True)
        self.terminal_view.setFont(QFont("Consolas", 9))
        self.terminal_view.setStyleSheet(
            "QTextEdit { background-color: #05070B; color: #38BDF8; border: 1px solid #1E293B; "
            "border-radius: 6px; padding: 6px; }"
        )
        term_box.addWidget(self.terminal_view)
        output_layout.addLayout(term_box, stretch=1)

        # Plot Preview
        plot_box = QVBoxLayout()
        self.plot_title = QLabel(get_text("sandbox_plot_title", self._lang), output_widget)
        self.plot_title.setStyleSheet("color: #94A3B8; font-weight: 700; font-size: 10px;")
        plot_box.addWidget(self.plot_title)

        self.plot_scroll = QScrollArea(output_widget)
        self.plot_scroll.setStyleSheet("QScrollArea { background-color: #05070B; border: 1px solid #1E293B; border-radius: 6px; }")
        self.plot_scroll.setWidgetResizable(True)

        self.plot_label = QLabel(self.plot_scroll)
        self.plot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_label.setStyleSheet("color: #475569; font-size: 11px;")
        self.plot_label.setText("No plot generated yet")
        self.plot_scroll.setWidget(self.plot_label)

        plot_box.addWidget(self.plot_scroll)
        output_layout.addLayout(plot_box, stretch=1)

        splitter.addWidget(output_widget)
        splitter.setSizes([320, 260])

        layout.addWidget(splitter)
        self.setWidget(container)

    def _run_code(self) -> None:
        """Execute Python script inside isolated sandbox."""
        code = self.code_editor.toPlainText()
        self.btn_run.setEnabled(False)
        self.status_label.setText("Executing script...")

        res = self.sandbox.execute_script(code)
        self.last_result = res
        self.btn_run.setEnabled(True)

        # Update terminal
        out_text = res.stdout
        if res.stderr:
            out_text += f"\n[STDERR]\n{res.stderr}"
        if not out_text.strip():
            out_text = f"Execution finished cleanly in {res.execution_time_ms:.1f}ms (No stdout)."

        self.terminal_view.setPlainText(out_text)
        self.status_label.setText(f"Completed in {res.execution_time_ms:.1f}ms")

        # Update Plot Preview
        if res.plots:
            latest_plot = res.plots[-1]
            if Path(latest_plot).exists():
                pix = QPixmap(latest_plot)
                self.plot_label.setPixmap(pix.scaled(480, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                self.btn_insert.setEnabled(True)
        else:
            self.plot_label.setPixmap(QPixmap())
            self.plot_label.setText("No plot generated in this execution run.")
            self.btn_insert.setEnabled(bool(res.stdout.strip()))

    def _insert_to_report(self) -> None:
        """Emit markdown fragment to insert into active synthesis report."""
        if self.last_result:
            md = self.last_result.to_markdown()
            self.insert_requested.emit(md)
            self.status_label.setText("Inserted verification results to report.")

    def retranslate_ui(self, lang: str = "en") -> None:
        self._lang = lang
        self.setWindowTitle(get_text("dock_sandbox_title", lang))
        self.btn_run.setText(get_text("btn_run_sandbox", lang))
        self.btn_insert.setText(get_text("btn_insert_plot", lang))
        self.plot_title.setText(get_text("sandbox_plot_title", lang))
