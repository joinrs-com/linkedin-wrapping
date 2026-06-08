import html
import re
from fastapi import Depends, Response
from sqlmodel import Session
from datetime import datetime, timezone
from email.utils import format_datetime

from utils.database import get_session
from api.wrapping.service import get_available_job_postings, get_hirematic_job_feed_rows
from api.platforms.base import (
    rewrite_apply_url_for_jooble_feed,
    rewrite_apply_url_for_linkedin_feed,
)


def _format_rfc1123_gmt(dt: datetime | None = None) -> str:
    """Return date formatted as RFC1123 in GMT."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    # email.utils.format_datetime handles RFC 5322; with UTC tz it yields RFC1123-like string
    return format_datetime(dt)


def _ensure_utf8(value: str) -> str:
    """Ensure string is valid UTF-8."""
    if value is None:
        return ""
    try:
        # Try to decode and re-encode to ensure valid UTF-8
        if isinstance(value, bytes):
            return value.decode('utf-8', errors='replace')
        # Ensure proper UTF-8 encoding
        return value.encode('utf-8', errors='replace').decode('utf-8')
    except Exception:
        # Fallback: convert to string and handle encoding issues
        return str(value).encode('utf-8', errors='replace').decode('utf-8')


def _escape_cdata(value: str) -> str:
    """Escape CDATA ending sequence and clean invalid XML characters."""
    if value is None:
        return ""
    
    # First ensure valid UTF-8 encoding
    value_str = _ensure_utf8(value)
    
    # Remove invalid XML control characters (except tab \x09, newline \x0A, carriage return \x0D)
    # These characters break XML parsing: \x00-\x08, \x0B-\x0C, \x0E-\x1F, \x7F
    value_str = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', value_str)
    
    # Replace ]]> with ]]>]]&gt;<![CDATA[ to prevent premature CDATA closure
    # This is the standard way to include ]]> in CDATA sections
    value_str = value_str.replace("]]>", "]]]]><![CDATA[>")
    
    return value_str


def _appcast_element_text(value: object | None) -> str:
    """Entity-escaped text for Appcast-style XML (no CDATA), matching Hirematic examples."""
    if value is None:
        return ""
    s = _ensure_utf8(str(value))
    s = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]", "", s)
    return html.escape(s, quote=False)


def _format_generation_time_appcast(dt: datetime | None = None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S %z")


def _appcast_posted_at(job: object) -> str:
    """DB column `post_date`; Appcast XML tag `posted_at` (YYYY-MM-DD)."""
    pd = getattr(job, "post_date", None)
    if pd is None:
        return ""
    if hasattr(pd, "isoformat"):
        return pd.isoformat()
    return str(pd)


def generate_hirematic_appcast_xml(rows: list) -> str:
    """Appcast-compatible XML for Hirematic (see Hirematic feed documentation)."""
    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append("<source>")
    parts.append("<jobs>")
    for job in rows:
        jid = getattr(job, "id", None)
        job_reference = str(jid) if jid is not None else ""
        parts.append("<job>")
        parts.append(f"<location>{_appcast_element_text(getattr(job, 'location', None))}</location>")
        parts.append(f"<title>{_appcast_element_text(getattr(job, 'title', None))}</title>")
        parts.append(f"<city>{_appcast_element_text(getattr(job, 'city', None))}</city>")
        parts.append(f"<state>{_appcast_element_text(getattr(job, 'state', None))}</state>")
        parts.append(f"<zip>{_appcast_element_text(getattr(job, 'postal_code', None))}</zip>")
        parts.append(f"<country>{_appcast_element_text(getattr(job, 'country', None))}</country>")
        parts.append("<job_type></job_type>")
        parts.append(f"<posted_at>{_appcast_element_text(_appcast_posted_at(job))}</posted_at>")
        parts.append(f"<job_reference>{_appcast_element_text(job_reference)}</job_reference>")
        parts.append(f"<company>{_appcast_element_text(getattr(job, 'company', None))}</company>")
        parts.append("<mobile_friendly_apply></mobile_friendly_apply>")
        parts.append(f"<category>{_appcast_element_text(getattr(job, 'category', None))}</category>")
        parts.append("<html_jobs></html_jobs>")
        parts.append(f"<url>{_appcast_element_text(getattr(job, 'url', None))}</url>")
        parts.append(f"<body>{_appcast_element_text(getattr(job, 'description', None))}</body>")
        parts.append(f"<cpc>{_appcast_element_text(getattr(job, 'cpc', None))}</cpc>")
        parts.append(f"<priority>{_appcast_element_text(getattr(job, 'priority', None))}</priority>")
        parts.append("</job>")
    parts.append("</jobs>")
    parts.append(f"<generation_time>{_appcast_element_text(_format_generation_time_appcast())}</generation_time>")
    parts.append(f"<jobs_count>{len(rows)}</jobs_count>")
    parts.append("</source>")
    return "\n".join(parts)


def generate_wrapping_xml(
    job_postings,
    *,
    apply_url_mode: str,
    prefer_employers_name_as_company: bool = False,
    include_priority: bool = False,
    include_employers_id: bool = False,
) -> str:
    """
    Generate XML for wrapping (LinkedIn/Jooble).

    - apply_url_mode: 'linkedin' (utm_medium=job-offer-ats in XML) or 'jooble' (apply URL without query params).
    - If prefer_employers_name_as_company is true, <company> uses employers_name when present, else falls back to company.
    - If include_priority is true, outputs <priority> (empty if missing).
    - If include_employers_id is true, outputs <employers_id> from job_postings.employers_id (Jooble only).
    """
    # Use max last_build_date from job postings if available, otherwise generate current time
    last_build_dates = [job.last_build_date for job in job_postings if getattr(job, "last_build_date", None) is not None]
    if last_build_dates:
        last_build_date = _format_rfc1123_gmt(max(last_build_dates))
    else:
        last_build_date = _format_rfc1123_gmt()

    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append("<source>")
    parts.append(f" <lastBuildDate> {last_build_date} </lastBuildDate>")

    for job in job_postings:
        # Use partner_job_id if available, fallback to id
        partner_job_id = getattr(job, "partner_job_id", None) or (job.id if getattr(job, "id", None) is not None else "")
        partner_job_id_str = str(partner_job_id) if partner_job_id is not None else ""
        if prefer_employers_name_as_company:
            company_value = getattr(job, "employers_name", None) or getattr(job, "company", None) or ""
        else:
            company_value = getattr(job, "company", None) or ""
        company = _escape_cdata(company_value)
        title = _escape_cdata(job.position if getattr(job, "position", None) else "")
        description = _escape_cdata(getattr(job, "description", None) or "")
        raw_apply_url = getattr(job, "apply_url", None) or ""
        if apply_url_mode == "linkedin":
            apply_url = rewrite_apply_url_for_linkedin_feed(raw_apply_url)
        elif apply_url_mode == "jooble":
            apply_url = rewrite_apply_url_for_jooble_feed(raw_apply_url)
        else:
            raise ValueError(f"apply_url_mode must be 'linkedin' or 'jooble', got {apply_url_mode!r}")
        apply_url = _escape_cdata(apply_url)
        company_id = _escape_cdata(getattr(job, "company_id", None) or "")
        location = _escape_cdata(getattr(job, "location", None) or "")
        workplace_types = _escape_cdata(getattr(job, "workplace_types", None) or "")
        experience_level = _escape_cdata(getattr(job, "experience_level", None) or "")
        jobtype = _escape_cdata(getattr(job, "jobtype", None) or "")
        priority_raw = getattr(job, "priority", None)
        priority = _escape_cdata("" if priority_raw is None else str(priority_raw))
        employers_id_raw = getattr(job, "employers_id", None)
        employers_id = _escape_cdata("" if employers_id_raw is None else str(employers_id_raw))

        parts.append(" <job>")
        # partner_job_id is typically numeric, but escape it anyway for safety
        partner_job_id_escaped = _escape_cdata(partner_job_id_str)
        parts.append(f"  <partnerJobId><![CDATA[{partner_job_id_escaped}]]></partnerJobId>")
        parts.append(f"  <company><![CDATA[{company}]]></company>")
        if include_priority:
            parts.append(f"  <priority><![CDATA[{priority}]]></priority>")
        if include_employers_id:
            parts.append(f"  <employers_id><![CDATA[{employers_id}]]></employers_id>")
        parts.append(f"  <title><![CDATA[{title}]]></title>")
        parts.append(f"  <description><![CDATA[{description}]]></description>")
        parts.append(f"  <applyUrl><![CDATA[{apply_url}]]></applyUrl>")
        parts.append(f"  <companyId> <![CDATA[{company_id}]]></companyId>")
        parts.append(f"  <location><![CDATA[{location}]]></location>")
        parts.append(f"  <workplaceTypes><![CDATA[{workplace_types}]]></workplaceTypes>")
        parts.append(f"  <experienceLevel><![CDATA[{experience_level}]]></experienceLevel>")
        parts.append(f"  <jobtype><![CDATA[{jobtype}]]></jobtype>")
        parts.append(" </job>")

    parts.append("</source>")

    return "\n".join(parts)


async def get_wrapping(session: Session = Depends(get_session)) -> Response:
    """GET /wrapping endpoint: XML with job postings for LinkedIn (apply URLs with utm_source=linkedin)."""
    job_postings = get_available_job_postings(session)
    xml_content = generate_wrapping_xml(job_postings, apply_url_mode="linkedin")
    return Response(
        content=xml_content.encode('utf-8'),
        media_type="application/xml; charset=utf-8"
    )


async def get_wrapping_jooble(session: Session = Depends(get_session)) -> Response:
    """GET /wrapping/jooble: XML for Jooble; apply_url is the canonical job link without query params."""
    job_postings = get_available_job_postings(session)
    xml_content = generate_wrapping_xml(
        job_postings,
        apply_url_mode="jooble",
        prefer_employers_name_as_company=True,
        include_priority=True,
        include_employers_id=True,
    )
    return Response(
        content=xml_content.encode('utf-8'),
        media_type="application/xml; charset=utf-8"
    )


async def get_wrapping_hirematic(session: Session = Depends(get_session)) -> Response:
    """GET /wrapping/hirematic: Appcast-compatible XML from hirematic_job_feed (URLs as stored, no UTM rewrite)."""
    rows = get_hirematic_job_feed_rows(session)
    xml_content = generate_hirematic_appcast_xml(rows)
    return Response(
        content=xml_content.encode("utf-8"),
        media_type="application/xml; charset=utf-8",
    )

