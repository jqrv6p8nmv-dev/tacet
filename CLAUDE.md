# Tacet — Claude Session Context

## What This App Does
macOS menubar dictation app: records audio → transcribes via mlx-whisper (Apple Silicon) → optionally polishes via LLM → inserts text at cursor.

**Deployed as a macOS LaunchAgent** (not a py2app bundle — that path was abandoned). Runs directly from the venv via `scripts/install_launchagent.sh`. Starts automatically on login, no Terminal needed.

## Environment
- macOS, Apple Silicon (arm64)
- Python 3.14 (`.venv/`)
- Primary model: `mlx-community/whisper-tiny-mlx` via `mlx_whisper`
- Hotkey: `ctrl+shift+space` (toggle mode)

## Entry Point
`src/main.py` → `src/ui/menubar.py` (rumps menubar app)

## Key Files
| File | Purpose |
|------|---------|
| `scripts/install_launchagent.sh` | Installs LaunchAgent plist, starts app on login |
| `src/audio/capture.py` | Microphone capture (sounddevice, 16kHz mono) |
| `src/transcription/whisper_engine.py` | mlx-whisper engine |
| `src/ui/menubar.py` | rumps menubar UI |
| `src/hotkey/listener.py` | Global hotkey via NSEvent (no pynput/ScriptMonitor) |
| `src/insertion/paste.py` | Text insertion via CGEventPost (no osascript) |
| `src/ui/overlay.py` | Floating status indicator (recording/processing/done) |
| `config/default_config.json` | Default user settings |

## Architecture Decisions (Hard Won)

### Hotkey: NSEvent, not pynput
`pynput.GlobalHotKeys` uses ScriptMonitor which crashes after 1-2 uses on Ventura/Sonoma.
`src/hotkey/listener.py` uses `NSEvent.addGlobalMonitorForEventsMatchingMask_handler_` instead.
Monitor is created on main thread via `NSOperationQueue.mainQueue().addOperationWithBlock_`.
`event.isARepeat()` guard prevents rapid-fire when key is held.

### Paste: CGEventPost, not osascript
osascript fails with error 1002 ("not allowed to send keystrokes") without Accessibility.
`src/insertion/paste.py` uses CoreGraphics `CGEventPost` via ctypes to simulate Cmd+V.
50ms sleep between `pyperclip.copy()` and `CGEventPost` lets clipboard settle.

### Overlay: guard CALayer calls
`content_view.layer()` can return None on some macOS versions before layer is initialized.
`src/ui/overlay.py` guards `setCornerRadius_` and `setBackgroundColor_` with `if layer is not None`.

### No startup dialog
`rumps.alert()` before `app.run()` crashes the app (modal shown before run loop starts).
Accessibility check result is logged only — no dialog shown.

## macOS Permissions Required
Both must be enabled in System Settings → Privacy & Security for the app to work:
1. **Accessibility** → `python3.14` — required for CGEventPost (Cmd+V simulation)
2. **Input Monitoring** → `python3.14` — required for NSEvent global hotkey listener

## LaunchAgent Management
```bash
# Install / reinstall
bash scripts/install_launchagent.sh

# Reload after code changes
launchctl bootout "gui/$(id -u)" ~/Library/LaunchAgents/com.tacet.app.plist 2>/dev/null; true
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.tacet.app.plist

# Watch logs
tail -f ~/Library/Logs/Tacet/tacet-error.log
```

## Git
- Remote: `https://github.com/jqrv6p8nmv-dev/tacet`
- Dev branch: `claude/explain-codebase-mm2f2zzhmujeb9cy-sVI0D`

## Current Status
- [x] LaunchAgent installed, starts on login
- [x] Hotkey `ctrl+shift+space` fires via NSEvent
- [x] Audio recording works
- [x] Transcription works (mlx-whisper-tiny, ~0.1-0.2s)
- [x] Text insertion works (CGEventPost Cmd+V)
- [x] Overlay shows recording/processing/done states
- [ ] **Pending: verify app auto-starts correctly after full machine restart**
