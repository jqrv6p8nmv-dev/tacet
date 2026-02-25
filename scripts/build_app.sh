#!/usr/bin/env bash
# Build WhisperMe as a standalone macOS .app bundle using py2app.
# Usage: bash scripts/build_app.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$REPO_DIR/dist"
BUILD_DIR="$REPO_DIR/build"

info()    { echo "  [INFO]  $*"; }
success() { echo "  [✓]     $*"; }
error()   { echo "  [ERROR] $*" >&2; exit 1; }

cd "$REPO_DIR"

# ── Pre-flight checks ───────────────────────────────────────────────────────

if [[ "$(uname)" != "Darwin" ]]; then
    error "Building .app bundles requires macOS."
fi

if ! command -v python3 &>/dev/null; then
    error "python3 not found. Run scripts/install.sh first."
fi

# ── Install py2app ──────────────────────────────────────────────────────────

info "Installing py2app..."
python3 -m pip install py2app --quiet
success "py2app ready"

# ── Clean previous builds ────────────────────────────────────────────────────

info "Cleaning previous build artifacts..."
rm -rf "$DIST_DIR" "$BUILD_DIR"

# ── Build ────────────────────────────────────────────────────────────────────

info "Building WhisperMe.app (this may take a few minutes)..."
python3 setup.py py2app

if [[ -d "$DIST_DIR/WhisperMe.app" ]]; then
    success "WhisperMe.app built at: $DIST_DIR/WhisperMe.app"
    echo ""
    echo "  To run: open $DIST_DIR/WhisperMe.app"
    echo "  To install: cp -r $DIST_DIR/WhisperMe.app /Applications/"
else
    error "Build failed — WhisperMe.app not found in $DIST_DIR"
fi
