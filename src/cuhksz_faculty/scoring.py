"""Score how well a professor's work matches the configured themes."""
from __future__ import annotations

import re
from dataclasses import dataclass

from cuhksz_faculty.config import Theme
from cuhksz_faculty.publications import split_publications

FIELD_WEIGHT = 0.60
PAPER_WEIGHT = 0.25
BIO_WEIGHT = 0.10
SITE_WEIGHT = 0.05
PAPERS_FOR_FULL_CREDIT = 3
SITE_HITS_FOR_FULL_CREDIT = 5
MAX_CLOSEST_PAPERS = 5
MIN_SITE_PAPER_CHARS = 50


@dataclass(frozen=True)
class ThemeMatch:
    strength: float
    in_fields: bool
    papers: int
    terms: tuple[str, ...]


@dataclass(frozen=True)
class Score:
    total: int
    themes: dict[str, ThemeMatch]
    closest_papers: tuple[str, ...]


def latest_year(text: str) -> int:
    years = [int(year) for year in re.findall(r"\b(19[89]\d|20[0-3]\d)\b", text)]
    return max(years, default=0)


def score_person(person: dict, site_text: str, themes: tuple[Theme, ...]) -> Score:
    """Combine themes so one direct match on a heavily weighted theme scores high."""
    fields = " ; ".join(person["research_field"] + person["academic_area"])
    sections = person["sections"]
    if sections:
        bio = sections.get("Biography", "")
        publications = split_publications(sections.get("Academic Publications"))
    else:
        # Many professors link straight to a personal site, with no directory profile.
        bio = site_text
        publications = [line.strip() for line in site_text.splitlines()
                        if len(line.strip()) >= MIN_SITE_PAPER_CHARS and latest_year(line)]
    remaining = 1.0
    matches: dict[str, ThemeMatch] = {}
    closest: set[str] = set()
    for theme in themes:
        in_fields = bool(theme.regex.search(fields))
        papers = [paper for paper in publications if theme.regex.search(paper)]
        strength = (
            FIELD_WEIGHT * in_fields
            + PAPER_WEIGHT * min(1, len(papers) / PAPERS_FOR_FULL_CREDIT)
            + BIO_WEIGHT * bool(theme.regex.search(bio))
            + SITE_WEIGHT * min(1, len(theme.regex.findall(site_text)) / SITE_HITS_FOR_FULL_CREDIT)
        )
        remaining *= 1 - theme.weight * strength
        terms = sorted({m.group(0).lower() for source in (fields, bio, " ".join(papers)) for m in theme.regex.finditer(source)})
        matches[theme.name] = ThemeMatch(round(strength, 2), in_fields, len(papers), tuple(terms[:6]))
        closest.update(papers)
    newest_first = sorted(closest, key=lambda paper: (-latest_year(paper), paper))
    return Score(round(100 * (1 - remaining)), matches, tuple(newest_first[:MAX_CLOSEST_PAPERS]))
