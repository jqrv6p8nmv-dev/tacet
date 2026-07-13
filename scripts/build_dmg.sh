#!/usr/bin/env bash
# Build Tacet.app and package it as a distributable DMG.
#
# Usage:
#   bash scripts/build_dmg.sh
#
# With Developer ID signing (optional):
#   DEVELOPER_ID="Developer ID Application: Your Name (XXXXXXXXXX)" bash scripts/build_dmg.sh
#
# Signing identity matters for TCC: macOS keys Accessibility/Microphone grants
# to the app's code identity. Ad-hoc signing (--sign -) produces a new identity
# on every build, so grants silently stop matching after a rebuild ("toggle is
# ON but paste doesn't work"). A persistent identity fixes this. Without a paid
# Developer ID, create a free self-signed code-signing cert once:
#   Keychain Access → Certificate Assistant → Create a Certificate…
#   Name: "Tacet Dev Signing", Identity Type: Self-Signed Root,
#   Certificate Type: Code Signing
# (or generate via openssl and `security import` / `security add-trusted-cert`).
# The script picks it up automatically when present.

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

    <!-- Prevent multiple instances from launching -->
    <key>LSMultipleInstancesProhibited</key>
    <true/>

    <!-- macOS permission usage descriptions (shown in system prompts) -->
    <key>NSMicrophoneUsageDescription</key>
    <string>Tacet needs microphone access to capture your voice for transcription.</string>
    <key>NSAccessibilityUsageDescription</key>
    <string>Tacet needs Accessibility access to insert transcribed text into other apps.</string>
</dict>
</plist>
PLIST

# Compile the native launcher — a proper compiled binary at Contents/MacOS/tacet
# means macOS TCC attributes Accessibility/Input Monitoring prompts to "Tacet"
# (from the bundle's Info.plist) rather than to python3 / Python.framework.
info "Compiling native launcher..."
clang -fobjc-arc \
    -o "$APP_DIR/Contents/MacOS/tacet" \
    "$REPO_DIR/launcher/tacet_launcher.m" \
    -framework Cocoa \
    -framework Carbon \
    || error "clang failed — ensure Xcode Command Line Tools are installed (xcode-select --install)"
chmod +x "$APP_DIR/Contents/MacOS/tacet"

# Copy Python source and default config
info "Copying source files..."
cp -r "$REPO_DIR/src"    "$APP_DIR/Contents/Resources/"
cp -r "$REPO_DIR/config" "$APP_DIR/Contents/Resources/"

# Copy the full venv — all dependencies pre-installed, no pip needed at install time
info "Copying Python environment (this may take a moment)..."
cp -rp "$VENV" "$APP_DIR/Contents/Resources/.venv"

success "Bundle structure created"

# Download Whisper model into the bundle so the app works offline on first launch.
# Uses the venv's huggingface_hub (already installed as an mlx-whisper dependency).
WHISPER_MODEL="mlx-community/whisper-small-mlx"
WHISPER_MODEL_STEM="${WHISPER_MODEL##*/}"   # whisper-small-mlx
MODEL_DEST="$APP_DIR/Contents/Resources/models/$WHISPER_MODEL_STEM"
if [[ -d "$MODEL_DEST" ]] && [[ -n "$(ls -A "$MODEL_DEST" 2>/dev/null)" ]]; then
    info "Whisper model already present — skipping download"
else
    info "Downloading Whisper model ($WHISPER_MODEL) into bundle..."
    mkdir -p "$MODEL_DEST"
    "$VENV/bin/python3" - <<PYEOF
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="$WHISPER_MODEL",
    local_dir="$MODEL_DEST",
    local_dir_use_symlinks=False,
    ignore_patterns=["*.gitattributes", ".gitattributes"],
)
PYEOF
    success "Whisper model bundled ($WHISPER_MODEL_STEM)"
fi

# Stamp with build time so stale installs are easy to identify
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$APP_DIR/Contents/Resources/BUILD_TIMESTAMP"
info "Build timestamp: $(cat "$APP_DIR/Contents/Resources/BUILD_TIMESTAMP")"

# ── Code signing ─────────────────────────────────────────────────────────────

# Identity resolution (stable identity keeps TCC grants valid across rebuilds):
#   1. $DEVELOPER_ID if set
#   2. "Tacet Dev Signing" self-signed cert if present in the keychain
#   3. Ad-hoc (grants will NOT survive the next rebuild)
SELF_SIGN_ID="Tacet Dev Signing"
if [[ -n "$DEVELOPER_ID" ]]; then
    info "Signing with Developer ID: $DEVELOPER_ID"
    codesign --force --deep --options runtime \
        --entitlements "$REPO_DIR/Tacet.entitlements" \
        --sign "$DEVELOPER_ID" \
        "$APP_DIR"
    success "Signed with Developer ID (submit for notarization to remove Gatekeeper warning)"
elif security find-identity -v -p codesigning 2>/dev/null | grep -q "$SELF_SIGN_ID"; then
    info "Signing with self-signed identity: $SELF_SIGN_ID"
    # No --options runtime: hardened-runtime library validation would reject the
    # venv's unsigned-by-same-team .so files without notarization entitlements.
    codesign --force --deep --sign "$SELF_SIGN_ID" "$APP_DIR"
    success "Signed with $SELF_SIGN_ID — TCC grants persist across rebuilds"
else
    info "No DEVELOPER_ID and no '$SELF_SIGN_ID' cert — using ad-hoc signing"
    codesign --force --deep --sign - "$APP_DIR"
    echo "  [WARN]  Ad-hoc signature changes every build: Accessibility grants"
    echo "  [WARN]  will NOT survive a rebuild (System Settings toggle stays ON"
    echo "  [WARN]  but stops matching). Create the '$SELF_SIGN_ID' cert —"
    echo "  [WARN]  see the header of this script."
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
echo "  Note: Not notarized. First-time install:"
echo "    1. Open DMG, drag Tacet to /Applications"
echo "    2. Launch, then System Settings → Privacy & Security → Open Anyway"
echo "       (macOS 15+ removed the right-click → Open bypass; once only)"
echo "    3. Grant Accessibility and Microphone when prompted — no relaunch needed"
echo ""
fi
echo "  To add to Login Items: Tacet menu → Launch at Login"
echo ""
