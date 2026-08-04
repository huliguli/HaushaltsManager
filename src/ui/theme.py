"""Design system: colour tokens, type scale and the application style sheet.

Direction "Kontoblatt" (v4.0): a quiet sheet of paper with the numbers in front,
closer to a well-set bank statement than to a SaaS dashboard.

Three rules drive every value below.

1. **Two designed themes, not one recoloured.** The light theme is warm-neutral
   paper; the dark theme is neutral graphite. Neither has a navy cast, and the
   sidebar belongs to the page in BOTH — the near-black sidebar that used to sit
   next to white content was the single strongest ageing signal.
2. **One accent, and money owns its own colours.** The brand accent is a deep
   petrol; green and red are reserved exclusively for the direction of an amount
   and are never used for branding or generic state. Colour is never the only
   channel — a sign or a column carries the same information (WCAG 1.4.1).
3. **Depth from surface steps and hairlines, never shadows.** Qt silently drops
   ``box-shadow`` from a style sheet, so anything relying on it would just look
   flat with no warning.

Contrast targets: >=4.5:1 for text, >=3:1 for control borders and focus rings.
``tests/test_theme_contrast.py`` checks the pairs mechanically.
"""

from __future__ import annotations

# --- Type scale -------------------------------------------------------------
# Segoe UI Variable is the Windows 11 system family; the fallbacks keep older
# Windows and the macOS build readable. Weights stay in 400/500/600 — the old
# theme jumped to 700 for every heading, which is what made the UI shout.
FONT_STACK = '"Segoe UI Variable Text", "Segoe UI", "Inter", system-ui, sans-serif'
FONT_HEADING = '"Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI", sans-serif'

FONT_SIZES = {
    "label": 11,     # all-caps captions (the only place letter-spacing is used)
    "small": 12,     # hints, secondary rows
    "table": 13,     # table cells and list rows
    "body": 14,      # default
    "card": 16,      # card titles
    "title": 20,     # view titles
    "hero": 30,      # the one leading number per card
}

RADIUS_CARD = 10
RADIUS_CONTROL = 7
# 4px base grid; six steps is enough for the whole app.
SPACE = (4, 8, 12, 16, 24, 32)

# --- Semantic colour tokens ------------------------------------------------
# Key names are deliberately unchanged from v3.x so every view keeps working;
# only the values moved to the new direction.
LIGHT = {
    "bg": "#f4f3f0",              # warm paper, no blue cast
    "bg_subtle": "#efeeea",
    "surface": "#ffffff",
    "surface_2": "#faf9f7",
    "surface_3": "#eeece7",
    "border": "#e0ddd6",          # hairline — the only separator
    # Control border: >=3:1 on EVERY surface it can sit on, incl. surface_3
    # (WCAG 1.4.11). The lighter warm grey this started as failed at 2.65:1.
    "border_strong": "#8c867c",
    "text": "#1b1a18",
    "text_muted": "#5c584f",
    "text_faint": "#6f6a62",      # captions, >=4.5:1 on surface and bg
    # Brand accent: deep petrol. Explicitly not blue — blue is the default of
    # administrative software and a main reason the old UI read as dated.
    "primary": "#125e5b",
    "primary_hover": "#0e4c4a",
    "primary_press": "#0a3d3b",
    "primary_soft": "#e1eeed",
    "primary_btn": "#125e5b",
    "primary_btn_hover": "#0e4c4a",
    "primary_btn_press": "#0a3d3b",
    "on_primary": "#ffffff",
    "focus": "#125e5b",
    # Sidebar is part of the paper, separated by a hairline only.
    "sidebar": "#eae8e3",
    "sidebar_2": "#e1dfd8",
    "sidebar_text": "#4a463f",
    "sidebar_text_active": "#0e4c4a",
    "sidebar_active": "#ffffff",
    "sidebar_accent": "#125e5b",
    # Money semantics. Foregrounds clear 4.5:1 on surface AND on their *_soft.
    "green": "#1a6b41",
    "green_soft": "#e3f1e8",
    "amber": "#845410",
    "amber_soft": "#f6ebd8",
    "red": "#a33228",
    "red_soft": "#f8e6e3",
    "blue": "#1f5a86",
    "blue_soft": "#e4eef6",
    "grey": "#5c584f",
    "grey_soft": "#eeece7",
    # Categorical series: muted and print-like, distinct from the accent so a
    # chart slice never reads as "brand". Eight hues — beyond that a breakdown
    # should roll up into "Sonstige" rather than grow more colours.
    "chart": ["#125e5b", "#845410", "#44578a", "#75405c", "#3d6b4a", "#8f5c38",
              "#565377", "#2b6d73"],
}

