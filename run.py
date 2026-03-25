"""
WhisperMe — py2app application entry point.

This script is the entry point for the standalone .app bundle built by py2app.
It must live at the project root (not inside a package) so that:
  1. py2app can use it as APP = ["run.py"] without relative-import issues.
  2. multiprocessing.freeze_support() is called before any other code,
     which prevents orphaned child processes on macOS frozen apps.
"""
import multiprocessing

# MUST be the first call in the frozen entry point.
# Prevents mlx-whisper's multiprocessing workers from spawning runaway
# Python processes when the app bundle is relaunched.
multiprocessing.freeze_support()

from src.main import main

main()
