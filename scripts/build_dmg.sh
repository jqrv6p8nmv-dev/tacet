#!/usr/bin/env bash
# Build Tacet.app and package it as a distributable DMG.
#
# Usage:
#   bash scripts/build_dmg.sh
#
# With Developer ID signing (optional):
#   DEVELOPER_ID="Developer ID Application: Your Name (XXXXXXXXXX)" bash scripts/build_dmg.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$REPO_DIR/.venv"
DIST_DIR="$REPO_DIR/dist"
APP_NAME="Tacet"
BUNDLE_ID="com.tacet.app"
VERSION="0.1.0"
APP_DIR="$DIST_DIR/$APP_NAME.app"
DMG_PATH="$DIST_DIR/$APP_NAME-$VERSION.dmg"
DEVELOPER_ID="${DEVELOPER_ID:-}"

info()    { echo "  [INFO]  $*"; }
success() { echo "  [✓]     $*"; }
error()   { echo "  [ERROR] $*" >&2; exit 1; }

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║      Tacet — Build DMG           ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# ── Pre-flight ───────────────────────────────────────────────────────────────

[[ "$(uname)" == "Darwin" ]] || error "Must run on macOS"
[[ "$(uname -m)" == "arm64" ]] || error "Must run on Apple Silicon"
[[ -x "$VENV/bin/python3" ]] || error "venv not found at $VENV — run scripts/install.sh first"

# ── Clean ────────────────────────────────────────────────────────────────────

info "Cleaning previous build..."
rm -rf "$APP_DIR" "$DMG_PATH"
mkdir -p "$DIST_DIR"

# ── Build .app bundle ────────────────────────────────────────────────────────

info "Creating $APP_NAME.app bundle..."
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Info.plist — bundle metadata and TCC usage descriptions
cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>${BUNDLE_ID}</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleExecutable</key>
    <string>tacet</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>

    <!-- Run as a menubar-only app — no dock icon -->
    <key>LSUIElement</key>
    <true/>

    <!-- macOS permission usage descriptions (shown in system prompts) -->
    <key>NSMicrophoneUsageDescription</key>
    <string>Tacet needs microphone access to capture your voice for transcription.</string>
    <key>NSAccessibilityUsageDescription</key>
    <string>Tacet needs Accessibility access to insert transcribed text into other apps.</string>
</dict>
</plist>
PLIST

# Launcher — shell script that exec's Python from the bundled venv.
# exec replaces the shell with Python so it becomes the main app process,
# keeping macOS bundle identity intact for TCC (permission) prompts.
cat > "$APP_DIR/Contents/MacOS/tacet" << 'LAUNCHER'
#!/bin/bash
RESOURCES="$(cd "$(dirname "$0")/../Resources" && pwd)"
exec "$RESOURCES/.venv/bin/python3" -m src.main
LAUNCHER
chmod +x "$APP_DIR/Contents/MacOS/tacet"

# Copy Python source and default config
info "Copying source files..."
cp -r "$REPO_DIR/src"    "$APP_DIR/Contents/Resources/"
cp -r "$REPO_DIR/config" "$APP_DIR/Contents/Resources/"

# Copy the full venv — all dependencies pre-installed, no pip needed at install time
info "Copying Python environment (this may take a moment)..."
cp -rp "$VENV" "$APP_DIR/Contents/Resources/.venv"

success "Bundle structure created"

# ── Code signing ─────────────────────────────────────────────────────────────

if [[ -n "$DEVELOPER_ID" ]]; then
    info "Signing with Developer ID: $DEVELOPER_ID"
    codesign --force --deep --options runtime \
        --entitlements "$REPO_DIR/Tacet.entitlements" \
        --sign "$DEVELOPER_ID" \
        "$APP_DIR"
    success "Signed with Developer ID (submit for notarization to remove Gatekeeper warning)"
else
    info "No DEVELOPER_ID — using ad-hoc signing"
    codesign --force --deep --sign - "$APP_DIR"
    success "Ad-hoc signed (recipients right-click → Open on first launch)"
fi

# ── Create DMG ───────────────────────────────────────────────────────────────

info "Creating DMG..."
hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$APP_DIR" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

success "DMG created: $DMG_PATH"

echo ""
echo "  ╔══════════════════════════════════════════════════════════╗"
echo "  ║  Build complete!                                         ║"
echo "  ╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  App: $APP_DIR"
echo "  DMG: $DMG_PATH"
echo ""
if [[ -z "$DEVELOPER_ID" ]]; then
echo "  Note: Ad-hoc signed. First-time install:"
echo "    1. Open DMG, drag Tacet to /Applications"
echo "    2. Right-click Tacet.app → Open → Open (once only)"
echo "    3. Grant Microphone, Accessibility, Input Monitoring when prompted"
echo ""
fi
echo "  To add to Login Items: Tacet menu → Launch at Login"
echo ""
