"""Step 3: classify blue vs white collar. Rule-based first; LLM fallback only when uncertain."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from enrichment.llm import call_openai_chat, llm_budget_exhausted

# Strong signals (word boundary)
BLUE_KEYWORDS = re.compile(
    r"\b(operaio|magazziniere|saldatore|manutentore|mulettista|autista|addetto|facchino|"
    r"operai|magazzinieri|saldatori|manutentori|mulettisti|autisti|addetti|facchini)\b",
    re.I,
)
WHITE_KEYWORDS = re.compile(
    r"\b(developer|analyst|consultant|marketing|hr\s|accountant|manager|"
    r"sviluppatore|consulente|analista|responsabile)\b",
    re.I,
)


@dataclass
class CollarResult:
    collar_type: str  # "blue" | "white"
    confidence: float
    method: str  # "rule" | "llm"
    explanation: Optional[dict] = None


def classify_collar_rule(
    normalized_title: str,
    normalized_text: str,
    *,
    title_only: bool = False,
) -> Optional[CollarResult]:
    """Rule-based classification. Returns None if uncertain. If title_only=True, use only title (avoids false positives from description)."""
    text = normalized_title if title_only else f"{normalized_title} {normalized_text}"
    blue_count = len(BLUE_KEYWORDS.findall(text))
    white_count = len(WHITE_KEYWORDS.findall(text))
    if blue_count > white_count and blue_count >= 1:
        return CollarResult(
            collar_type="blue",
            confidence=0.90,
            method="rule",
            explanation={"matched": "blue", "blue_count": blue_count, "white_count": white_count},
        )
    if white_count > blue_count and white_count >= 1:
        return CollarResult(
            collar_type="white",
            confidence=0.90,
            method="rule",
            explanation={"matched": "white", "blue_count": blue_count, "white_count": white_count},
        )
    return None


def classify_collar_llm_fallback(
    normalized_title: str,
    normalized_text: str,
    *,
    title_only: bool = False,
) -> Optional[CollarResult]:
    """LLM fallback only when budget allows. Returns None if budget exhausted or call fails."""
    if llm_budget_exhausted():
        return None
    text_part = "" if title_only else "\nText (excerpt): " + (normalized_text[:1500] or "")
    prompt = (
        "Classify this job as either blue collar or white collar based on the job title (and text if provided). "
        "Reply with a JSON object: {\"collar_type\": \"blue\" or \"white\", \"confidence\": 0.0-1.0}. "
        "Title: " + (normalized_title[:500] or "") + text_part
    )
    out = call_openai_chat(
        [{"role": "user", "content": prompt}],
        json_mode=True,
    )
    if not out:
        return None
    try:
        data = json.loads(out)
        ct = data.get("collar_type", "").lower()
        if ct not in ("blue", "white"):
            ct = "white"
        conf = float(data.get("confidence", 0.7))
        conf = max(0.0, min(1.0, conf))
        return CollarResult(
            collar_type=ct,
            confidence=conf,
            method="llm",
            explanation={"llm_response": data},
        )
    except (json.JSONDecodeError, TypeError):
        return None


def classify_collar(
    normalized_title: str,
    normalized_text: str,
    *,
    title_only: bool = False,
) -> CollarResult:
    """
    Classify blue vs white. Use rule-based first; if uncertain, LLM fallback (if budget allows).
    If title_only=True, only the title is used (avoids false positives from description).
    Default to white with low confidence if both fail.
    """
    result = classify_collar_rule(normalized_title, normalized_text, title_only=title_only)
    if result is not None:
        return result
    result = classify_collar_llm_fallback(normalized_title, normalized_text, title_only=title_only)
    if result is not None:
        return result
    return CollarResult(
        collar_type="white",
        confidence=0.5,
        method="default",
        explanation={"reason": "rule_uncertain_and_llm_unavailable"},
    )
