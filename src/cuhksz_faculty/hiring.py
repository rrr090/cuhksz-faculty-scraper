"""Decide from a professor's own pages whether they appear to be recruiting.

The rules are deliberately sentence-level: a recruiting phrase and a role must
appear together, and sentences describing the past are ignored. Results are
marked as auto-detected. A review file can override any of them.
"""
from __future__ import annotations

import re

MIN_READABLE_CHARS = 400
MAX_QUOTE = 320

STATUSES = ("ra", "undergrad", "students", "none", "unreadable", "no_site")

_RECRUIT = re.compile(
    r"recruit|hiring|looking for|seeking|\bopenings?\b|positions? (?:for|available)|are available|"
    r"work with me as|join (?:the lab|our|us|my)\b.*\bas\b|are considered|招聘|招收|招募|招生",
    re.I,
)
# Case-sensitive so that "IEEE-RAS" and "RA-L" (a robotics journal) do not match.
_RA = re.compile(r"\bRAs?\b(?!-)|[Rr]esearch [Aa]ssistants?|\b[Ii]nterns?\b|Internship|internship|科研助理|研究助理|实习生")
_UNDERGRAD = re.compile(r"undergraduate|undergrad\b|本科生", re.I)
_STUDENT = re.compile(r"ph\.?\s?d|postdoc|m\.?phil|master|\bstudents?\b|researchers|博士|硕士", re.I)
_PAST = re.compile(
    r"\b(?:was|were|worked as|served as|received|complete[ds]?|started?|start an|offer from|congrats|"
    r"no longer|looking forward|expired)\b|intern(?:ship)? at\b|research intern (?:at|with)",
    re.I,
)
# Award and funding programme names such as "Pearl River Talent Recruitment Project" are not job ads.
_PROGRAMME = re.compile(
    r"talent (?:recruitment|introduction)|recruitment (?:program(?:me)?|project|plan|scheme)s?\b|"
    r"人才(?:引进|招聘)|(?:引进|招聘)计划",
    re.I,
)
_MEMBER_HEADING = re.compile(r"^(?:undergraduate|undergrad)s?(?: research)?(?: students?| interns?| researchers?)?(?: in .*)?$", re.I)


def _sentences(text: str) -> list[str]:
    flat = re.sub(r"\s*\n\s*", " ", text)
    # Do not split on the full stops in "Ph.D." or "M.Phil.".
    parts = re.split(r"(?<![A-Z])(?<!Ph\.D)(?<!Phil)[.!?。！？]\s+", flat)
    return [p.strip() for p in parts if p.strip()]


def _quote(sentence: str, match: re.Match) -> str:
    if len(sentence) <= MAX_QUOTE:
        return sentence
    start = max(0, match.start() - 120)
    return sentence[start:start + MAX_QUOTE].strip()


def classify_pages(pages: list[dict]) -> dict:
    """Return the strongest recruiting signal found in `pages`."""
    best: dict[str, dict] = {}
    for page in pages:
        for sentence in _sentences(page["text"]):
            recruit = _RECRUIT.search(_PROGRAMME.sub(lambda m: " " * len(m.group()), sentence))
            if not recruit or _PAST.search(sentence):
                continue
            for status, regex in (("ra", _RA), ("undergrad", _UNDERGRAD), ("students", _STUDENT)):
                if status not in best and regex.search(sentence):
                    best[status] = {"quote": _quote(sentence, recruit), "url": page["url"]}
        lines = [line.strip() for line in page["text"].split("\n")]
        for line, following in zip(lines, lines[1:]):
            if "undergrad" not in best and _MEMBER_HEADING.match(line) and following:
                best["undergrad"] = {"url": page["url"], "note": "The members page lists current undergraduates."}
    for status in ("ra", "undergrad", "students"):
        if status in best:
            return {"status": status, **best[status]}
    return {"status": "none"}


def resolve_hiring(person: dict, site: dict | None, reviews: dict[str, dict]) -> dict:
    """Use a hand review when there is one, otherwise auto-detect."""
    reviewed = reviews.get(str(person["id"]))
    if reviewed:
        return {**reviewed, "origin": "reviewed"}
    if not site or not site["urls"]:
        return {"status": "no_site", "origin": "auto"}
    if sum(len(page["text"]) for page in site["pages"]) < MIN_READABLE_CHARS:
        reason = "; ".join(site["notes"]) or "The page has almost no readable text (it may be rendered by JavaScript)."
        return {"status": "unreadable", "note": reason, "origin": "auto"}
    return {**classify_pages(site["pages"]), "origin": "auto"}
