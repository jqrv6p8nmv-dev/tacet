"""
Context-aware formatting: detect the active application and adjust
the text style and formatting accordingly.

Uses NSWorkspace to get the frontmost app's bundle ID on macOS.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# App bundle ID -> formatting profile name
APP_PROFILES: dict[str, str] = {
    # Email clients -> formal tone
    "com.apple.mail": "formal",
    "com.microsoft.Outlook": "formal",
    "com.google.Chrome": "neutral",   # Could be Gmail -- heuristic
    # Messaging / chat -> casual
    "com.tinyspeck.slackmacgap": "casual",
    "com.hnc.Discord": "casual",
    "com.apple.MobileSMS": "casual",
    "ru.keepcoder.Telegram": "casual",
    # Code editors -> technical (preserve variable names, etc.)
    "com.microsoft.VSCode": "technical",
    "com.jetbrains.intellij": "technical",
    "com.apple.Xcode": "technical",
    "com.sublimetext.4": "technical",
    # Notes / writing apps -> neutral
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


def _get_frontmost_app():
    """Return the frontmost NSRunningApplication via NSWorkspace, or None."""
    try:
        from AppKit import NSWorkspace  # type: ignore
        return NSWorkspace.sharedWorkspace().frontmostApplication()
    except Exception:
        return None


def get_active_app_bundle_id() -> Optional[str]:
    """
    Return the bundle ID of the currently frontmost application, or None on failure.

    Uses NSWorkspace directly (no osascript / ScriptMonitor required).
    """
    app = _get_frontmost_app()
    if app is None:
        return None
    bundle_id = app.bundleIdentifier()
    if bundle_id:
        logger.debug(f"Active app: {bundle_id}")
    return bundle_id or None


def get_active_app_name() -> Optional[str]:
    """Return the display name of the frontmost app."""
    app = _get_frontmost_app()
    if app is None:
        return None
    return app.localizedName() or None


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
