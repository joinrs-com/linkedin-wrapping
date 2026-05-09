"""Shared helpers for platform-specific export (e.g. apply URL tracking)."""
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from api.platforms.jooble import UTM_SOURCE as JOOBLE_UTM_SOURCE
from api.platforms.linkedin import LINKEDIN_FEED_UTM_MEDIUM, UTM_SOURCE as LINKEDIN_UTM_SOURCE


def _set_query_params(url: str, updates: dict[str, str]) -> str:
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query, keep_blank_values=True)
    for key, value in updates.items():
        query[key] = [value]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def rewrite_apply_url_for_linkedin_feed(url: str | None) -> str:
    """
    LinkedIn XML: utm_source=linkedin, utm_medium=job-offer-ats, utm_campaign unchanged.
    """
    if not url or not url.strip():
        return url or ""
    return _set_query_params(
        url,
        {"utm_source": LINKEDIN_UTM_SOURCE, "utm_medium": LINKEDIN_FEED_UTM_MEDIUM},
    )


def rewrite_apply_url_for_jooble_feed(url: str | None) -> str:
    """
    Jooble XML: utm_source=jooble; utm_medium and utm_campaign stay as stored (employers_id-priority).
    """
    if not url or not url.strip():
        return url or ""
    return _set_query_params(url, {"utm_source": JOOBLE_UTM_SOURCE})


def rewrite_apply_url_utm_source(url: str | None, utm_source: str) -> str:
    """
    Set or replace utm_source in the query string of an apply URL.
    Returns the original URL unchanged if it is empty; otherwise returns
    the URL with utm_source set to the given value.
    """
    if not url or not url.strip():
        return url or ""
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["utm_source"] = [utm_source]
    new_query = urlencode(query, doseq=True)
    new = parsed._replace(query=new_query)
    return urlunparse(new)
