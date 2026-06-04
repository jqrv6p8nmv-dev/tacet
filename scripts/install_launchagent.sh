#!/usr/bin/env bash
# Install Tacet as a macOS LaunchAgent so it starts automatically on login
# with no Terminal window.
#
# Usage: bash scripts/install_launchagent.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="$REPO_DIR/.venv/bin/python"
PLIST_LABEL="com.tacet.app"
PLIST_DEST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
LOG_DIR="$HOME/Library/Logs/Tacet"

info()    { echo "  [INFO]  $*"; }
success() { echo "  [✓]     $*"; }
warn()    { echo "  [WARN]  $*"; }
error()   { echo "  [ERROR] $*" >&2; exit 1; }

# ── Pre-flight ───────────────────────────────────────────────────────────────

if [[ "$(uname)" != "Darwin" ]]; then
    error "LaunchAgents are a macOS feature."
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
    error "Virtual environment not found at $VENV_PYTHON — run scripts/install.sh first."
fi

# ── Stop any running instance ────────────────────────────────────────────────

if launchctl list "$PLIST_LABEL" &>/dev/null 2>&1; then
    info "Stopping existing Tacet agent..."
    launchctl bootout "gui/$(id -u)" "$PLIST_DEST" 2>/dev/null || true
fi

# ── Create log directory ─────────────────────────────────────────────────────

mkdir -p "$LOG_DIR"
success "Log directory: $LOG_DIR"

# ── Write the plist ──────────────────────────────────────────────────────────

info "Writing LaunchAgent plist to $PLIST_DEST ..."

cat > "$PLIST_DEST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${VENV_PYTHON}</string>
        <string>-m</string>
        <string>src.main</string>
    </array>

    <!-- Run from the project directory so relative imports work -->
    <key>WorkingDirectory</key>
    <string>${REPO_DIR}</string>

    <!-- Start immediately when the agent is loaded / user logs in -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Restart only if the process crashes (exit ≠ 0).
         If the user quits via the menu bar it exits cleanly and won't restart. -->
    <key>KeepAlive</key>
    <dict>
        <key>Crashed</key>
        <true/>
    </dict>

    <!-- Wait at least 15 s before restarting to avoid rapid crash loops -->
    <key>ThrottleInterval</key>
    <integer>15</integer>

    <!-- Logs (tail -f ~/Library/Logs/Tacet/tacet.log to watch) -->
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/tacet.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/tacet-error.log</string>

    <!-- Provide a sensible PATH so ffmpeg, ollama, etc. are found -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>${HOME}</string>
    </dict>
</dict>
</plist>
PLIST

success "Plist written"

# ── Load the agent (starts Tacet now + on every future login) ────────────

info "Loading LaunchAgent..."
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"
success "Tacet LaunchAgent loaded — it will start now and on every login"

echo ""
echo "  Tacet is starting in the menu bar."
echo "  No Terminal window needed from now on."
echo ""
echo "  Logs:  tail -f $LOG_DIR/tacet.log"
echo "  Stop:  bash scripts/uninstall_launchagent.sh   (removes auto-start)"
echo "         — or use 'Quit Tacet' in the menu bar (stops this session)"
echo ""
