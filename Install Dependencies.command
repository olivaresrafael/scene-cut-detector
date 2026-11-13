#!/bin/bash
# Installs the Python dependencies in an isolated .venv folder inside this
# project. It never touches the system Python.

cd "$(dirname "$0")" || exit 1

pause() {
  echo
  read -n 1 -s -r -p "Press Enter to close..."
  echo
}

echo
echo "=== Scene Cut Detector - dependency installer ==="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 was not found."
  echo "Install Python 3.10 or newer from https://www.python.org/downloads/"
  pause
  exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo "Using Python $PY_VERSION"
echo "Project folder: $(pwd)"
echo

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating virtual environment in .venv ..."
  if ! python3 -m venv .venv; then
    echo
    echo "ERROR: could not create the virtual environment."
    pause
    exit 1
  fi
fi

echo "Upgrading pip ..."
if ! .venv/bin/python -m pip install --quiet --upgrade pip; then
  echo
  echo "ERROR: could not upgrade pip."
  pause
  exit 1
fi

echo "Installing PySceneDetect, OpenCV and PySide6."
echo "This may take a few minutes the first time ..."
if ! .venv/bin/python -m pip install -r requirements.txt; then
  echo
  echo "ERROR: dependency installation failed."
  echo "Check your internet connection and try again."
  pause
  exit 1
fi

echo
echo "Checking the installation ..."
if ! .venv/bin/python - <<'PY'
import cv2
import scenedetect
from PySide6 import __version__ as pyside_version

print(f"  PySceneDetect {scenedetect.__version__}")
print(f"  OpenCV        {cv2.__version__}")
print(f"  PySide6       {pyside_version}")
PY
then
  echo
  echo "ERROR: the dependencies were installed but cannot be imported."
  pause
  exit 1
fi

echo
echo "Done. Launch the app by double-clicking:"
echo "  Launch Scene Cut Detector.command"
echo
echo "Tip: you can also drag a video file onto the launcher."
pause
