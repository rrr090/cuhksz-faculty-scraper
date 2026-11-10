"""Write the Obsidian vault. Each note's Outreach and My notes sections survive rebuilds.

Compatibility scores appear only when the config defines themes. Without
themes the vault holds directory data and hiring evidence alone, so it can be
shared without revealing anyone's research interests.
"""
from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass
from datetime import date

from cuhksz_faculty.config import Config
from cuhksz_faculty.hiring import STATUSES, resolve_hiring
from cuhksz_faculty.interests import research_interests
from cuhksz_faculty.publications import split_publications
from cuhksz_faculty.scoring import Score, score_person

STATUS_LABELS = {
    "ra": ("🟢", "Recruiting RAs or interns"),
    "undergrad": ("🟢", "Takes undergraduates"),
    "students": ("🟡", "Recruiting, RAs not mentioned"),
    "none": ("⚪", "No recruiting statement found"),
    "unreadable": ("⚪", "Site could not be read"),
    "no_site": ("⚪", "No personal site listed"),
}
OPEN_STATUSES = ("ra", "undergrad")
CONTACT_FIRST_SCORE = 40
COLD_EMAIL_SCORE = 50
START_PAGE_ROWS = 25
THEME_TAG_STRENGTH = 0.25
TAIL_MARKER = "## Outreach"
RANKING_PAGE = "Compatibility ranking"
INDEX_PAGE = "All professors"
# Pages older versions of the tool wrote, removed on rebuild.
OBSOLETE_PAGES = ("Outreach email template",)

OUTREACH_TAIL = """## Outreach
- [ ] Check personal website for open RA/intern positions
- [ ] Read a recent paper
- [ ] Draft tailored email
- [ ] Sent email (date: )
- [ ] Response received

## My notes
"""


@dataclass(frozen=True)
class Row:
    stem: str
    display: str
    rank: str
    email: str
    schools: list[str]
    areas: list[str]
    fields: list[str]
    hire: dict
    score: int | None = None


def file_stem(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "", name.replace(",", "")).strip()


def assign_stems(people: list[dict]) -> None:
    """Give each person a unique note name, adding detail only where names collide."""
    groups: dict[str, list[dict]] = {}
    for person in people:
        groups.setdefault(file_stem(person["display"]).lower(), []).append(person)
    for group in groups.values():
        if len(group) == 1:
            group[0]["stem"] = file_stem(group[0]["display"])
            continue
        suffixes = (
            lambda p: p["rank"],
            lambda p: f"{p['schools'][0].upper()} {p['rank']}",
            lambda p: p["id"],
        )
        for suffix in suffixes:
            labels = [file_stem(suffix(person)) for person in group]
            if len({label.lower() for label in labels}) == len(group):
                break
        for person, label in zip(group, labels):
            person["stem"] = f"{file_stem(person['display'])} ({label})"


def _yaml_str(value: str) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def _yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(_yaml_str(v) for v in values) + "]"


def _cell(text: str) -> str:
    return (text or "").replace("|", "/")


def _link(row: Row) -> str:
    return f"[[{row.stem}\\|{row.display}]]" if row.stem != row.display else f"[[{row.stem}]]"


def _existing_tail(path: pathlib.Path) -> str:
    if path.exists():
        text = path.read_text(encoding="utf-8")
        index = text.find(TAIL_MARKER)
        if index >= 0:
            # Older notes linked to sections and pages that may no longer exist.
            return text[index:].replace(' (see "Closest papers" above)', "").replace(" ([[Outreach email template]])", "")
    return OUTREACH_TAIL


def _section(sections: dict[str, str], prefix: str) -> str:
    """Section text by heading prefix, since schools word their headings differently."""
    return next((text for heading, text in sections.items() if heading.startswith(prefix)), "")


