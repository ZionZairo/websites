"""Offline tests: classification, ATS scoring, tailoring integrity and rendering."""
from pathlib import Path

from jobhunter import ats, classify, render
from jobhunter.cv import load_master, to_text
from jobhunter.models import Job
from jobhunter.tailor import keyword_engine, validate

HERE = Path(__file__).parent
MASTER = load_master(HERE.parent / "profile" / "master_cv.example.yaml")
ADVERT = (HERE / "sample_advert.txt").read_text()
CFG = {"search": {"exclude_title_words": ["senior", "manager"]}}


def job(title="Supply Chain Graduate Programme 2027", desc=ADVERT):
    return classify.enrich(Job(title=title, company="Example Manufacturing", url="", source="test", description=desc), CFG)


def test_categories():
    assert job().category == "graduate_programme"
    assert job("Logistics Learnership NQF 4", "").category == "learnership"
    assert job("Supply Chain Intern", "").category == "internship"
    assert job("Logistics Coordinator", "").category == "job"


def test_relevance_and_exclusion():
    assert job().relevance >= 30
    assert job("Receptionist", "Answer phones").relevance < 30
    assert classify.excluded(job("Senior Supply Chain Manager", ""), CFG)


def test_keywords_found():
    kws = ats.extract_keywords(ADVERT)
    for k in ("procurement", "demand planning", "sap", "pivot tables"):
        assert k in kws


def test_tailoring_raises_ats_score():
    kws = ats.extract_keywords(ADVERT)
    t = keyword_engine(MASTER, job(), kws)
    assert validate(MASTER, t) == []
    txt = render.to_text(MASTER, t, "graduate_programme")
    assert ats.score(txt, kws)["score"] >= ats.score(to_text(MASTER), kws)["score"] * 0.9
    # Early-career roles lead with education.
    assert txt.index("EDUCATION") < txt.index("EXPERIENCE")


def test_validate_blocks_fabrication():
    t = {
        "skills": ["SAP", "Oracle TMS"],                                    # Oracle TMS is not in master
        "experience": [
            {"id": "exp1", "bullets": [
                {"source_id": "exp1.1", "text": "Counted 5,000 SKUs weekly"},  # number not in source
                {"source_id": "exp9.1", "text": "Managed a fleet of 40 trucks"},  # no such source
            ]},
            {"id": "exp7", "bullets": []},                                   # no such role
        ],
    }
    warnings = validate(MASTER, t)
    assert t["skills"] == ["SAP"]
    assert len(t["experience"]) == 1 and len(t["experience"][0]["bullets"]) == 1
    assert "1,200" in t["experience"][0]["bullets"][0]["text"]               # reverted to original
    assert len(warnings) == 4


def test_docx_renders(tmp_path):
    kws = ats.extract_keywords(ADVERT)
    t = keyword_engine(MASTER, job(), kws)
    out = tmp_path / "cv.docx"
    render.to_docx(MASTER, t, "graduate_programme", out)
    from docx import Document
    text = "\n".join(p.text for p in Document(out).paragraphs)
    assert "Thabo Example" in text and "EDUCATION" in text
    assert not Document(out).tables                                          # ATS-safe: no tables
