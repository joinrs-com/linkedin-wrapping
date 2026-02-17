"""Step 4: classify sector (macro + micro). Scoring with cache; LLM only among top-5 candidates."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from enrichment.llm import call_openai_chat, llm_budget_exhausted
from enrichment.taxonomy_cache import SectorMicro, TaxonomyCache

TITLE_WEIGHT = 3.0
DESCRIPTION_WEIGHT = 1.5


def _keyword_score(text: str, keywords_str: Optional[str], in_title: bool) -> float:
    """Score for one micro: keyword matches. Whole word > substring; support prefix (e.g. saldat*)."""
    if not keywords_str or not text:
        return 0.0
    weight = TITLE_WEIGHT if in_title else DESCRIPTION_WEIGHT
    total = 0.0
    for part in keywords_str.split(","):
        part = part.strip().lower()
        if not part:
            continue
        is_prefix = part.endswith("*")
        if is_prefix:
            pattern = part[:-1].rstrip()
            if not pattern:
                continue
            # prefix match as whole word start
            regex = re.compile(r"\b" + re.escape(pattern) + r"\w*", re.I)
        else:
            regex = re.compile(r"\b" + re.escape(part) + r"\b", re.I)
        matches = regex.findall(text)
        total += weight * len(matches)
    return total


def score_micro_sectors(
    cache: TaxonomyCache,
    normalized_title: str,
    normalized_text: str,
) -> list[tuple[SectorMicro, float]]:
    """Score each micro sector; return list of (micro, score) sorted by score desc."""
    scored: list[tuple[SectorMicro, float]] = []
    for micro in cache.micro_sectors:
        s_title = _keyword_score(normalized_title, micro.keywords, in_title=True)
        s_desc = _keyword_score(normalized_text, micro.keywords, in_title=False)
        total = s_title + s_desc
        scored.append((micro, total))
    scored.sort(key=lambda x: -x[1])
    return scored


@dataclass
class SectorResult:
    sector_macro_id: Optional[int]
    sector_micro_id: Optional[int]
    sector_confidence: float
    sector_method: str  # "rule" | "llm"
    explanation: Optional[dict] = None


def classify_sector_rule(
    cache: TaxonomyCache,
    normalized_title: str,
    normalized_text: str,
    scored: list[tuple[SectorMicro, float]],
    high_threshold: float = 2.0,
    medium_threshold: float = 0.5,
) -> Optional[SectorResult]:
    """If top score is clear, return rule-based result. Otherwise return None for LLM."""
    if not scored:
        return SectorResult(None, None, 0.0, "rule", {"reason": "no_candidates"})
    top_micro, top_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0.0
    macro = cache.get_macro_for_micro(top_micro.id)
    macro_id = macro.id if macro else None
    if top_score >= high_threshold and top_score > second_score:
        return SectorResult(
            sector_macro_id=macro_id,
            sector_micro_id=top_micro.id,
            sector_confidence=0.90,
            sector_method="rule",
            explanation={"top_score": top_score, "top_micro_id": top_micro.id},
        )
    if top_score >= medium_threshold and top_score > second_score:
        return SectorResult(
            sector_macro_id=macro_id,
            sector_micro_id=top_micro.id,
            sector_confidence=0.65,
            sector_method="rule",
            explanation={"top_score": top_score, "top_micro_id": top_micro.id},
        )
    # Tie or low score → need LLM among top-5
    return None


def classify_sector_llm(
    cache: TaxonomyCache,
    normalized_title: str,
    normalized_text: str,
    scored: list[tuple[SectorMicro, float]],
) -> Optional[SectorResult]:
    """LLM chooses only among top-5 micro sectors. No invented categories."""
    if llm_budget_exhausted():
        return None
    top5 = scored[:5]
    if not top5:
        return None
    choices = [f"id={m.id} name={m.name}" for m, _ in top5]
    prompt = (
        "Choose the single best sector for this job from the following list only. "
        "Reply with JSON: {\"sector_micro_id\": <id number>}. "
        "List (choose one id): " + " | ".join(choices) + "\n\n"
        "Title: " + (normalized_title[:400] or "") + "\nText: " + (normalized_text[:800] or "")
    )
    out = call_openai_chat([{"role": "user", "content": prompt}], json_mode=True)
    if not out:
        return None
    try:
        data = json.loads(out)
        micro_id = int(data.get("sector_micro_id", 0))
        if not any(m.id == micro_id for m, _ in top5):
            micro_id = top5[0][0].id
        micro = cache.micro_by_id.get(micro_id)
        macro = cache.get_macro_for_micro(micro_id) if micro else None
        return SectorResult(
            sector_macro_id=macro.id if macro else None,
            sector_micro_id=micro_id,
            sector_confidence=0.75,
            sector_method="llm",
            explanation={"llm_micro_id": micro_id, "top5_ids": [m.id for m, _ in top5]},
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def classify_sector(
    cache: TaxonomyCache,
    normalized_title: str,
    normalized_text: str,
) -> SectorResult:
    """Classify sector; use rule first, then LLM only among top-5 if ambiguous."""
    scored = score_micro_sectors(cache, normalized_title, normalized_text)
    result = classify_sector_rule(cache, normalized_title, normalized_text, scored)
    if result is not None:
        return result
    result = classify_sector_llm(cache, normalized_title, normalized_text, scored)
    if result is not None:
        return result
    # Default: first micro if any
    if scored:
        m = scored[0][0]
        macro = cache.get_macro_for_micro(m.id)
        return SectorResult(
            sector_macro_id=macro.id if macro else None,
            sector_micro_id=m.id,
            sector_confidence=0.5,
            sector_method="default",
            explanation={"reason": "fallback_first_candidate"},
        )
    return SectorResult(None, None, 0.0, "default", {"reason": "no_sectors"})

