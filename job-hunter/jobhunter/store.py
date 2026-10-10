"""SQLite tracker: every job found, its category, fit score, CV path and application status."""
from __future__ import annotations

import csv
import sqlite3
from dataclasses import asdict, fields
from pathlib import Path

from .models import Job

COLS = [f.name for f in fields(Job)]


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        cols = ", ".join(f"{c} TEXT" if c != "relevance" else f"{c} REAL" for c in COLS)
        self.db.execute(f"CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, {cols})")
        self.db.commit()

    def upsert(self, job: Job) -> bool:
        """Insert a new job; returns True if it was new. Existing rows keep their status/CV."""
        if self.db.execute("SELECT 1 FROM jobs WHERE id=?", (job.id,)).fetchone():
            # Keep the longest description we have seen (company feeds beat aggregator snippets).
            self.db.execute(
                "UPDATE jobs SET description=? WHERE id=? AND length(coalesce(description,'')) < ?",
                (job.description, job.id, len(job.description)),
            )
            self.db.commit()
            return False
        d = asdict(job)
        self.db.execute(
            f"INSERT INTO jobs (id, {', '.join(COLS)}) VALUES (?, {', '.join('?' for _ in COLS)})",
            [job.id] + [d[c] for c in COLS],
        )
        self.db.commit()
        return True

    def get(self, job_id: str) -> Job | None:
        row = self.db.execute("SELECT * FROM jobs WHERE id LIKE ?", (job_id + "%",)).fetchone()
        return Job(**{c: row[c] for c in COLS}) if row else None

    def update(self, job_id: str, **values) -> None:
        sets = ", ".join(f"{k}=?" for k in values)
        self.db.execute(f"UPDATE jobs SET {sets} WHERE id=?", [*values.values(), job_id])
        self.db.commit()

    def list(self, status: str | None = None, category: str | None = None, min_relevance: float = 0) -> list[Job]:
        q, args = "SELECT * FROM jobs WHERE relevance >= ?", [min_relevance]
        if status:
            q += " AND status=?"
            args.append(status)
        if category:
            q += " AND category=?"
            args.append(category)
        q += " ORDER BY relevance DESC, found_at DESC"
        return [Job(**{c: r[c] for c in COLS}) for r in self.db.execute(q, args)]

    def export_csv(self, path: Path) -> None:
        jobs = self.list()
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            keep = ["title", "company", "category", "relevance", "location", "status", "url", "cv_path", "found_at", "closing_date"]
            w.writerow(["id"] + keep)
            for j in jobs:
                w.writerow([j.id] + [getattr(j, k) for k in keep])
