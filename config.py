"""Loads and validates config.toml."""
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.toml")


class ConfigError(Exception):
    pass


@dataclass
class Config:
    header_text: str
    section_div_class: str
    default_dir: str
    subfolder_per_section: bool
    preferred_provider: str
    sequential: bool
    retries: int
    delay: float


def _require(table: dict, key: str, section: str):
    value = table.get(key)
    if value in (None, ""):
        raise ConfigError(f"Missing '{key}' in [{section}] of the config file.")
    return value


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    if not Path(path).exists():
        raise ConfigError(f"Config file not found: {path}")
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    site = raw.get("site", {})
    download = raw.get("download", {})
    providers = raw.get("providers", {})
    behavior = raw.get("behavior", {})

    return Config(
        header_text=_require(site, "header_text", "site"),
        section_div_class=_require(site, "section_div_class", "site"),
        default_dir=_require(download, "default_dir", "download"),
        subfolder_per_section=download.get("subfolder_per_section", True),
        preferred_provider=providers.get("preferred", "FuckingFast"),
        sequential=behavior.get("sequential", True),
        retries=int(behavior.get("retries", 3)),
        delay=float(behavior.get("delay_between_files", 1.0)),
    )