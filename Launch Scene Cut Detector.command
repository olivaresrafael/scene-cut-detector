#!/bin/bash
# Launches Scene Cut Detector.
# You can also drag a video file onto this file to open it directly.

cd "$(dirname "$0")" || exit 1

pause() {
  echo
  read -n 1 -s -r -p "Press Enter to close..."
  echo
}

ask_to_install() {
  echo "Dependencies are missing or incomplete."
  echo
  read -r -p "Run 'Install Dependencies.command' now? [Y/n] " answer
  case "$answer" in
    [nN]*) pause; exit 1 ;;
  esac
  echo
  bash "Install Dependencies.command" || exit 1
}

if [ ! -x ".venv/bin/python" ]; then
  ask_to_install
fi

if ! .venv/bin/python -c "import PySide6, scenedetect" >/dev/null 2>&1; then
  ask_to_install
fi

exec .venv/bin/python gui.py "$@"
