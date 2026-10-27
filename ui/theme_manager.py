"""Theme and dynamic typography manager for OmniResearch Studio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class ColorPalette:
    name: str
    bg: str
    surface: str
    card: str
    border: str
    text_primary: str
    text_muted: str
    accent: str
    accent_hover: str
    btn_bg: str
    btn_hover: str
    status_strip: str


THEMES: Dict[str, ColorPalette] = {
    "dark": ColorPalette(
        name="Dark Studio",
        bg="#0B0F19",
        surface="#161B22",
        card="#0F172A",
        border="#30363D",
        text_primary="#C9D1D9",
        text_muted="#94A3B8",
        accent="#58A6FF",
        accent_hover="#79C0FF",
        btn_bg="#1E293B",
        btn_hover="#334155",
        status_strip="#090D16",
    ),
    "oled": ColorPalette(
        name="OLED Black",
        bg="#000000",
        surface="#0A0A0A",
        card="#050505",
        border="#27272A",
        text_primary="#FFFFFF",
        text_muted="#A1A1AA",
        accent="#38BDF8",
        accent_hover="#7DD3FC",
        btn_bg="#18181B",
        btn_hover="#27272A",
        status_strip="#000000",
    ),
    "light": ColorPalette(
        name="Academic Light",
        bg="#F8FAFC",
        surface="#FFFFFF",
        card="#F1F5F9",
        border="#CBD5E1",
        text_primary="#0F172A",
        text_muted="#64748B",
        accent="#0284C7",
        accent_hover="#0369A1",
        btn_bg="#E2E8F0",
        btn_hover="#CBD5E1",
        status_strip="#E2E8F0",
    ),
}

AVAILABLE_FONTS: List[str] = [
    "Segoe UI",
    "Pretendard",
    "Inter",
    "Cascadia Code",
    "Merriweather",
    "Malgun Gothic",
]


class ThemeManager(QObject):
    """Manages application stylesheet dynamic generation, color palette swapping, and typography zoom."""

    theme_changed = pyqtSignal(str)
    font_changed = pyqtSignal(str, int)

    _instance: Optional[ThemeManager] = None

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.current_theme: str = "dark"
        self.current_font: str = "Segoe UI"
        self.current_font_size: int = 13

    @classmethod
    def get_instance(cls) -> ThemeManager:
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    def set_theme(self, theme_key: str) -> str:
        """Switch active theme palette ('dark', 'oled', 'light') and return updated stylesheet."""
        if theme_key in THEMES:
            self.current_theme = theme_key
            self.theme_changed.emit(self.current_theme)
        return self.get_stylesheet()

    def apply_title_bar(self, window: Any) -> None:
        """Apply Windows DWM immersive dark mode to window based on active palette."""
        is_dark = self.current_theme in ("dark", "oled")
        apply_windows_dark_title_bar(window, dark=is_dark)

    def set_font_family(self, family: str) -> str:
        """Update active font family and return updated stylesheet."""
        self.current_font = family
        self.font_changed.emit(self.current_font, self.current_font_size)
        return self.get_stylesheet()

    def zoom_in(self) -> str:
        """Increase typography scale up to 24pt."""
        if self.current_font_size < 24:
            self.current_font_size += 1
            self.font_changed.emit(self.current_font, self.current_font_size)
        return self.get_stylesheet()

    def zoom_out(self) -> str:
        """Decrease typography scale down to 9pt."""
        if self.current_font_size > 9:
            self.current_font_size -= 1
            self.font_changed.emit(self.current_font, self.current_font_size)
        return self.get_stylesheet()

    def reset_zoom(self) -> str:
        """Reset typography scale to standard 13pt."""
        self.current_font_size = 13
        self.font_changed.emit(self.current_font, self.current_font_size)
        return self.get_stylesheet()

    def get_stylesheet(self) -> str:
        """Generate comprehensive application QSS for active theme and typography."""
        p = THEMES.get(self.current_theme, THEMES["dark"])
        font_str = f"'{self.current_font}', 'Malgun Gothic', sans-serif"
        sz = self.current_font_size

        return f"""
