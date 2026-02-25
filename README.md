# WhisperMe

Free, local-first voice dictation for macOS. Hold the Fn key, speak naturally, get clean formatted text inserted into any app — no cloud, no subscription.

Inspired by Wispr Flow. All processing happens on-device using Apple Silicon-optimized models.

## Features (MVP)

- **Fn key hold-to-record** — press to start, release to stop (just like a walkie-talkie)
- **Local Whisper transcription** via `mlx-whisper` (Apple Silicon optimized)
- **AI text cleanup** via Ollama (removes fillers, fixes punctuation, handles self-corrections)
- **Text insertion** into any focused app via clipboard paste
- **Floating status overlay** showing recording / processing / done states
- **Menubar app** with status icon and quick settings

## Prerequisites

```bash
# Install Homebrew if needed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install system dependencies
brew install python ffmpeg ollama

# Pull a small LLM for text cleanup
ollama pull llama3.2:3b
```

## Installation

```bash
# Clone and set up
git clone https://github.com/yourusername/whisperme.git
cd whisperme
bash scripts/install.sh
```

Or manually:

```bash
pip install -r requirements.txt
python -m src.main
```

## Usage

1. Launch WhisperMe — a microphone icon appears in your menubar
2. **Hold the Fn key** to start recording
3. Speak naturally
4. **Release the Fn key** to stop — text is transcribed, cleaned up, and pasted into your focused app
5. You can also click "Start Recording" in the menubar menu

> **Note on the Fn key:** On macOS Sonoma+, the Fn key may open the emoji picker by default.
> To disable that: **System Settings → Keyboard → Press Fn/Globe key to → Do Nothing**.
> WhisperMe will then intercept the Fn key directly.

## Configuration

Config lives at `~/.config/whisperme/config.json`. See `config/default_config.json` for all options.

Key settings:
- `hotkey.record` — change the trigger key (`"fn"` for Fn hold-to-record, or a combo like `"ctrl+shift+space"` for toggle mode)
- `transcription.model` — choose Whisper model size (tiny → large)
- `processing.llm_cleanup` — toggle AI cleanup on/off
- `processing.ollama_model` — choose which Ollama model to use

## macOS Permissions

On first launch, grant these permissions in System Settings → Privacy & Security:
- **Microphone** — required for audio capture
- **Accessibility** — required for Fn key detection and text insertion

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Menubar UI | rumps |
| Overlay UI | PyObjC (AppKit) |
| Audio capture | sounddevice + numpy |
| Transcription | mlx-whisper (Apple Silicon) |
| Text cleanup | Ollama API (local LLM) |
| Text insertion | pyperclip + osascript |
| Hotkey | pynput |
| Config | JSON |

## Privacy

- All audio is processed **100% locally** — never leaves your machine
- Audio buffers are discarded immediately after transcription
- No telemetry, no analytics, no accounts
- Ollama runs fully offline after model download

## Performance Targets (Apple Silicon)

| Operation | Target |
|-----------|--------|
| Recording → text inserted | < 3 seconds (10s utterance) |
| Whisper transcription | ~1–2s for 10s audio |
| LLM cleanup pass | < 1s with llama3.2:3b |
| Idle memory | < 200 MB |

## Development

```bash
# Run tests
python -m pytest tests/

# Build .app bundle
bash scripts/build_app.sh
```

## Roadmap

- [x] Phase 1: Working MVP
- [ ] Phase 2: Ollama LLM cleanup + custom dictionary + settings UI
- [ ] Phase 3: Command mode + context-aware formatting + snippets
- [ ] Phase 4: Standalone .app packaging + auto-update
