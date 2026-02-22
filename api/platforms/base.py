"""Shared helpers for platform-specific export (e.g. apply URL tracking)."""
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


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
