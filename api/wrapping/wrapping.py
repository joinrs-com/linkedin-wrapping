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


def generate_wrapping_xml(job_postings) -> str:
    """Generate XML response for LinkedIn wrapping in the LinkedIn expected format."""
    last_build_date = _format_rfc1123_gmt()

    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append("<source>")
    parts.append(f" <lastBuildDate> {last_build_date} </lastBuildDate>")

    for job in job_postings:
        partner_job_id = job.id if getattr(job, "id", None) is not None else ""
        company = getattr(job, "company", None) or ""
        title = job.position if getattr(job, "position", None) else ""
        description = getattr(job, "description", None) or ""
        apply_url = getattr(job, "apply_url", None) or ""
        company_id = getattr(job, "company_id", None) or ""
        location = getattr(job, "location", None) or ""
        workplace_types = getattr(job, "workplace_types", None) or ""
        experience_level = getattr(job, "experience_level", None) or ""
        jobtype = getattr(job, "jobtype", None) or ""

        parts.append(" <job>")
        parts.append(f"  <partnerJobId><![CDATA[{partner_job_id}]]></partnerJobId>")
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
        content=xml_content,
        media_type="application/xml"
    )

