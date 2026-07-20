"""Talent.com description normalization: Markdown → allowed HTML only."""

from __future__ import annotations

import re
from html.parser import HTMLParser


_ALLOWED_TAGS = frozenset({"p", "br", "strong", "em", "ul", "li"})


class _TalentHTMLFilter(HTMLParser):
    """Keep only Talent-allowed tags; strip attributes; preserve text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ARG002
        name = tag.lower()
        if name == "br":
            self._parts.append("<br>")
        elif name in _ALLOWED_TAGS:
            self._parts.append(f"<{name}>")

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in _ALLOWED_TAGS and name != "br":
            self._parts.append(f"</{name}>")

    def handle_startendtag(self, tag: str, attrs) -> None:  # noqa: ARG002
        if tag.lower() == "br":
            self._parts.append("<br>")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def output(self) -> str:
        return "".join(self._parts)


def _markdown_bold_italic(text: str) -> str:
    # Bold first (double markers), then single italic — avoid list markers at line start.
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text, flags=re.DOTALL)
    # Headings left inside HTML paragraphs (e.g. <p>## Title)
    text = re.sub(r"#{1,6}\s+([^<\n]+)", r"<strong>\1</strong>", text)
    text = re.sub(
        r"(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)",
        r"<em>\1</em>",
        text,
    )
    text = re.sub(r"(?<!_)_(?!_)([^_\n]+?)(?<!_)_(?!_)", r"<em>\1</em>", text)
    return text


def _convert_markdown_lines(text: str) -> str:
    """Convert ## headers and -/* list lines to HTML; leave other lines as-is."""
    lines = text.split("\n")
    out: list[str] = []
    list_items: list[str] = []

    def flush_list() -> None:
        nonlocal list_items
        if not list_items:
            return
        items = "".join(f"<li>{item}</li>" for item in list_items)
        out.append(f"<ul>{items}</ul>")
        list_items = []

    for line in lines:
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.*)$", line)
        if heading:
            flush_list()
            title = heading.group(1).strip()
            if title:
                out.append(f"<p><strong>{title}</strong></p>")
            continue

        bullet = re.match(r"^\s*[-*]\s+(.*)$", line)
        if bullet:
            list_items.append(bullet.group(1).strip())
            continue

        flush_list()
        out.append(line)

    flush_list()
    return "\n".join(out)


def _normalize_legacy_tags(text: str) -> str:
    text = re.sub(r"<b(\s[^>]*)?>", "<strong>", text, flags=re.IGNORECASE)
    text = re.sub(r"</b>", "</strong>", text, flags=re.IGNORECASE)
    text = re.sub(r"<i(\s[^>]*)?>", "<em>", text, flags=re.IGNORECASE)
    text = re.sub(r"</i>", "</em>", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "<br>", text, flags=re.IGNORECASE)
    return text


def _whitelist_html(text: str) -> str:
    parser = _TalentHTMLFilter()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        # If parse fails, strip all tags as last resort
        return re.sub(r"<[^>]+>", "", text)
    return parser.output()


def _strip_residual_markdown(text: str) -> str:
    text = text.replace("**", "")
    text = text.replace("__", "")
    # Remove leftover single * used as markdown (not already converted)
    text = re.sub(r"(?<!\w)\*(?!\w)", "", text)
    return text


def normalize_description_for_talent(description: str | None) -> str:
    """
    Convert Markdown-ish job descriptions to Talent.com-allowed HTML.

    Allowed tags only: p, br, strong, em, ul, li (no attributes).
    """
    if not description:
        return ""

    text = str(description)
    text = _convert_markdown_lines(text)
    text = _markdown_bold_italic(text)
    text = _normalize_legacy_tags(text)
    text = _whitelist_html(text)
    text = _strip_residual_markdown(text)
    return text
