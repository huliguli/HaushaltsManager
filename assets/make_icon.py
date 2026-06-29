"""Generate the production app icon from the chosen 'Ring-Haus' concept.

Renders the brand SVG at each target size with Qt's SVG engine (crisp per-size,
not a single downsample) and assembles a multi-resolution Windows .ico, plus a
256px PNG for the Qt window/app icon and the source SVG. Reproducible:

    python assets/make_icon.py

Outputs into assets/: app.svg, app.ico (16/24/32/48/64/128/256), app_icon.png.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

OUT = Path(__file__).resolve().parent
SIZES = [16, 24, 32, 48, 64, 128, 256]

# Brand palette: navy tile, white house, blue donut ring (nods to the dashboard
# chart). currentColor is not used here on purpose — this is a fixed brand mark.
APP_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0.25" y2="1">
      <stop offset="0" stop-color="#1d2a45"/>
      <stop offset="1" stop-color="#0d1422"/>
    </linearGradient>
  </defs>
  <rect x="6" y="6" width="244" height="244" rx="56" fill="url(#bg)"/>
  <circle cx="128" cy="122" r="60" fill="none" stroke="#2f5fc0" stroke-width="26"/>
  <circle cx="128" cy="122" r="60" fill="none" stroke="#8fb6ff" stroke-width="26"
          stroke-dasharray="113 264" transform="rotate(-90 128 122)"/>
  <path d="M128 92 L164 122 L92 122 Z" fill="#ffffff"/>
  <rect x="103" y="120" width="50" height="40" rx="6" fill="#ffffff"/>
</svg>
"""


def render_png_bytes(svg: str, size: int) -> bytes:
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()

    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return data


def build_ico(frames: list[tuple[int, bytes]], path: Path) -> None:
    """Assemble a PNG-payload .ico (Vista+) from per-size PNG frames."""
    count = len(frames)
    header = struct.pack("<HHH", 0, 1, count)  # reserved, type=icon, count
    offset = 6 + 16 * count
    entries = bytearray()
    payload = bytearray()
    for size, png in frames:
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO spec
        entries += struct.pack(
            "<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        payload += png
        offset += len(png)
    path.write_bytes(header + bytes(entries) + bytes(payload))


def main() -> None:
    app = QApplication(sys.argv)  # noqa: F841 - keep Qt alive during rendering
    (OUT / "app.svg").write_text(APP_SVG, encoding="utf-8")

    frames = [(s, render_png_bytes(APP_SVG, s)) for s in SIZES]
    build_ico(frames, OUT / "app.ico")
    (OUT / "app_icon.png").write_bytes(dict(frames)[256])

    print(f"Wrote app.ico ({len(SIZES)} sizes), app_icon.png, app.svg in {OUT}")


if __name__ == "__main__":
    main()
