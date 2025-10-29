from sqlmodel import Session, select
from typing import List

from api.wrapping.models import JobPostings


def get_available_job_postings(session: Session) -> List[JobPostings]:
    """
    Query job postings available to be published to LinkedIn via wrapping.
    Currently returns all job postings, can be extended with filtering logic.
    """
    statement = select(JobPostings)
    results = session.exec(statement)
    return list(results.all())

