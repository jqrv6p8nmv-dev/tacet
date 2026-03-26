# WhisperMe — Claude Session Context

## What This App Does
macOS menubar dictation app: records audio → transcribes via mlx-whisper (Apple Silicon) → optionally polishes via LLM → inserts text at cursor.

Packaged as a standalone `.app` bundle using **py2app**.

## Environment
- macOS, Apple Silicon (arm64)
- Python 3.14 (`.venv/`)
- py2app 0.28.10+
- Primary model: `mlx-community/whisper-small-mlx` via `mlx_whisper`

## Entry Point
`run.py` → `src/main.py` → `src/ui/menubar.py` (rumps menubar app)

## Build
```bash
bash scripts/build_app.sh
# Output: dist/WhisperMe.app
```

## Key Files
| File | Purpose |
|------|---------|
| `setup.py` | py2app build config |
| `scripts/build_app.sh` | Build orchestration + post-build mlx copy |
| `src/audio/capture.py` | Microphone capture (sounddevice, 16kHz mono) |
| `src/transcription/whisper_engine.py` | mlx-whisper engine with openai-whisper fallback |
| `src/ui/menubar.py` | rumps menubar UI |
| `src/hotkey/listener.py` | Global hotkey via pynput |
| `src/insertion/paste.py` | Text insertion via Accessibility API / pyperclip |
| `config/default_config.json` | Default user settings |

## Known py2app Quirks (Hard Won)

### 1. Recursion limit
`sys.setrecursionlimit(10000)` at top of `setup.py` — modulegraph's AST visitor blows the default limit on large deps (mlx, numpy).

### 2. libportaudio.dylib can't load from inside a zip
`dlopen()` cannot load dylibs from `python314.zip`. Fix:
- `setup.py`: `"frameworks": _find_portaudio()` — copies dylib to `Contents/Frameworks/`
- `src/audio/capture.py`: patches `ctypes.util.find_library` before sounddevice imports

### 3. mlx / mlx_whisper — imp_find_module crash
py2app's `collect_packagedirs` uses `imp.find_module` which crashes on mlx's non-standard layout.
**Do NOT add `mlx` or `mlx_whisper` to the `packages` list in setup.py.**
Instead, `build_app.sh` copies them manually from the venv into the bundle after py2app finishes.

### 4. PyObjC bridges (AppKit, Foundation, Cocoa, objc)
py2app handles these internally. **Do NOT add them to `packages`.**

### 5. email module
`urllib3` → `requests` depends on `email`. Do NOT put `email` in `excludes`.

### 6. openai-whisper not installed
Only `mlx_whisper` is in the venv. The fallback in `whisper_engine.py` will always fail if mlx_whisper isn't in the bundle.

## Git
- Remote: `https://github.com/jqrv6p8nmv-dev/whspr-me`
- Dev branch: `claude/explain-codebase-mm2f2zzhmujeb9cy-sVI0D`

## Current Status
- [x] py2app build completes without errors
- [x] libportaudio.dylib loads correctly from Contents/Frameworks/
- [x] App launches, menubar icon appears
- [x] Audio recording works
- [ ] Transcription: mlx_whisper not in bundle → **post-build copy fix in build_app.sh**
