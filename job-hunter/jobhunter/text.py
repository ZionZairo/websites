"""HTML-to-text and page fetching helpers (stdlib only)."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

import requests

USER_AGENT = "Mozilla/5.0 (job-hunter personal tool)"
_BLOCK = {"p", "br", "li", "div", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "ul", "ol", "section"}


class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "nav", "footer", "header"):
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n- " if tag == "li" else "\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "nav", "footer", "header") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    raw = html.unescape(raw)  # Greenhouse double-encodes its HTML
    s = _Stripper()
    s.feed(raw)
    text = "".join(s.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def fetch_text(url: str, timeout: int = 20) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return html_to_text(resp.text)