DARK = {
    "bg": "#141618",              # neutral graphite, never pure black
    "bg_subtle": "#101214",
    "surface": "#1d2023",
    "surface_2": "#23272a",
    "surface_3": "#2c3033",
    "border": "#31363a",
    # >=3:1 on every surface incl. surface_3 (WCAG 1.4.11).
    "border_strong": "#787f84",
    "text": "#e9e8e4",
    "text_muted": "#a8a7a1",
    "text_faint": "#918f89",
    "primary": "#59b3ac",
    "primary_hover": "#68bfb8",
    "primary_press": "#4a9d97",
    "primary_soft": "#17322f",
    # On dark the accent is bright, so the filled button carries DARK text —
    # white on #59b3ac would only reach ~2.4:1.
    "primary_btn": "#59b3ac",
    "primary_btn_hover": "#68bfb8",
    "primary_btn_press": "#4a9d97",
    "on_primary": "#0c1a19",
    "focus": "#59b3ac",
    "sidebar": "#101214",
    "sidebar_2": "#191c1f",
    "sidebar_text": "#a09f99",
    "sidebar_text_active": "#7fc8c2",
    "sidebar_active": "#1d2023",
    "sidebar_accent": "#59b3ac",
    "green": "#5cc088",
    "green_soft": "#13291d",
    "amber": "#d9a441",
    "amber_soft": "#2c2314",
    "red": "#e8776c",
    "red_soft": "#2e1a18",
    "blue": "#6ba8d8",
    "blue_soft": "#152431",
    "grey": "#a8a7a1",
    "grey_soft": "#272b2e",
    "chart": ["#59b3ac", "#d9a441", "#8098d4", "#c78fa8", "#7fbb92", "#d09f74",
              "#a09dc4", "#6bb8bf"],
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


def app_font():
    """The application base font, with TABULAR figures switched on.

    Segoe UI Variable ships a narrow "1" (5.0px vs 8.0px for every other digit
    at 14px), so amounts in a column visibly jitter and the eye cannot compare
    them. The OpenType ``tnum`` feature gives every digit the same advance.

    Setting this once on the QApplication is enough: the feature survives the
    global ``font-family``/``font-size`` rule in :func:`build_qss` (verified),
    so it reaches every label and table cell without per-widget work.
    Requires Qt >= 6.7 for ``QFont.setFeature``; older builds simply keep
    proportional digits.
    """
    from PyQt6.QtGui import QFont

    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Inter"])
    font.setPixelSize(FONT_SIZES["body"])
    try:
        font.setFeature(QFont.Tag("tnum"), 1)
    except (AttributeError, TypeError):  # pragma: no cover - older Qt
        pass
    return font


def ampel_color(key: str, colors: dict) -> str:
    fg, _ = AMPEL.get(key, ("grey", "grey_soft"))
    return colors[fg]


def ampel_soft(key: str, colors: dict) -> str:
    _, bg = AMPEL.get(key, ("grey", "grey_soft"))
    return colors[bg]


def chart_colors(colors: dict) -> list[str]:
    return colors.get("chart", [colors["primary"]])


def _relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))

    def lin(channel: float) -> float:
        channel /= 255.0
        return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two hex colours (1.0 - 21.0)."""
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def on_color(hex_color: str) -> str:
    """Return black or white — whichever reads with more contrast on the colour."""
    lum = _relative_luminance(hex_color)
    white_ratio = 1.05 / (lum + 0.05)
    black_ratio = (lum + 0.05) / 0.05
    return "#ffffff" if white_ratio >= black_ratio else "#151a26"


def build_qss(c: dict) -> str:
    """Build the application-wide style sheet from a colour dictionary."""
    from ui import icons
    s = FONT_SIZES

    def img(name: str, color: str, size: int = 28) -> str:
        return icons.stylesheet_image_path(name, color, size)

    # Qt cannot embed images inline, so glyphs are materialised to PNG once.
    # Every rule degrades gracefully to "no image" if that ever fails.
    arrow = img("chevron_down", c["text_muted"], 28)
    arrow_rule = (f"QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url({arrow}); "
                  f"width: 13px; height: 13px; }}" if arrow else "")
    tick = img("check", c["on_primary"], 24)
    tick_rule = (f"QCheckBox::indicator:checked {{ image: url({tick}); }}"
                 if tick else "")
    dash = img("minus", c["on_primary"], 24)
    dash_rule = (f"QCheckBox::indicator:indeterminate {{ image: url({dash}); }}"
                 if dash else "")
    up = img("chevron_up", c["text_muted"], 24)
    down = img("chevron_down", c["text_muted"], 24)
    spin_rule = (
        f"QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({up}); "
        f"width: 11px; height: 11px; }}"
        f"QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({down}); "
        f"width: 11px; height: 11px; }}" if up and down else "")

    return f"""
