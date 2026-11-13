#!/usr/bin/env python3
"""Render assets/icon.svg into the PNG sizes macOS needs and build icon.icns.

Run from the project root with the project's virtual environment:

    .venv/bin/python make_icon.py

The generated files (assets/icon.png, assets/icon.icns and the .iconset
folder) are build artifacts and are ignored by git.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
SVG_PATH = ASSETS / "icon.svg"
ICONSET = ASSETS / "SceneCutDetector.iconset"

ICON_SIZES = [
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
]


def render_png(renderer: QSvgRenderer, size: int, target: Path) -> None:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()
    if not image.save(str(target)):
        raise RuntimeError(f"Could not write {target}")


def main() -> int:
    if not SVG_PATH.is_file():
        print(f"ERROR: icon source not found: {SVG_PATH}", file=sys.stderr)
        return 1

    app = QGuiApplication(sys.argv)  # noqa: F841 - needed by Qt
    renderer = QSvgRenderer(str(SVG_PATH))
    if not renderer.isValid():
        print(f"ERROR: could not read {SVG_PATH}", file=sys.stderr)
        return 1

    if ICONSET.exists():
        shutil.rmtree(ICONSET)
    ICONSET.mkdir(parents=True)

    for size, name in ICON_SIZES:
        render_png(renderer, size, ICONSET / name)

    shutil.copyfile(ICONSET / "icon_512x512@2x.png", ASSETS / "icon.png")

    if sys.platform == "darwin" and shutil.which("iconutil"):
        subprocess.run(
            [
                "iconutil",
                "-c", "icns",
                str(ICONSET),
                "-o", str(ASSETS / "icon.icns"),
            ],
            check=True,
        )
        print(f"Generated {ASSETS / 'icon.icns'}")
    else:
        print("iconutil not available; generated PNG files only.")

    print(f"Generated {ASSETS / 'icon.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
