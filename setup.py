"""
Setup script for WhisperMe — used exclusively by py2app to build the .app bundle.

Build command:
    bash scripts/build_app.sh
"""
import sys

# modulegraph's recursive AST visitor exceeds the default limit when scanning
# large dependency trees (mlx, numpy, etc.) on Python 3.14+.
sys.setrecursionlimit(10000)

from setuptools import setup

APP = ["run.py"]

DATA_FILES = [
    # Bundled at Contents/Resources/config/default_config.json
    ("config", ["config/default_config.json"]),
]

OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "LSUIElement": True,
        "CFBundleName": "WhisperMe",
        "CFBundleDisplayName": "WhisperMe",
        "CFBundleIdentifier": "com.whisperme.app",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "NSMicrophoneUsageDescription": "WhisperMe needs microphone access to capture your speech.",
        "NSAccessibilityUsageDescription": "WhisperMe needs Accessibility access to insert text and listen for hotkeys.",
    },
    "packages": [
        "src",
        "rumps",
        "sounddevice",
        "numpy",
        "pynput",
        "pyperclip",
        "requests",
        # mlx / mlx_whisper: Apple's MLX framework has a non-standard
        # package layout that imp_find_module can't resolve; modulegraph
        # already discovers them via static analysis of the import graph.
        # AppKit / Foundation / Cocoa / objc: PyObjC system bridges are
        # handled internally by py2app and must NOT be listed here.
        "certifi",
        "charset_normalizer",
        "urllib3",
        "idna",
    ],
    "includes": [
        "numpy.core",
        "ctypes",
        "ctypes.util",
        "threading",
        "multiprocessing",
        "multiprocessing.resource_tracker",
        "logging",
        "logging.handlers",
        "signal",
        "json",
        "pathlib",
        "queue",
    ],
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
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
)
