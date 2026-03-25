"""
Setup script for WhisperMe.
Used by py2app to create a standalone .app bundle.

Build the app:
    bash scripts/build_app.sh
"""
from setuptools import setup, find_packages

# ── py2app entry point ───────────────────────────────────────────────────────
# Must be a root-level script (not inside a package) to avoid relative-import
# issues. See run.py for freeze_support() and the actual launch logic.
APP = ["run.py"]

# ── Data files bundled into Contents/Resources/ ──────────────────────────────
DATA_FILES = [
    # Placed at Contents/Resources/config/default_config.json
    ("config", ["config/default_config.json"]),
]

# ── py2app options ────────────────────────────────────────────────────────────
OPTIONS = {
    # No argv emulation — rumps/AppKit handle the event loop directly.
    "argv_emulation": False,

    # Info.plist overrides
    "plist": {
        "LSUIElement": True,            # Menubar-only app (no Dock icon)
        "CFBundleName": "WhisperMe",
        "CFBundleDisplayName": "WhisperMe",
        "CFBundleIdentifier": "com.whisperme.app",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        # Permission usage strings shown in System Settings
        "NSMicrophoneUsageDescription": (
            "WhisperMe needs microphone access to capture your speech."
        ),
        "NSAccessibilityUsageDescription": (
            "WhisperMe needs Accessibility access to insert text and listen for hotkeys."
        ),
    },

    # Force these top-level packages to be included as directory trees rather
    # than being frozen into the zip. Needed for packages that do runtime
    # resource loading or have native extensions.
    "packages": [
        "src",
        "rumps",
        "sounddevice",
        "numpy",
        "pynput",
        "pyperclip",
        "requests",
        "mlx",
        "mlx_whisper",
        "AppKit",
        "Foundation",
        "Cocoa",
        "objc",
        "certifi",      # requests TLS certs
        "charset_normalizer",
        "urllib3",
        "idna",
    ],

    # Individual modules that py2app's static analysis might miss
    "includes": [
        "numpy.core",
        "ctypes",
        "ctypes.util",
        "threading",
        "multiprocessing",
        "multiprocessing.resource_tracker",
        "multiprocessing.managers",
        "logging",
        "logging.handlers",
        "signal",
        "json",
        "pathlib",
        "queue",
        "re",
        "time",
        "abc",
    ],

    # Packages that are definitely not needed — trimming reduces bundle size
    "excludes": [
        "tkinter",
        "_tkinter",
        "matplotlib",
        "scipy",
        "PIL",
        "test",
        "unittest",
        "distutils",
        "lib2to3",
        "email",
        "http.server",
        "xmlrpc",
        "ftplib",
        "imaplib",
        "poplib",
        "smtplib",
        "telnetlib",
        "turtle",
        "curses",
    ],
}

setup(
    app=APP,
    name="WhisperMe",
    version="0.1.0",
    description="Local-first voice dictation for macOS",
    author="WhisperMe contributors",
    license="MIT",
    packages=find_packages(),
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
    install_requires=[
        "mlx-whisper>=0.4.0",
        "sounddevice>=0.4.6",
        "numpy>=1.24.0",
        "rumps>=0.4.0",
        "pynput>=1.7.6",
        "pyperclip>=1.8.2",
        "requests>=2.31.0",
        "pyobjc-core>=10.0",
        "pyobjc-framework-Cocoa>=10.0",
    ],
)
