"""Step 5: extract seniority. Regex + dict; LLM only if ambiguous."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from enrichment.llm import call_openai_chat, llm_budget_exhausted
from enrichment.taxonomy_cache import TaxonomyCache

# Patterns and mapping to standard codes (must match seniority_levels.code in DB)
SENIORITY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bstage\b|\btirocinio\b", re.I), "internship"),
    (re.compile(r"\bapprendistato\b", re.I), "apprenticeship"),
    (re.compile(r"\bsenza\s+esperienza\b|\bnessuna\s+esperienza\b|entry\s+level\b", re.I), "entry_level"),
    (re.compile(r"\b(1|2)\s*[-]?\s*anni\b|\bjunior\b|\b0\s*[-]?\s*2\s*anni\b", re.I), "junior"),
    (re.compile(r"\b(3|4|5)\s*anni\b|\bmid\b|\b3\s*[-]?\s*5\s*anni\b", re.I), "mid_level"),
    (re.compile(r"\bpluriennale\b|\besperto\b|\bsenior\b|\b(5|6|7|8|9|\d{2,})\s*\+?\s*anni\b", re.I), "senior"),
    (re.compile(r"\bcapo\s*turno\b|\bresponsabile\b|\bcoordinamento\b|\bteam\s*leader\b|\bmanager\b", re.I), "manager"),
]


@dataclass
class SeniorityResult:
    seniority_id: Optional[int]
    seniority_confidence: float
    seniority_method: str
    explanation: Optional[dict] = None


# Default seniority code when no rule/LLM match (by collar)
DEFAULT_SENIORITY_CODE_BLUE = "entry_level"
DEFAULT_SENIORITY_CODE_WHITE = "mid_level"


def classify_seniority_rule(
    normalized_text: str, cache: TaxonomyCache, collar_type: str = "blue"
) -> Optional[SeniorityResult]:
    """First match wins (order: internship, apprenticeship, entry, junior, mid, senior, manager)."""
    for pattern, code in SENIORITY_PATTERNS:
        if pattern.search(normalized_text):
            sid = cache.get_seniority_id_by_code_or_name(code, collar_type)
            if sid is not None:
                return SeniorityResult(
                    seniority_id=sid,
                    seniority_confidence=0.85,
                    seniority_method="rule",
                    explanation={"trigger": code, "pattern": pattern.pattern[:50]},
                )
            return None
    return None


def _valid_seniority_codes(cache: TaxonomyCache) -> list[str]:
    """Codes the LLM may choose from: cache normalized_label/code if any, else our pattern codes."""
    from_cache = [
        (s.normalized_label or s.code) for s in cache.seniority_levels
        if (s.normalized_label or s.code)
    ]
    if from_cache:
        return from_cache
    return [code for _, code in SENIORITY_PATTERNS]


def classify_seniority_llm(
    normalized_text: str,
    cache: TaxonomyCache,
    collar_type: str = "blue",
) -> Optional[SeniorityResult]:
    """LLM picks among known seniority codes. Resolve id by code_or_name."""
    if llm_budget_exhausted() or not cache.seniority_levels:
        return None
    codes = _valid_seniority_codes(cache)
    if not codes:
        return None
    collar_hint = "This is a %s collar job; prefer levels typical for this context." % (
        "white" if collar_type == "white" else "blue"
    )
    prompt = (
        "Choose the best seniority level for this job. Reply with JSON: {\"code\": \"<code>\"}. "
        "Valid codes only: " + ", ".join(codes) + ". " + collar_hint + "\n\nText: " + (normalized_text[:1000] or "")
    )
    out = call_openai_chat([{"role": "user", "content": prompt}], json_mode=True)
    if not out:
        return None
    try:
        data = json.loads(out)
        code = data.get("code", "")
        if code not in codes:
            code = codes[0]
        sid = cache.get_seniority_id_by_code_or_name(code, collar_type)
        if sid is None:
            sid = cache.seniority_levels[0].id
        return SeniorityResult(
            seniority_id=sid,
            seniority_confidence=0.70,
            seniority_method="llm",
            explanation={"llm_code": code},
        )
    except (json.JSONDecodeError, TypeError):
        return None


def classify_seniority(
    normalized_text: str,
    cache: TaxonomyCache,
    collar_type: str = "blue",
) -> SeniorityResult:
    """Extract seniority; rule first, then LLM. Default by collar if no match."""
    result = classify_seniority_rule(normalized_text, cache, collar_type)
    if result is not None:
        return result
    result = classify_seniority_llm(normalized_text, cache, collar_type)
    if result is not None:
        return result
    default_code = DEFAULT_SENIORITY_CODE_WHITE if collar_type == "white" else DEFAULT_SENIORITY_CODE_BLUE
    first_id = cache.get_seniority_id_by_code_or_name(default_code, collar_type)
    if first_id is None and cache.seniority_levels:
        first_id = cache.seniority_levels[0].id
    return SeniorityResult(
        seniority_id=first_id,
        seniority_confidence=0.5,
        seniority_method="default",
        explanation={"reason": "no_match", "default_code": default_code},
    )
