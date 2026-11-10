"""Small shared helpers."""
import re

ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def sanitize(name: str, max_len: int = 100) -> str:
    """Make a string safe as a Windows file or folder name."""
    cleaned = ILLEGAL_CHARS.sub("", name).strip().rstrip(". ")
    cleaned = cleaned[:max_len].rstrip(". ")
    if cleaned.split(".")[0].upper() in RESERVED:
        cleaned = "_" + cleaned
    return cleaned or "download"