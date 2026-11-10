"""Split the publication list on a directory profile into separate entries."""
from __future__ import annotations

import re

MIN_ENTRY_CHARS = 30


def split_publications(text: str | None) -> list[str]:
    """Split a numbered publication list such as '1. A ... 2. B ...' or 'J1) A ...'."""
    parts = re.split(r"(?:(?<=\s)|^)(?:[JCPjcp]?\d{1,3}[.)、]|\[\d{1,3}\])\s+", text or "")
    return [part.strip() for part in parts if len(part.strip()) >= MIN_ENTRY_CHARS]
