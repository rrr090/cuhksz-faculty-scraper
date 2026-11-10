import pytest

from cuhksz_faculty.hiring import classify_pages, resolve_hiring


def status(text):
    return classify_pages([{"url": "https://lab.example.org", "text": text}])["status"]


@pytest.mark.parametrize("text, expected", [
    ("I am looking for self-motivated Ph.D. students and research assistants.", "ra"),
    ("Recruiting: Postdoc, PhD, MPhil, RA.", "ra"),
    ("I have positions available for remote interns.", "ra"),
    ("We are recruiting undergraduate students this year.", "undergrad"),
    ("I am actively recruiting PhD students.", "students"),
    ("本组招收博士生。", "students"),
    ("Nothing about the group here.", "none"),
])
def test_recruiting_sentences(text, expected):
    assert status(text) == expected


@pytest.mark.parametrize("text", [
    "I worked as a research assistant at another university.",
    "He was seeking research interns at the time.",
    "Congrats to the student who received an internship offer from a company.",
    "I am no longer recruiting PhD students.",
    "Position 5 - Research Assistant (Expired). We are recruiting a Research Assistant (Expired).",
    "Associate Editor, IEEE-RAS Technical Committee, seeking papers.",
    "Young Scholar of the Pearl River Talent Recruitment Project; advised 12 master students.",
    "入选深圳市海外高层次人才引进计划，指导博士生5名。",
])
def test_past_or_unrelated_mentions_are_ignored(text):
    assert status(text) == "none"


def test_member_list_heading_counts_as_taking_undergraduates():
    assert status("Group\nUndergraduate Students\nA. Student (2026 - Present)") == "undergrad"


def test_review_overrides_detection():
    person = {"id": 1}
    site = {"urls": ["https://x"], "pages": [{"url": "https://x", "text": "a" * 500}], "notes": []}
    hire = resolve_hiring(person, site, {"1": {"status": "ra", "quote": "checked"}})
    assert hire == {"status": "ra", "quote": "checked", "origin": "reviewed"}


def test_missing_and_thin_sites():
    person = {"id": 1}
    assert resolve_hiring(person, {"urls": [], "pages": [], "notes": []}, {})["status"] == "no_site"
    assert resolve_hiring(person, {"urls": ["https://x"], "pages": [{"url": "x", "text": "hi"}], "notes": []}, {})["status"] == "unreadable"
