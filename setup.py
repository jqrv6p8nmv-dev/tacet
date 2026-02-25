"""
Setup script for WhisperMe.
Also used by py2app to create a standalone .app bundle.
"""
from setuptools import setup, find_packages

APP = ["src/main.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "LSUIElement": True,  # Run as background app (no Dock icon)
        "CFBundleName": "WhisperMe",
        "CFBundleDisplayName": "WhisperMe",
        "CFBundleIdentifier": "com.whisperme.app",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "NSMicrophoneUsageDescription": "WhisperMe needs microphone access to capture your speech.",
        "NSAccessibilityUsageDescription": "WhisperMe needs Accessibility access to insert text and listen for hotkeys.",
    },
    "packages": ["rumps", "sounddevice", "numpy", "pynput", "pyperclip", "requests"],
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
