"""OpenAI wrapper with exponential backoff retry. Hard limit MAX_LLM_CALLS_PER_RUN (plan rule 5)."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger("enrichment")

# Global counter for this run; reset at pipeline start, decremented on each LLM call
_llm_calls_remaining: Optional[int] = None


def init_llm_budget(max_calls: int) -> None:
    """Set the remaining LLM call budget for this run. Call once at pipeline start.
    Use 0 or negative for unlimited (LLM called whenever needed)."""
    global _llm_calls_remaining
    _llm_calls_remaining = None if max_calls <= 0 else max_calls


def llm_budget_exhausted() -> bool:
    """True if no more LLM calls are allowed this run (plan rule 5)."""
    if _llm_calls_remaining is None:
        return False
    return _llm_calls_remaining <= 0


def consume_llm_budget() -> bool:
    """
    Decrement budget by one. Returns True if call was allowed, False if limit already reached.
    Call before invoking OpenAI; if False, do not call and use default classification.
    """
    global _llm_calls_remaining
    if _llm_calls_remaining is None:
        return True
    if _llm_calls_remaining <= 0:
        logger.critical(
            "MAX_LLM_CALLS_PER_RUN reached; blocking further LLM fallback. Use default classification.",
            extra={"extra": {"event": "llm_budget_exhausted"}},
        )
        return False
    _llm_calls_remaining -= 1
    return True


def call_openai_chat(
    messages: list[dict[str, str]],
    *,
    model: Optional[str] = None,
    json_mode: bool = False,
) -> Optional[str]:
    """
    Call OpenAI chat completions with retry (rate limit, timeout, transient errors).
    Returns None on failure after retries; caller must use default.
    """
    from openai import OpenAI

    from enrichment.config import config

    if not consume_llm_budget():
        return None

    model = model or config.OPENAI_MODEL
    client = OpenAI(api_key=config.OPENAI_API_KEY)

    @retry(
        retry=retry_if_exception_type((
            Exception,  # rate limit, timeout, 5xx, connection
        )),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        reraise=False,
    )
    def _call() -> str:
        kwargs: dict[str, Any] = {"model": model, "messages": messages}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        if not resp.choices:
            raise ValueError("Empty choices from OpenAI")
        return (resp.choices[0].message.content or "").strip()

    try:
        return _call()
    except Exception as e:
        logger.warning(
            "OpenAI call failed after retries; using default",
            extra={"extra": {"error": str(e), "event": "llm_failed"}},
        )
        return None
