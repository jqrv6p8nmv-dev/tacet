"""
Context-aware formatting: detect the active application and adjust
the text style and formatting accordingly.

Uses NSWorkspace to get the frontmost app's bundle ID on macOS.
"""
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# App bundle ID → formatting profile name
APP_PROFILES: dict[str, str] = {
    # Email clients → formal tone
    "com.apple.mail": "formal",
    "com.microsoft.Outlook": "formal",
    "com.google.Chrome": "neutral",   # Could be Gmail — heuristic
    # Messaging / chat → casual
    "com.tinyspeck.slackmacgap": "casual",
    "com.hnc.Discord": "casual",
    "com.apple.MobileSMS": "casual",
    "ru.keepcoder.Telegram": "casual",
    # Code editors → technical (preserve variable names, etc.)
    "com.microsoft.VSCode": "technical",
    "com.jetbrains.intellij": "technical",
    "com.apple.Xcode": "technical",
    "com.sublimetext.4": "technical",
    # Notes / writing apps → neutral
    "com.apple.Notes": "neutral",
    "md.obsidian": "neutral",
    "com.notion.id": "neutral",
}

PROFILE_HINTS: dict[str, str] = {
    "formal": "This is for a formal email or document. Use professional tone and complete sentences.",
    "casual": "This is for a chat message. Keep it casual and conversational.",
    "technical": "This is for a code editor or technical document. Preserve technical terms exactly.",
    "neutral": "",
}


def get_active_app_bundle_id() -> Optional[str]:
    """
    Return the bundle ID of the currently frontmost application, or None on failure.

    Uses osascript to query NSWorkspace via AppleScript.
    """
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get bundle identifier of '
                "(first process whose frontmost is true)",
            ],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if result.returncode == 0:
            bundle_id = result.stdout.strip()
            logger.debug(f"Active app: {bundle_id}")
            return bundle_id
    except (subprocess.TimeoutExpired, OSError):
        logger.debug("Could not determine active app bundle ID")
    return None


def get_active_app_name() -> Optional[str]:
    """Return the display name of the frontmost app."""
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of '
                "(first process whose frontmost is true)",
            ],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def get_formatting_profile(bundle_id: Optional[str] = None) -> str:
    """
    Return the formatting profile name for the given bundle ID.
    Defaults to "neutral" for unknown apps.
    """
    if not bundle_id:
        return "neutral"
    return APP_PROFILES.get(bundle_id, "neutral")


def get_llm_context_hint(bundle_id: Optional[str] = None, app_name: Optional[str] = None) -> str:
    """
    Return a context hint string for the LLM prompt based on the active app.
    Returns an empty string for neutral contexts.
    """
    profile = get_formatting_profile(bundle_id)
    hint = PROFILE_HINTS.get(profile, "")

    # Append app name for additional context
    if app_name and hint:
        hint = f"Context: {hint} (App: {app_name})"
    elif app_name:
        hint = f"App: {app_name}"

    return hint
