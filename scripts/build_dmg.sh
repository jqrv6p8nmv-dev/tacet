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
#
# Ships as a drag-to-Applications installer: the mounted DMG shows Tacet.app
# next to an /Applications shortcut so the natural action is dragging it in.
# This matters beyond convenience — a copy double-clicked straight from the
# mounted DMG (still quarantined) gets App Translocation'd by Gatekeeper to a
# randomized read-only path, which breaks the app (see CLAUDE.md). Dragging
# into /Applications via Finder is what stops that from happening.

info "Staging DMG contents..."
STAGING_DIR="$DIST_DIR/dmg-staging"
DRAG_LABEL="Drag Tacet Here"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
cp -R "$APP_DIR" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/$DRAG_LABEL"

info "Creating writable DMG..."
TMP_DMG="$DIST_DIR/$APP_NAME-tmp.dmg"
MOUNT_DIR="$DIST_DIR/mnt-$APP_NAME"
rm -f "$TMP_DMG"
APP_SIZE_MB="$(du -sm "$STAGING_DIR" | cut -f1)"
hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$STAGING_DIR" \
    -ov \
    -fs HFS+ \
    -format UDRW \
    -size "$((APP_SIZE_MB + 200))m" \
    "$TMP_DMG"

info "Configuring Finder layout (drag-to-Applications)..."
rm -rf "$MOUNT_DIR"; mkdir -p "$MOUNT_DIR"
hdiutil attach "$TMP_DMG" -mountpoint "$MOUNT_DIR" -nobrowse -quiet

# hdiutil attach can return before Finder's own volume list catches up, which
# made the layout script below fail intermittently ("Can't get disk 'Tacet'").
# Wait for Finder to actually see the volume before scripting it.
FINDER_SEES_DISK=false
for _ in 1 2 3 4 5 6 7 8 9 10; do
    if [[ "$(osascript -e "tell application \"Finder\" to exists disk \"$APP_NAME\"" 2>/dev/null)" == "true" ]]; then
        FINDER_SEES_DISK=true
        break
    fi
    sleep 0.5
done
[[ "$FINDER_SEES_DISK" == "true" ]] || echo "  [WARN]  Finder never saw the mounted disk — skipping layout"

if [[ "$FINDER_SEES_DISK" == "true" ]]; then
osascript <<APPLESCRIPT || echo "  [WARN]  Finder layout script failed — DMG will still work, just unstyled"
tell application "Finder"
    tell disk "$APP_NAME"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {200, 120, 760, 480}
        set theViewOptions to the icon view options of container window
        set arrangement of theViewOptions to not arranged
        set icon size of theViewOptions to 96
        set position of item "$APP_NAME.app" of container window to {140, 180}
        set position of item "$DRAG_LABEL" of container window to {420, 180}
        update without registering applications
        delay 1
        close
    end tell
end tell
APPLESCRIPT
fi
sync
hdiutil detach "$MOUNT_DIR" -quiet || hdiutil detach "$MOUNT_DIR" -force -quiet
rmdir "$MOUNT_DIR" 2>/dev/null || true

info "Converting to compressed, read-only DMG..."
rm -f "$DMG_PATH"
hdiutil convert "$TMP_DMG" -format UDZO -ov -o "$DMG_PATH"
rm -f "$TMP_DMG"
rm -rf "$STAGING_DIR"

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
