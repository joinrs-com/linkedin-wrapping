"""Unit tests for Talent.com description Markdown → HTML sanitization."""

from api.platforms.talent import normalize_description_for_talent


def test_bold_markdown_to_strong():
    out = normalize_description_for_talent("Hello **world** today")
    assert "<strong>world</strong>" in out
    assert "**" not in out


def test_heading_and_list_markdown():
    src = "## Title\n\n- one\n- two\n"
    out = normalize_description_for_talent(src)
    assert "<strong>Title</strong>" in out
    assert "<ul>" in out
    assert "<li>one</li>" in out
    assert "<li>two</li>" in out
    assert "##" not in out


def test_b_and_i_mapped_and_attrs_stripped():
    src = '<p style="text-align:left"><b>Bold</b> and <i>ital</i></p>'
    out = normalize_description_for_talent(src)
    assert "<strong>Bold</strong>" in out
    assert "<em>ital</em>" in out
    assert "<b>" not in out.lower().replace("<br>", "")
    assert "style=" not in out
    assert "<i>" not in out


def test_disallowed_tags_unwrapped():
    src = "<div><span>keep</span><script>x</script></div>"
    out = normalize_description_for_talent(src)
    assert "keep" in out
    assert "<div>" not in out
    assert "<span>" not in out
    assert "<script>" not in out


def test_empty_input():
    assert normalize_description_for_talent(None) == ""
    assert normalize_description_for_talent("") == ""
