"""Decide what kind of opportunity a posting is and how well it fits your target field.

Rules are plain keyword lists (editable in config.yaml) so every decision is explainable.
"""
from __future__ import annotations

import re

from .models import Job

CATEGORY_RULES = {
    # Order matters: the first match wins (a "graduate learnership" is a learnership).
    "learnership": [r"learnership", r"\bseta\b", r"\bteta\b", r"\bnqf\s*(level)?\s*\d", r"\byes\s+(programme|program|youth)", r"apprentice"],
    "internship": [r"\bintern(ship)?s?\b", r"in-?service train", r"work[- ]integrated learning", r"\bwil\b", r"experiential (learning|training)", r"vacation (work|programme)"],
    "graduate_programme": [r"graduate (programme|program|trainee|development|intake)", r"\bgraduate\b", r"management trainee", r"\btrainee\b", r"young professionals?"],
}

DEFAULT_FIELD_TERMS = [
    "logistics", "supply chain", "procurement", "purchasing", "buyer", "warehouse", "warehousing",
    "inventory", "stock control", "distribution", "transport", "fleet", "freight", "shipping",
    "clearing", "forwarding", "customs", "import", "export", "demand planning", "supply planning",
    "planner", "materials", "sourcing", "operations", "dispatch", "fulfilment", "fulfillment",
    "3pl", "last mile", "cold chain", "port", "rail", "courier", "s&op", "mrp", "wms", "tms",
]


def _hits(patterns: list[str], text: str) -> int:
    return sum(1 for p in patterns if re.search(p, text, re.I))


def categorise(job: Job) -> str:
    title, body = job.title.lower(), job.description.lower()
    for cat, pats in CATEGORY_RULES.items():
        if _hits(pats, title):
            return cat
    # Body-only signals are weaker; require the strongest phrases.
    if re.search(r"learnership|\bnqf\s*level", body):
        return "learnership"
    if re.search(r"internship|in-?service training|work[- ]integrated learning", body):
        return "internship"
    if re.search(r"graduate (programme|program)", body):
        return "graduate_programme"
    return "job"


def relevance(job: Job, cfg: dict) -> float:
    """0-100. Title matches count 3x — a 'Supply Chain Intern' beats an admin job that mentions 'stock'."""
    terms = cfg.get("search", {}).get("field_terms") or DEFAULT_FIELD_TERMS
    title, body = job.title.lower(), job.description.lower()
    t = sum(1 for k in terms if k in title)
    b = sum(1 for k in terms if k in body)
    score = min(100.0, t * 35 + b * 8)
    return round(score, 1)


def excluded(job: Job, cfg: dict) -> bool:
    """Drop roles that are clearly above entry level or otherwise unwanted."""
    words = cfg.get("search", {}).get("exclude_title_words", [])
    title = job.title.lower()
    return any(re.search(rf"\b{re.escape(w.lower())}\b", title) for w in words)


def enrich(job: Job, cfg: dict) -> Job:
    job.category = categorise(job)
    job.relevance = relevance(job, cfg)
    return job
