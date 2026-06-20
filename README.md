# Tacet

Free, local voice dictation for macOS. Press a hotkey, speak naturally, get clean text inserted wherever your cursor is — no cloud, no subscription, nothing leaving your machine.

Inspired by Wispr Flow. All processing runs on-device using Apple Silicon-optimized models.

---

## Requirements

- Apple Silicon Mac (M1 or later)
- macOS Ventura 13 or later

## Install

### DMG (recommended)

1. Download `Tacet-0.1.0.dmg` from [Releases](https://github.com/jqrv6p8nmv-dev/tacet/releases)
2. Open the DMG and drag **Tacet.app** to `/Applications`
3. **Right-click Tacet.app → Open → Open** — required once to bypass Gatekeeper (Tacet is not yet signed with an Apple Developer certificate)

### From source

Requires Xcode Command Line Tools (`xcode-select --install`) and Python 3.14.

```bash
git clone https://github.com/jqrv6p8nmv-dev/tacet.git
cd tacet
python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt
bash scripts/build_dmg.sh
```

Then open `dist/Tacet-0.1.0.dmg` and drag to `/Applications`.

---

## First-time setup

Tacet needs two permissions. Follow this order exactly — the Accessibility step requires a restart to take effect.

### Step 1 — Grant Accessibility (before first launch)

Open **System Settings → Privacy & Security → Accessibility**

Click **+** and add `/Applications/Tacet.app`, then make sure the toggle is **on**.

> **Why before launch?** macOS only applies Accessibility grants to processes started after the grant is recorded. If you launch first and grant later, quit and relaunch Tacet.

### Step 2 — Launch Tacet

```
open /Applications/Tacet.app
```

A 🎙 icon appears in your menu bar.

### Step 3 — Grant Microphone

Press `Ctrl+Shift+Space`. macOS will ask for microphone access — click **Allow**.

That's it. Dictation works immediately.

### Optional: start at login

Click the 🎙 menubar icon → **Launch at Login: OFF** to toggle it on.

---

## Usage

| Action | What happens |
|--------|-------------|
| `Ctrl+Shift+Space` | Start recording — icon turns 🔴 |
| `Ctrl+Shift+Space` again, or stop talking for ~1.5s | Stop recording, transcribe, insert text |

A small overlay appears at the bottom of the screen showing recording / processing / done state.

---

## Configuration

Config lives at `~/.config/tacet/config.json` (created automatically on first launch from `config/default_config.json`).

| Setting | Default | Description |
|---------|---------|-------------|
| `hotkey.record` | `ctrl+shift+space` | Global trigger |
| `transcription.model` | `mlx-community/whisper-small-mlx` | Whisper model — smaller = faster, larger = more accurate |
| `processing.llm_cleanup` | `true` | Polish text via Ollama (requires Ollama installed) |
| `processing.ollama_model` | `llama3.2:3b` | Ollama model for cleanup |
| `audio.silence_duration` | `1.5` | Seconds of silence before auto-stop |
| `clipboard_restore` | `true` | Restore clipboard after paste |

### Whisper model options

| Model | Speed | Accuracy |
|-------|-------|----------|
| `mlx-community/whisper-tiny-mlx` | ~0.1s | Good for clear speech |
| `mlx-community/whisper-small-mlx` | ~0.3s | Better for accents, mumbling (default) |
| `mlx-community/whisper-large-v3-mlx` | ~1–2s | Best accuracy |

### LLM text cleanup (optional)

With `llm_cleanup: true`, transcribed text is polished by a local Ollama model before insertion. Requires [Ollama](https://ollama.com) with a compatible model:

```bash
brew install ollama
ollama pull llama3.2:3b
```

If Ollama isn't running or isn't installed, Tacet falls back to rule-based cleanup (filler removal, punctuation) without any error.

---

## Performance

Measured on Apple Silicon with the default whisper-small model:

| Step | Time |
|------|------|
| Silence detection | ~0.1s |
| Transcription | ~0.3s |
| Text insertion | ~0.15s |
| **Total (stop talking → text appears)** | **~0.6s** |

---

## Transcription model

Tacet uses **[Whisper](https://github.com/openai/whisper)**, an open-source speech recognition model created by OpenAI and released under the MIT license. Specifically it uses the [`whisper-small`](https://huggingface.co/mlx-community/whisper-small-mlx) variant, optimized for Apple Silicon by the [MLX Community](https://huggingface.co/mlx-community) and bundled directly inside the app.

**No internet connection is required for transcription.** The model runs entirely on-device — your audio never leaves your machine.

You can swap in a different model size by editing `~/.config/tacet/config.json` (`transcription.model`). Larger models are more accurate but slower; smaller models are faster but may struggle with accents or background noise. Any model from the [mlx-community Whisper collection](https://huggingface.co/collections/mlx-community/whisper-mlx-models) works — a one-time download is required when switching.

---

## Privacy

- Audio is processed **entirely on-device** — never sent anywhere
- Audio buffers are discarded immediately after transcription
- No accounts, no telemetry, no analytics
- Ollama (if used) runs fully offline after initial model download

---

## Tech stack

| Component | Technology |
|-----------|-----------|
| Native launcher | Objective-C (Cocoa + Carbon) |
| Global hotkey | Carbon `RegisterEventHotKey` — no TCC permission required |
| Text insertion | CoreGraphics `CGEventPost` — requires Accessibility |
| Menubar UI | Python + rumps |
| Audio capture | sounddevice (16 kHz mono) |
| Transcription | mlx-whisper (Apple Silicon optimized) |
| Text cleanup | Ollama (optional, local LLM) |
| Login item | `SMAppService` |

The native launcher forks Python after initializing NSApplication so Carbon hotkey events are delivered without requiring Input Monitoring permission.

---

## Logs

```bash
# Real-time
tail -f ~/Library/Logs/Tacet/tacet.log

# Launcher (hotkey, paste)
tail -f ~/Library/Logs/Tacet/launcher.log
```

---

## Uninstall

```bash
# Remove the app and config
rm -rf /Applications/Tacet.app ~/.config/tacet

# Remove from Login Items first if enabled (via the menubar)
```
