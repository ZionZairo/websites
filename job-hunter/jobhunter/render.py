"""Render a tailored CV as an ATS-safe .docx plus a plain-text copy.

ATS-safe means: one column, no tables/text boxes/images, contact details in the body (many parsers
skip page headers), standard section headings, a common font, real bullet styles, dates on the line.
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

EARLY_CAREER = {"graduate_programme", "internship", "learnership"}


def _lookup(master: dict, section: str) -> dict:
    return {i["id"]: i for i in master.get(section) or []}


def build_sections(master: dict, tailored: dict, category: str) -> list[tuple[str, list]]:
    """Ordered (heading, lines) pairs. Lines are str or ('bullet', str) or ('role', str, str)."""
    c = master.get("contact", {})
    sections: list[tuple[str, list]] = []

    sections.append(("PROFESSIONAL SUMMARY", [tailored.get("summary", "")]))
    if tailored.get("skills"):
        sections.append(("KEY SKILLS", [" | ".join(tailored["skills"])]))

    edu_lines: list = []
    for e in master.get("education") or []:
        edu_lines.append(("role", f"{e.get('qualification', '')} — {e.get('institution', '')}", str(e.get("year", ""))))
        edu_lines.extend(("bullet", d) for d in e.get("details") or [])

    exp_lines: list = []
    roles = _lookup(master, "experience")
    for item in tailored.get("experience") or []:
        r = roles[item["id"]]
        dates = f"{r.get('start', '')} – {r.get('end', 'Present')}".strip(" –")
        head = f"{r.get('title', '')} — {r.get('company', '')}" + (f", {r['location']}" if r.get("location") else "")
        exp_lines.append(("role", head, dates))
        exp_lines.extend(("bullet", b["text"]) for b in item["bullets"])

    prj_lines: list = []
    projects = _lookup(master, "projects")
    for item in tailored.get("projects") or []:
        p = projects[item["id"]]
        prj_lines.append(("role", p.get("name", ""), str(p.get("year", ""))))
        prj_lines.extend(("bullet", b["text"]) for b in item["bullets"])

    # Early-career adverts screen on qualifications first, so lead with education.
    ordered = [("EDUCATION", edu_lines), ("EXPERIENCE", exp_lines)]
    if category not in EARLY_CAREER:
        ordered.reverse()
    sections.extend((h, l) for h, l in ordered if l)
    if prj_lines:
        sections.append(("PROJECTS", prj_lines))

    certs = [f"{x.get('name', '')}, {x.get('issuer', '')} ({x.get('year', '')})".replace(", ()", "").replace(" ()", "")
             for x in master.get("certifications") or []]
    if certs:
        sections.append(("CERTIFICATIONS", [("bullet", x) for x in certs]))

    extras = master.get("extras") or {}
    extra_lines = [("bullet", f"{k.replace('_', ' ').title()}: {', '.join(v) if isinstance(v, list) else v}")
                   for k, v in extras.items() if v]
    if extra_lines:
        sections.append(("ADDITIONAL INFORMATION", extra_lines))
    if master.get("references"):
        sections.append(("REFERENCES", [master["references"]]))
    return sections


def contact_line(master: dict) -> str:
    c = master.get("contact", {})
    return " | ".join(str(c[k]) for k in ("phone", "email", "location", "linkedin") if c.get(k))


def to_docx(master: dict, tailored: dict, category: str, path: Path) -> None:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name, style.font.size = "Calibri", Pt(11)
    for s in doc.sections:
        s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Pt(54)

    name = doc.add_paragraph()
    run = name.add_run(master.get("contact", {}).get("name", ""))
    run.bold, run.font.size = True, Pt(18)
    name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for text in (tailored.get("headline", ""), contact_line(master)):
        p = doc.add_paragraph(text)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(2)

    for heading, lines in build_sections(master, tailored, category):
        h = doc.add_paragraph()
        r = h.add_run(heading)
        r.bold, r.font.size = True, Pt(12)
        h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(10), Pt(2)
        for line in lines:
            if isinstance(line, str):
                doc.add_paragraph(line)
            elif line[0] == "bullet":
                doc.add_paragraph(line[1], style="List Bullet")
            else:  # role line: bold title, dates after a tab-free separator (tabs confuse some parsers)
                p = doc.add_paragraph()
                p.add_run(line[1]).bold = True
                if line[2]:
                    p.add_run(f"   {line[2]}")
                p.paragraph_format.space_before = Pt(6)
    doc.save(path)


def to_text(master: dict, tailored: dict, category: str) -> str:
    out = [master.get("contact", {}).get("name", ""), tailored.get("headline", ""), contact_line(master), ""]
    for heading, lines in build_sections(master, tailored, category):
        out.append(heading)
        for line in lines:
            if isinstance(line, str):
                out.append(line)
            elif line[0] == "bullet":
                out.append(f"• {line[1]}")
            else:
                out.append(f"{line[1]}   {line[2]}".rstrip())
        out.append("")
    return "\n".join(out)


def safe_name(*parts: str) -> str:
    return "_".join(re.sub(r"[^A-Za-z0-9]+", "-", p).strip("-") for p in parts if p)[:120]
