"""Produce a job-specific CV from the master CV.

Two engines:
  * claude   — Claude rewrites the summary and rephrases/reorders bullets in the advert's language.
  * keywords — offline fallback: reorders skills and bullets by keyword overlap, no rewording.

Whatever the engine, `validate()` enforces the no-fabrication rule: every bullet must trace to a
master-CV bullet, skills must come from the master list, and no new numbers may appear.
"""
from __future__ import annotations

import json
import logging
import re

from . import ats
from .config import secret
from .cv import all_skills, bullet_index
from .models import Job

log = logging.getLogger(__name__)

SYSTEM = """You are an expert CV writer for logistics and supply chain roles, graduate programmes,
internships and learnerships (South African market; adverts may use SA terms like NQF, SETA, B-BBEE).

Your job: tailor the candidate's MASTER CV to one job advert so it ranks well in an Applicant Tracking
System AND reads well to a recruiter.

Hard rules — breaking any of these makes the CV dishonest and unusable:
1. Use ONLY facts in the master CV. Never invent employers, dates, tools, qualifications, metrics or duties.
2. Every bullet you output must cite the master bullet it comes from (source_id). You may rephrase it to
   mirror the advert's wording where the meaning is genuinely the same (e.g. "stock counts" -> "cycle
   counts" only if that is what was done). Do not add numbers that are not in the source bullet.
3. Skills must be chosen from the master skills list, exactly as written there. Put the most relevant first.
4. If the advert asks for something the candidate does not have, list it under `gaps` — do not hide it in the CV.

Tailoring guidance:
- Summary: 2-3 sentences, targeted at this role and level, using the advert's key terms truthfully.
- Headline: the advert's job title (or the closest honest version) e.g. "Supply Chain Graduate".
- Keep the 3-5 most relevant bullets per role; drop irrelevant roles' bullets down to 1-2 rather than deleting the role.
- Start bullets with strong verbs; keep each under ~25 words.
"""

TOOL = {
    "name": "submit_tailored_cv",
    "description": "Return the tailored CV content.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string"},
            "summary": {"type": "string"},
            "skills": {"type": "array", "items": {"type": "string"}},
            "experience": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"},
                "bullets": {"type": "array", "items": {"type": "object", "properties": {
                    "source_id": {"type": "string"}, "text": {"type": "string"}},
                    "required": ["source_id", "text"]}}},
                "required": ["id", "bullets"]}},
            "projects": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"},
                "bullets": {"type": "array", "items": {"type": "object", "properties": {
                    "source_id": {"type": "string"}, "text": {"type": "string"}},
                    "required": ["source_id", "text"]}}},
                "required": ["id", "bullets"]}},
            "gaps": {"type": "array", "items": {"type": "string"},
                     "description": "Advert requirements the candidate does not evidence."},
        },
        "required": ["headline", "summary", "skills", "experience", "gaps"],
    },
}


def _overlap(text: str, keywords: list[str]) -> int:
    t = text.lower()
    return sum(1 for k in keywords if k in t)


def keyword_engine(master: dict, job: Job, keywords: list[str], bullets_per_role: int = 4) -> dict:
    skills = sorted(all_skills(master), key=lambda s: -_overlap(s, keywords))
    out = {"headline": job.title or master.get("headline", ""), "summary": master.get("summary", ""),
           "skills": skills, "experience": [], "projects": [], "gaps": []}
    for section in ("experience", "projects"):
        for item in master.get(section) or []:
            ranked = sorted(item["bullets"], key=lambda b: -_overlap(b["text"], keywords))
            out[section].append({"id": item["id"], "bullets": [
                {"source_id": b["id"], "text": b["text"]} for b in ranked[:bullets_per_role]]})
    return out


def claude_engine(master: dict, job: Job, keywords: list[str], model: str) -> dict:
    import anthropic  # imported lazily so the offline engine needs no API package

    client = anthropic.Anthropic()
    master_view = {k: v for k, v in master.items() if k != "contact"}  # no need to send personal contact info
    prompt = (
        f"JOB ADVERT\nTitle: {job.title}\nCompany: {job.company}\nCategory: {job.category}\n"
        f"Location: {job.location}\n\n{job.description[:12000]}\n\n"
        f"ATS KEYWORDS DETECTED IN ADVERT: {', '.join(keywords)}\n\n"
        f"MASTER CV (YAML-like JSON; bullet ids are the source_ids you must cite):\n"
        f"{json.dumps(master_view, indent=1, ensure_ascii=False)}"
    )
    msg = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": TOOL["name"]},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in msg.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("Claude returned no tailored CV")


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", text))


def validate(master: dict, tailored: dict) -> list[str]:
    """Strip anything not traceable to the master CV. Returns human-readable warnings."""
    warnings: list[str] = []
    src = bullet_index(master)
    master_skills = {s.lower(): s for s in all_skills(master)}

    kept = []
    for s in tailored.get("skills", []):
        if s.lower() in master_skills:
            kept.append(master_skills[s.lower()])
        else:
            warnings.append(f"Dropped skill not in master CV: {s!r}")
    tailored["skills"] = list(dict.fromkeys(kept))

    for section in ("experience", "projects"):
        valid_ids = {i["id"] for i in master.get(section) or []}
        clean = []
        for item in tailored.get(section) or []:
            if item.get("id") not in valid_ids:
                warnings.append(f"Dropped unknown {section} entry {item.get('id')!r}")
                continue
            bullets = []
            for b in item.get("bullets", []):
                original = src.get(b.get("source_id", ""))
                if original is None or not b.get("source_id", "").startswith(item["id"] + "."):
                    warnings.append(f"Dropped untraceable bullet: {b.get('text', '')[:60]!r}")
                    continue
                new_nums = _numbers(b["text"]) - _numbers(original)
                if new_nums:
                    warnings.append(f"Reverted bullet {b['source_id']} (new numbers {sorted(new_nums)})")
                    b = {"source_id": b["source_id"], "text": original}
                bullets.append(b)
            clean.append({"id": item["id"], "bullets": bullets})
        tailored[section] = clean
    return warnings


def tailor(master: dict, job: Job, cfg: dict) -> tuple[dict, list[str], list[str]]:
    """Returns (tailored_cv, ats_keywords, warnings)."""
    tcfg = cfg.get("tailor", {})
    keywords = ats.extract_keywords(job.description or job.title, top_n=tcfg.get("keywords", 25))
    engine = tcfg.get("engine", "claude")
    if engine == "claude" and not secret("ANTHROPIC_API_KEY"):
        log.warning("ANTHROPIC_API_KEY not set — using offline keyword engine (reorders, no rewording)")
        engine = "keywords"
    if engine == "claude":
        tailored = claude_engine(master, job, keywords, tcfg.get("model", "claude-sonnet-5-5"))
    else:
        tailored = keyword_engine(master, job, keywords, tcfg.get("bullets_per_role", 4))
    warnings = validate(master, tailored)
    tailored["engine"] = engine
    return tailored, keywords, warnings
