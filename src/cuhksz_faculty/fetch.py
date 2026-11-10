"""Polite HTTP: per-host rate limiting, robots.txt checks and a disk cache."""
from __future__ import annotations

import hashlib
import json
import pathlib
import ssl
import threading
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

MAX_BYTES = 3_000_000
ROBOTS_ATTEMPTS = 3
ROBOTS_RETRY_SECONDS = 5.0



class LegacyCipherAdapter(HTTPAdapter):
    """Allow older ciphers, which the university servers need. Certificates and hostnames are still verified."""

    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.set_ciphers("DEFAULT:@SECLEVEL=1")
        kwargs["ssl_context"] = context
        return super().init_poolmanager(*args, **kwargs)

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        # requests would otherwise replace our context with its preloaded one.
        return self.poolmanager.connection_from_url(request.url)


@dataclass(frozen=True)
class Page:
    status: int
    html: str
    url: str


class Fetcher:
    def __init__(self, cache_dir: pathlib.Path, user_agent: str, delay: float = 1.0, legacy_tls_hosts: tuple[str, ...] = ()):
        self.cache_dir = pathlib.Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent
        self.delay = delay
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        for prefix in legacy_tls_hosts:
            self.session.mount(prefix, LegacyCipherAdapter(pool_connections=16, pool_maxsize=16))
        self._guard = threading.Lock()
        self._host_locks: dict[str, threading.Lock] = {}
        self._host_last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}

    def _request(self, url: str, timeout: int = 25) -> requests.Response:
        host = urlparse(url).netloc
        with self._guard:
            lock = self._host_locks.setdefault(host, threading.Lock())
        with lock:
            wait = self.delay - (time.monotonic() - self._host_last.get(host, -self.delay))
            if wait > 0:
                time.sleep(wait)
            try:
                return self.session.get(url, timeout=timeout, allow_redirects=True)
            finally:
                self._host_last[host] = time.monotonic()

    def allowed(self, url: str) -> bool:
        """Whether robots.txt permits fetching `url`. Unreachable robots files count as no."""
        parts = urlparse(url)
        root = f"{parts.scheme}://{parts.netloc}"
        with self._guard:
            parser = self._robots.get(root)
        if parser is None:
            parser = _load_robots(lambda: self._request(f"{root}/robots.txt", timeout=15))
            with self._guard:
                self._robots[root] = parser
        return parser.can_fetch(self.user_agent, url)

    def get(self, url: str) -> Page:
        """Fetch `url` through the cache. Network failures return status 0 and are not cached."""
        path = self.cache_dir / f"{hashlib.sha1(url.encode()).hexdigest()}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return Page(data["status"], data["html"], data["final"])
        try:
            response = self._request(url)
        except requests.RequestException as e:
            print(f"  network error on {url}: {type(e).__name__}", flush=True)
            return Page(0, "", url)
        html = ""
        if "html" in response.headers.get("content-type", "") and len(response.content) <= MAX_BYTES:
            if not response.encoding or response.encoding.lower() == "iso-8859-1":
                response.encoding = response.apparent_encoding
            html = response.text
        path.write_text(
            json.dumps({"status": response.status_code, "html": html, "final": response.url}, ensure_ascii=False),
            encoding="utf-8",
        )
        return Page(response.status_code, html, response.url)


def _load_robots(fetch, attempts: int = ROBOTS_ATTEMPTS) -> urllib.robotparser.RobotFileParser:
    """Read robots.txt, retrying network errors. A host that stays unreachable is treated as disallowing everything."""
    parser = urllib.robotparser.RobotFileParser()
    for attempt in range(attempts):
        try:
            response = fetch()
            break
        except requests.RequestException:
            if attempt == attempts - 1:
                parser.disallow_all = True
                return parser
            time.sleep(ROBOTS_RETRY_SECONDS * (attempt + 1))
    if response.status_code in (401, 403):
        parser.disallow_all = True
    elif response.status_code == 200 and "html" not in response.headers.get("content-type", ""):
        parser.parse(response.text.splitlines())
        parser.modified()  # An empty robots.txt allows everything; mark it as read.
    else:
        parser.allow_all = True
    return parser