* {{
    font-family: {FONT_STACK};
    font-size: {s['body']}px;
    color: {c['text']};
}}
QWidget#Root, QStackedWidget, QMainWindow {{ background: {c['bg']}; }}
QToolTip {{
    background: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border_strong']};
    padding: 6px 10px;
    border-radius: {RADIUS_CONTROL}px;
}}

/* ---- Dialogs follow the app theme (not the OS dark/light mode) ---- */
QDialog, QMessageBox, QInputDialog {{ background: {c['bg']}; }}
QMessageBox QLabel, QInputDialog QLabel {{ color: {c['text']}; background: transparent; }}

/* ---- Sidebar: part of the page, separated by a hairline ---- */
QWidget#Sidebar {{
    background: {c['sidebar']};
    border: none;
    border-right: 1px solid {c['border']};
}}
QLabel#Brand {{ color: {c['text']}; font-family: {FONT_HEADING};
    font-size: {s['card']}px; font-weight: 600; padding: 2px 6px; }}
QLabel#BrandSub {{ color: {c['text_faint']}; font-size: {s['label']}px;
    letter-spacing: 1.2px; font-weight: 600; }}
QPushButton#NavButton {{
    color: {c['sidebar_text']}; background: transparent;
    border: 1px solid transparent;
    border-radius: {RADIUS_CONTROL}px; padding: 9px 12px; text-align: left;
    font-size: {s['table']}px; font-weight: 500;
}}
QPushButton#NavButton:hover {{ background: {c['sidebar_2']}; color: {c['text']}; }}
QPushButton#NavButton:checked {{
    background: {c['sidebar_active']}; color: {c['sidebar_text_active']};
    border: 1px solid {c['border']}; font-weight: 600;
}}
/* Focus must be visible (WCAG 2.4.7) but must NOT look like the selected item —
   the old theme styled :focus exactly like :checked, so two entries always
   appeared active at once. A ring says "keyboard is here", a filled pill says
   "this is the open view". */
QPushButton#NavButton:focus {{ border: 1px solid {c['focus']}; }}

