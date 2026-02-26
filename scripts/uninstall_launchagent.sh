#!/usr/bin/env bash
# Remove the WhisperMe LaunchAgent — stops the running instance and prevents
# it from starting on future logins.
#
# Usage: bash scripts/uninstall_launchagent.sh

set -euo pipefail

PLIST_LABEL="com.whisperme.app"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

info()    { echo "  [INFO]  $*"; }
success() { echo "  [✓]     $*"; }
warn()    { echo "  [WARN]  $*"; }

if launchctl list "$PLIST_LABEL" &>/dev/null 2>&1; then
    info "Stopping WhisperMe..."
    launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
    success "Agent stopped"
else
    warn "WhisperMe agent was not running"
fi

if [[ -f "$PLIST_PATH" ]]; then
    rm "$PLIST_PATH"
    success "Plist removed: $PLIST_PATH"
else
    warn "Plist not found (already removed?)"
fi

echo ""
echo "  WhisperMe will no longer start on login."
echo "  To re-enable: bash scripts/install_launchagent.sh"
echo ""
