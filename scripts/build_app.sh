#!/usr/bin/env bash
# Build Tacet as a standalone macOS .app bundle using py2app.
#
# Usage:
#   bash scripts/build_app.sh
#
# After a successful build, the app is at dist/Tacet.app.
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

info "Building Tacet.app — this takes a few minutes on first run..."
"$PYTHON" setup.py py2app 2>&1

if [[ ! -d "$DIST_DIR/Tacet.app" ]]; then
    error "Build failed — Tacet.app not found in $DIST_DIR"
fi

success "Build complete: $DIST_DIR/Tacet.app"

# ── Copy mlx + mlx_whisper into the bundle ───────────────────────────────────
# py2app's collect_packagedirs uses imp.find_module, which crashes on mlx's
# non-standard package layout.  We intentionally exclude mlx/mlx_whisper from
# setup.py's packages list and copy them manually here instead.

VENV_SITE=$("$PYTHON" -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || true)

# Locate the python-versioned lib dir inside the app bundle
BUNDLE_LIB="$DIST_DIR/Tacet.app/Contents/Resources/lib"
BUNDLE_PY_LIB=$(ls -d "$BUNDLE_LIB"/python3.*/ 2>/dev/null | head -1)

if [[ -z "$BUNDLE_PY_LIB" ]]; then
    info "Warning: could not find python lib dir inside bundle — skipping mlx copy"
elif [[ -z "$VENV_SITE" ]]; then
    info "Warning: could not determine venv site-packages — skipping mlx copy"
else
    for PKG in mlx mlx_whisper; do
        SRC="$VENV_SITE/$PKG"
        DST="$BUNDLE_PY_LIB$PKG"
        if [[ -d "$SRC" ]]; then
            rm -rf "$DST"
            cp -r "$SRC" "$DST"
            success "Copied $PKG into bundle"
        else
            info "Warning: $PKG not found in venv ($SRC) — transcription will fall back"
        fi
    done

    # mlx ships compiled .so extensions; also copy any mlx_*.dist-info dirs
    # so that importlib.metadata can find the package if needed.
    for DIST_INFO in "$VENV_SITE"/mlx*.dist-info "$VENV_SITE"/mlx_whisper*.dist-info; do
        [[ -d "$DIST_INFO" ]] && cp -r "$DIST_INFO" "$BUNDLE_PY_LIB" 2>/dev/null || true
    done

    # Fix mlx C-extension rpath: core.cpython-*.so links against @rpath/libmlx.dylib
    # but there is no rpath pointing to mlx/lib/ inside the bundle.  Rewrite the
    # reference to use @loader_path (= the directory of the .so itself) so the
    # dynamic linker finds mlx/lib/libmlx.dylib without needing DYLD_LIBRARY_PATH.
    MLX_SO=$(ls "$BUNDLE_PY_LIB"mlx/core.cpython-*.so 2>/dev/null | head -1)
    if [[ -n "$MLX_SO" && -f "$BUNDLE_PY_LIB"mlx/lib/libmlx.dylib ]]; then
        install_name_tool -change \
            @rpath/libmlx.dylib \
            @loader_path/lib/libmlx.dylib \
            "$MLX_SO" 2>/dev/null && success "Fixed libmlx.dylib rpath in bundle" \
            || info "Warning: install_name_tool failed — mlx may not load correctly"
    else
        info "Warning: mlx .so or libmlx.dylib not found — skipping rpath fix"
    fi
fi

# ── Ad-hoc code sign ─────────────────────────────────────────────────────────
# An ad-hoc signature lets the app run on the build machine without Gatekeeper
# blocking it every launch.  It is NOT a Developer ID signature — the app
# cannot be distributed to other Macs without a paid Apple Developer account.

info "Signing app (ad-hoc)..."
if codesign --force --deep --sign - "$DIST_DIR/Tacet.app" 2>/dev/null; then
    success "Signed (ad-hoc)"
else
    info "codesign not available — skipping signature"
fi

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "  ┌─────────────────────────────────────────────────────────┐"
echo "  │  Tacet.app is ready.                                │"
echo "  │                                                         │"
echo "  │  To run now:                                            │"
echo "  │    open $DIST_DIR/Tacet.app"
echo "  │                                                         │"
echo "  │  To install system-wide:                                │"
echo "  │    cp -r $DIST_DIR/Tacet.app /Applications/        │"
echo "  │                                                         │"
echo "  │  First launch: grant Microphone + Accessibility access  │"
echo "  │  in System Settings → Privacy & Security.              │"
echo "  └─────────────────────────────────────────────────────────┘"
echo ""
