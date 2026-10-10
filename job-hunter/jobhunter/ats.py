"""Deterministic ATS keyword analysis.

Applicant Tracking Systems mostly (1) parse the CV into fields and (2) rank by keyword overlap
with the advert. This module measures (2) so you can see the before/after effect of tailoring,
and lists keywords the advert wants that your CV does not show — those are *gaps to consider
honestly*, not words to paste in.
"""
from __future__ import annotations

import re
from collections import Counter

# Domain lexicon: multi-word phrases ATS filters commonly key on in logistics / SCM adverts.
LEXICON = [
    "supply chain management", "supply chain", "logistics", "procurement", "purchasing", "sourcing",
    "strategic sourcing", "supplier management", "vendor management", "contract management",
    "inventory management", "inventory control", "stock control", "stock take", "cycle count",
    "warehouse management", "warehousing", "distribution", "transport management", "fleet management",
    "route planning", "freight", "freight forwarding", "clearing and forwarding", "customs", "incoterms",
    "import", "export", "shipping", "last mile", "cold chain", "reverse logistics", "3pl",
    "demand planning", "supply planning", "forecasting", "s&op", "mrp", "erp", "sap", "sap mm",
    "oracle", "sage", "syspro", "wms", "tms", "power bi", "excel", "advanced excel", "data analysis",
    "pivot tables", "sql", "python", "tableau", "kpi", "kpis", "lean", "six sigma", "continuous improvement",
    "process improvement", "root cause analysis", "health and safety", "ohs", "iso 9001", "quality control",
    "cost reduction", "budget", "reporting", "stakeholder management", "communication", "teamwork",
    "problem solving", "attention to detail", "time management", "project management", "negotiation",
    "customer service", "order processing", "dispatch", "receiving", "goods receiving", "invoicing",
    "b-bbee", "pfma", "scm", "bcom", "bachelor", "degree", "diploma", "nqf", "driver's licence",
    "drivers licence", "code 8", "code 10", "forklift",
]

STOP = set("""a an the and or of to in for on with at by from as is are be been being this that these those
you your we our us will can may must should would could it its their they them he she his her i my
able ability within across per via into over under than then also such other more most all any each
job role position candidate candidates applicants applicant company team work working experience
years year required requirements requirement minimum preferred advantage responsibilities duties
include including includes key strong good excellent knowledge skills skill understanding using
""".split())


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def _contains(haystack: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", haystack) is not None


def extract_keywords(jd: str, top_n: int = 25) -> list[str]:
    """Lexicon phrases present in the advert, plus the advert's most repeated meaningful terms."""
    text = _clean(jd)
    found = [k for k in LEXICON if _contains(text, k)]
    # Drop sub-phrases already covered by a longer match ("supply chain" inside "supply chain management").
    found = [k for k in found if not any(k != o and k in o and _contains(text, o) for o in found)]
    tokens = [t for t in re.findall(r"[a-z][a-z0-9&+#/-]{2,}", text) if t not in STOP]
    freq = Counter(tokens)
    extra = [w for w, c in freq.most_common(60) if c >= 2 and not any(w in k for k in found)]
    return (found + extra)[:top_n]


def score(cv_text: str, keywords: list[str]) -> dict:
    cv = _clean(cv_text)
    matched = [k for k in keywords if _contains(cv, k)]
    missing = [k for k in keywords if k not in matched]
    pct = round(100 * len(matched) / len(keywords), 1) if keywords else 0.0
    return {"score": pct, "matched": matched, "missing": missing}
