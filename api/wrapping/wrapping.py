import re
from fastapi import Depends, Response
from sqlmodel import Session
from datetime import datetime, timezone
from email.utils import format_datetime

from utils.database import get_session
from api.wrapping.service import get_available_job_postings


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


def generate_wrapping_xml(job_postings) -> str:
    """Generate XML response for LinkedIn wrapping in the LinkedIn expected format."""
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
        company = _escape_cdata(getattr(job, "company", None) or "")
        title = _escape_cdata(job.position if getattr(job, "position", None) else "")
        description = _escape_cdata(getattr(job, "description", None) or "")
        apply_url = _escape_cdata(getattr(job, "apply_url", None) or "")
        company_id = _escape_cdata(getattr(job, "company_id", None) or "")
        location = _escape_cdata(getattr(job, "location", None) or "")
        workplace_types = _escape_cdata(getattr(job, "workplace_types", None) or "")
        experience_level = _escape_cdata(getattr(job, "experience_level", None) or "")
        jobtype = _escape_cdata(getattr(job, "jobtype", None) or "")

        parts.append(" <job>")
        # partner_job_id is typically numeric, but escape it anyway for safety
        partner_job_id_str = _escape_cdata(str(partner_job_id))
        parts.append(f"  <partnerJobId><![CDATA[{partner_job_id_str}]]></partnerJobId>")
        parts.append(f"  <company><![CDATA[{company}]]></company>")
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
    """GET /wrapping endpoint that returns XML with job postings data."""
    job_postings = get_available_job_postings(session)
    xml_content = generate_wrapping_xml(job_postings)
    
    return Response(
        content=xml_content.encode('utf-8'),
        media_type="application/xml; charset=utf-8"
    )

