"""Render the app-icon concept variants and a side-by-side preview grid.

Each concept is a self-contained 256x256 SVG (rounded navy tile + mark) in the
app's brand palette (navy #10182a/#1b2330, accent blue #2f6bd8/#4d82f3). Run
with the project venv:  python assets/icon_concepts.py
Outputs concept_<key>.png (256px) and concepts_preview.png (comparison grid).
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

OUT = Path(__file__).resolve().parent

# Shared rounded-tile background (navy gradient).
_DEFS = """
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="0.25" y2="1">
    <stop offset="0" stop-color="#1d2a45"/>
    <stop offset="1" stop-color="#0d1422"/>
  </linearGradient>
</defs>
<rect x="6" y="6" width="244" height="244" rx="56" fill="url(#bg)"/>
"""

WHITE = "#ffffff"
BLUE = "#3f7bf0"
LEDGER = "#16243c"

# Concept A — "Haus-Ledger": a house whose body holds ledger lines (Haushalt +
# Buchführung). White house, navy ledger lines, blue "saldo" line.
SVG_A = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">{_DEFS}
  <path d="M128 50 L218 126 L38 126 Z" fill="{WHITE}"/>
  <rect x="62" y="122" width="132" height="90" rx="13" fill="{WHITE}"/>
  <rect x="84" y="142" width="88" height="13" rx="6.5" fill="{LEDGER}"/>
  <rect x="84" y="166" width="88" height="13" rx="6.5" fill="{LEDGER}"/>
  <rect x="84" y="190" width="52" height="13" rx="6.5" fill="{BLUE}"/>
</svg>"""

# Concept B — "Euro-Budget": a clean geometric € with a blue budget baseline.
SVG_B = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">{_DEFS}
  <path d="M176 90 A58 58 0 1 0 176 166" fill="none" stroke="{WHITE}"
        stroke-width="24" stroke-linecap="round"/>
  <rect x="58" y="112" width="100" height="18" rx="9" fill="{WHITE}"/>
  <rect x="58" y="140" width="100" height="18" rx="9" fill="{WHITE}"/>
  <rect x="74" y="200" width="108" height="12" rx="6" fill="{BLUE}"/>
</svg>"""

# Concept C — "Ring-Haus": a donut ring (nod to the dashboard chart) framing a
# small house — ties the icon to the app's own visual language.
SVG_C = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">{_DEFS}
  <circle cx="128" cy="122" r="60" fill="none" stroke="#2f5fc0" stroke-width="26"/>
  <circle cx="128" cy="122" r="60" fill="none" stroke="#8fb6ff" stroke-width="26"
          stroke-dasharray="113 264" transform="rotate(-90 128 122)"/>
  <path d="M128 92 L164 122 L92 122 Z" fill="{WHITE}"/>
  <rect x="103" y="120" width="50" height="40" rx="6" fill="{WHITE}"/>
</svg>"""

CONCEPTS = {
    "A": ("Haus-Ledger", SVG_A),
    "B": ("Euro-Budget", SVG_B),
    "C": ("Ring-Haus", SVG_C),
}


def render_svg(svg: str, size: int) -> QImage:
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(p)
    p.end()
    return img


def build_preview() -> None:
    light = QColor("#eef1f6")
    dark = QColor("#0f141c")
    small_sizes = [64, 48, 32, 24, 16]

    row_h = 252
    canvas = QImage(1130, row_h * len(CONCEPTS) + 70, QImage.Format.Format_ARGB32)
    canvas.fill(QColor("#ffffff"))
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    title = QFont("Segoe UI", 15)
    title.setBold(True)
    p.setFont(title)
    p.setPen(QColor("#1b2330"))
    p.drawText(QRectF(24, 16, 1000, 34), Qt.AlignmentFlag.AlignLeft,
               "HaushaltsManager – App-Icon-Konzepte (auf hell / dunkel, inkl. 16 px)")

    label_font = QFont("Segoe UI", 12)
    label_font.setBold(True)
    small_font = QFont("Segoe UI", 8)

    for i, (key, (name, svg)) in enumerate(CONCEPTS.items()):
        y = 64 + i * row_h
        p.setFont(label_font)
        p.setPen(QColor("#2f6bd8"))
        p.drawText(QRectF(24, y, 200, 24), Qt.AlignmentFlag.AlignLeft, f"{key} · {name}")

        big = render_svg(svg, 196)
        # Light panel
        p.fillRect(QRectF(24, y + 28, 196, 196), light)
        p.drawImage(24, y + 28, big)
        # Dark panel
        p.fillRect(QRectF(236, y + 28, 196, 196), dark)
        p.drawImage(236, y + 28, big)

        # Small-size strips on light then dark (legibility check, incl. 16 px).
        for panel_x, bg in ((452, light), (792, dark)):
            p.fillRect(QRectF(panel_x, y + 28, 320, 196), bg)
            cx = panel_x + 18
            for s in small_sizes:
                img = render_svg(svg, s)
                cy = y + 28 + (196 - s) // 2 - 8
                p.drawImage(cx, cy, img)
                p.setFont(small_font)
                p.setPen(QColor("#5d6877") if bg == light else QColor("#9aa6b6"))
                p.drawText(QRectF(cx, y + 28 + 150, max(s, 28), 18),
                           Qt.AlignmentFlag.AlignLeft, f"{s}px")
                cx += s + 24
    p.end()
    canvas.save(str(OUT / "concepts_preview.png"))

    for key, (name, svg) in CONCEPTS.items():
        render_svg(svg, 256).save(str(OUT / f"concept_{key}.png"))


if __name__ == "__main__":
    app = QApplication(sys.argv)  # keep a reference so Qt isn't torn down mid-render
    build_preview()
    print("Wrote", OUT / "concepts_preview.png")
