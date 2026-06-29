"""Design tokens and Qt style sheet (QSS) for light and dark themes.

The whole look of the app is driven from two colour dictionaries here, so the
visual language stays consistent and a theme switch is a single ``setStyleSheet``
call. Colours are deliberately restrained — a calm neutral canvas, one confident
accent and a clear traffic-light set — to avoid the over-saturated "AI default"
look.
"""

from __future__ import annotations

# --- Colour tokens ---------------------------------------------------------
LIGHT = {
    "bg": "#eef1f6",
    "surface": "#ffffff",
    "surface_2": "#f5f7fa",
    "surface_3": "#eaeef4",
    "border": "#dce1e9",
    "border_strong": "#c6cdd9",
    "text": "#1b2330",
    "text_muted": "#5d6877",
    "text_faint": "#8a93a3",
    "primary": "#2f6bd8",
    "primary_hover": "#285fc4",
    "primary_soft": "#e6eefb",
    "sidebar": "#10182a",
    "sidebar_text": "#aeb8c9",
    "sidebar_text_active": "#ffffff",
    "sidebar_active": "#22324f",
    "sidebar_accent": "#4d82f3",
    # Traffic-light / semantic
    "green": "#1f9d57",
    "green_soft": "#e3f5ea",
    "amber": "#d98817",
    "amber_soft": "#fbeede",
    "red": "#d6453d",
    "red_soft": "#fbe5e4",
    "blue": "#2f6bd8",
    "blue_soft": "#e6eefb",
    "grey": "#8a93a3",
    "grey_soft": "#eceff4",
    "shadow": "rgba(20, 30, 50, 0.10)",
}

DARK = {
    "bg": "#0f141c",
    "surface": "#19212d",
    "surface_2": "#202a38",
    "surface_3": "#27323f",
    "border": "#2b3645",
    "border_strong": "#3a4858",
    "text": "#e7edf5",
    "text_muted": "#9aa6b6",
    "text_faint": "#6c7889",
    "primary": "#4d82f3",
    "primary_hover": "#5e8ff5",
    "primary_soft": "#1c2c46",
    "sidebar": "#0b111c",
    "sidebar_text": "#9aa6b6",
    "sidebar_text_active": "#ffffff",
    "sidebar_active": "#1c2839",
    "sidebar_accent": "#4d82f3",
    "green": "#37b870",
    "green_soft": "#13301f",
    "amber": "#e2a13a",
    "amber_soft": "#33260f",
    "red": "#e85d54",
    "red_soft": "#3a1c1a",
    "blue": "#4d82f3",
    "blue_soft": "#16233b",
    "grey": "#6c7889",
    "grey_soft": "#222c39",
    "shadow": "rgba(0, 0, 0, 0.35)",
}

# Map a traffic-light key to its (foreground, soft-background) token names.
AMPEL = {
    "green": ("green", "green_soft"),
    "amber": ("amber", "amber_soft"),
    "red": ("red", "red_soft"),
    "blue": ("blue", "blue_soft"),
    "grey": ("grey", "grey_soft"),
}


def palette(theme: str) -> dict:
    return DARK if theme == "dark" else LIGHT


def ampel_color(key: str, colors: dict) -> str:
    fg, _ = AMPEL.get(key, ("grey", "grey_soft"))
    return colors[fg]


def ampel_soft(key: str, colors: dict) -> str:
    _, bg = AMPEL.get(key, ("grey", "grey_soft"))
    return colors[bg]


