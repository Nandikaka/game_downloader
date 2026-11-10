"""Interactive prompts and naming helpers."""
import re
from pathlib import Path

import questionary

from utils import sanitize

PART_SUFFIX = re.compile(r"[._\-\s]*part\s*0*\d+.*$", re.IGNORECASE)


def resource_folder_name(part_names: list[str]) -> str:
    """Derive 'Resource_Name' from 'Resource_Name_part001.rar'."""
    for name in part_names:
        stem = PART_SUFFIX.sub("", name)
        if stem and stem != name:
            return sanitize(stem)
    # No 'partNNN' pattern found: fall back to the first filename without extension.
    return sanitize(Path(part_names[0]).stem) if part_names else "download"


def _valid_url(value: str):
    v = value.strip()
    if v.lower().startswith(("http://", "https://")) and "." in v:
        return True
    return "Enter a full URL starting with http:// or https://"


def ask_url():
    """Prompt for the page URL. Returns None if cancelled."""
    answer = questionary.text("Paste the page URL:", validate=_valid_url).ask()
    return answer.strip() if answer else None


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