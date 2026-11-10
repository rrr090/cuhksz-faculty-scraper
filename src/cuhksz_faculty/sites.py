"""Crawl each professor's personal or lab website."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from cuhksz_faculty.faculty import clean
from cuhksz_faculty.fetch import Fetcher

MAX_TEXT = 150_000
SKIP_HOSTS = ("scholar.google", "dblp.org", "researchgate.net", "linkedin.com", "orcid.org")
SKIP_FILES = re.compile(r"\.(pdf|zip|png|jpe?g|gif|pptx?|docx?|mp4)$", re.I)

# Links most likely to mention openings come first.
LINK_PRIORITY = [
    r"join|opening|vacanc|recruit|hiring|prospective|position|招生|招聘|加入|招募",
    r"student|team|people|member|group|团队|成员",
    r"research|project|publication|paper|成果|研究|论文",
    r"about|bio|cv|home|news|简介|新闻",
]


def to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return re.sub(r"\n\s*\n+", "\n", soup.get_text("\n", strip=True))


def site_urls(raw: str | None) -> list[str]:
    """Pull usable website URLs out of a free-text directory field."""
    found = re.findall(r"https?://[^\s,;，；]+", raw or "")
    if not found and raw and "." in raw and " " not in raw.strip():
        found = ["https://" + raw.strip()]
    return [url for url in found if not any(host in url for host in SKIP_HOSTS)]


def rank_links(html: str, base: str, limit: int) -> list[str]:
    """Same-site links worth following, most relevant first."""
    host = urlparse(base).netloc
    seen: set[str] = set()
    scored: list[tuple[int, int, str]] = []
    for anchor in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = urljoin(base, anchor["href"]).split("#")[0]
        parts = urlparse(href)
        if (parts.scheme not in ("http", "https") or parts.netloc != host or href in seen
                or href.rstrip("/") == base.rstrip("/") or SKIP_FILES.search(parts.path)):
            continue
        seen.add(href)
        label = f"{parts.path} {clean(anchor.get_text())}".lower()
        for rank, pattern in enumerate(LINK_PRIORITY):
            if re.search(pattern, label):
                scored.append((rank, len(scored), href))
                break
    return [href for _, _, href in sorted(scored)][:limit]


def crawl_person(fetcher: Fetcher, person: dict, max_pages: int) -> dict:
    result = {"id": person["id"], "urls": site_urls(person.get("website")), "pages": [], "notes": []}
    for start in result["urls"][:2]:
        if not fetcher.allowed(start):
            result["notes"].append(f"robots.txt disallows {start}")
            continue
        page = fetcher.get(start)
        if page.status != 200 or not page.html:
            result["notes"].append(f"{start} returned status {page.status}")
            continue
        result["pages"].append({"url": page.url, "text": to_text(page.html)[:MAX_TEXT]})
        for link in rank_links(page.html, page.url, max_pages - 1):
            if not fetcher.allowed(link):
                continue
            sub = fetcher.get(link)
            if sub.status == 200 and sub.html:
                result["pages"].append({"url": sub.url, "text": to_text(sub.html)[:MAX_TEXT]})
    print(f"{person['display']}: {len(result['pages'])} pages {result['notes'] or ''}", flush=True)
    return result


def crawl_sites(fetcher: Fetcher, people: list[dict], max_pages: int, workers: int) -> list[dict]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda p: crawl_person(fetcher, p, max_pages), people))