def build_qss(c: dict) -> str:
    """Build the application-wide style sheet from a colour dictionary."""
    return f"""
* {{
    font-family: "Segoe UI", "Inter", "Roboto", sans-serif;
    font-size: 14px;
    color: {c['text']};
}}
QWidget#Root, QStackedWidget, QMainWindow {{
    background: {c['bg']};
}}
QToolTip {{
    background: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border_strong']};
    padding: 6px 9px;
    border-radius: 6px;
}}

/* ---- Dialogs (force app-theme colours so they don't follow the OS dark/light
        mode, which previously made message-box text unreadable) ---- */
QDialog, QMessageBox, QInputDialog {{
    background: {c['bg']};
}}
QMessageBox QLabel, QInputDialog QLabel {{
    color: {c['text']};
    background: transparent;
}}

/* ---- Sidebar ---- */
QWidget#Sidebar {{
    background: {c['sidebar']};
    border: none;
}}
QLabel#Brand {{
    color: {c['sidebar_text_active']};
    font-size: 18px;
    font-weight: 700;
    padding: 4px 6px;
}}
QLabel#BrandSub {{
    color: {c['sidebar_text']};
    font-size: 11px;
    letter-spacing: 1px;
}}
QPushButton#NavButton {{
    color: {c['sidebar_text']};
    background: transparent;
    border: none;
    border-radius: 9px;
    padding: 11px 14px;
    text-align: left;
    font-size: 14px;
    font-weight: 500;
}}
QPushButton#NavButton:hover {{
    background: {c['sidebar_active']};
    color: {c['sidebar_text_active']};
}}
QPushButton#NavButton:checked {{
    background: {c['sidebar_active']};
    color: {c['sidebar_text_active']};
    font-weight: 600;
}}

/* ---- Cards & panels ---- */
QFrame#Card, QFrame#Panel {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 14px;
}}
QFrame#Panel {{
    border-radius: 12px;
}}
QLabel#CardTitle {{
    color: {c['text_muted']};
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}}
QLabel#CardValue {{
    font-size: 26px;
    font-weight: 700;
    color: {c['text']};
}}
QLabel#CardHint {{
    color: {c['text_faint']};
    font-size: 12px;
}}
QLabel#H1 {{ font-size: 23px; font-weight: 700; }}
QLabel#H2 {{ font-size: 17px; font-weight: 700; }}
QLabel#Muted {{ color: {c['text_muted']}; }}
QLabel#Faint {{ color: {c['text_faint']}; font-size: 12px; }}

/* ---- Buttons ---- */
QPushButton {{
    background: {c['surface_2']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 9px;
    padding: 8px 15px;
    font-weight: 500;
}}
QPushButton:hover {{ background: {c['surface_3']}; }}
QPushButton:disabled {{ color: {c['text_faint']}; background: {c['surface_2']}; }}
QPushButton#Primary {{
    background: {c['primary']};
    color: #ffffff;
    border: 1px solid {c['primary']};
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: {c['primary_hover']}; border-color: {c['primary_hover']}; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid {c['border']}; }}
QPushButton#Ghost:hover {{ background: {c['surface_2']}; }}
QPushButton#Danger {{ color: {c['red']}; border: 1px solid {c['border']}; background: transparent; }}
QPushButton#Danger:hover {{ background: {c['red_soft']}; }}
QPushButton#Link {{ background: transparent; border: none; color: {c['primary']}; padding: 4px; }}
QPushButton#Link:hover {{ color: {c['primary_hover']}; text-decoration: underline; }}

/* ---- Inputs ---- */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
    background: {c['surface']};
    border: 1px solid {c['border_strong']};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {c['primary']};
    selection-color: #ffffff;
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {c['primary']};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {c['surface']};
    border: 1px solid {c['border_strong']};
    selection-background-color: {c['primary_soft']};
    selection-color: {c['text']};
    outline: none;
}}
QLabel#FieldLabel {{ color: {c['text_muted']}; font-size: 12px; font-weight: 600; }}

/* ---- Tables ---- */
QTableWidget, QTableView {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 12px;
    gridline-color: {c['surface_3']};
    selection-background-color: {c['primary_soft']};
    selection-color: {c['text']};
    alternate-background-color: {c['surface_2']};
}}
QHeaderView::section {{
    background: {c['surface_2']};
    color: {c['text_muted']};
    padding: 9px 10px;
    border: none;
    border-bottom: 1px solid {c['border']};
    font-weight: 600;
    font-size: 12px;
}}
QTableWidget::item, QTableView::item {{ padding: 6px 8px; }}
QTableCornerButton::section {{ background: {c['surface_2']}; border: none; }}

/* ---- Tabs ---- */
QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 12px; top: -1px; }}
QTabBar::tab {{
    background: transparent;
    color: {c['text_muted']};
    padding: 9px 16px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:selected {{ color: {c['primary']}; border-bottom: 2px solid {c['primary']}; }}
QTabBar::tab:hover {{ color: {c['text']}; }}

/* ---- Scrollbars ---- */
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border_strong']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['text_faint']}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border_strong']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- Misc ---- */
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid {c['border_strong']}; background: {c['surface']};
}}
QCheckBox::indicator:checked {{ background: {c['primary']}; border-color: {c['primary']}; }}
QProgressBar {{
    background: {c['surface_3']}; border: none; border-radius: 6px; height: 8px; text-align: center;
}}
QProgressBar::chunk {{ background: {c['primary']}; border-radius: 6px; }}
"""
