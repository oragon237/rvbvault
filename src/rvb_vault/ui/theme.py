from __future__ import annotations

import ctypes
import os
import re
from ctypes import wintypes

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget


LIGHT = {
    "window": "rgba(238,241,245,242)", "panel": "rgba(255,255,255,225)",
    "sidebar": "rgba(247,248,250,218)", "list": "rgba(252,252,253,226)", "detail": "rgba(247,248,250,215)",
    "field": "rgba(255,255,255,220)", "preview": "rgba(244,246,248,210)",
    "text": "#181a1e", "muted": "#737982", "faint": "#9ca1a8", "border": "rgba(24,29,36,24)",
    "borderStrong": "rgba(24,29,36,42)", "hover": "rgba(22,27,34,12)", "pressed": "rgba(22,27,34,22)",
    "selected": "rgba(26,31,38,22)", "focus": "#8e959e", "accent": "#25282d", "accentText": "#ffffff",
    "danger": "#b14a43", "dangerHover": "rgba(177,74,67,12)", "highlight": "#e8eaed", "midlight": "#f2f3f5",
}
DARK = {
    "window": "rgba(16,17,19,244)", "panel": "rgba(27,29,32,224)",
    "sidebar": "rgba(22,24,27,224)", "list": "rgba(27,29,32,224)", "detail": "rgba(23,25,28,220)",
    "field": "rgba(34,36,40,216)", "preview": "rgba(18,20,23,205)",
    "text": "#f0f1f2", "muted": "#9ca2aa", "faint": "#727880", "border": "rgba(255,255,255,18)",
    "borderStrong": "rgba(255,255,255,34)", "hover": "rgba(255,255,255,10)", "pressed": "rgba(255,255,255,18)",
    "selected": "rgba(255,255,255,18)", "focus": "#747b84", "accent": "#f0f1f2", "accentText": "#1b1d20",
    "danger": "#e37a72", "dangerHover": "rgba(227,122,114,11)", "highlight": "#3a3d42", "midlight": "#303338",
}


def effective_mode(app: QApplication, preference: str) -> str:
    if preference.lower() == "system":
        scheme = app.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"
    return preference.lower()


def stylesheet(tokens: dict[str, str]) -> str:
    return f"""
    * {{ font-family: "Segoe UI"; font-size: 13px; color: {tokens['text']}; }}
    QMainWindow, QDialog {{ background: {tokens['window']}; }}
    QWidget#rootCard {{ background: {tokens['panel']}; border: 1px solid {tokens['borderStrong']}; border-radius: 12px; }}
    QWidget#sidebar {{ background: {tokens['sidebar']}; border-right: 1px solid {tokens['border']}; border-top-left-radius: 12px; border-bottom-left-radius: 12px; }}
    QWidget#resultPanel {{ background: {tokens['list']}; border-right: 1px solid {tokens['border']}; }}
    QWidget#detailPanel {{ background: {tokens['detail']}; border-top-right-radius: 12px; border-bottom-right-radius: 12px; }}
    QFrame#fieldRow, QFrame#groupCard, QFrame#segmentRow {{ background: {tokens['field']}; border: 1px solid {tokens['border']}; border-radius: 8px; }}
    QFrame#procedureStep {{ background: {tokens['preview']}; border: 1px solid {tokens['borderStrong']}; border-radius: 9px; }}
    QFrame#groupCard {{ border: 1px solid {tokens['borderStrong']}; }}
    QLabel#segmentBadge {{ color: {tokens['muted']}; font-size: 10px; font-weight: 650; padding: 2px 5px; background: {tokens['hover']}; border-radius: 4px; }}
    QLabel#brand {{ font-size: 17px; font-weight: 650; letter-spacing: -0.2px; }}
    QLabel#workspaceTitle {{ font-size: 20px; font-weight: 650; letter-spacing: -0.3px; }}
    QLabel#sectionTitle {{ font-size: 10px; font-weight: 650; color: {tokens['muted']}; letter-spacing: 0.6px; text-transform: uppercase; }}
    QLabel#muted, QLabel.muted {{ color: {tokens['muted']}; }}
    QLabel#faint {{ color: {tokens['faint']}; }}
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{
        background: {tokens['field']}; border: 1px solid {tokens['border']}; border-radius: 6px; padding: 6px 8px;
        selection-background-color: {tokens['selected']};
    }}
    QLineEdit, QComboBox, QSpinBox {{ min-height: 20px; }}
    QLineEdit#searchInput {{ background: {tokens['preview']}; padding-left: 4px; }}
    QLineEdit#entryTitle {{ background: transparent; border: 0; border-bottom: 1px solid {tokens['border']}; border-radius: 0; padding: 8px 2px; font-size: 20px; font-weight: 650; }}
    QLineEdit#entryTitle:focus {{ border: 0; border-bottom: 1px solid {tokens['focus']}; }}
    QPlainTextEdit#preview {{ background: {tokens['preview']}; border-color: {tokens['border']}; }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {tokens['focus']}; }}
    QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled {{ color: {tokens['faint']}; background: {tokens['hover']}; }}
    QComboBox {{ padding-right: 26px; }}
    QComboBox::drop-down {{ border: 0; border-left: 1px solid {tokens['border']}; width: 24px; }}
    QComboBox QAbstractItemView {{ background: {tokens['panel']}; border: 1px solid {tokens['borderStrong']}; selection-background-color: {tokens['selected']}; outline: 0; }}
    QPushButton {{ background: transparent; border: 1px solid {tokens['borderStrong']}; border-radius: 6px; padding: 5px 10px; min-height: 20px; }}
    QPushButton:hover {{ background: {tokens['hover']}; }}
    QPushButton:pressed {{ background: {tokens['pressed']}; }}
    QPushButton:focus {{ border: 1px solid {tokens['focus']}; }}
    QPushButton#primary {{ background: {tokens['accent']}; color: {tokens['accentText']}; border: 0; font-weight: 600; }}
    QPushButton#primary:hover {{ opacity: 0.92; }}
    QPushButton#danger, QToolButton[danger="true"] {{ color: {tokens['danger']}; }}
    QPushButton#danger:hover, QToolButton[danger="true"]:hover {{ background: {tokens['dangerHover']}; }}
    QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 5px; min-height: 18px; }}
    QToolButton:hover {{ background: {tokens['hover']}; }}
    QToolButton:pressed {{ background: {tokens['pressed']}; }}
    QToolButton:focus {{ border: 1px solid {tokens['focus']}; }}
    QToolButton:disabled, QPushButton:disabled {{ color: {tokens['faint']}; background: transparent; border-color: transparent; }}
    QCheckBox {{ spacing: 7px; color: {tokens['muted']}; }}
    QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {tokens['borderStrong']}; border-radius: 4px; background: {tokens['field']}; }}
    QCheckBox::indicator:hover {{ border-color: {tokens['focus']}; background: {tokens['hover']}; }}
    QCheckBox::indicator:checked {{ background: {tokens['accent']}; border-color: {tokens['accent']}; }}
    QCheckBox::indicator:disabled {{ background: {tokens['hover']}; border-color: {tokens['border']}; }}
    QListWidget {{ background: transparent; border: 0; outline: 0; }}
    QListWidget#navigation::item {{ border-radius: 6px; padding: 6px 8px; margin: 1px 0; }}
    QListWidget::item:hover {{ background: {tokens['hover']}; }}
    QListWidget::item:selected {{ background: {tokens['selected']}; }}
    QListWidget#navigation::item:selected {{ color: {tokens['text']}; }}
    QListWidget#importPreviewList {{ background: {tokens['preview']}; border: 1px solid {tokens['border']}; border-radius: 7px; padding: 5px; }}
    QListWidget#importPreviewList::item {{ padding: 7px 8px; border-radius: 5px; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: 0; }}
    QScrollBar:vertical {{ width: 8px; background: transparent; margin: 2px 1px; }}
    QScrollBar::handle:vertical {{ background: {tokens['borderStrong']}; border-radius: 3px; min-height: 28px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QSplitter::handle {{ background: {tokens['border']}; }}
    QMenu {{ background: {tokens['panel']}; border: 1px solid {tokens['border']}; padding: 5px; }}
    QMenu::item {{ padding: 6px 24px 6px 9px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {tokens['selected']}; }}
    QToolTip {{ background: {tokens['panel']}; color: {tokens['text']}; border: 1px solid {tokens['borderStrong']}; border-radius: 4px; padding: 5px 7px; }}
    QLabel#toast {{ background: {tokens['accent']}; color: {tokens['accentText']}; border-radius: 7px; padding: 7px 12px; font-weight: 600; }}
    """


