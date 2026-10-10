"""Public careers-page APIs of companies you want to watch directly.

Many employers host jobs on Greenhouse, Lever or SmartRecruiters, which expose free,
key-less JSON feeds. Add the company's board slug to config.yaml under sources.companies.
These feeds include the FULL job description, which gives the best tailoring results.
"""
from __future__ import annotations

import logging

import requests

from ..models import Job
from ..text import USER_AGENT, html_to_text

log = logging.getLogger(__name__)
H = {"User-Agent": USER_AGENT}


def greenhouse(slug: str, name: str) -> list[Job]:
    r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"}, headers=H, timeout=20)
    r.raise_for_status()
    return [Job(
        title=j.get("title", ""),
        company=name,
        url=j.get("absolute_url", ""),
        source=f"greenhouse:{slug}",
        description=html_to_text(j.get("content", "")),
        location=(j.get("location") or {}).get("name", ""),
        posted_at=j.get("updated_at", ""),
    ) for j in r.json().get("jobs", [])]


def lever(slug: str, name: str) -> list[Job]:
    r = requests.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"}, headers=H, timeout=20)
    r.raise_for_status()
    jobs = []
    for j in r.json():
        parts = [j.get("descriptionPlain", "")]
        for section in j.get("lists", []):
            parts.append(f"{section.get('text', '')}\n{html_to_text(section.get('content', ''))}")
        parts.append(j.get("additionalPlain", ""))
        jobs.append(Job(
            title=j.get("text", ""),
            company=name,
            url=j.get("hostedUrl", ""),
            source=f"lever:{slug}",
            description="\n\n".join(p for p in parts if p),
            location=(j.get("categories") or {}).get("location", ""),
        ))
    return jobs


def smartrecruiters(slug: str, name: str) -> list[Job]:
    base = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    r = requests.get(base, params={"limit": 100}, headers=H, timeout=20)
    r.raise_for_status()
    jobs = []
    for j in r.json().get("content", []):
        loc = j.get("location") or {}
        jobs.append(Job(
            title=j.get("name", ""),
            company=name,
            url=f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}",
            source=f"smartrecruiters:{slug}",
            description="",  # fetched lazily at tailor time (detail call per posting)
            location=", ".join(x for x in (loc.get("city"), loc.get("country")) if x),
            posted_at=j.get("releasedDate", ""),
        ))
    return jobs


PLATFORMS = {"greenhouse": greenhouse, "lever": lever, "smartrecruiters": smartrecruiters}


def search(cfg: dict) -> list[Job]:
    jobs: list[Job] = []
    for c in cfg.get("sources", {}).get("companies", []) or []:
        fn = PLATFORMS.get(c.get("platform", ""))
        if not fn:
            log.warning("Unknown platform for %s: %s", c.get("name"), c.get("platform"))
            continue
        try:
            jobs.extend(fn(c["slug"], c.get("name", c["slug"])))
        except requests.RequestException as e:
            log.warning("%s (%s) failed: %s", c.get("name"), c.get("platform"), e)
    return jobs
