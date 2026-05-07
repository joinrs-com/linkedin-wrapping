from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from main import app
from utils.database import get_session as original_get_session
from api.wrapping import models


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    yield


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    # Isolated in-memory DB shared across connections
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def get_test_session() -> Generator[Session, None, None]:
        session = Session(engine)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[original_get_session] = get_test_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health_endpoint(client: TestClient):
    """Test health check endpoint."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() in ({"Ok!"}, ["Ok!"])


def test_root_endpoint(client: TestClient):
    """Test root endpoint."""
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["message"] == "LinkedIn Wrapping Service API"
    assert data["version"] == "1.0.0"


def test_wrapping_endpoint_empty(client: TestClient):
    """Test wrapping endpoint with no job postings."""
    r = client.get("/wrapping/")  # trailing slash to avoid redirect
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    content = r.text
    assert "<source>" in content
    assert "</source>" in content
    assert "<lastBuildDate>" in content


def test_wrapping_endpoint_with_jobs(client: TestClient):
    """Test wrapping endpoint with job postings."""
    # Create test job postings
    get_sess = list(app.dependency_overrides.values())[0]
    _now = datetime.now(timezone.utc)
    with next(get_sess()) as s:  # type: ignore
        job1 = models.JobPostings(id=1, position="Software Engineer", created_at=_now, updated_at=_now)
        job2 = models.JobPostings(id=2, position="Data Scientist", created_at=_now, updated_at=_now)
        s.add(job1)
        s.add(job2)
        s.commit()

    r = client.get("/wrapping/")
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    content = r.text

    # Check XML structure
    assert "<source>" in content
    assert "</source>" in content
    assert "<lastBuildDate>" in content
    # Job 1
    assert "<job>" in content
    assert "<![CDATA[1]]>" in content  # partnerJobId CDATA
    assert "<![CDATA[Software Engineer]]>" in content  # title CDATA
    # Job 2
    assert "<![CDATA[2]]>" in content
    assert "<![CDATA[Data Scientist]]>" in content


def test_wrapping_linkedin_apply_url_has_utm_source_linkedin(client: TestClient):
    """LinkedIn endpoint must output applyUrl with utm_source=linkedin."""
    _now = datetime.now(timezone.utc)
    get_sess = list(app.dependency_overrides.values())[0]
    with next(get_sess()) as s:  # type: ignore
        job = models.JobPostings(
            id=1,
            position="Test",
            apply_url="https://example.com/job/1/?utm_source=jooble&utm_medium=job-offer-ats",
            created_at=_now,
            updated_at=_now,
        )
        s.add(job)
        s.commit()

    r = client.get("/wrapping/")
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    # LinkedIn endpoint rewrites apply URL to utm_source=linkedin
    assert "utm_source=linkedin" in r.text
    assert "<applyUrl>" in r.text


def test_wrapping_jooble_apply_url_has_utm_source_jooble(client: TestClient):
    """Jooble endpoint must output applyUrl with utm_source=jooble."""
    _now = datetime.now(timezone.utc)
    get_sess = list(app.dependency_overrides.values())[0]
    with next(get_sess()) as s:  # type: ignore
        job = models.JobPostings(
            id=1,
            position="Test",
            apply_url="https://example.com/job/1/?utm_source=linkedin&utm_medium=job-offer-ats",
            created_at=_now,
            updated_at=_now,
        )
        s.add(job)
        s.commit()

    r = client.get("/wrapping/jooble")
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    assert "<source>" in r.text
    assert "utm_source=jooble" in r.text
    assert "<applyUrl>" in r.text


def test_wrapping_jooble_company_uses_employers_name(client: TestClient):
    """Jooble endpoint must output <company> from employers_name (fallback to company)."""
    _now = datetime.now(timezone.utc)
    get_sess = list(app.dependency_overrides.values())[0]
    with next(get_sess()) as s:  # type: ignore
        job = models.JobPostings(
            id=1,
            position="Test",
            company="OldCompany",
            employers_name="NewEmployer",
            priority=3,
            apply_url="https://example.com/job/1/?utm_source=linkedin&utm_medium=job-offer-ats",
            created_at=_now,
            updated_at=_now,
        )
        s.add(job)
        s.commit()

    r = client.get("/wrapping/jooble")
    assert r.status_code == 200
    assert "<company><![CDATA[NewEmployer]]></company>" in r.text
    assert "<priority><![CDATA[3]]></priority>" in r.text

    # LinkedIn must remain unchanged: uses `company`
    r2 = client.get("/wrapping/")
    assert r2.status_code == 200
    assert "<company><![CDATA[OldCompany]]></company>" in r2.text
    assert "<priority>" not in r2.text


def test_wrapping_jooble_empty(client: TestClient):
    """Jooble endpoint with no jobs returns valid XML."""
    r = client.get("/wrapping/jooble")
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    assert "<source>" in r.text
    assert "<lastBuildDate>" in r.text


def test_wrapping_hirematic_empty(client: TestClient):
    r = client.get("/wrapping/hirematic")
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    assert "<source>" in r.text
    assert "<jobs>" in r.text
    assert "<jobs_count>0</jobs_count>" in r.text


def test_wrapping_hirematic_one_job_body_escaped(client: TestClient):
    get_sess = list(app.dependency_overrides.values())[0]
    with next(get_sess()) as s:  # type: ignore
        row = models.HirematicJobFeed(
            id=1,
            location="Strathroy, Canada",
            title="Talent Acquisition Manager",
            city="Strathroy",
            state="ON",
            postal_code="N7C",
            country="Canada",
            post_date=date(2022, 4, 21),
            company="Acme",
            category="Human Resources and Personnel",
            url="https://example.com/",
            description="<p>lorem ipsum</p>",
            cpc=0.0,
            priority=10,
        )
        s.add(row)
        s.commit()

    r = client.get("/wrapping/hirematic")
    assert r.status_code == 200
    assert "<jobs_count>1</jobs_count>" in r.text
    assert "&lt;p&gt;lorem ipsum&lt;/p&gt;" in r.text
    assert "<p>lorem ipsum</p>" not in r.text
    assert "<job_reference>1</job_reference>" in r.text
    assert "<posted_at>2022-04-21</posted_at>" in r.text
    assert "<priority>10</priority>" in r.text