def render_note(person: dict, score: Score | None, hire: dict, config: Config, tail: str) -> str:
    """One professor's note. `score` is None when no themes are configured."""
    icon, label = STATUS_LABELS[hire["status"]]
    tags = ["professor"] + person["schools"]
    if score:
        tag_by_theme = {theme.name: theme.tag for theme in config.themes}
        tags += [tag_by_theme[n] for n, m in score.themes.items() if m.strength >= THEME_TAG_STRENGTH]
    school_names = {school.key: school.name for school in config.schools}
    sections = person["sections"]
    publications = split_publications(sections.get("Academic Publications"))
    interests = research_interests(person)
    lines = [
        "---",
        f"name: {_yaml_str(person['display'])}",
        f"rank: {_yaml_str(person['rank'])}",
        f"appointment: {_yaml_str(person['appointment'])}",
        f"schools: {_yaml_list(person['schools'])}",
    ]
    if score:
        lines.append(f"compatibility: {score.total}")
    lines += [
        f"hiring: {hire['status']}",
        f"hiring_origin: {hire['origin']}",
        f"email: {_yaml_str(person['email'])}",
        f"website: {_yaml_str(person['website'])}",
        f"areas: {_yaml_list(person['academic_area'])}",
        f"interests: {_yaml_list(interests)}",
        f"fields: {_yaml_list(person['research_field'])}",
        f"source: {_yaml_str(person['source'])}",
        f"tags: {_yaml_list(tags)}",
        "---",
        "",
        f"# {person['display']}",
        "",
        (f"**Compatibility: {score.total}/100** · " if score else "") + f"{icon} {label}",
        "",
        person["rank"] + (f" ({person['appointment']})" if person["appointment"] else "") + "  ",
        "School: " + ", ".join(f"[[{school_names[key]}]]" for key in person["schools"]) + "  ",
        f"Email: {person['email'] or 'not listed'}  ",
    ]
    if person["website"]:
        lines.append(f"Website: {person['website']}  ")
    lines += [f"[Listing]({person['source']})", ""]
    if score:
        lines += ["## Why this score", "",
                  "| Theme | Strength | In listed fields | Matching papers | Terms |", "|---|---|---|---|---|"]
        for name, match in score.themes.items():
            lines.append(f"| {name} | {match.strength:.2f} | {'yes' if match.in_fields else 'no'} | {match.papers} | {', '.join(match.terms) or '-'} |")
        lines += ["", "## Closest papers", ""]
        lines += [f"- {paper}" for paper in score.closest_papers] or ["No listed papers match your themes."]
        lines.append("")
    lines += ["## Hiring evidence", "", f"{icon} **{label}**", ""]
    if hire.get("quote"):
        lines += [f"> {hire['quote']}", ""]
    if hire.get("url"):
        lines += [f"Source: {hire['url']}", ""]
    if hire.get("note"):
        lines += [hire["note"], ""]
    if hire["origin"] == "auto" and hire["status"] in ("ra", "undergrad", "students"):
        lines += ["Auto-detected: read the source page before relying on this.", ""]
    lines += ["## Research", ""]
    if interests:
        lines += ["Research interests: " + ", ".join(f"[[{file_stem(a)}]]" for a in interests), ""]
    lines.append("Fields: " + (", ".join(person["research_field"]) or "not listed"))
    if person["credentials"]:
        lines += ["", "## Credentials", ""] + [f"- {c}" for c in person["credentials"]]
    if _section(sections, "Education"):
        lines += ["", "## Education", "", _section(sections, "Education")]
    if sections.get("Biography"):
        lines += ["", "## Biography", "", sections["Biography"]]
    if publications:
        lines += ["", "## Publications listed on profile", ""]
        lines += [f"{number}. {paper}" for number, paper in enumerate(publications, 1)]
    return "\n".join(lines + ["", tail.rstrip(), ""])


def _score_cell(row: Row) -> str:
    return "" if row.score is None else f"{row.score} | "


