"""Adzuna job search API — aggregates many SA boards. Free key: https://developer.adzuna.com/

Note: Adzuna returns only a ~500-char description snippet. The tailor step fetches the
full advert from the job URL when it can; otherwise paste the advert in with `add`.
"""
from __future__ import annotations

import logging

import requests

from ..config import secret
from ..models import Job

log = logging.getLogger(__name__)
API = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def search(cfg: dict) -> list[Job]:
    app_id, app_key = secret("ADZUNA_APP_ID"), secret("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        log.warning("Adzuna skipped: set ADZUNA_APP_ID and ADZUNA_APP_KEY")
        return []
    opts = cfg.get("sources", {}).get("adzuna", {})
    country = opts.get("country", "za")
    jobs: list[Job] = []
    for query in cfg.get("search", {}).get("queries", []):
        for where in cfg.get("search", {}).get("locations", [""]):
            for page in range(1, opts.get("pages", 1) + 1):
                params = {
                    "app_id": app_id,
                    "app_key": app_key,
                    "what": query,
                    "results_per_page": opts.get("results_per_page", 50),
                    "max_days_old": cfg.get("search", {}).get("max_days_old", 14),
                    "content-type": "application/json",
                }
                if where:
                    params["where"] = where
                try:
                    r = requests.get(API.format(country=country, page=page), params=params, timeout=20)
                    r.raise_for_status()
                except requests.RequestException as e:
                    log.warning("Adzuna '%s' %s failed: %s", query, where, e)
                    break
                results = r.json().get("results", [])
                for item in results:
                    jobs.append(Job(
                        title=item.get("title", "").replace("<strong>", "").replace("</strong>", ""),
                        company=(item.get("company") or {}).get("display_name", ""),
                        url=item.get("redirect_url", ""),
                        source="adzuna",
                        description=item.get("description", ""),
                        location=(item.get("location") or {}).get("display_name", ""),
                        posted_at=item.get("created", ""),
                    ))
                if len(results) < params["results_per_page"]:
                    break
    return jobs
