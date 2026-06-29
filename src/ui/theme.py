"""Design system: colour tokens and the application style sheet (QSS).

The whole look is driven from two semantic colour dictionaries (light / dark)
plus a few shared scale constants, so a theme switch is one ``setStyleSheet``
call and there is a single place to tune the brand. Values follow the project's
design-token principles: named decisions only, semantic over raw, WCAG AA
contrast for text (>=4.5:1) and UI borders (>=3:1), restrained palette, visible
focus rings. The brand is the navy + blue of the Ring-Haus app icon.
"""

from __future__ import annotations

# --- Shared scale (Primitive layer) ---------------------------------------
FONT_STACK = '"Segoe UI Variable Text", "Segoe UI", "Inter", system-ui, sans-serif'
FONT_HEADING = '"Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI", sans-serif'
RADIUS_CARD = 16
RADIUS_CONTROL = 10

# --- Semantic colour tokens ------------------------------------------------
LIGHT = {
    "bg": "#f5f7fb",
    "bg_subtle": "#eef2f8",
    "surface": "#ffffff",
    "surface_2": "#f3f6fb",
    "surface_3": "#e9eef6",
    "border": "#e4e9f1",
    "border_strong": "#cfd8e5",
    "text": "#101729",
    "text_muted": "#566173",
    "text_faint": "#8a94a6",
    "primary": "#2f6cdf",
    "primary_hover": "#2659c2",
    "primary_press": "#1f4ca8",
    "primary_soft": "#e7effd",
    "on_primary": "#ffffff",
    "focus": "#2f6cdf",
    "sidebar": "#0d1526",
    "sidebar_2": "#101a31",
    "sidebar_text": "#9fabc2",
    "sidebar_text_active": "#ffffff",
    "sidebar_active": "#1b2942",
    "sidebar_accent": "#4d86f5",
    # Traffic-light / semantic
    "green": "#1a9d5a",
    "green_soft": "#e1f4ea",
    "amber": "#c47711",
    "amber_soft": "#fbeed8",
    "red": "#d8453b",
    "red_soft": "#fbe6e4",
    "blue": "#2f6cdf",
    "blue_soft": "#e7effd",
    "grey": "#7a8699",
    "grey_soft": "#eef1f6",
    # Chart slice palette (cohesive, AA-distinct)
    "chart": ["#2f6cdf", "#1a9d5a", "#c47711", "#d8453b", "#7c5cff", "#0ea5b7", "#e0699a", "#7a8699"],
}