QMainWindow, QWidget {{
    background-color: {p.bg};
    color: {p.text_primary};
    font-family: {font_str};
    font-size: {sz}px;
}}
QGroupBox {{
    border: 1px solid {p.border};
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: 600;
    color: {p.text_muted};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
}}
QPushButton {{
    background-color: {p.btn_bg};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {p.btn_hover};
    border-color: {p.accent};
}}
QPushButton:pressed {{
    background-color: {p.accent};
    color: #FFFFFF;
}}
QPushButton:disabled {{
    background-color: {p.surface};
    color: {p.text_muted};
    border-color: {p.border};
}}
QPushButton#PrimaryActionBtn {{
    background-color: #0284C7;
    border: 1px solid #38BDF8;
    color: #FFFFFF;
    font-weight: 600;
}}
QPushButton#PrimaryActionBtn:hover {{
    background-color: #0369A1;
}}
QPushButton#OmniSweepActionBtn {{
    background-color: #7E22CE;
    border: 1px solid #A855F7;
    color: #FFFFFF;
    font-weight: 600;
}}
QPushButton#OmniSweepActionBtn:hover {{
    background-color: #6B21A8;
}}
QPushButton#AudioActionBtn {{
    background-color: #059669;
    border: 1px solid #10B981;
    color: #FFFFFF;
    font-weight: 600;
}}
QPushButton#AudioActionBtn:hover {{
    background-color: #047857;
}}
QPushButton#CancelTaskBtn {{
    background-color: #991B1B;
    border: 1px solid #F43F5E;
    color: #FFFFFF;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 700;
    border-radius: 5px;
}}
QPushButton#CancelTaskBtn:hover {{
    background-color: #B91C1C;
}}
QPushButton#ToggleViewBtn {{
    background-color: {p.surface};
    border: 1px solid {p.accent};
    color: {p.accent};
    padding: 4px 10px;
    font-size: 12px;
    border-radius: 5px;
}}
QToolButton#ExportSplitBtn {{
    background-color: {p.btn_bg};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 6px;
    padding: 7px 26px 7px 12px;
    font-weight: 600;
}}
QToolButton#ExportSplitBtn:hover {{
    background-color: {p.btn_hover};
}}
QSplitter::handle {{
    background-color: {p.border};
    width: 4px;
}}
QSplitter::handle:hover {{
    background-color: {p.accent};
}}
QMenuBar {{
    background-color: {p.bg};
    color: {p.text_primary};
    border-bottom: 1px solid {p.border};
}}
QMenuBar::item:selected {{
    background-color: {p.btn_bg};
}}
QMenu {{
    background-color: {p.surface};
    color: {p.text_primary};
    border: 1px solid {p.border};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px 6px 14px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {p.accent};
    color: #FFFFFF;
}}
QPushButton#ActionBtnPrimary {{
    background-color: #2563EB;
    color: #FFFFFF;
    font-weight: 600;
    border: none;
}}
QPushButton#ActionBtnPrimary:hover {{
    background-color: #1D4ED8;
}}
QPushButton#ActionBtnPrimary:disabled {{
    background-color: {p.btn_bg};
    color: {p.text_muted};
}}
QPushButton#CancelBtnActive {{
    background-color: #DC2626;
    color: #FFFFFF;
    font-weight: 600;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton#CancelBtnActive:hover {{
    background-color: #B91C1C;
}}
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {p.surface};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {p.accent};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {p.accent};
}}
QComboBox {{
    background-color: {p.surface};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 6px;
    padding: 5px 8px;
}}
QComboBox:hover {{
    border-color: {p.accent};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {p.surface};
    color: {p.text_primary};
    selection-background-color: {p.btn_hover};
    border: 1px solid {p.border};
}}
QProgressBar {{
    border: 1px solid {p.border};
    border-radius: 4px;
    text-align: center;
    background-color: {p.surface};
    color: {p.text_primary};
    font-size: 11px;
    font-weight: bold;
}}
QProgressBar::chunk {{
    background-color: {p.accent};
    border-radius: 3px;
}}
QTabBar::tab {{
    background-color: {p.surface};
    color: {p.text_muted};
    border: 1px solid {p.border};
    border-bottom: none;
    padding: 8px 16px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {p.card};
    color: {p.accent};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    background-color: {p.btn_bg};
}}
QHeaderView::section {{
    background-color: {p.surface};
    color: {p.text_muted};
    padding: 6px;
    border: 1px solid {p.border};
    font-weight: 600;
}}
QScrollBar:vertical {{
    border: none;
    background-color: {p.bg};
    width: 10px;
    margin: 0px 0px 0px 0px;
}}
QScrollBar::handle:vertical {{
    background-color: {p.border};
    min-height: 20px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {p.text_muted};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""


def apply_windows_dark_title_bar(window: Any, dark: bool = True) -> None:
    """Set the Windows DWM title bar to dark or light mode using DwmSetWindowAttribute.
    Ensures window handles passed to DwmSetWindowAttribute are explicitly cast:
    hwnd = ctypes.wintypes.HWND(int(window.winId())), wrapping the call in a try...except block.
    """
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = ctypes.wintypes.HWND(int(window.winId()))
        value = ctypes.c_int(1 if dark else 0)
        dwmapi = ctypes.WinDLL("dwmapi")
        # Try DWMWA_USE_IMMERSIVE_DARK_MODE (20 on Win 11 / 10 20H1+, 19 on older Win 10 builds)
        res = dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        if res != 0:
            dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass
