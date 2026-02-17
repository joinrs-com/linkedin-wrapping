"""Step 2: detect language (Italian / English). Output for job_enrichment.detected_language only."""

from __future__ import annotations

import re
from typing import Optional

# Simple heuristic: Italian-specific patterns vs English. No external lib required for baseline.
ITA_PATTERNS = re.compile(
    r"\b(il\s|la\s|di\s|del\s|della\s|per\s|con\s|nel\s|nella\s|un\s|una\s|e\s|che\s|sono\s|siamo\s|presso\s|offerta\s|ricerca\s|azienda\s|lavoro\s|titolo\s|esperienza\s|anni\s|requisiti\s|laurea\s|diploma)\b",
    re.I,
)
ENG_PATTERNS = re.compile(
    r"\b(the\s|and\s|for\s|with\s|you\s|we\s|are\s|is\s|company\s|experience\s|years\s|required\s|degree\s|team\s|work\s|job\s|position)\b",
    re.I,
)


def detect_language(normalized_text: str) -> str:
    """
    Detect italian or english. Returns 'it' or 'en'.
    Uses simple keyword counts; no LLM. For job_enrichment.detected_language only.
    """
    if not normalized_text or not normalized_text.strip():
        return "en"
    it_count = len(ITA_PATTERNS.findall(normalized_text))
    en_count = len(ENG_PATTERNS.findall(normalized_text))
    return "it" if it_count >= en_count else "en"
