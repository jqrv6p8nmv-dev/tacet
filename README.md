# Tacet

Free, local voice dictation for macOS. Press a hotkey, speak naturally, get clean text inserted into any app — no cloud, no subscription, nothing phoning home.

Inspired by Wispr Flow. All processing runs on-device using Apple Silicon-optimized models.

---

## Requirements

- Apple Silicon Mac (M1 / M2 / M3 / M4)
- macOS Ventura 13 or later
- [Homebrew](https://brew.sh) (the installer will set it up if missing)

## Install — DMG (recommended for most users)

1. Download `Tacet-0.1.0.dmg` from [Releases](https://github.com/jqrv6p8nmv-dev/tacet/releases)
2. Open the DMG and drag **Tacet.app** to `/Applications`
3. **Right-click Tacet.app → Open → Open** (required once to bypass Gatekeeper — Tacet is not yet signed with an Apple Developer certificate)

## Install — from source (developers)

```bash
git clone https://github.com/jqrv6p8nmv-dev/tacet.git
cd tacet
bash scripts/install.sh
```

The installer handles everything: Python, virtual environment, dependencies, and the LaunchAgent that starts Tacet automatically on every login.

## Grant permissions (required)

Tacet needs two permissions to function. macOS will prompt for **Microphone** automatically on first launch. The other two require a one-time manual step:

Open **System Settings → Privacy & Security** and enable `python3` under:

1. **Accessibility** — lets Tacet type text into other apps
2. **Input Monitoring** — lets Tacet detect the global hotkey

For each: click `+`, press `Cmd+Shift+G` in the file picker, and paste:
```
/opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python
```

Then restart Tacet. These are one-time steps — macOS remembers them across reboots.

## Usage

Tacet runs as a menubar app. Look for 🎙 in your menu bar.

| Action | Result |
|--------|--------|
| Press `Ctrl+Shift+Space` | Start recording (icon turns 🔴) |
| Press `Ctrl+Shift+Space` again | Stop and transcribe |
| Stop talking for ~1.5s | Auto-stops and transcribes |

Transcribed text is inserted at the cursor in whatever app is focused.

## Configuration

User config lives at `~/.config/tacet/config.json`. All available options are in `config/default_config.json`.

Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `hotkey.record` | `ctrl+shift+space` | Trigger key combo |
| `transcription.model` | `mlx-community/whisper-tiny-mlx` | Whisper model size |
| `processing.llm_cleanup` | `true` | AI text polish via Ollama |
| `processing.ollama_model` | `llama3.2:3b` | Ollama model to use |
| `audio.silence_duration` | `1.5` | Seconds of silence before auto-stop |

## Performance

On Apple Silicon with the default tiny model:

| Step | Time |
|------|------|
| Transcription | ~0.1–0.2s |
| Total (hotkey → text inserted) | ~0.5–0.7s |

For better accuracy at the cost of speed, switch to `mlx-community/whisper-small-mlx` in config.

## Privacy

- Audio is processed **entirely on-device** — never sent anywhere
- Audio buffers are discarded immediately after transcription
- No accounts, no telemetry, no analytics
- Ollama (if installed) runs fully offline after the initial model download

## Tech stack

| Component | Technology |
|-----------|-----------|
| Menubar UI | rumps |
| Audio capture | sounddevice |
| Transcription | mlx-whisper (Apple Silicon) |
| Text cleanup | Ollama (local LLM, optional) |
| Hotkey detection | AppKit NSEvent global monitor |
| Text insertion | CoreGraphics CGEventPost |
| Auto-start | macOS LaunchAgent |

## Uninstall

Delete `/Applications/Tacet.app` and `~/.config/tacet/`.

If you installed via the LaunchAgent path:
```bash
bash scripts/uninstall_launchagent.sh
```

## Logs

```bash
tail -f ~/Library/Logs/Tacet/tacet-error.log
```