/* ---- Cards & panels: hairline only, no shadow (Qt drops box-shadow) ---- */
QFrame#Card {{
    background: {c['surface']}; border: 1px solid {c['border']};
    border-radius: {RADIUS_CARD}px;
}}
QFrame#Panel {{
    background: {c['surface_2']}; border: 1px solid {c['border']};
    border-radius: {RADIUS_CARD}px;
}}
QLabel#CardTitle {{ color: {c['text_faint']}; font-size: {s['label']}px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.8px; }}
QLabel#CardValue {{ font-family: {FONT_HEADING}; font-size: {s['hero']}px;
    font-weight: 600; color: {c['text']}; }}
QLabel#CardHint {{ color: {c['text_faint']}; font-size: {s['small']}px; }}
QLabel#H1 {{ font-family: {FONT_HEADING}; font-size: {s['title']}px; font-weight: 600; }}
QLabel#H2 {{ font-family: {FONT_HEADING}; font-size: {s['card']}px; font-weight: 600; }}
QLabel#Muted {{ color: {c['text_muted']}; }}
QLabel#Faint {{ color: {c['text_faint']}; font-size: {s['small']}px; }}
QLabel#ErrorText {{ color: {c['red']}; font-size: {s['small']}px; }}
QLabel#FieldLabel {{ color: {c['text_muted']}; font-size: {s['small']}px; font-weight: 600; }}

/* ---- Buttons ---- */
QPushButton {{
    background: {c['surface']}; color: {c['text']};
    border: 1px solid {c['border_strong']}; border-radius: {RADIUS_CONTROL}px;
    padding: 8px 15px; font-weight: 500; min-height: 18px;
}}
QPushButton:hover {{ background: {c['surface_2']}; }}
QPushButton:pressed {{ background: {c['surface_3']}; }}
QPushButton:focus {{ border: 1px solid {c['focus']}; outline: none; }}
QPushButton:disabled {{ color: {c['text_faint']}; background: {c['surface_2']};
    border-color: {c['border']}; }}
QPushButton#Primary {{ background: {c['primary_btn']}; color: {c['on_primary']};
    border: 1px solid {c['primary_btn']}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {c['primary_btn_hover']};
    border-color: {c['primary_btn_hover']}; }}
QPushButton#Primary:pressed {{ background: {c['primary_btn_press']};
    border-color: {c['primary_btn_press']}; }}
QPushButton#Primary:disabled {{ background: {c['surface_3']}; color: {c['text_faint']};
    border-color: {c['border']}; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid {c['border_strong']};
    color: {c['text']}; }}
QPushButton#Ghost:hover {{ background: {c['surface_2']}; }}
QPushButton#Danger {{ color: {c['red']}; border: 1px solid {c['border_strong']};
    background: transparent; }}
QPushButton#Danger:hover {{ background: {c['red_soft']}; border-color: {c['red']}; }}
QPushButton#Link {{ background: transparent; border: none; color: {c['primary']};
    padding: 4px; font-weight: 600; }}
QPushButton#Link:hover {{ color: {c['primary_hover']}; text-decoration: underline; }}

/* ---- Inputs ---- */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
    background: {c['surface']}; border: 1px solid {c['border_strong']};
    border-radius: {RADIUS_CONTROL}px; padding: 7px 10px;
    selection-background-color: {c['primary']}; selection-color: {c['on_primary']};
}}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover,
QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {c['text_faint']}; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {c['focus']}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background: {c['surface_2']}; color: {c['text_faint']}; border-color: {c['border']}; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 24px; }}
{arrow_rule}
QComboBox#CellCombo {{ padding: 2px 9px; color: {c['text']}; background: {c['surface_2']}; }}
QComboBox QAbstractItemView {{
    background: {c['surface']}; border: 1px solid {c['border_strong']};
    border-radius: {RADIUS_CONTROL}px; selection-background-color: {c['primary_soft']};
    selection-color: {c['text']}; outline: none; padding: 4px;
}}

