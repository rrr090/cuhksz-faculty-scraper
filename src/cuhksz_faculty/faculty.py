"""Parse each school's directory listing and profile pages.

All schools share one site template, but they fill it in differently: names may
link to a directory profile or straight to a personal site, and the rank can be
in any of several blocks. The parsing here finds fields by content, not position.
"""
from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString

from cuhksz_faculty.config import School
from cuhksz_faculty.fetch import Fetcher

MAX_LIST_PAGES = 40
MAX_RANK_CHARS = 60
RANK = re.compile(r"\b(?:professor|lecturer|instructor|tutor|research (?:scientist|fellow|associate))\b", re.I)
NOT_A_CURRENT_RANK = ("former", "formerly", "previously")
HONORIFIC = re.compile(r"^(?:prof(?:essor)?|dr)\.?\s+", re.I)
PROFILE_PATH = re.compile(r"/(?:teacher|faculty)/([^/?#]+)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def split_list(text: str) -> list[str]:
    items = (item.strip() for item in re.split(r"[;,；，、]", text))
    return [re.sub(r"^and\s+", "", item) for item in items if item]


def _value(element) -> str:
    """Text of `<div><span>Label: </span>value</div>` without its label."""
    span = element.find("span")
    if span:
        span.extract()
    return clean(element.get_text(" "))


def pick_rank(lines: list[str]) -> str:
    """Choose the academic rank from a card's descriptive lines."""
    candidates = [line for line in lines if not line.lower().startswith(NOT_A_CURRENT_RANK)]
    for line in candidates:
        if RANK.search(line) and len(line) <= MAX_RANK_CHARS and not re.search(r"[,;，；]", line):
            return line
    for line in candidates:
        for part in re.split(r"[,;，；]", line):
            if RANK.search(part) and len(part.strip()) <= MAX_RANK_CHARS:
                return part.strip()
    return lines[0] if lines else ""


def parse_cards(html: str, school: School) -> list[dict]:
    """Extract one record per professor from a directory listing page."""
    soup = BeautifulSoup(html, "html.parser")
    records = []
    school_host = urlparse(school.base_url).netloc
    for card in soup.select(".list-content"):
        title = card.select_one(".list-title")
        if not title or not clean(title.get_text()):
            continue
        anchor = title.find("a", href=True)
        href = urljoin(school.base_url + "/", anchor["href"]) if anchor else ""
        if urlparse(href).scheme not in ("http", "https"):
            href = ""
        profile = PROFILE_PATH.search(urlparse(href).path) if urlparse(href).netloc == school_host else None
        name = clean(title.get_text())

        lines: list[str] = []
        for element in card.select(".list-des"):
            lines += [clean(x) for x in element.get_text("\n").split("\n") if clean(x)]
        email = ""
        for element in card.select(".list-email"):
            if element.find("span"):
                email = _value(element)
            elif clean(element.get_text()):  # Some schools put the rank in this block.
                lines.append(clean(element.get_text()))

        record = {
            "id": f"{school.key}-{profile.group(1) if profile else hashlib.sha1((href or name).encode()).hexdigest()[:8]}",
            "name": name,
            "schools": [school.key],
            "rank": pick_rank(lines),
            "academic_area": [],
            "research_field": [],
            "email": email,
            "website": "",
            "profile_url": href if profile else "",
            "source": href or f"{school.base_url}/en/teacher-search",
        }
        record["credentials"] = [line for line in lines if line != record["rank"]]
        for element in card.select(".list-area"):
            span = element.find("span")
            label = clean(span.get_text()) if span else ""
            value = _value(element)
            if label.startswith("Academic"):
                record["academic_area"] = split_list(value)
            elif label.startswith("Research"):
                record["research_field"] = split_list(value)
        website = card.select_one(".list-website")
        if website:
            record["website"] = _value(website)
        if href and not profile and not record["website"]:
            record["website"] = href  # The name links straight to a personal site.
        records.append(record)
    return records


def parse_profile(html: str) -> dict[str, str]:
    """Return {section heading: section text} for a profile page."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    headings = soup.select("div.sub-title")
    if not headings:
        return {}
    # Sections live in the main content block; the page footer is a separate block.
    container = headings[0].find_parent(class_="block-system") or soup
    heading_ids = {id(h) for h in headings}
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for node in container.descendants:
        if id(node) in heading_ids:
            current = sections.setdefault(clean(node.get_text()), [])
        elif current is not None and isinstance(node, NavigableString) and not node.find_parent(class_="sub-title"):
            text = clean(str(node))
            if text:
                current.append(text)
    return {heading: " ".join(parts) for heading, parts in sections.items()}


def base_name(raw: str) -> str:
    """'Prof. WU, Zhizheng (By Courtesy)' -> 'WU, Zhizheng'."""
    return HONORIFIC.sub("", clean(re.sub(r"[(（].*?[)）]", "", raw))).strip(" ,")


def appointment(raw: str) -> str:
    """'WU, Zhizheng (By Courtesy)' -> 'By Courtesy'."""
    match = re.search(r"[(（](.*?)[)）]", raw)
    return match.group(1).strip() if match else ""


def scrape_school(fetcher: Fetcher, school: School) -> list[dict]:
    """Walk one school's paginated directory, then fetch its profile pages."""
    people: dict[str, dict] = {}
    for number in range(MAX_LIST_PAGES):
        url = f"{school.base_url}/en/teacher-search?page={number}"
        if not fetcher.allowed(url):
            raise RuntimeError(f"{url} is disallowed by robots.txt, or robots.txt could not be reached")
        page = fetcher.get(url)
        new = [c for c in parse_cards(page.html, school) if c["id"] not in people] if page.status == 200 else []
        print(f"{school.key}: list page {number}: {len(new)} new", flush=True)
        if not new:
            break
        people.update((c["id"], c) for c in new)

    for index, record in enumerate(people.values(), 1):
        record["sections"] = {}
        if record["profile_url"]:
            page = fetcher.get(record["profile_url"])
            if page.status == 200:
                record["sections"] = parse_profile(page.html)
            print(f"{school.key}: [{index}/{len(people)}] {record['name']}: {page.status}", flush=True)
        # Directory cards can show the wrong address; profile pages are more reliable.
        listed = EMAIL.search(record["sections"].get("Email", ""))
        record["email"] = listed.group(0) if listed else record["email"]
        record["display"] = base_name(record["name"])
        record["appointment"] = appointment(record["name"])
    return list(people.values())


def _name_tokens(person: dict) -> set[str]:
    return {token for token in re.findall(r"[a-z]+", person["display"].lower()) if len(token) > 1}


def _site_key(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.netloc.removeprefix('www.')}{parts.path.rstrip('/')}".lower()


def merge_duplicates(people: list[dict]) -> list[dict]:
    """Combine people listed by several schools.

    Records merge only when they share an email or website and their names
    overlap, because an assistant's address can appear on several cards.
    """
    merged: list[dict] = []
    by_key: dict[str, dict] = {}
    for person in people:
        keys = [k for k in (person["email"].lower(), _site_key(person["website"]) if person["website"] else "") if k]
        match = next((by_key[k] for k in keys if k in by_key and _name_tokens(by_key[k]) & _name_tokens(person)), None)
        if match is None:
            merged.append(person)
            by_key.update({k: person for k in keys})
            continue
        match["schools"] += [s for s in person["schools"] if s not in match["schools"]]
        if person["sections"] and not match["sections"]:
            for field in ("sections", "profile_url", "source", "id"):
                match[field] = person[field]
        for field in ("academic_area", "research_field", "credentials"):
            match[field] = match[field] or person[field]
        by_key.update({k: match for k in keys})
    return merged


def scrape_faculty(fetcher: Fetcher, schools: tuple[School, ...]) -> list[dict]:
    """Scrape several schools at once. Each is a separate host, so rate limits still hold."""
    with ThreadPoolExecutor(max_workers=len(schools)) as pool:
        results = list(pool.map(lambda school: scrape_school(fetcher, school), schools))
    return sorted(merge_duplicates([p for people in results for p in people]), key=lambda r: r["display"])
