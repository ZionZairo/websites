"""Master CV: the single source of truth every tailored CV is built from.

Tailoring may select, reorder and reword what is here — it may never add facts that are not.
"""
from __future__ import annotations

from pathlib import Path

import yaml


def load_master(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Copy profile/master_cv.example.yaml to profile/master_cv.yaml and fill it in."
        )
    cv = yaml.safe_load(path.read_text())
    # Give every role / project / bullet a stable id so tailored output can be traced to its source.
    for section, prefix in (("experience", "exp"), ("projects", "prj")):
        for i, item in enumerate(cv.get(section) or [], 1):
            item.setdefault("id", f"{prefix}{i}")
            item["bullets"] = [
                b if isinstance(b, dict) else {"text": b} for b in (item.get("bullets") or [])
            ]
            for j, b in enumerate(item["bullets"], 1):
                b.setdefault("id", f"{item['id']}.{j}")
    return cv


def all_skills(cv: dict) -> list[str]:
    skills = cv.get("skills") or []
    if isinstance(skills, dict):
        return [s for group in skills.values() for s in (group or [])]
    return list(skills)


def bullet_index(cv: dict) -> dict[str, str]:
    return {
        b["id"]: b["text"]
        for section in ("experience", "projects")
        for item in cv.get(section) or []
        for b in item["bullets"]
    }


def to_text(cv: dict) -> str:
    """Flatten the master CV to plain text for ATS keyword scoring."""
    parts = [cv.get("headline", ""), cv.get("summary", ""), " ".join(all_skills(cv))]
    for section in ("experience", "projects"):
        for item in cv.get(section) or []:
            parts.append(f"{item.get('title', '')} {item.get('name', '')} {item.get('company', '')}")
            parts.extend(b["text"] for b in item["bullets"])
    for e in cv.get("education") or []:
        parts.append(f"{e.get('qualification', '')} {e.get('institution', '')} {' '.join(e.get('details') or [])}")
    for c in cv.get("certifications") or []:
        parts.append(f"{c.get('name', '')} {c.get('issuer', '')}")
    extras = cv.get("extras") or {}
    parts.extend(str(v) if not isinstance(v, list) else " ".join(map(str, v)) for v in extras.values())
    return "\n".join(p for p in parts if p)