def _table(rows: list[Row], scored: bool) -> str:
    head = ("Score | " if scored else "") + "Professor | School | Hiring | Rank | Focus | Email"
    out = [f"| {head} |", "|" + "---|" * head.count("|") + "---|"]
    for row in rows:
        icon, label = STATUS_LABELS[row.hire["status"]]
        focus = _cell(", ".join(row.fields or row.areas))[:90]
        schools = ", ".join(key.upper() for key in row.schools)
        out.append(f"| {_score_cell(row)}{_link(row)} | {schools} | {icon} {label} | {_cell(row.rank)} | {focus} | {row.email} |")
    return "\n".join(out)


def _recruiting_page(rows: list[Row], stamp: str, scored: bool) -> str:
    parts = [f"# Who is recruiting\n\nRead from each professor's own website on {stamp}. Pages go out of date, so confirm by email.\n"]
    for status in STATUSES:
        group = [row for row in rows if row.hire["status"] == status]
        if not group:
            continue
        icon, label = STATUS_LABELS[status]
        parts.append(f"## {icon} {label} ({len(group)})\n")
        if status in ("ra", "undergrad", "students"):
            parts.append(("| Score " if scored else "") + "| Professor | School | What the page says |\n"
                         + ("|---" if scored else "") + "|---|---|---|")
            parts += [f"| {_score_cell(row)}{_link(row)} | {', '.join(k.upper() for k in row.schools)} | "
                      f"{_cell(row.hire.get('quote') or row.hire.get('note', ''))[:260]} |" for row in group]
            parts.append("")
        else:
            parts.append(", ".join(_link(row) + (f" ({row.score})" if scored else "") for row in group) + "\n")
    return "\n".join(parts)


def _start_page(rows: list[Row], config: Config, stamp: str, scored: bool) -> str:
    open_call = [row for row in rows if row.hire["status"] in OPEN_STATUSES]
    unknown = sum(row.hire["status"] in ("no_site", "unreadable") for row in rows)
    auto = sum(row.hire["origin"] == "auto" and row.hire["status"] in ("ra", "undergrad", "students") for row in rows)
    present = sorted({key for row in rows for key in row.schools})
    names = {school.key: school.name for school in config.schools}
    schools = ", ".join(f"[[{names[key]}]] ({sum(key in row.schools for row in rows)})" for key in present)
    if scored:
        first = [row for row in open_call if row.score >= CONTACT_FIRST_SCORE]
        cold = [row for row in rows if row.score >= COLD_EMAIL_SCORE and row.hire["status"] not in OPEN_STATUSES]
        themes = "\n".join(f"- **{theme.name}**: worth up to {round(theme.weight * 100)} points alone" for theme in config.themes)
        top = f"""## Contact first
{_table(first[:START_PAGE_ROWS], scored)}

## Strong match, no RA call found
No public call does not mean no openings.

{_table(cold[:START_PAGE_ROWS], scored)}
"""
        method = f"""
## How the score works
Each theme is measured from listed research fields (60%), papers on the profile (25%), biography (10%) and personal site (5%). Matches combine, so one direct hit on a heavily weighted theme scores high. Professors with no directory profile are scored from their personal site instead.

{themes}

It is keyword matching, so use it to decide who to read about. Each note shows what matched.
"""
    else:
        top = f"""## Taking RAs, interns or undergraduates
{_table(open_call, scored)}
"""
        method = ""
    return f"""# CUHK-Shenzhen faculty

{len(rows)} professors, scraped {stamp}. {len(open_call)} show evidence of taking RAs, interns or undergraduates.

{top}
## Browse
- [[{RANKING_PAGE if scored else INDEX_PAGE}]]
- [[Who is recruiting]]
- Schools: {schools}
- Research interests: each note links to shared topic pages in `Areas`. They combine the directory's academic areas with topics matched from listed research fields.

## Graph colours
In the graph view, each school's professors share a colour. Someone in several schools takes the colour of the first one listed here.

{_graph_legend(config.schools)}
{method}
## How far to trust the hiring column
- It reflects what each site said on {stamp}.
- {auto} recruiting labels are auto-detected and should be checked against their source.
- {unknown} professors have no site or an unreadable one, so their status is unknown.
"""


