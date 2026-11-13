#!/bin/bash
# Builds a standalone macOS app bundle with PyInstaller.
# The result is dist/Scene Cut Detector.app (no Python install required).

cd "$(dirname "$0")" || exit 1

pause() {
  echo
  read -n 1 -s -r -p "Press Enter to close..."
  echo
}

if [ ! -x ".venv/bin/python" ]; then
  echo "ERROR: run 'Install Dependencies.command' first."
  pause
  exit 1
fi

if ! command -v iconutil >/dev/null 2>&1; then
  echo "ERROR: iconutil not found. This script requires macOS."
  pause
  exit 1
fi

echo
echo "=== Building Scene Cut Detector.app ==="
echo

echo "Generating the app icon ..."
if ! .venv/bin/python make_icon.py; then
  echo "ERROR: could not generate the icon."
  pause
  exit 1
fi

if ! .venv/bin/python -c "import PyInstaller" >/dev/null 2>&1; then
  echo "Installing PyInstaller ..."
  if ! .venv/bin/python -m pip install --quiet "pyinstaller>=6.3,<7"; then
    echo "ERROR: could not install PyInstaller."
    pause
    exit 1
  fi
fi

echo "Packaging the app (this may take a few minutes) ..."
rm -rf build dist

if ! .venv/bin/python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "Scene Cut Detector" \
  --osx-bundle-identifier "com.scenecutdetector.app" \
  --icon "assets/icon.icns" \
  --add-data "assets:assets" \
  --collect-all scenedetect \
  --hidden-import cv2 \
  --hidden-import PySide6.QtSvg \
  gui.py
then
  echo
  echo "ERROR: PyInstaller failed."
  pause
  exit 1
fi

echo
echo "Done: dist/Scene Cut Detector.app"
echo
echo "You can move the app to /Applications. It includes Python and all"
echo "dependencies, so it runs without the project folder."
echo
open dist
pause
