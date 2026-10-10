"""Command line: search → review → tailor → track.

  python -m jobhunter search                 find new opportunities and store them
  python -m jobhunter list [--category X]    show what was found, best fit first
  python -m jobhunter add --url URL          add an advert you found yourself (LinkedIn, PNet, etc.)
  python -m jobhunter tailor ID              build a tailored CV for one job
  python -m jobhunter run                    search, then tailor the top new matches
  python -m jobhunter status ID applied      update the application tracker
  python -m jobhunter export                 write tracker.csv
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import ats, classify, render
from .config import load_config, resolve
from .cv import load_master, to_text as master_text
from .models import Job
from .sources import adzuna, ats_boards
from .store import Store
from .tailor import tailor
from .text import fetch_text

log = logging.getLogger("jobhunter")
SOURCES = {"adzuna": adzuna.search, "companies": ats_boards.search}
LABEL = {"graduate_programme": "GRAD", "internship": "INTERN", "learnership": "LEARN", "job": "JOB"}


def cmd_search(cfg, store, args) -> list[Job]:
    found: list[Job] = []
    for name, fn in SOURCES.items():
        if cfg.get("sources", {}).get(name, {}) is False:
            continue
        jobs = fn(cfg)
        log.info("%s: %d postings", name, len(jobs))
        found.extend(jobs)

    wanted = set(cfg.get("search", {}).get("categories") or LABEL)
    min_rel = cfg.get("search", {}).get("min_relevance", 30)
    new = []
    for job in found:
        classify.enrich(job, cfg)
        if classify.excluded(job, cfg) or job.category not in wanted or job.relevance < min_rel:
            continue
        if store.upsert(job):
            new.append(job)
    new.sort(key=lambda j: -j.relevance)
    print(f"\n{len(new)} new matching opportunities ({len(found)} postings scanned)\n")
    _print(new)
    return new


def _print(jobs: list[Job]) -> None:
    for j in jobs:
        print(f"  {j.id}  [{LABEL.get(j.category, j.category):6}] {j.relevance:5.1f}  {j.title} — {j.company}"
              f" ({j.location})  [{j.status}]")
        print(f"              {j.url}")


def cmd_list(cfg, store, args):
    _print(store.list(status=args.status, category=args.category, min_relevance=args.min))


def cmd_add(cfg, store, args):
    if args.file:
        desc = Path(args.file).read_text() if args.file != "-" else sys.stdin.read()
    elif args.url:
        desc = fetch_text(args.url)
    else:
        sys.exit("Give --url or --file (use --file - to paste from stdin)")
    job = Job(title=args.title or "", company=args.company or "", url=args.url or "", source="manual",
              description=desc, location=args.location or "")
    if not job.title:
        job.title = next((l.strip() for l in desc.splitlines() if l.strip()), "Untitled")[:100]
    classify.enrich(job, cfg)
    store.upsert(job)
    print(f"Added {job.id}: {job.title} — {job.company} [{job.category}, fit {job.relevance}]")


def _ensure_description(store: Store, job: Job) -> Job:
    """Aggregator snippets are short; try the full advert page before tailoring."""
    if len(job.description) >= 1200 or not job.url:
        return job
    try:
        full = fetch_text(job.url)
        if len(full) > len(job.description):
            job.description = full[:20000]
            store.update(job.id, description=job.description)
    except Exception as e:  # noqa: BLE001 — any fetch failure just means we keep the snippet
        log.warning("Could not fetch full advert (%s). Tailoring from the %d-char snippet; "
                    "for best results re-add it with: add --file advert.txt", e, len(job.description))
    return job


def cmd_tailor(cfg, store, args, job: Job | None = None):
    job = job or store.get(args.id)
    if not job:
        sys.exit(f"No job with id {args.id}")
    job = _ensure_description(store, job)
    master = load_master(resolve(cfg, "master_cv", "profile/master_cv.yaml"))
    tailored, keywords, warnings = tailor(master, job, cfg)

    out_dir = resolve(cfg, "output", "output") / render.safe_name(job.company, job.title, job.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = master.get("contact", {}).get("name", "CV")
    docx_path = out_dir / f"{render.safe_name(name, 'CV', job.company)}.docx"
    render.to_docx(master, tailored, job.category, docx_path)
    cv_txt = render.to_text(master, tailored, job.category)
    (out_dir / "cv.txt").write_text(cv_txt)
    (out_dir / "advert.txt").write_text(f"{job.title}\n{job.company}\n{job.url}\n\n{job.description}")

    before = ats.score(master_text(master), keywords)
    after = ats.score(cv_txt, keywords)
    report = [
        f"# {job.title} — {job.company}",
        f"Category: {job.category} | Fit: {job.relevance} | Engine: {tailored['engine']}",
        f"URL: {job.url}", "",
        f"## ATS keyword match: {before['score']}% (master CV) → {after['score']}% (tailored CV)",
        f"Matched: {', '.join(after['matched']) or '-'}",
        f"Missing: {', '.join(after['missing']) or '-'}", "",
        "## Gaps to address honestly (cover letter, or upskill — do not paste into CV)",
        *[f"- {g}" for g in tailored.get("gaps") or ["(none flagged)"]], "",
        "## Integrity checks", *[f"- {w}" for w in warnings or ["All content traced to master CV."]], "",
        "## Before you submit",
        "- Read the CV once end to end — you are accountable for every line.",
        "- Check the closing date and any required documents (ID, transcripts, matric certificate).",
        "- Save as PDF only if the advert asks for it; .docx parses most reliably in ATS.",
    ]
    (out_dir / "report.md").write_text("\n".join(report))
    (out_dir / "tailored.json").write_text(json.dumps(tailored, indent=2, ensure_ascii=False))
    store.update(job.id, status="tailored" if job.status == "new" else job.status, cv_path=str(docx_path))
    print(f"✓ {job.title} — {job.company}: ATS {before['score']}% → {after['score']}%  ->  {docx_path}")
    if warnings:
        print(f"  {len(warnings)} integrity warning(s) — see {out_dir / 'report.md'}")


def cmd_run(cfg, store, args):
    new = cmd_search(cfg, store, args)
    limit = args.limit if args.limit is not None else cfg.get("tailor", {}).get("auto_tailor_top", 5)
    for job in new[:limit]:
        try:
            cmd_tailor(cfg, store, args, job=job)
        except Exception as e:  # noqa: BLE001 — one bad advert must not stop the batch
            log.error("Tailoring %s failed: %s", job.id, e)


def cmd_status(cfg, store, args):
    job = store.get(args.id)
    if not job:
        sys.exit(f"No job with id {args.id}")
    store.update(job.id, status=args.status)
    print(f"{job.id} {job.title} → {args.status}")


def cmd_export(cfg, store, args):
    path = resolve(cfg, "tracker_csv", "data/tracker.csv")
    store.export_csv(path)
    print(f"Wrote {path}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="jobhunter", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("search")
    s = sub.add_parser("list")
    s.add_argument("--status")
    s.add_argument("--category", choices=list(LABEL))
    s.add_argument("--min", type=float, default=0)
    s = sub.add_parser("add")
    s.add_argument("--url")
    s.add_argument("--file")
    s.add_argument("--title")
    s.add_argument("--company")
    s.add_argument("--location")
    s = sub.add_parser("tailor")
    s.add_argument("id")
    s = sub.add_parser("run")
    s.add_argument("--limit", type=int)
    s = sub.add_parser("status")
    s.add_argument("id")
    s.add_argument("status", choices=["new", "tailored", "applied", "interview", "rejected", "offer", "skipped"])
    sub.add_parser("export")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config(args.config)
    store = Store(resolve(cfg, "database", "data/jobs.db"))
    {"search": cmd_search, "list": cmd_list, "add": cmd_add, "tailor": cmd_tailor, "run": cmd_run,
     "status": cmd_status, "export": cmd_export}[args.cmd](cfg, store, args)


if __name__ == "__main__":
    main()
