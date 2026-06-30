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
    "border_strong": "#868fa1",   # control border, >=3:1 on surface (WCAG 1.4.11)
    "text": "#101729",
    "text_muted": "#566173",
    "text_faint": "#667086",      # caption/hint text, >=4.5:1 on surface and bg
    "primary": "#2f6cdf",
    "primary_hover": "#2659c2",
    "primary_press": "#1f4ca8",
    "primary_soft": "#e7effd",
    # Filled-primary-button fill (white label needs >=4.5:1): equals the accent
    # in light mode, but kept separate so dark mode can darken the button without
    # dulling the brighter accent used for links/tabs/focus on dark surfaces.
    "primary_btn": "#2f6cdf",
    "primary_btn_hover": "#2659c2",
    "primary_btn_press": "#1f4ca8",
    "on_primary": "#ffffff",
    "focus": "#2f6cdf",
    "sidebar": "#0d1526",
    "sidebar_2": "#101a31",
    "sidebar_text": "#9fabc2",
    "sidebar_text_active": "#ffffff",
    "sidebar_active": "#1b2942",
    "sidebar_accent": "#4d86f5",
    # Traffic-light / semantic. Foregrounds are dark enough to clear 4.5:1 both
    # as value text on white surface AND as pill text on their *_soft background.
    "green": "#0f6e3d",
    "green_soft": "#e1f4ea",
    "amber": "#94590b",
    "amber_soft": "#fbeed8",
    "red": "#bf352b",
    "red_soft": "#fbe6e4",
    "blue": "#205bc6",
    "blue_soft": "#e7effd",
    "grey": "#566173",
    "grey_soft": "#eef1f6",
    # Chart slice palette (cohesive, AA-distinct)
    # Cyclic donut/legend palette. Widened to 14 well-separated hues so a
    # month with many of the finer expense categories still gets distinct
    # slices; the legend additionally shows name + % so colour is never the
    # sole differentiator (WCAG 1.4.1).
    "chart": ["#2f6cdf", "#1a9d5a", "#c47711", "#d8453b", "#7c5cff", "#0ea5b7",
              "#e0699a", "#7a8699", "#0f8a6e", "#9a8410", "#3f4fb0", "#b5409a",
              "#8a5a2b", "#5d9e2f"],
}

DARK = {
    "bg": "#0c121e",
    "bg_subtle": "#0f1626",
    "surface": "#161e2e",
    "surface_2": "#1d2738",
    "surface_3": "#273246",
    "border": "#293449",
    "border_strong": "#586c98",   # control border, >=3:1 on surface (WCAG 1.4.11)
    "text": "#e9eef7",
    "text_muted": "#9aa6bb",
    "text_faint": "#7e8ca6",      # caption/hint text, >=4.5:1 on surface
    "primary": "#5088f5",         # bright accent for links/tabs/focus on dark surface
    "primary_hover": "#6296f7",
    "primary_press": "#3b6fe0",
    "primary_soft": "#1a2742",
    # Darker filled-button fill so white labels clear 4.5:1 (the bright accent
    # above only reaches 3.4:1 against white).
    "primary_btn": "#3367dc",
    "primary_btn_hover": "#3a6ee2",
    "primary_btn_press": "#2f63d4",
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
    "grey": "#8b98af",            # lightened so grey pill text clears 4.5:1 on grey_soft
    "grey_soft": "#222d40",
    # Cyclic donut/legend palette (dark theme) — same 14-hue spread, brighter
    # variants so each slice reads on the dark card surface.
    "chart": ["#5088f5", "#34c277", "#e0a23c", "#ec5f55", "#9d83ff", "#2bc2d4",
              "#f07cab", "#74819a", "#2bb58f", "#cbb43e", "#6f7ee0", "#d765bd",
              "#bd8a5a", "#86c450"],
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


def _relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))

    def lin(channel: float) -> float:
        channel /= 255.0
        return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def on_color(hex_color: str) -> str:
    """Return black or white — whichever reads with more contrast on the colour.

    Used for solid coloured badges (e.g. the car-feasibility banner) so the label
    stays legible whether the fill is a dark (light-theme) or bright (dark-theme)
    semantic colour, instead of forcing white onto a light fill.
    """
    lum = _relative_luminance(hex_color)
    white_ratio = 1.05 / (lum + 0.05)
    black_ratio = (lum + 0.05) / 0.05
    return "#ffffff" if white_ratio >= black_ratio else "#151a26"


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
/* Keyboard focus must be visible (WCAG 2.4.7): highlight the focused nav item. */
QPushButton#NavButton:focus {{
    background: {c['sidebar_active']}; color: {c['sidebar_text_active']};
    border-left: 3px solid {c['sidebar_accent']};
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
QPushButton#Primary {{ background: {c['primary_btn']}; color: {c['on_primary']}; border: 1px solid {c['primary_btn']}; }}
QPushButton#Primary:hover {{ background: {c['primary_btn_hover']}; border-color: {c['primary_btn_hover']}; }}
QPushButton#Primary:pressed {{ background: {c['primary_btn_press']}; border-color: {c['primary_btn_press']}; }}
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
QTabBar::tab:focus {{ color: {c['text']}; background: {c['surface_2']}; border-bottom: 2px solid {c['border_strong']}; }}

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