def apply_theme(app: QApplication, preference: str) -> str:
    mode = effective_mode(app, preference)
    tokens = DARK if mode == "dark" else LIGHT
    app.setStyleSheet(stylesheet(tokens))
    palette = app.palette()
    def color(value: str) -> QColor:
        match = re.fullmatch(r"rgba\((\d+),(\d+),(\d+),(\d+)\)", value.replace(" ", ""))
        return QColor(*map(int, match.groups())) if match else QColor(value)

    palette.setColor(QPalette.ColorRole.WindowText, color(tokens["text"]))
    palette.setColor(QPalette.ColorRole.Text, color(tokens["text"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, color(tokens["muted"]))
    palette.setColor(QPalette.ColorRole.Window, color(tokens["window"]))
    palette.setColor(QPalette.ColorRole.Base, color(tokens["field"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, color(tokens["preview"]))
    palette.setColor(QPalette.ColorRole.Button, color(tokens["field"]))
    palette.setColor(QPalette.ColorRole.ButtonText, color(tokens["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, color(tokens["highlight"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, color(tokens["text"]))
    palette.setColor(QPalette.ColorRole.Midlight, color(tokens["midlight"]))
    app.setPalette(palette)
    return mode


def enable_windows_blur(widget: QWidget, dark: bool) -> bool:
    """Best-effort acrylic; the stylesheet remains the portable fallback."""
    if os.name != "nt":
        return False
    try:
        class AccentPolicy(ctypes.Structure):
            _fields_ = [("state", ctypes.c_int), ("flags", ctypes.c_int), ("color", ctypes.c_uint), ("animation", ctypes.c_int)]

        class WindowCompositionAttributeData(ctypes.Structure):
            _fields_ = [("attribute", ctypes.c_int), ("data", ctypes.c_void_p), ("size", ctypes.c_size_t)]

        accent = AccentPolicy(4, 2, 0xCC18191B if dark else 0xCCF5F5F5, 0)
        data = WindowCompositionAttributeData(19, ctypes.addressof(accent), ctypes.sizeof(accent))
        result = ctypes.windll.user32.SetWindowCompositionAttribute(wintypes.HWND(int(widget.winId())), ctypes.byref(data))
        return bool(result)
    except Exception:
        return False
