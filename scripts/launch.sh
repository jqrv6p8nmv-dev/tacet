#!/usr/bin/env bash
# Launch Tacet using the project's virtual environment.
# Double-click this file in Finder, or add it to Login Items.

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
exec "$REPO_DIR/.venv/bin/python3" -m src.main
