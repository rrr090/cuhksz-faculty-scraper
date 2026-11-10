import dataclasses
import json
import re
import urllib.robotparser

import pytest
import requests

from cuhksz_faculty.config import ConfigError, Theme, load_config
from cuhksz_faculty.fetch import _load_robots
from cuhksz_faculty.publications import split_publications
from cuhksz_faculty.scoring import score_person
from cuhksz_faculty.vault import assign_stems, build_vault

THEMES = (Theme("Graph learning", 0.8, "graphs", re.compile(r"graph learning|graph neural", re.I)),)


def person(pid="abc-1", name="DOE, Alex", rank="Professor", fields=("Graph Learning",), pubs="", school="sai", sections=True):
    return {
        "id": pid, "name": name, "display": name, "appointment": "", "rank": rank, "credentials": [], "schools": [school],
        "academic_area": ["Machine Learning"], "research_field": list(fields), "email": "a@example.edu",
        "website": "", "source": f"https://example.edu/{pid}", "profile_url": "",
        "sections": {"Biography": "Works on learning.", "Academic Publications": pubs} if sections else {},
    }


def test_split_publications():
    text = "1. A first paper about something long enough, 2024. 2. A second paper about something else, 2025."
    assert len(split_publications(text)) == 2


def test_listed_field_outscores_unrelated_work():
    assert score_person(person(), "", THEMES).total > score_person(person(fields=("Databases",)), "", THEMES).total


def test_closest_papers_are_newest_first():
    pubs = ("1. Graph learning for an old problem, Venue, 2019. "
            "2. Graph learning for a new problem, Venue, 2025.")
    assert "2025" in score_person(person(pubs=pubs), "", THEMES).closest_papers[0]


def test_personal_site_stands_in_when_there_is_no_profile():
    site = "Biography\nAuthor, Graph learning for a new problem, Example Venue, 2025."
    without_site = score_person(person(fields=("Databases",), sections=False), "", THEMES)
    with_site = score_person(person(fields=("Databases",), sections=False), site, THEMES)
    assert with_site.total > without_site.total
    assert with_site.closest_papers


def test_default_config_has_no_themes():
    assert load_config().themes == ()


def _build(tmp_path, config):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    pubs = "1. Graph learning for a new problem, Example Venue, 2025."
    (data / "faculty.json").write_text(json.dumps([person(pubs=pubs)]), encoding="utf-8")
    (data / "sites.json").write_text(json.dumps([{"id": "abc-1", "urls": [], "pages": [], "notes": []}]), encoding="utf-8")
    build_vault(data, tmp_path / "vault", config, {})
    return tmp_path / "vault"


def _all_text(vault):
    return "\n".join(path.read_text(encoding="utf-8") for path in vault.rglob("*.md"))


def test_vault_without_themes_has_no_scores(tmp_path):
    vault = _build(tmp_path, load_config())
    text = _all_text(vault)
    for word in ("ompatibility", "Score", "Closest papers", "Why this score", "Graph learning\n"):
        assert word not in text
    assert "## Publications listed on profile" in text
    assert (vault / "All professors.md").exists() and not (vault / "Compatibility ranking.md").exists()


def test_vault_with_themes_has_scores_and_switching_back_cleans_up(tmp_path):
    scored = dataclasses.replace(load_config(), themes=THEMES)
    vault = _build(tmp_path, scored)
    note = (vault / "Professors" / "DOE Alex.md").read_text(encoding="utf-8")
    assert "compatibility:" in note and "## Closest papers" in note and '"graphs"' in note
    assert (vault / "Compatibility ranking.md").exists()
    _build(tmp_path, load_config())
    assert "ompatibility" not in _all_text(vault)
    assert not (vault / "Compatibility ranking.md").exists()


def test_identical_names_get_distinct_notes():
    people = [person("a-1", "LI, Sam", "Professor"), person("a-2", "LI, Sam", "Assistant Professor")]
    assign_stems(people)
    assert {p["stem"] for p in people} == {"LI Sam (Professor)", "LI Sam (Assistant Professor)"}


def test_same_name_and_rank_uses_the_school():
    people = [person("a-1", "LI, Sam", school="sai"), person("b-2", "LI, Sam", school="med")]
    assign_stems(people)
    assert {p["stem"] for p in people} == {"LI Sam (SAI Professor)", "LI Sam (MED Professor)"}


