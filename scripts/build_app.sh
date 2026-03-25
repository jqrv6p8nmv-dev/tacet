#!/usr/bin/env bash
# Build WhisperMe as a standalone macOS .app bundle using py2app.
#
# Usage:
#   bash scripts/build_app.sh
#
# After a successful build, the app is at dist/WhisperMe.app.
# Double-click it or drag it to /Applications to install.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$REPO_DIR/dist"
BUILD_DIR="$REPO_DIR/build"

info()    { echo "  [INFO]  $*"; }
success() { echo "  [✓]     $*"; }
error()   { echo "  [ERROR] $*" >&2; exit 1; }

cd "$REPO_DIR"

# ── Pre-flight checks ────────────────────────────────────────────────────────

if [[ "$(uname)" != "Darwin" ]]; then
    error "Building .app bundles requires macOS."
fi

# ── Detect Python (prefer the project venv) ──────────────────────────────────

if [[ -x "$REPO_DIR/.venv/bin/python3" ]]; then
    PYTHON="$REPO_DIR/.venv/bin/python3"
    PIP="$REPO_DIR/.venv/bin/pip"
    info "Using virtual environment: .venv"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
    PIP="python3 -m pip"
    info "Using system python3 ($(python3 --version))"
else
    error "python3 not found. Run scripts/install.sh first."
fi

# ── Install / upgrade py2app in the active Python ────────────────────────────

info "Installing py2app..."
"$PIP" install --quiet --upgrade py2app
PY2APP_VER=$("$PYTHON" -c "import py2app; print(py2app.__version__)" 2>/dev/null || echo "unknown")
success "py2app ready (version $PY2APP_VER)"

# ── Clean previous builds ────────────────────────────────────────────────────

info "Cleaning previous build artifacts..."
rm -rf "$DIST_DIR" "$BUILD_DIR"

# ── Build ─────────────────────────────────────────────────────────────────────

info "Building WhisperMe.app — this takes a few minutes on first run..."
"$PYTHON" setup.py py2app 2>&1

if [[ ! -d "$DIST_DIR/WhisperMe.app" ]]; then
    error "Build failed — WhisperMe.app not found in $DIST_DIR"
fi

success "Build complete: $DIST_DIR/WhisperMe.app"

# ── Ad-hoc code sign ─────────────────────────────────────────────────────────
# An ad-hoc signature lets the app run on the build machine without Gatekeeper
# blocking it every launch.  It is NOT a Developer ID signature — the app
# cannot be distributed to other Macs without a paid Apple Developer account.

info "Signing app (ad-hoc)..."
if codesign --force --deep --sign - "$DIST_DIR/WhisperMe.app" 2>/dev/null; then
    success "Signed (ad-hoc)"
else
    info "codesign not available — skipping signature"
fi

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "  ┌─────────────────────────────────────────────────────────┐"
echo "  │  WhisperMe.app is ready.                                │"
echo "  │                                                         │"
echo "  │  To run now:                                            │"
echo "  │    open $DIST_DIR/WhisperMe.app"
echo "  │                                                         │"
echo "  │  To install system-wide:                                │"
echo "  │    cp -r $DIST_DIR/WhisperMe.app /Applications/        │"
echo "  │                                                         │"
echo "  │  First launch: grant Microphone + Accessibility access  │"
echo "  │  in System Settings → Privacy & Security.              │"
echo "  └─────────────────────────────────────────────────────────┘"
echo ""