def _school_query(school) -> str:
    return f"tag:#{school.key}"


def write_graph_colors(vault: pathlib.Path, schools) -> None:
    """Colour each school's notes in Obsidian's graph view.

    Only the school colour groups are replaced. Other graph settings and any
    colour groups the user added in Obsidian are kept. A professor in several
    schools takes the colour of the first one listed in the config.
    """
    path = vault / ".obsidian" / "graph.json"
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {}
    ours = {_school_query(school) for school in schools}
    kept = [group for group in settings.get("colorGroups", []) if group.get("query") not in ours]
    settings["colorGroups"] = [
        {"query": _school_query(school), "color": {"a": 1, "rgb": int(school.color[1:], 16)}} for school in schools
    ] + kept
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def _graph_legend(schools) -> str:
    return "\n".join(f'- <span style="color:{s.color}">●</span> {s.name} (`#{s.key}`)' for s in schools)


def build_vault(data_dir: pathlib.Path, vault: pathlib.Path, config: Config, reviews: dict[str, dict]) -> list[Row]:
    people = json.loads((data_dir / "faculty.json").read_text(encoding="utf-8"))
    sites = {site["id"]: site for site in json.loads((data_dir / "sites.json").read_text(encoding="utf-8"))}
    scored = bool(config.themes)
    professors = vault / "Professors"
    area_dir = vault / "Areas"
    school_dir = vault / "Schools"
    for folder in (professors, area_dir, school_dir):
        folder.mkdir(parents=True, exist_ok=True)
    assign_stems(people)

    rows: list[Row] = []
    for person in people:
        site = sites.get(person["id"])
        score = None
        if scored:
            site_text = "\n".join(page["text"] for page in site["pages"]) if site else ""
            score = score_person(person, site_text, config.themes)
        hire = resolve_hiring(person, site, reviews)
        path = professors / f"{person['stem']}.md"
        path.write_text(render_note(person, score, hire, config, _existing_tail(path)), encoding="utf-8")
        rows.append(Row(person["stem"], person["display"], person["rank"], person["email"], person["schools"],
                        research_interests(person), person["research_field"], hire, score.total if score else None))
    rows.sort(key=lambda row: (-(row.score or 0), row.display.lower()))

    stamp = date.today().isoformat()
    # Only one of these exists at a time, so switching modes does not leave a stale page behind.
    index, stale = (RANKING_PAGE, INDEX_PAGE) if scored else (INDEX_PAGE, RANKING_PAGE)
    for name in (stale, *OBSOLETE_PAGES):
        (vault / f"{name}.md").unlink(missing_ok=True)
    (vault / f"{index}.md").write_text(f"# {index}\n\n{_table(rows, scored)}\n", encoding="utf-8")
    (vault / "00 Start here.md").write_text(_start_page(rows, config, stamp, scored), encoding="utf-8")
    (vault / "Who is recruiting.md").write_text(_recruiting_page(rows, stamp, scored), encoding="utf-8")
    for area in sorted({a for row in rows for a in row.areas}):
        group = [row for row in rows if area in row.areas]
        (area_dir / f"{file_stem(area)}.md").write_text(f"# {area}\n\n{_table(group, scored)}\n", encoding="utf-8")
    for school in config.schools:
        group = [row for row in rows if school.key in row.schools]
        if group:
            # The tag gives the school's own hub note its colour in the graph view.
            page = f"---\ntags: [\"school\", {_yaml_str(school.key)}]\n---\n\n# {school.name}\n\n{_table(group, scored)}\n"
            (school_dir / f"{file_stem(school.name)}.md").write_text(page, encoding="utf-8")
    write_graph_colors(vault, config.schools)
    return rows