DARK = {
    "bg": "#0c121e",
    "bg_subtle": "#0f1626",
    "surface": "#161e2e",
    "surface_2": "#1d2738",
    "surface_3": "#273246",
    "border": "#293449",
    "border_strong": "#3a4865",
    "text": "#e9eef7",
    "text_muted": "#9aa6bb",
    "text_faint": "#6b7892",
    "primary": "#5088f5",
    "primary_hover": "#6296f7",
    "primary_press": "#3b6fe0",
    "primary_soft": "#1a2742",
    "on_primary": "#ffffff",
    "focus": "#5088f5",
    "sidebar": "#080d17",
    "sidebar_2": "#0c1320",
    "sidebar_text": "#93a0b8",
    "sidebar_text_active": "#ffffff",
    "sidebar_active": "#19243a",
    "sidebar_accent": "#5088f5",
    "green": "#34c277",
    "green_soft": "#10301f",
    "amber": "#e0a23c",
    "amber_soft": "#33260f",
    "red": "#ec5f55",
    "red_soft": "#371b19",
    "blue": "#5088f5",
    "blue_soft": "#17233b",
    "grey": "#74819a",
    "grey_soft": "#222d40",
    "chart": ["#5088f5", "#34c277", "#e0a23c", "#ec5f55", "#9d83ff", "#2bc2d4", "#f07cab", "#74819a"],
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


def chart_colors(colors: dict) -> list[str]:
    return colors.get("chart", [colors["primary"]])


def build_qss(c: dict) -> str:
    """Build the application-wide style sheet from a colour dictionary."""
    return f"""
* {{
    font-family: {FONT_STACK};
    font-size: 14px;
    color: {c['text']};
}}
QWidget#Root, QStackedWidget, QMainWindow {{ background: {c['bg']}; }}
QToolTip {{
    background: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border_strong']};
    padding: 6px 10px;
    border-radius: 8px;
}}

/* ---- Dialogs follow the app theme (not the OS dark/light mode) ---- */
QDialog, QMessageBox, QInputDialog {{ background: {c['bg']}; }}
QMessageBox QLabel, QInputDialog QLabel {{ color: {c['text']}; background: transparent; }}

/* ---- Sidebar ---- */
QWidget#Sidebar {{ background: {c['sidebar']}; border: none; }}
QLabel#Brand {{ color: {c['sidebar_text_active']}; font-family: {FONT_HEADING};
    font-size: 19px; font-weight: 700; padding: 2px 6px; }}
QLabel#BrandSub {{ color: {c['sidebar_text']}; font-size: 10px; letter-spacing: 1.6px; font-weight: 600; }}
QPushButton#NavButton {{
    color: {c['sidebar_text']}; background: transparent;
    border: none; border-left: 3px solid transparent;
    border-radius: 10px; padding: 11px 13px; text-align: left;
    font-size: 14px; font-weight: 500;
}}
QPushButton#NavButton:hover {{ background: {c['sidebar_2']}; color: {c['sidebar_text_active']}; }}
QPushButton#NavButton:checked {{
    background: {c['sidebar_active']}; color: {c['sidebar_text_active']};
    border-left: 3px solid {c['sidebar_accent']}; font-weight: 600;
}}

/* ---- Cards & panels ---- */
QFrame#Card {{
    background: {c['surface']}; border: 1px solid {c['border']};
    border-radius: {RADIUS_CARD}px;
}}
QFrame#Panel {{
    background: {c['surface_2']}; border: 1px solid {c['border']};
    border-radius: 12px;
}}
QLabel#CardTitle {{ color: {c['text_muted']}; font-size: 11px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.7px; }}
QLabel#CardValue {{ font-family: {FONT_HEADING}; font-size: 27px; font-weight: 700; color: {c['text']}; }}
QLabel#CardHint {{ color: {c['text_faint']}; font-size: 12px; }}
QLabel#H1 {{ font-family: {FONT_HEADING}; font-size: 24px; font-weight: 700; }}
QLabel#H2 {{ font-family: {FONT_HEADING}; font-size: 17px; font-weight: 700; }}
QLabel#Muted {{ color: {c['text_muted']}; }}
QLabel#Faint {{ color: {c['text_faint']}; font-size: 12px; }}
QLabel#FieldLabel {{ color: {c['text_muted']}; font-size: 12px; font-weight: 600; }}

/* ---- Buttons ---- */
QPushButton {{
    background: {c['surface_2']}; color: {c['text']};
    border: 1px solid {c['border_strong']}; border-radius: {RADIUS_CONTROL}px;
    padding: 9px 16px; font-weight: 600; min-height: 18px;
}}
QPushButton:hover {{ background: {c['surface_3']}; }}
QPushButton:pressed {{ background: {c['surface_3']}; }}
QPushButton:focus {{ border: 1px solid {c['focus']}; outline: none; }}
QPushButton:disabled {{ color: {c['text_faint']}; background: {c['surface_2']}; border-color: {c['border']}; }}
QPushButton#Primary {{ background: {c['primary']}; color: {c['on_primary']}; border: 1px solid {c['primary']}; }}
QPushButton#Primary:hover {{ background: {c['primary_hover']}; border-color: {c['primary_hover']}; }}
QPushButton#Primary:pressed {{ background: {c['primary_press']}; border-color: {c['primary_press']}; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid {c['border_strong']}; color: {c['text']}; }}
QPushButton#Ghost:hover {{ background: {c['surface_2']}; border-color: {c['border_strong']}; }}
QPushButton#Danger {{ color: {c['red']}; border: 1px solid {c['border_strong']}; background: transparent; }}
QPushButton#Danger:hover {{ background: {c['red_soft']}; border-color: {c['red']}; }}
QPushButton#Link {{ background: transparent; border: none; color: {c['primary']}; padding: 4px; font-weight: 600; }}
QPushButton#Link:hover {{ color: {c['primary_hover']}; text-decoration: underline; }}

/* ---- Inputs ---- */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
    background: {c['surface']}; border: 1px solid {c['border_strong']};
    border-radius: {RADIUS_CONTROL}px; padding: 8px 11px;
    selection-background-color: {c['primary']}; selection-color: {c['on_primary']};
}}
QLineEdit:hover, QComboBox:hover {{ border-color: {c['text_faint']}; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {c['focus']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {c['surface']}; border: 1px solid {c['border_strong']};
    border-radius: 8px; selection-background-color: {c['primary_soft']};
    selection-color: {c['text']}; outline: none; padding: 4px;
}}
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid {c['border_strong']}; background: {c['surface']}; }}
QCheckBox::indicator:hover {{ border-color: {c['primary']}; }}
QCheckBox::indicator:checked {{ background: {c['primary']}; border-color: {c['primary']}; }}

/* ---- Tables ---- */
QTableWidget, QTableView {{
    background: {c['surface']}; border: 1px solid {c['border']};
    border-radius: 14px; gridline-color: transparent;
    selection-background-color: {c['primary_soft']}; selection-color: {c['text']};
    alternate-background-color: {c['surface_2']};
}}
QHeaderView::section {{
    background: {c['surface']}; color: {c['text_muted']};
    padding: 11px 10px; border: none; border-bottom: 1px solid {c['border']};
    font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px;
}}
QTableWidget::item, QTableView::item {{ padding: 8px 8px; border: none; }}
QTableWidget::item:hover, QTableView::item:hover {{ background: {c['surface_2']}; }}
QTableCornerButton::section {{ background: {c['surface']}; border: none; }}

/* ---- Tabs ---- */
QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 14px; top: -1px; background: {c['surface']}; }}
QTabBar::tab {{ background: transparent; color: {c['text_muted']};
    padding: 9px 18px; border: none; border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: {c['primary']}; border-bottom: 2px solid {c['primary']}; }}
QTabBar::tab:hover {{ color: {c['text']}; }}

/* ---- Scrollbars (thin, unobtrusive) ---- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px 4px 0; }}
QScrollBar::handle:vertical {{ background: {c['border_strong']}; border-radius: 5px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: {c['text_faint']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0 4px 2px 4px; }}
QScrollBar::handle:horizontal {{ background: {c['border_strong']}; border-radius: 5px; min-width: 36px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- Progress ---- */
QProgressBar {{ background: {c['surface_3']}; border: none; border-radius: 6px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {c['primary']}; border-radius: 6px; }}
"""
