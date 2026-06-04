#!/usr/bin/env bash
# WhisperMe — one-command installer for macOS (Apple Silicon)
#
# Usage:
#   git clone https://github.com/jqrv6p8nmv-dev/whspr-me
#   cd whspr-me
#   bash scripts/install.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# ── Helpers ──────────────────────────────────────────────────────────────────

info()    { echo "  [INFO]  $*"; }
success() { echo "  [✓]     $*"; }
warn()    { echo "  [WARN]  $*"; }
error()   { echo "  [ERROR] $*" >&2; exit 1; }

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║       WhisperMe Installer        ║"
echo "  ║  Local voice dictation for macOS ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# ── 1. Platform checks ───────────────────────────────────────────────────────

if [[ "$(uname)" != "Darwin" ]]; then
    error "WhisperMe requires macOS."
fi

if [[ "$(uname -m)" != "arm64" ]]; then
    error "WhisperMe requires Apple Silicon (M1/M2/M3/M4). Intel Macs are not supported."
fi

OS_VER=$(sw_vers -productVersion)
MAJOR=$(echo "$OS_VER" | cut -d. -f1)
if [[ "$MAJOR" -lt 13 ]]; then
    error "WhisperMe requires macOS Ventura (13) or later. Detected: $OS_VER"
fi
success "macOS $OS_VER on Apple Silicon"

# ── 2. Homebrew ──────────────────────────────────────────────────────────────

if ! command -v brew &>/dev/null; then
    info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add Homebrew to PATH for Apple Silicon
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi
success "Homebrew: $(brew --version | head -1)"

# ── 3. Python 3.11+ ──────────────────────────────────────────────────────────

PYTHON_CMD=""
for cmd in python3.14 python3.13 python3.12 python3.11; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    info "Installing Python 3.13 via Homebrew..."
    brew install python@3.13
    PYTHON_CMD="python3.13"
fi
success "Python: $($PYTHON_CMD --version)"

# ── 4. Virtual environment + dependencies ────────────────────────────────────

info "Creating virtual environment..."
cd "$REPO_DIR"
"$PYTHON_CMD" -m venv .venv
VENV_PIP="$REPO_DIR/.venv/bin/pip"
"$VENV_PIP" install --upgrade pip --quiet
info "Installing dependencies (this may take a few minutes the first time)..."
"$VENV_PIP" install -r requirements.txt
success "Dependencies installed"

# ── 5. Ollama (optional — needed only for AI text cleanup) ───────────────────

echo ""
read -r -p "  Install Ollama for AI text cleanup? (y/N): " install_ollama
if [[ "$install_ollama" =~ ^[Yy]$ ]]; then
    if ! command -v ollama &>/dev/null; then
        info "Installing Ollama..."
        brew install ollama
    fi
    success "Ollama: $(ollama --version 2>&1 | head -1)"
    if ! ollama list 2>/dev/null | grep -q "llama3.2:3b"; then
        info "Pulling llama3.2:3b model (this may take a few minutes)..."
        ollama pull llama3.2:3b || warn "Failed to pull model — run 'ollama pull llama3.2:3b' later"
    fi
else
    info "Skipping Ollama — AI cleanup will be disabled. You can install it later."
fi

# ── 6. User config ───────────────────────────────────────────────────────────

CONFIG_DIR="$HOME/.config/whisperme"
CONFIG_FILE="$CONFIG_DIR/config.json"
mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG_FILE" ]]; then
    cp "$REPO_DIR/config/default_config.json" "$CONFIG_FILE"
    success "Config created at $CONFIG_FILE"
else
    info "Config already exists at $CONFIG_FILE — not overwriting"
fi

# ── 7. LaunchAgent ───────────────────────────────────────────────────────────

echo ""
info "Installing LaunchAgent (auto-start on login)..."
bash "$REPO_DIR/scripts/install_launchagent.sh"

# ── 8. Permissions reminder ──────────────────────────────────────────────────

PYTHON_BIN="$($REPO_DIR/.venv/bin/python -c 'import sys; print(sys.executable)')"
PYTHON_NAME="$(basename "$PYTHON_BIN")"

echo ""
echo "  ╔══════════════════════════════════════════════════════════╗"
echo "  ║           Two permissions required in macOS              ║"
echo "  ╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Open System Settings → Privacy & Security and enable"
echo "  '$PYTHON_NAME' in each of these two sections:"
echo ""
echo "  1. Accessibility      — lets WhisperMe type text into apps"
echo "  2. Input Monitoring   — lets WhisperMe detect the hotkey"
echo ""
echo "  If '$PYTHON_NAME' isn't listed, toggle it off/on or restart"
echo "  and macOS will prompt you automatically on first use."
echo ""
echo "  ╔══════════════════════════════════════════════════════════╗"
echo "  ║  WhisperMe is running. Press Ctrl+Shift+Space to record. ║"
echo "  ╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Hotkey:  Ctrl+Shift+Space (press to start, press again to stop)"
echo "  Logs:    tail -f ~/Library/Logs/WhisperMe/whisperme-error.log"
echo "  Uninstall: bash scripts/uninstall_launchagent.sh"
echo ""
