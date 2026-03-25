"""
macOS menubar application using rumps.

Provides the system tray icon, menu items, and wires together all
WhisperMe components into a single cohesive app.
"""
import json
import logging
import threading
from pathlib import Path
from typing import Optional

import os
import sys

import rumps

logger = logging.getLogger(__name__)

# Menubar icon states
ICON_IDLE = "🎙"
ICON_RECORDING = "🔴"
ICON_PROCESSING = "⏳"

CONFIG_DIR = Path("~/.config/whisperme").expanduser()
CONFIG_PATH = CONFIG_DIR / "config.json"

# Same frozen-app path logic as config.py — __file__ is unusable inside a zip.
if getattr(sys, "frozen", False):
    _resource_dir = Path(os.environ.get("RESOURCEPATH", ""))
    DEFAULT_CONFIG_PATH = _resource_dir / "config" / "default_config.json"
else:
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


class WhisperMeApp(rumps.App):
    """
    Main WhisperMe menubar application.

    Integrates audio capture, transcription, post-processing, and text
    insertion into a workflow triggered by the Fn key (hold-to-record)
    or a configurable hotkey combo.
    """

    def __init__(self):
        super().__init__(
            name="WhisperMe",
            title=ICON_IDLE,
            quit_button="Quit WhisperMe",
        )
        self.config = _load_config()
        self._recording = False
        self._processing = False

        # Components wired in via setup()
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
            rumps.MenuItem("About WhisperMe", callback=self._show_about),
        ]

    # ------------------------------------------------------------------
    # Public API called from main.py
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
    # Recording workflow — public entry points
    # ------------------------------------------------------------------

    def toggle_recording(self) -> None:
        """Toggle recording on/off (used by combo hotkeys)."""
        if self._recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self) -> None:
        """Begin recording (called on Fn press or menu click)."""
        try:
            import AppKit
            if not AppKit.NSThread.isMainThread():
                AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(self.start_recording)
                return
        except ImportError:
            pass

        try:
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
        except Exception:
            logger.exception("Error in start_recording")

    def stop_recording(self) -> None:
        """Stop recording and kick off processing (called on Fn release or menu click)."""
        try:
            import AppKit
            if not AppKit.NSThread.isMainThread():
                AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(self.stop_recording)
                return
        except ImportError:
            pass

        try:
            if not self._recording:
                return

            logger.info("Stopping recording…")
            self._recording = False
            self._processing = True
            self.title = ICON_PROCESSING
            self.menu["Start Recording"].title = "Start Recording"

            if self._overlay:
                self._overlay.show_processing()

            t = threading.Thread(target=self._process_audio, daemon=True)
            t.start()
        except Exception:
            logger.exception("Error in stop_recording")

    # ------------------------------------------------------------------
    # Internal callbacks
    # ------------------------------------------------------------------

    def _toggle_recording(self, sender) -> None:
        """Menu item callback."""
        self.toggle_recording()

    def _on_auto_stop(self) -> None:
        """Called by AudioCapture when silence is detected."""
        logger.debug("Auto-stop triggered")
        self.stop_recording()

    def _process_audio(self) -> None:
        """Background thread: stop capture → transcribe → clean → insert."""
        import time
        try:
            t0 = time.perf_counter()
            audio = self._capture.stop() if self._capture else None
            if audio is None or len(audio) == 0:
                logger.warning("No audio captured")
                self._finish(success=False)
                return
            logger.info(f"[timing] capture.stop: {time.perf_counter()-t0:.2f}s")

            t1 = time.perf_counter()
            text = self._whisper.transcribe(audio) if self._whisper else ""
            logger.info(f"[timing] transcribe: {time.perf_counter()-t1:.2f}s")
            if not text:
                logger.warning("Transcription returned empty result")
                self._finish(success=False)
                return

            logger.info(f"Transcribed: {text!r}")

            t2 = time.perf_counter()
            if self._pipeline:
                text = self._pipeline.process(text)
            logger.info(f"[timing] pipeline: {time.perf_counter()-t2:.2f}s")

            t3 = time.perf_counter()
            from ..insertion.paste import insert_text
            restore = self.config.get("clipboard_restore", True)
            success = insert_text(text, restore_clipboard=restore)
            logger.info(f"[timing] insert_text: {time.perf_counter()-t3:.2f}s")

            logger.info(f"[timing] total: {time.perf_counter()-t0:.2f}s")
            self._finish(success=success)

        except Exception:
            logger.exception("Error during audio processing")
            self._finish(success=False)

    def _finish(self, success: bool) -> None:
        """Called from background thread — dispatch AppKit work to main thread."""
        self._processing = False
        try:
            import AppKit
            def _on_main():
                try:
                    self.title = ICON_IDLE
                except Exception:
                    logger.debug("Failed to reset title", exc_info=True)
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_on_main)
        except ImportError:
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
            title="WhisperMe",
            message=(
                "Free, local-first voice dictation for macOS.\n\n"
                "Hold the Fn key to record. Release to transcribe.\n\n"
                "All processing happens on-device — no cloud, no subscription."
            ),
        )
