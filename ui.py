"""Interactive prompts and naming helpers."""
import re
from pathlib import Path

import questionary

ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
PART_SUFFIX = re.compile(r"[._\-\s]*part\s*0*\d+.*$", re.IGNORECASE)


def sanitize(name: str, max_len: int = 100) -> str:
    """Strip Windows-illegal characters and trailing dots/spaces."""
    cleaned = ILLEGAL_CHARS.sub("", name).strip().rstrip(". ")
    return cleaned[:max_len].rstrip(". ") or "download"


def resource_folder_name(part_names: list[str]) -> str:
    """Derive 'Resource_Name' from 'Resource_Name_part001.rar'."""
    for name in part_names:
        stem = PART_SUFFIX.sub("", name)
        if stem and stem != name:
            return sanitize(stem)
    # No 'partNNN' pattern found: fall back to the first filename without extension.
    return sanitize(Path(part_names[0]).stem) if part_names else "download"


def choose_parts(parts):
    """Checkbox list, all pre-ticked. Returns the chosen parts (possibly empty), or None if cancelled."""
    choices = [questionary.Choice(title=p.name, value=p, checked=True) for p in parts]
    return questionary.checkbox(
        "Select parts to download (space = toggle, a = toggle all, enter = confirm):",
        choices=choices,
    ).ask()


def ask_save_dir(default_dir: str):
    """Prompt for the save folder with the config default pre-filled."""
    answer = questionary.path("Save to:", default=default_dir, only_directories=True).ask()
    return Path(answer.strip().strip('"')) if answer else None