def test_rebuild_keeps_personal_notes_and_writes_school_pages(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "faculty.json").write_text(json.dumps([person()]), encoding="utf-8")
    (data / "sites.json").write_text(json.dumps([{"id": "abc-1", "urls": [], "pages": [], "notes": []}]), encoding="utf-8")
    vault = tmp_path / "vault"
    config = load_config()
    build_vault(data, vault, config, {})
    note = vault / "Professors" / "DOE Alex.md"
    note.write_text(note.read_text(encoding="utf-8") + "\nMY PRIVATE NOTE\n", encoding="utf-8")
    build_vault(data, vault, config, {})
    assert "MY PRIVATE NOTE" in note.read_text(encoding="utf-8")
    assert (vault / "Schools" / "School of Artificial Intelligence.md").exists()


def test_each_school_gets_its_own_graph_color(tmp_path):
    config = load_config()
    colors = [s.color for s in config.schools]
    assert len(set(colors)) == len(colors) == 8
    vault = _build(tmp_path, config)
    groups = json.loads((vault / ".obsidian" / "graph.json").read_text(encoding="utf-8"))["colorGroups"]
    assert [g["query"] for g in groups] == [f"tag:#{s.key}" for s in config.schools]
    assert groups[0]["color"] == {"a": 1, "rgb": int(colors[0][1:], 16)}
    school_page = (vault / "Schools" / "School of Artificial Intelligence.md").read_text(encoding="utf-8")
    assert school_page.startswith('---\ntags: ["school", "sai"]\n---')


def test_rebuild_keeps_obsidian_graph_settings_and_user_groups(tmp_path):
    graph = tmp_path / "vault" / ".obsidian" / "graph.json"
    graph.parent.mkdir(parents=True)
    mine = {"query": "path:Areas", "color": {"a": 1, "rgb": 0}}
    stale = {"query": "tag:#sai", "color": {"a": 1, "rgb": 1}}
    graph.write_text(json.dumps({"linkDistance": 250, "colorGroups": [stale, mine]}), encoding="utf-8")
    for _ in range(2):
        _build(tmp_path, load_config())
    settings = json.loads(graph.read_text(encoding="utf-8"))
    assert settings["linkDistance"] == 250
    assert settings["colorGroups"][-1] == mine and len(settings["colorGroups"]) == 9
    assert stale not in settings["colorGroups"]


def test_bad_school_color_is_rejected(tmp_path):
    bad = tmp_path / "c.toml"
    bad.write_text('[[schools]]\nkey="a"\nname="A"\nbase_url="https://a.example"\ncolor="red"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="color"):
        load_config(bad)


def test_invalid_config_is_rejected(tmp_path):
    bad = tmp_path / "c.toml"
    bad.write_text('[[schools]]\nkey="a"\nname="A"\nbase_url="https://a.example"\n'
                   '[[themes]]\nname="x"\nweight=2\ntag="x"\npattern="a"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(bad)


def test_all_eight_schools_are_configured():
    assert [s.key for s in load_config().schools] == ["sai", "sds", "sse", "sme", "hss", "med", "music", "spp"]


def test_school_selection():
    config = load_config()
    assert [s.key for s in config.select_schools(["sds", "sai"])] == ["sds", "sai"]
    assert len(config.select_schools(None)) == 8
    with pytest.raises(ConfigError, match="unknown school nope"):
        config.select_schools(["nope"])


class FakeResponse:
    def __init__(self, status, text=""):
        self.status_code, self.text, self.headers = status, text, {"content-type": "text/plain"}


@pytest.mark.parametrize("response, expected", [
    (FakeResponse(200, ""), True),
    (FakeResponse(404), True),
    (FakeResponse(403), False),
    (FakeResponse(200, "User-agent: *\nDisallow: /"), False),
])
def test_robots_handling(response, expected):
    parser: urllib.robotparser.RobotFileParser = _load_robots(lambda: response)
    assert parser.can_fetch("bot", "https://example.org/page") is expected


def flaky(failures, response):
    calls = []
    def fetch():
        calls.append(1)
        if len(calls) <= failures:
            raise requests.ConnectionError("reset")
        return response
    return fetch, calls


def test_robots_network_error_is_retried(monkeypatch):
    monkeypatch.setattr("cuhksz_faculty.fetch.ROBOTS_RETRY_SECONDS", 0)
    fetch, calls = flaky(1, FakeResponse(404))
    assert _load_robots(fetch).can_fetch("bot", "https://example.org/page")
    assert len(calls) == 2


def test_robots_unreachable_after_retries_disallows(monkeypatch):
    monkeypatch.setattr("cuhksz_faculty.fetch.ROBOTS_RETRY_SECONDS", 0)
    fetch, calls = flaky(99, FakeResponse(404))
    assert not _load_robots(fetch, attempts=3).can_fetch("bot", "https://example.org/page")
    assert len(calls) == 3
