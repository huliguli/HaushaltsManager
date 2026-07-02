"""Vector icons embedded as SVG strings, rendered to tinted QIcons/QPixmaps.

Keeping the icon set inline (rather than shipping .svg files) removes a whole
class of PyInstaller resource-path bugs and lets us recolour each glyph for the
current theme on the fly. Style is a consistent Feather-like 24px stroke set.
"""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

# Inner SVG markup (paths only); wrapped by _SVG_TEMPLATE below.
_PATHS: dict[str, str] = {
    "dashboard": '<rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="5" rx="1.5"/><rect x="13" y="11" width="8" height="10" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/>',
    "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
    "credit": '<rect x="2" y="5" width="20" height="14" rx="2.5"/><path d="M2 10h20"/><path d="M6 15h4"/>',
    "calculator": '<rect x="4" y="2" width="16" height="20" rx="2.5"/><path d="M8 6h8"/><path d="M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01M8 19h4"/>',
    "exchange": '<path d="M17 3l4 4-4 4"/><path d="M21 7H7"/><path d="M7 21l-4-4 4-4"/><path d="M3 17h14"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    "plus": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "edit": '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z"/>',
    "trash": '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/>',
    "sun": '<circle cx="12" cy="12" r="4.5"/><path d="M12 1v3M12 20v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M1 12h3M20 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "alert": '<path d="M10.3 3.6 1.8 18a2 2 0 0 0 1.7 3h16.9a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    "arrow_right": '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
    "arrow_down": '<path d="M12 5v14"/><path d="M6 13l6 6 6-6"/>',
    "chevron_down": '<path d="M6 9l6 6 6-6"/>',
    "chevron_left": '<path d="M15 18l-6-6 6-6"/>',
    "chevron_right": '<path d="M9 18l6-6-6-6"/>',
    "chart": '<path d="M3 3v18h18"/><rect x="7" y="11" width="3" height="6" rx="0.5"/><rect x="12" y="7" width="3" height="10" rx="0.5"/><rect x="17" y="13" width="3" height="4" rx="0.5"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    "wallet": '<path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4z"/>',
    "car": '<path d="M5 17h14M5 17a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm18 0a2 2 0 1 1-4 0 2 2 0 0 1 4 0z"/><path d="M3 17v-5l2-5h11l3 5v5"/><path d="M5 12h14"/>',
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9 21v-6h6v6"/>',
    "percent": '<path d="M19 5 5 19"/><circle cx="7.5" cy="7.5" r="2.5"/><circle cx="16.5" cy="16.5" r="2.5"/>',
    "refresh": '<path d="M21 3v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 9"/><path d="M3 21v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 15"/>',
    "filter": '<path d="M22 3H2l8 9.5V19l4 2v-8.5z"/>',
    "close": '<path d="M18 6 6 18M6 6l12 12"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/>',
    "magic": '<path d="M15 4V2M15 16v-2M8 9h2M20 9h2M17.8 11.8 19 13M17.8 6.2 19 5M3 21l9-9M12.2 6.2 11 5"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "calendar": '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M8 2v4M16 2v4"/>',
    "trend": '<path d="M22 7l-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>',
}

_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="1.9" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)


def svg_string(name: str, color: str = "#1b2330") -> str:
    return _SVG_TEMPLATE.format(color=color, body=_PATHS.get(name, ""))


def pixmap(name: str, color: str = "#1b2330", size: int = 22) -> QPixmap:
    """Render an icon to a high-DPI-aware tinted pixmap."""
    renderer = QSvgRenderer(QByteArray(svg_string(name, color).encode("utf-8")))
    ratio = 2  # render at 2x for crispness on high-DPI displays
    pm = QPixmap(size * ratio, size * ratio)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str = "#1b2330", size: int = 22) -> QIcon:
    return QIcon(pixmap(name, color, size))


def stylesheet_image_path(name: str, color: str, size: int = 28) -> str:
    """Render an icon to a cached PNG and return a forward-slashed absolute path.

    Qt stylesheets cannot embed images inline, so for ``image: url(...)`` we
    materialise the icon once into the (always-writable) user data dir and reuse
    it. Returns ``""`` if rendering is not possible (e.g. no QApplication yet),
    so callers can simply omit the rule.
    """
    try:
        from app_meta import data_dir
        cache = data_dir() / "iconcache"
        cache.mkdir(parents=True, exist_ok=True)
        out = cache / f"{name}_{color.lstrip('#')}_{size}.png"
        if not out.exists():
            if not pixmap(name, color, size).save(str(out), "PNG"):
                return ""
        return str(out).replace("\\", "/")
    except Exception:  # noqa: BLE001 - styling must never break startup
        return ""
