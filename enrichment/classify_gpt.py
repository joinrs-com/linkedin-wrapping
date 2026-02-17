"""Classify white collar ambiti (macro = gpt_questions_groups, micro = gpt_questions). Same pattern as sector."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from enrichment.llm import call_openai_chat, llm_budget_exhausted
from enrichment.taxonomy_cache import GptQuestionEntry, TaxonomyCache

TITLE_WEIGHT = 3.0
DESCRIPTION_WEIGHT = 1.5


def _keyword_score(text: str, keywords_str: Optional[str], in_title: bool) -> float:
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
            regex = re.compile(r"\b" + re.escape(pattern) + r"\w*", re.I)
        else:
            regex = re.compile(r"\b" + re.escape(part) + r"\b", re.I)
        matches = regex.findall(text)
        total += weight * len(matches)
    return total


def score_gpt_questions(
    cache: TaxonomyCache,
    normalized_title: str,
    normalized_text: str,
) -> list[tuple[GptQuestionEntry, float]]:
    """Score each gpt_question; return list of (question, score) sorted by score desc."""
    scored: list[tuple[GptQuestionEntry, float]] = []
    for q in cache.gpt_questions:
        s_title = _keyword_score(normalized_title, q.keywords, in_title=True)
        s_desc = _keyword_score(normalized_text, q.keywords, in_title=False)
        total = s_title + s_desc
        scored.append((q, total))
    scored.sort(key=lambda x: -x[1])
    return scored


@dataclass
class GptResult:
    gpt_group_id: Optional[int]
    gpt_question_id: Optional[int]
    gpt_confidence: float
    gpt_method: str  # "rule" | "llm" | "default"
    explanation: Optional[dict] = None


def classify_gpt_rule(
    cache: TaxonomyCache,
    normalized_title: str,
    normalized_text: str,
    scored: list[tuple[GptQuestionEntry, float]],
    high_threshold: float = 2.0,
    medium_threshold: float = 0.5,
) -> Optional[GptResult]:
    if not scored:
        return GptResult(None, None, 0.0, "rule", {"reason": "no_candidates"})
    top_q, top_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0.0
    group = cache.get_gpt_group_for_question(top_q.id)
    group_id = group.id if group else None
    if top_score >= high_threshold and top_score > second_score:
        return GptResult(
            gpt_group_id=group_id,
            gpt_question_id=top_q.id,
            gpt_confidence=0.90,
            gpt_method="rule",
            explanation={"top_score": top_score, "top_question_id": top_q.id},
        )
    if top_score >= medium_threshold and top_score > second_score:
        return GptResult(
            gpt_group_id=group_id,
            gpt_question_id=top_q.id,
            gpt_confidence=0.65,
            gpt_method="rule",
            explanation={"top_score": top_score, "top_question_id": top_q.id},
        )
    return None


def classify_gpt_llm(
    cache: TaxonomyCache,
    normalized_title: str,
    normalized_text: str,
    scored: list[tuple[GptQuestionEntry, float]],
    *,
    top_n: int = 5,
) -> Optional[GptResult]:
    """LLM chooses one gpt_question_id from the top_n scored candidates."""
    if llm_budget_exhausted():
        return None
    top = scored[:top_n]
    if not top:
        return None
    choices = [f"id={q.id} name={q.name}" for q, _ in top]
    prompt = (
        "Choose the single best work area (ambito) for this white collar job from the following list only. "
        "Reply with JSON: {\"gpt_question_id\": <id number>}. "
        "List (choose one id): " + " | ".join(choices) + "\n\n"
        "Title: " + (normalized_title[:400] or "") + "\nText: " + (normalized_text[:800] or "")
    )
    out = call_openai_chat([{"role": "user", "content": prompt}], json_mode=True)
    if not out:
        return None
    try:
        data = json.loads(out)
        q_id = int(data.get("gpt_question_id", 0))
        if not any(q.id == q_id for q, _ in top):
            q_id = top[0][0].id
        q = cache.gpt_question_by_id.get(q_id)
        group = cache.get_gpt_group_for_question(q_id) if q else None
        return GptResult(
            gpt_group_id=group.id if group else None,
            gpt_question_id=q_id,
            gpt_confidence=0.75,
            gpt_method="llm",
            explanation={"llm_question_id": q_id, "top_ids": [q.id for q, _ in top]},
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def classify_gpt(
    cache: TaxonomyCache,
    normalized_title: str,
    normalized_text: str,
    *,
    force_llm: bool = False,
) -> GptResult:
    """Classify white collar ambito (group + question). If force_llm=True, always use LLM among top-10 (more precise)."""
    scored = score_gpt_questions(cache, normalized_title, normalized_text)
    if force_llm:
        result = classify_gpt_llm(cache, normalized_title, normalized_text, scored, top_n=10)
        if result is not None:
            return result
        if scored:
            q = scored[0][0]
            group = cache.get_gpt_group_for_question(q.id)
            return GptResult(
                gpt_group_id=group.id if group else None,
                gpt_question_id=q.id,
                gpt_confidence=0.5,
                gpt_method="default",
                explanation={"reason": "llm_failed_fallback_first"},
            )
        return GptResult(None, None, 0.0, "default", {"reason": "no_gpt_questions"})
    result = classify_gpt_rule(cache, normalized_title, normalized_text, scored)
    if result is not None:
        return result
    result = classify_gpt_llm(cache, normalized_title, normalized_text, scored)
    if result is not None:
        return result
    if scored:
        q = scored[0][0]
        group = cache.get_gpt_group_for_question(q.id)
        return GptResult(
            gpt_group_id=group.id if group else None,
            gpt_question_id=q.id,
            gpt_confidence=0.5,
            gpt_method="default",
            explanation={"reason": "fallback_first_candidate"},
        )
    return GptResult(None, None, 0.0, "default", {"reason": "no_gpt_questions"})