/* Spin buttons: stacked, borderless, own chevrons. The Qt default drew two
   square boxes with sharp corners inside a rounded field. */
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; border: none; background: transparent;
    width: 20px; margin-right: 3px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-position: top right; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-position: bottom right; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {c['surface_3']}; border-radius: 4px; }}
{spin_rule}

/* ---- Check boxes: a filled square is not a tick ---- */
QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px;
    border: 1px solid {c['border_strong']}; background: {c['surface']}; }}
QCheckBox::indicator:hover {{ border-color: {c['primary']}; }}
QCheckBox::indicator:checked, QCheckBox::indicator:indeterminate {{
    background: {c['primary']}; border-color: {c['primary']}; }}
QCheckBox::indicator:disabled {{ background: {c['surface_3']};
    border-color: {c['border']}; }}
{tick_rule}
{dash_rule}

/* ---- Radio buttons: were raw Qt-Fusion next to styled check boxes ---- */
QRadioButton {{ spacing: 9px; }}
QRadioButton::indicator {{ width: 18px; height: 18px; border-radius: 9px;
    border: 1px solid {c['border_strong']}; background: {c['surface']}; }}
QRadioButton::indicator:hover {{ border-color: {c['primary']}; }}
QRadioButton::indicator:checked {{
    border: 5px solid {c['primary']}; background: {c['surface']}; }}
QRadioButton::indicator:disabled {{ background: {c['surface_3']};
    border-color: {c['border']}; }}

/* ---- Tables ---- */
QTableWidget, QTableView {{
    background: {c['surface']}; border: 1px solid {c['border']};
    border-radius: {RADIUS_CARD}px; gridline-color: transparent;
    selection-background-color: {c['primary_soft']}; selection-color: {c['text']};
    alternate-background-color: {c['surface_2']};
    font-size: {s['table']}px;
}}
QHeaderView::section {{
    background: {c['surface']}; color: {c['text_faint']};
    padding: 10px; border: none; border-bottom: 1px solid {c['border']};
    font-weight: 600; font-size: {s['label']}px; text-transform: uppercase;
    letter-spacing: 0.6px;
}}
QTableWidget::item, QTableView::item {{ padding: 7px 8px; border: none; }}
QTableWidget::item:hover, QTableView::item:hover {{ background: {c['surface_2']}; }}
QTableCornerButton::section {{ background: {c['surface']}; border: none; }}

/* ---- Tabs ---- */
QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: {RADIUS_CARD}px;
    top: -1px; background: {c['surface']}; }}
QTabBar::tab {{ background: transparent; color: {c['text_muted']};
    padding: 9px 17px; border: none; border-bottom: 2px solid transparent;
    font-weight: 500; }}
QTabBar::tab:selected {{ color: {c['primary']}; border-bottom: 2px solid {c['primary']};
    font-weight: 600; }}
QTabBar::tab:hover {{ color: {c['text']}; }}
QTabBar::tab:focus {{ color: {c['text']}; border-bottom: 2px solid {c['border_strong']}; }}

/* ---- Scrollbars ---- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px 4px 0; }}
QScrollBar::handle:vertical {{ background: {c['border_strong']}; border-radius: 5px;
    min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: {c['text_faint']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0 4px 2px 4px; }}
QScrollBar::handle:horizontal {{ background: {c['border_strong']}; border-radius: 5px;
    min-width: 36px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- Progress ---- */
QProgressBar {{ background: {c['surface_3']}; border: none; border-radius: 4px;
    height: 7px; text-align: center; }}
QProgressBar::chunk {{ background: {c['primary']}; border-radius: 4px; }}

/* ---- Calendar popup (QDateEdit) followed the OS palette before ---- */
QCalendarWidget QWidget {{ alternate-background-color: {c['surface_2']}; }}
QCalendarWidget QAbstractItemView:enabled {{
    background: {c['surface']}; color: {c['text']};
    selection-background-color: {c['primary']}; selection-color: {c['on_primary']}; }}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {c['surface_2']}; }}
"""
