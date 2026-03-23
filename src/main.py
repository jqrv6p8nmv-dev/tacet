"""
WhisperMe — Entry point.

Sets up logging, loads config, instantiates all components, and starts
the rumps menubar application.
"""
import logging
import sys
from pathlib import Path


def _setup_logging(level: str = "info") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    # ------------------------------------------------------------------ #
    # 1. Load config
    # ------------------------------------------------------------------ #
    from .config import load_config, get as cfg_get
    config = load_config()

    _setup_logging(cfg_get(config, "log_level", default="info"))
    logger = logging.getLogger(__name__)
    logger.info("WhisperMe starting…")

    # ------------------------------------------------------------------ #
    # 2. Instantiate components
    # ------------------------------------------------------------------ #

    # Audio capture
    from .audio.capture import AudioCapture
    audio_cfg = config.get("audio", {})
    capture = AudioCapture(
        sample_rate=audio_cfg.get("sample_rate", 16000),
        silence_threshold=audio_cfg.get("silence_threshold", 0.01),
        silence_duration=audio_cfg.get("silence_duration", 1.5),
        max_duration=audio_cfg.get("max_duration", 60.0),
    )

    # Whisper transcription engine
    from .transcription.whisper_engine import WhisperEngine
    tx_cfg = config.get("transcription", {})
    whisper_engine = WhisperEngine(
        model=tx_cfg.get("model", "mlx-community/whisper-small-mlx"),
        language=tx_cfg.get("language", "en"),
        backend=tx_cfg.get("backend", "mlx-whisper"),
    )

    # Post-processing pipeline
    from .processing.dictionary import CustomDictionary
    from .processing.pipeline import ProcessingPipeline
    proc_cfg = config.get("processing", {})
    dict_path_str = config.get(
        "custom_dictionary_path", "~/.config/whisperme/custom_dictionary.json"
    )
    dictionary = CustomDictionary(path=Path(dict_path_str).expanduser())
    pipeline = ProcessingPipeline(
        remove_fillers=proc_cfg.get("remove_fillers", True),
        handle_corrections=proc_cfg.get("handle_self_corrections", True),
        llm_cleanup=proc_cfg.get("llm_cleanup", True),
        ollama_model=proc_cfg.get("ollama_model", "llama3.2:3b"),
        ollama_url=proc_cfg.get("ollama_url", "http://localhost:11434"),
        custom_dictionary=dictionary,
    )

    # Floating overlay
    from .ui.overlay import StatusOverlay
    ui_cfg = config.get("ui", {})
    overlay = StatusOverlay(position=ui_cfg.get("overlay_position", "bottom-center"))

    # Menubar app
    from .ui.menubar import WhisperMeApp
    app = WhisperMeApp()
    app.config = config

    # Hotkey listener — Fn key (hold-to-record) or combo (toggle)
    from .hotkey.listener import create_listener
    hotkey_str = cfg_get(config, "hotkey", "record", default="fn")
    listener = create_listener(
        hotkey=hotkey_str,
        on_activate=app.toggle_recording,   # used by combo/toggle mode
        on_start=app.start_recording,        # used by Fn hold mode
        on_stop=app.stop_recording,          # used by Fn hold mode
    )

    # Wire everything together
    app.setup(
        capture=capture,
        whisper_engine=whisper_engine,
        pipeline=pipeline,
        overlay=overlay,
        hotkey_listener=listener,
    )

    # ------------------------------------------------------------------ #
    # 3. Warm up Whisper in background so first transcription is instant
    # ------------------------------------------------------------------ #
    import threading
    threading.Thread(target=whisper_engine.warm_up, daemon=True).start()

    # ------------------------------------------------------------------ #
    # 4. Check permissions (non-blocking warning)
    # ------------------------------------------------------------------ #
    from .insertion.paste import check_accessibility_permission
    if not check_accessibility_permission():
        import rumps
        rumps.alert(
            title="Accessibility Permission Required",
            message=(
                "WhisperMe needs Accessibility access to insert text.\n\n"
                "Go to: System Settings → Privacy & Security → Accessibility\n"
                "and enable WhisperMe (or Terminal if running from the command line)."
            ),
        )

    # ------------------------------------------------------------------ #
    # 5. Install SIGINT handler for clean Ctrl+C exit
    # ------------------------------------------------------------------ #
    import signal
    import rumps as _rumps

    def _sigint_handler(sig, frame):
        logger.info("Received SIGINT — shutting down…")
        _rumps.quit_application()

    signal.signal(signal.SIGINT, _sigint_handler)

    # ------------------------------------------------------------------ #
    # 6. Start listener and run the app
    # ------------------------------------------------------------------ #
    listener.start()
    logger.info(f"Hotkey registered: {listener.hotkey_str}")
    logger.info(f"WhisperMe ready. Hotkey: {listener.hotkey_str}")

    try:
        app.run()
    finally:
        listener.stop()
        logger.info("WhisperMe exited.")


if __name__ == "__main__":
    if __package__ is None:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from src.main import main
    main()
