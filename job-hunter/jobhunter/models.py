"""Core data types shared across sources, storage and tailoring."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


@dataclass
class Job:
    title: str
    company: str
    url: str
    source: str
    description: str = ""
    location: str = ""
    posted_at: str = ""
    closing_date: str = ""
    category: str = "job"          # job | graduate_programme | internship | learnership
    relevance: float = 0.0         # 0-100 fit to your target field
    status: str = "new"            # new | tailored | applied | interview | rejected | offer | skipped
    cv_path: str = ""
    found_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    @property
    def id(self) -> str:
        """Stable id: the same role at the same company dedupes across sources."""
        key = f"{_norm(self.title)}|{_norm(self.company)}|{_norm(self.location)}"
        return hashlib.sha1(key.encode()).hexdigest()[:10]
