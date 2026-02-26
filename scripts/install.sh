#!/usr/bin/env bash
# WhisperMe installation script for macOS
# Usage: bash scripts/install.sh

set -euo pipefail

PYTHON_MIN_VERSION="3.11"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=========================================="
echo "  WhisperMe Installer"
echo "=========================================="
echo ""

# ── Helper functions ────────────────────────────────────────────────────────

info()    { echo "  [INFO]  $*"; }
success() { echo "  [✓]     $*"; }
warn()    { echo "  [WARN]  $*"; }
error()   { echo "  [ERROR] $*" >&2; exit 1; }

check_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        error "WhisperMe requires macOS. Detected: $(uname)"
    fi
    OS_VER=$(sw_vers -productVersion)
    info "macOS version: $OS_VER"
}

check_homebrew() {
    if ! command -v brew &>/dev/null; then
        warn "Homebrew not found. Installing..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    success "Homebrew: $(brew --version | head -1)"
}

check_python() {
    # Find Python 3.11+
    for cmd in python3.13 python3.12 python3.11 python3; do
        if command -v "$cmd" &>/dev/null; then
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [[ "$major" -ge 3 && "$minor" -ge 11 ]]; then
                PYTHON_CMD="$cmd"
                success "Python: $ver ($cmd)"
                return
            fi
        fi
    done

    warn "Python 3.11+ not found. Installing via Homebrew..."
    brew install python@3.11
    PYTHON_CMD="python3.11"
    success "Python installed: $($PYTHON_CMD --version)"
}

check_ffmpeg() {
    if ! command -v ffmpeg &>/dev/null; then
        info "Installing ffmpeg (required by Whisper)..."
        brew install ffmpeg
    fi
    success "ffmpeg: $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"
}

check_ollama() {
    if ! command -v ollama &>/dev/null; then
        info "Installing Ollama (for AI text cleanup)..."
        brew install ollama
    fi
    success "Ollama: $(ollama --version 2>&1 | head -1)"

    # Check if a model is available
    if ! ollama list 2>/dev/null | grep -q "llama\|phi\|gemma"; then
        info "Pulling llama3.2:3b model for text cleanup (this may take a few minutes)..."
        ollama pull llama3.2:3b || warn "Failed to pull model — AI cleanup will be disabled until you run: ollama pull llama3.2:3b"
    fi
}

install_python_deps() {
    info "Creating virtual environment at $REPO_DIR/.venv ..."
    cd "$REPO_DIR"
    $PYTHON_CMD -m venv .venv
    VENV_PYTHON="$REPO_DIR/.venv/bin/python"
    VENV_PIP="$REPO_DIR/.venv/bin/pip"
    "$VENV_PIP" install --upgrade pip --quiet
    "$VENV_PIP" install -r requirements.txt --quiet
    success "Python packages installed into .venv"
}

setup_config() {
    CONFIG_DIR="$HOME/.config/whisperme"
    CONFIG_FILE="$CONFIG_DIR/config.json"
    mkdir -p "$CONFIG_DIR"

    if [[ ! -f "$CONFIG_FILE" ]]; then
        cp "$REPO_DIR/config/default_config.json" "$CONFIG_FILE"
        success "Config created at $CONFIG_FILE"
    else
        info "Config already exists at $CONFIG_FILE — not overwriting"
    fi
}

print_permissions_reminder() {
    echo ""
    echo "=========================================="
    echo "  Almost done! Grant these permissions:"
    echo "=========================================="
    echo ""
    echo "  1. Microphone:"
    echo "     System Settings → Privacy & Security → Microphone"
    echo "     → Enable Terminal (or WhisperMe.app)"
    echo ""
    echo "  2. Accessibility:"
    echo "     System Settings → Privacy & Security → Accessibility"
    echo "     → Enable Terminal (or WhisperMe.app)"
    echo ""
}

print_run_instructions() {
    echo "=========================================="
    echo "  Installation complete!"
    echo "=========================================="
    echo ""
    echo "  Run WhisperMe:"
    echo "    cd $REPO_DIR"
    echo "    source .venv/bin/activate"
    echo "    python -m src.main"
    echo ""
    echo "  Hotkey: Hold Fn key to record, release to transcribe"
    echo ""
}

# ── Main ────────────────────────────────────────────────────────────────────

check_macos
check_homebrew
check_python
check_ffmpeg
check_ollama
install_python_deps
setup_config
print_permissions_reminder
print_run_instructions
