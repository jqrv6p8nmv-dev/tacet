"""
Rule-based text cleanup: filler word removal, basic punctuation, and
self-correction handling.

This runs as a fast local pass before (and as a fallback to) the LLM.
"""
import logging
import re

logger = logging.getLogger(__name__)

# Common English filler words/phrases
FILLER_PATTERNS = [
    r"\b(um+|uh+|er+|ah+)\b",
    r"\blike,?\s+(?=\w)",           # "like I was saying" — remove leading "like"
    r"\byou know,?\s*",
    r"\bi mean,?\s*",
    r"\bso,?\s+(?=\w)",             # leading "so" at phrase start
    r"\bactually,?\s*",
    r"\bbasically,?\s*",
    r"\bright,?\s+(?=\w)",
    r"\bokay so,?\s*",
    r"\balright so,?\s*",
    r"\bkind of,?\s*",
    r"\bsort of,?\s*",
]

# Self-correction patterns: "X, no wait, Y" → "Y"
CORRECTION_PATTERNS = [
    # "meet at 4, no wait 3" → "meet at 3"
    (
        r"(\w[^,]*?),\s*(?:no wait|wait no|actually|i mean|sorry),?\s*(.+?)(?=,|$|\.|!|\?)",
        r"\2",
    ),
    # "...I mean, ..." — already covered by filler removal
]


def remove_fillers(text: str) -> str:
    """Strip common filler words from dictated text."""
    result = text
    for pattern in FILLER_PATTERNS:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    # Collapse multiple spaces
    result = re.sub(r" {2,}", " ", result).strip()
    return result


def handle_self_corrections(text: str) -> str:
    """
    Simplify self-corrections in dictated text.

    Example: "meet at 4, no wait, 3 pm" → "meet at 3 pm"
    """
    result = text
    for pattern, replacement in CORRECTION_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result.strip()


def basic_punctuation(text: str) -> str:
    """
    Apply light punctuation fixes:
    - Ensure sentence ends with punctuation
    - Capitalize first letter
    - Normalize whitespace around punctuation
    """
    if not text:
        return text

    # Normalize whitespace around existing punctuation
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    text = re.sub(r"([.,!?;:])\s*", r"\1 ", text).strip()

    # Capitalize first letter
    text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()

    # Ensure sentence ends with punctuation
    if text and text[-1] not in ".!?":
        text += "."

    return text


def format_numbered_list(text: str) -> str:
    """
    Convert spoken numbered lists to formatted lists.

    Example: "number one do this number two do that" →
             "1. Do this\n2. Do that"
    """
    # Match "number one/two/three..." or "first/second/third..."
    word_to_num = {
        "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
        "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
        "first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5",
    }

    pattern = r"\b(?:number\s+)?(" + "|".join(word_to_num.keys()) + r")\b[,:]?\s*"

    def replace_num(m: re.Match) -> str:
        word = m.group(1).lower()
        num = word_to_num[word]
        return f"\n{num}. "

    result = re.sub(pattern, replace_num, text, flags=re.IGNORECASE)
    return result.strip()


def quick_clean(text: str, remove_fillers_: bool = True, handle_corrections: bool = True) -> str:
    """
    Run the full rule-based cleanup pipeline.
    This is also the fallback when no LLM is available.
    """
    if not text:
        return text

    logger.debug(f"Cleanup input: {text!r}")

    if handle_corrections:
        text = handle_self_corrections(text)
    if remove_fillers_:
        text = remove_fillers(text)
    text = basic_punctuation(text)

    logger.debug(f"Cleanup output: {text!r}")
    return text
