"""Step 1: normalize text (HTML strip, lowercase, whitespace). Output for job_enrichment only; never write to source."""

from __future__ import annotations

import re
from typing import Optional


def strip_html(text: Optional[str]) -> str:
    """Remove HTML tags."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", text)


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace to single space and strip."""
    if not text:
        return ""
    return " ".join(text.split())


def normalize_title(title: Optional[str]) -> str:
    """Normalized title: strip HTML, lowercase, normalize whitespace."""
    if not title:
        return ""
    t = strip_html(title).lower()
    return normalize_whitespace(t)


def normalize_text(position: Optional[str], description: Optional[str]) -> str:
    """Unite title + description, strip HTML, lowercase, normalize whitespace. Used for job_enrichment.normalized_text."""
    parts = []
    if position:
        parts.append(strip_html(position))
    if description:
        parts.append(strip_html(description))
    combined = " ".join(parts).lower()
    return normalize_whitespace(combined)


def compute_normalized(
    position: Optional[str], description: Optional[str]
) -> tuple[str, str]:
    """Return (normalized_title, normalized_text) for a job. No DB write."""
    return (
        normalize_title(position),
        normalize_text(position, description),
    )
