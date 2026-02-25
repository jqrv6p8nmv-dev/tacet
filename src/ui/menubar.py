"""
macOS menubar application using rumps.

Provides the system tray icon, menu items, and wires together all
FlowVoice components into a single cohesive app.
"""
import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

import rumps

logger = logging.getLogger(__name__)

# Menubar icon states
ICON_IDLE = "🎙"
ICON_RECORDING = "🔴"
ICON_PROCESSING = "⏳"

CONFIG_DIR = Path("~/.config/flowvoice").expanduser()
CONFIG_PATH = CONFIG_DIR / "config.json"
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "default_config.json"


def _load_config() -> dict:
    """Load user config, falling back to defaults."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning(f"Failed to load config from {CONFIG_PATH} — using defaults")

    if DEFAULT_CONFIG_PATH.exists():
        with open(DEFAULT_CONFIG_PATH) as f:
            return json.load(f)

    return {}


def _save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


class FlowVoiceApp(rumps.App):
    """
    Main FlowVoice menubar application.

    Integrates audio capture, transcription, post-processing, and text
    insertion into a single toggle-based workflow triggered by hotkey or
    menubar click.
    """

    def __init__(self):
        super().__init__(
            name="FlowVoice",
            title=ICON_IDLE,
            quit_button="Quit FlowVoice",
        )
        self.config = _load_config()
        self._recording = False
        self._processing = False

        # Lazy-initialized components (initialized in setup())
        self._capture = None
        self._whisper = None
        self._pipeline = None
        self._overlay = None
        self._hotkey_listener = None

        self._build_menu()

    def _build_menu(self) -> None:
        """Build the menubar dropdown menu."""
        self.menu = [
            rumps.MenuItem("Start Recording", callback=self._toggle_recording),
            rumps.separator,
            rumps.MenuItem(
                "AI Cleanup: ON" if self.config.get("processing", {}).get("llm_cleanup", True)
                else "AI Cleanup: OFF",
                callback=self._toggle_llm_cleanup,
            ),
            rumps.separator,
            rumps.MenuItem("About FlowVoice", callback=self._show_about),
        ]

    # ------------------------------------------------------------------
    # Public API called from main.py after init
    # ------------------------------------------------------------------

    def setup(
        self,
        capture,
        whisper_engine,
        pipeline,
        overlay,
        hotkey_listener,
    ) -> None:
        """Wire up all components. Called before app.run()."""
        self._capture = capture
        self._whisper = whisper_engine
        self._pipeline = pipeline
        self._overlay = overlay
        self._hotkey_listener = hotkey_listener

    # ------------------------------------------------------------------
    # Recording workflow
    # ------------------------------------------------------------------

    def toggle_recording(self) -> None:
        """Public method — called by hotkey listener to toggle recording."""
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _toggle_recording(self, sender) -> None:
        """Menu item callback."""
        self.toggle_recording()

    def _start_recording(self) -> None:
        if self._processing:
            logger.debug("Cannot start recording while processing")
            return
        if self._recording:
            return

        logger.info("Starting recording…")
        self._recording = True
        self.title = ICON_RECORDING
        self.menu["Start Recording"].title = "Stop Recording"

        if self._overlay:
            self._overlay.show_recording()

        if self._capture:
            self._capture.on_auto_stop = self._on_auto_stop
            self._capture.start()

    def _stop_recording(self) -> None:
        if not self._recording:
            return

        logger.info("Stopping recording…")
        self._recording = False
        self.title = ICON_PROCESSING
        self.menu["Stop Recording"].title = "Start Recording"

        if self._overlay:
            self._overlay.show_processing()

        # Process audio on a background thread to keep the UI responsive
        t = threading.Thread(target=self._process_audio, daemon=True)
        t.start()

    def _on_auto_stop(self) -> None:
        """Called by AudioCapture when silence is detected."""
        logger.debug("Auto-stop triggered")
        self._stop_recording()

    def _process_audio(self) -> None:
        """Background thread: stop capture → transcribe → clean → insert."""
        try:
            audio = self._capture.stop() if self._capture else None
            if audio is None or len(audio) == 0:
                logger.warning("No audio captured")
                self._finish(success=False)
                return

            # Transcribe
            text = self._whisper.transcribe(audio) if self._whisper else ""
            if not text:
                logger.warning("Transcription returned empty result")
                self._finish(success=False)
                return

            logger.info(f"Transcribed: {text!r}")

            # Post-process
            if self._pipeline:
                text = self._pipeline.process(text)

            # Insert
            from ..insertion.paste import insert_text
            restore = self.config.get("clipboard_restore", True)
            success = insert_text(text, restore_clipboard=restore)
            self._finish(success=success)

        except Exception:
            logger.exception("Error during audio processing")
            self._finish(success=False)

    def _finish(self, success: bool) -> None:
        self._processing = False
        self.title = ICON_IDLE

        if self._overlay:
            if success:
                self._overlay.show_done()
            else:
                self._overlay.show_error()

    # ------------------------------------------------------------------
    # Menu callbacks
    # ------------------------------------------------------------------

    def _toggle_llm_cleanup(self, sender) -> None:
        proc = self.config.setdefault("processing", {})
        current = proc.get("llm_cleanup", True)
        proc["llm_cleanup"] = not current
        sender.title = f"AI Cleanup: {'ON' if proc['llm_cleanup'] else 'OFF'}"
        if self._pipeline:
            self._pipeline.llm_cleanup = proc["llm_cleanup"]
        _save_config(self.config)
        logger.info(f"LLM cleanup toggled: {proc['llm_cleanup']}")

    def _show_about(self, _sender) -> None:
        rumps.alert(
            title="FlowVoice",
            message=(
                "Free, local-first voice dictation for macOS.\n\n"
                "Press Ctrl+Shift+Space to toggle recording.\n\n"
                "All processing happens on-device — no cloud, no subscription."
            ),
        )
