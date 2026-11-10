"""Load and validate the TOML configuration."""
from __future__ import annotations

import importlib.resources
import pathlib
import re
import tomllib
from dataclasses import dataclass


class ConfigError(ValueError):
    """Raised when a configuration file is invalid or asks for something unknown."""


@dataclass(frozen=True)
class Theme:
    name: str
    weight: float
    tag: str
    regex: re.Pattern[str]


@dataclass(frozen=True)
class School:
    key: str
    name: str
    base_url: str
    color: str = ""  # "#RRGGBB" for Obsidian's graph view; empty picks one from GRAPH_PALETTE.


# Bright, well-separated hues that stand out on Obsidian's dark and light themes.
GRAPH_PALETTE = ("#3B82F6", "#F97316", "#22C55E", "#EF4444", "#A855F7", "#06B6D4", "#FACC15", "#EC4899", "#84CC16", "#94A3B8")
_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")


@dataclass(frozen=True)
class Config:
    user_agent: str
    host_delay: float
    max_pages_per_site: int
    workers: int
    legacy_tls_hosts: tuple[str, ...]
    schools: tuple[School, ...]
    # Optional. With no themes, the vault has no compatibility scores.
    themes: tuple[Theme, ...] = ()

    def select_schools(self, keys: list[str] | None) -> tuple[School, ...]:
        """The schools named in `keys`, or all of them when `keys` is empty."""
        if not keys:
            return self.schools
        known = {school.key: school for school in self.schools}
        unknown = [key for key in keys if key not in known]
        if unknown:
            raise ConfigError(f"unknown school {', '.join(unknown)}. Choose from: {', '.join(known)}")
        return tuple(known[key] for key in keys)


def _theme(raw: dict) -> Theme:
    name = raw.get("name", "<unnamed>")
    try:
        weight = float(raw["weight"])
        regex = re.compile(raw["pattern"], re.IGNORECASE)
        tag = str(raw["tag"])
    except KeyError as e:
        raise ConfigError(f"theme {name!r} is missing {e.args[0]!r}") from e
    except re.error as e:
        raise ConfigError(f"theme {name!r} has an invalid pattern: {e}") from e
    if not 0 <= weight <= 1:
        raise ConfigError(f"theme {name!r} needs a weight between 0 and 1")
    return Theme(name=name, weight=weight, tag=tag, regex=regex)


def _school(raw: dict, index: int) -> School:
    key = raw.get("key", "<unnamed>")
    color = raw.get("color") or GRAPH_PALETTE[index % len(GRAPH_PALETTE)]
    if not _HEX_COLOR.fullmatch(color):
        raise ConfigError(f"school {key!r} needs a color like \"#4E79A7\", not {color!r}")
    try:
        return School(key=raw["key"], name=raw["name"], base_url=raw["base_url"].rstrip("/"), color=color.upper())
    except KeyError as e:
        raise ConfigError(f"school {key!r} is missing {e.args[0]!r}") from e


def load_config(path: str | pathlib.Path | None = None) -> Config:
    """Read a config file, or the packaged default when `path` is None."""
    if path is None:
        text = importlib.resources.files("cuhksz_faculty").joinpath("default_config.toml").read_text(encoding="utf-8")
    else:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"invalid TOML: {e}") from e
    crawl = raw.get("crawl", {})
    themes = tuple(_theme(t) for t in raw.get("themes", []))
    schools = tuple(_school(s, i) for i, s in enumerate(raw.get("schools", [])))
    if not schools:
        raise ConfigError("at least one [[schools]] entry is required")
    return Config(
        user_agent=crawl.get("user_agent", "cuhksz-faculty-scraper/0.2"),
        host_delay=float(crawl.get("host_delay_seconds", 1.0)),
        max_pages_per_site=int(crawl.get("max_pages_per_site", 8)),
        workers=int(crawl.get("workers", 8)),
        legacy_tls_hosts=tuple(crawl.get("legacy_tls_hosts", [])) + tuple(s.base_url for s in schools),
        schools=schools,
        themes=themes,
    )
