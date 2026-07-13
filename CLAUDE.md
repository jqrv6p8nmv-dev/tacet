# Tacet — Claude Session Context

## What This App Does
macOS menubar dictation app: records audio → transcribes via mlx-whisper (Apple Silicon) → optionally polishes via local LLM (Ollama) → pastes text at cursor.

**Deployed as a self-contained app bundle**: `scripts/build_dmg.sh` builds `dist/Tacet.app` (ObjC launcher + bundled venv + bundled whisper-small-mlx model, ~910MB DMG), installed to `/Applications`. Login startup via SMAppService ("Launch at Login" in the menubar), NOT a LaunchAgent — the LaunchAgent and py2app paths were abandoned and their scripts removed.

## Environment
- macOS (Sequoia), Apple Silicon (arm64)
- Python 3.14 (`.venv/` for dev; a copy is bundled into the app)
- Model: `mlx-community/whisper-small-mlx`, bundled in the app at `Contents/Resources/models/whisper-small-mlx` (falls back to HuggingFace download if missing)
- Hotkey: `ctrl+shift+space` (toggle mode)
- User config: `~/.config/tacet/config.json` (defaults in `config/default_config.json`)

## Architecture: ObjC Launcher + Python Child

`Contents/MacOS/tacet` (compiled from `launcher/tacet_launcher.m`) forks a Python child (`src/main.py`, rumps menubar app) and talks to it over two pipes:

- **TACET_PASTE_FD** — Python writes `'P'` → launcher calls `CGEventPost(Cmd+V)`
- **TACET_HOTKEY_FD** — launcher writes event bytes to Python:
  - `'H'` hotkey pressed → toggle recording
  - `'A'` Accessibility granted (at startup if already trusted, or from the ax-poll thread when the grant lands mid-run)
  - `'N'` paste refused — launcher not AX-trusted; text stays on the clipboard

Key ordering constraint: **fork BEFORE `[NSApplication sharedApplication]`** — the child must not inherit the WindowServer connection. Carbon hotkey needs `[NSApp run]` on the launcher's main thread.

## Key Files
| File | Purpose |
|------|---------|
| `launcher/tacet_launcher.m` | ObjC launcher: fork, Carbon hotkey, CGEventPost paste, AX poll |
| `scripts/build_dmg.sh` | Builds, signs, and packages Tacet.app + DMG |
| `scripts/launch.sh` | Dev-mode launch from the repo venv (no launcher) |
| `src/main.py` | Python entry point, wires everything together |
| `src/ui/menubar.py` | rumps menubar UI, AX-grant UX, SMAppService login item |
| `src/hotkey/listener.py` | Reads launcher pipe events; NSEvent fallback in dev mode |
| `src/insertion/paste.py` | Paste gating on AX state; clipboard handling |
| `src/audio/capture.py` | Microphone capture (sounddevice, 16kHz mono) |
| `src/transcription/whisper_engine.py` | mlx-whisper engine, bundled-model resolution |
| `src/processing/` | Filler removal, punctuation, optional Ollama polish (`llama3.2:3b`) |
| `src/ui/overlay.py` | Floating status indicator (recording/processing/done) |

## Architecture Decisions (Hard Won)

### Hotkey: Carbon RegisterEventHotKey in the launcher
Needs NO TCC permission (no Accessibility, no Input Monitoring). `pynput.GlobalHotKeys` (ScriptMonitor) crashes after 1-2 uses; NSEvent global monitors need Input Monitoring. Both are avoided in bundle mode. `src/hotkey/listener.py` keeps an NSEvent path only as the standalone/dev fallback.

### Paste: CGEventPost from the launcher, gated on Accessibility
macOS **silently drops** CGEventPost from untrusted processes. The launcher checks `AXIsProcessTrusted()` before posting; if untrusted it sends `'N'` instead and Python leaves the dictated text on the clipboard (skips clipboard restore) so the user can Cmd+V manually. The menubar shows a "Grant Accessibility…" item and a rate-limited notification pointing at System Settings.

### Accessibility can be granted mid-run — no relaunch
tccd applies grants to live processes. The launcher's ax-poll thread watches `AXIsProcessTrusted()` and sends `'A'` when it flips; Python then un-gates pasting (`src/insertion/paste.py` `_AX_TRUSTED` event) and removes the grant menu item. Do NOT reintroduce "grant before launch / relaunch after grant" instructions.

### Signing: stable identity or TCC grants break on every rebuild
TCC keys grants to code identity. Ad-hoc signing (`--sign -`) yields a new CDHash per build → "toggle is ON but paste doesn't work". `build_dmg.sh` resolves identity: `$DEVELOPER_ID` → self-signed **"Tacet Dev Signing"** keychain cert (exists on this machine) → ad-hoc with a loud warning. No `--options runtime` with the self-signed cert (hardened runtime would reject the venv's .so files).

### Overlay: guard CALayer calls
`content_view.layer()` can return None before the layer initializes. `src/ui/overlay.py` guards `setCornerRadius_`/`setBackgroundColor_` with `if layer is not None`.

### No startup dialog
`rumps.alert()` before `app.run()` crashes the app (modal before the run loop starts).

## macOS Permissions (bundle mode)
1. **Accessibility** → `Tacet.app` — for the launcher's CGEventPost. Can be granted any time; the app handles it gracefully.
2. **Microphone** — prompted on first recording.
3. Input Monitoring is **not** needed (Carbon hotkey).

Dev mode (running from the venv without the launcher) instead needs Accessibility + Input Monitoring on `python3.14`.

## Build / Run / Debug
```bash
# Build app + DMG (signs with "Tacet Dev Signing" if present)
bash scripts/build_dmg.sh          # → dist/Tacet.app, dist/Tacet-<ver>.dmg

# Install: copy dist/Tacet.app to /Applications, launch it

# Dev mode (no launcher; NSEvent hotkey + python CGEventPost)
bash scripts/launch.sh

# Logs
tail -f ~/Library/Logs/Tacet/launcher.log      # launcher (hotkey, paste, AX)
tail -f ~/Library/Logs/Tacet/tacet-error.log   # python stderr

# Tests
.venv/bin/python -m pytest tests/
```

## Git
- Remote: `https://github.com/jqrv6p8nmv-dev/tacet`
- Work is committed directly to `main` (the old `claude/explain-codebase-…` branch is historical)

## Current Status (2026-07-13)
- [x] App bundle builds, signs with stable identity, installs from DMG
- [x] Carbon hotkey, recording, transcription (bundled whisper-small-mlx), paste — all verified
- [x] Mid-run Accessibility grant flow verified live (grant landed at 08:24, pastes worked immediately)
- [x] Launch at Login via SMAppService
- [ ] Pending: verify auto-start + full flow after a machine restart
