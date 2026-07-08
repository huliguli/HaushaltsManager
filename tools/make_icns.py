"""Render assets/app.svg into a macOS .iconset of PNGs.

Run on macOS CI before the PyInstaller build; ``iconutil -c icns`` then turns the
iconset into ``assets/app.icns`` (the .app bundle icon). Uses PyQt6's
QSvgRenderer (the same engine as the in-app icons), so no extra tooling beyond
the build deps is required. Writes to ``build/AppIcon.iconset``.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "assets" / "app.svg"
ICONSET = ROOT / "build" / "AppIcon.iconset"

# Apple iconset spec: each logical size in a base (@1x) and a @2x variant.
_SPECS = [
    (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
]


def main() -> int:
    from PyQt6.QtCore import QByteArray, Qt
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer
    from PyQt6.QtWidgets import QApplication

    QApplication([])  # a QApplication is needed to paint images
    renderer = QSvgRenderer(QByteArray(SVG.read_bytes()))
    ICONSET.mkdir(parents=True, exist_ok=True)
    for size, name in _SPECS:
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        painter = QPainter(img)
        renderer.render(painter)
        painter.end()
        if not img.save(str(ICONSET / name), "PNG"):
            raise SystemExit(f"Konnte {name} nicht schreiben")
    print(ICONSET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
