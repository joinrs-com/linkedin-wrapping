from fastapi import Depends, Response
from sqlmodel import Session
from xml.etree.ElementTree import Element, tostring

from utils.database import get_session
from api.wrapping.service import get_available_job_postings


def generate_wrapping_xml(job_postings) -> str:
    """Generate XML response for LinkedIn wrapping."""
    postings = Element("postings")
    
    for job in job_postings:
        job_elem = Element("job")
        job_elem.set("id", str(job.id))
        job_elem.set("position", job.position)
        if job.description:
            job_elem.set("description", job.description)
        postings.append(job_elem)
    
    return tostring(postings, encoding="unicode")


async def get_wrapping(session: Session = Depends(get_session)) -> Response:
    """GET /wrapping endpoint that returns XML with job postings data."""
    job_postings = get_available_job_postings(session)
    xml_content = generate_wrapping_xml(job_postings)
    
    return Response(
        content=xml_content,
        media_type="application/xml"
    )

