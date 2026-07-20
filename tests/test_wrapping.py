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
    """LinkedIn XML: utm_source=linkedin and utm_medium=job-offer-ats (canonical DB URL uses employer-priority in medium)."""
    _now = datetime.now(timezone.utc)
    get_sess = list(app.dependency_overrides.values())[0]
    with next(get_sess()) as s:  # type: ignore
        job = models.JobPostings(
            id=1,
            position="Test",
            apply_url=(
                "https://www.joinrs.com/jobs/1/"
                "?utm_source=linkedin&utm_medium=12345-3&utm_campaign=1-pro"
            ),
            created_at=_now,
            updated_at=_now,
        )
        s.add(job)
        s.commit()

    r = client.get("/wrapping/")
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    assert "utm_source=linkedin" in r.text
    assert "utm_medium=job-offer-ats" in r.text
    assert "utm_campaign=1-pro" in r.text
    assert "utm_medium=12345-3" not in r.text
    assert "<applyUrl>" in r.text


def test_wrapping_jooble_apply_url_has_no_query_params(client: TestClient):
    """Jooble XML: apply URL is canonical job link without query (Jooble adds UTMs)."""
    _now = datetime.now(timezone.utc)
    get_sess = list(app.dependency_overrides.values())[0]
    with next(get_sess()) as s:  # type: ignore
        row = models.JoobleJobFeed(
            id=1,
            position="Test",
            apply_url="https://www.joinrs.com/jobs/1",
            last_build_date=_now,
        )
        s.add(row)
        s.commit()

    r = client.get("/wrapping/jooble")
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    assert "<source>" in r.text
    assert "<applyUrl><![CDATA[https://www.joinrs.com/jobs/1]]></applyUrl>" in r.text
    assert "utm_" not in r.text.split("<applyUrl>")[1].split("</applyUrl>")[0]
    assert "<applyUrl>" in r.text


def test_wrapping_jooble_reads_from_jooble_job_feed_not_job_postings(client: TestClient):
    """Jooble main feed uses jooble_job_feed only; job_postings rows are ignored."""
    _now = datetime.now(timezone.utc)
    get_sess = list(app.dependency_overrides.values())[0]
    with next(get_sess()) as s:  # type: ignore
        s.add(
            models.JobPostings(
                id=99,
                position="Only LinkedIn",
                created_at=_now,
                updated_at=_now,
            )
        )
        s.add(
            models.JoobleJobFeed(
                id=1,
                position="Only Jooble",
                apply_url="https://www.joinrs.com/jobs/1",
                last_build_date=_now,
            )
        )
        s.commit()

    r = client.get("/wrapping/jooble")
    assert r.status_code == 200
    assert "<![CDATA[Only Jooble]]>" in r.text
    assert "Only LinkedIn" not in r.text

    r2 = client.get("/wrapping/")
    assert r2.status_code == 200
    assert "<![CDATA[Only LinkedIn]]>" in r2.text
    assert "Only Jooble" not in r2.text


def test_wrapping_jooble_company_uses_employers_name(client: TestClient):
    """Jooble endpoint must output <company> from employers_name (fallback to company)."""
    _now = datetime.now(timezone.utc)
    get_sess = list(app.dependency_overrides.values())[0]
    with next(get_sess()) as s:  # type: ignore
        s.add(
            models.JobPostings(
                id=1,
                position="LinkedIn Job",
                company="OldCompany",
                created_at=_now,
                updated_at=_now,
            )
        )
        s.add(
            models.JoobleJobFeed(
                id=1,
                position="Test",
                company="Joinrs",
                employers_name="NewEmployer",
                employers_id=2341296,
                priority=3,
                apply_url="https://www.joinrs.com/jobs/1",
                last_build_date=_now,
            )
        )
        s.commit()

    r = client.get("/wrapping/jooble")
    assert r.status_code == 200
    assert "<company><![CDATA[NewEmployer]]></company>" in r.text
    assert "<priority><![CDATA[3]]></priority>" in r.text
    assert "<employers_id><![CDATA[2341296]]></employers_id>" in r.text
    assert "<countries>" not in r.text

    # LinkedIn must remain unchanged: uses `company`
    r2 = client.get("/wrapping/")
    assert r2.status_code == 200
    assert "<company><![CDATA[OldCompany]]></company>" in r2.text
    assert "<priority>" not in r2.text
    assert "<employers_id>" not in r2.text


def test_wrapping_jooble_empty(client: TestClient):
    """Jooble endpoint with no jobs returns valid XML."""
    r = client.get("/wrapping/jooble")
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    assert "<source>" in r.text
    assert "<lastBuildDate>" in r.text


def test_wrapping_talent_empty(client: TestClient):
    """Talent endpoint mirrors Jooble feed XML."""
    r = client.get("/wrapping/talent")
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    assert "<source>" in r.text
    assert "<lastBuildDate>" in r.text


def test_wrapping_talent_sanitizes_markdown_jooble_does_not(client: TestClient):
    """Talent converts Markdown to allowed HTML; Jooble keeps raw description."""
    raw = (
        "<p>**Talenti** ricerca:</p>\n"
        "## Requisiti\n"
        "- Esperienza\n"
        "- Propensione\n"
        '<p style="color:red"><b>Note</b></p>'
    )
    get_sess = list(app.dependency_overrides.values())[0]
    with next(get_sess()) as s:  # type: ignore
        s.add(
            models.JoobleJobFeed(
                id=900001,
                position="Operator",
                employers_name="Talenti",
                employers_id=1,
                priority=2,
                description=raw,
                company="Joinrs",
                apply_url="https://www.joinrs.com/jobs/900001",
                company_id="829928",
                location="Italy",
                countries="ITA",
                workplace_types="On-site",
                experience_level="Entry Level",
                jobtype="Full Time",
                partner_job_id="900001",
                last_build_date=datetime.now(timezone.utc),
            )
        )
        s.commit()

    talent = client.get("/wrapping/talent")
    jooble = client.get("/wrapping/jooble")
    assert talent.status_code == 200
    assert jooble.status_code == 200

    assert "**" not in talent.text
    assert "<strong>Talenti</strong>" in talent.text
    assert "<strong>Requisiti</strong>" in talent.text
    assert "<li>Esperienza</li>" in talent.text
    assert "<strong>Note</strong>" in talent.text
    assert "style=" not in talent.text

    # Jooble unchanged (still has markdown markers from DB)
    assert "**Talenti**" in jooble.text


def test_wrapping_jooble_abroad_empty(client: TestClient):
    """Jooble abroad endpoint with no jobs returns valid XML."""
    r = client.get("/wrapping/jooble/abroad")
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    assert "<source>" in r.text
    assert "<lastBuildDate>" in r.text


def test_wrapping_jooble_abroad_one_job(client: TestClient):
    """Jooble abroad: countries, employers_id, apply URL without query params."""
    _now = datetime.now(timezone.utc)
    get_sess = list(app.dependency_overrides.values())[0]
    with next(get_sess()) as s:  # type: ignore
        row = models.JoobleAbroadJobFeed(
            id=3218063,
            position="Software Engineer",
            employers_name="Acme Corp",
            employers_id=589893,
            priority=2,
            description="<p>Enterprise role abroad</p>",
            company="Joinrs",
            apply_url=(
                "https://www.joinrs.com/jobs/3218063/"
                "?utm_source=linkedin&utm_medium=589893-2&utm_campaign=3218063-pro"
            ),
            company_id="829928",
            location="Multi-country",
            countries="DEU, FRA, ITA",
            workplace_types="Remote",
            experience_level="Mid Level",
            jobtype="Full Time",
            partner_job_id="3218063",
            last_build_date=_now,
        )
        s.add(row)
        s.commit()

    r = client.get("/wrapping/jooble/abroad")
    assert r.status_code == 200
    assert "<company><![CDATA[Acme Corp]]></company>" in r.text
    assert "<priority><![CDATA[2]]></priority>" in r.text
    assert "<employers_id><![CDATA[589893]]></employers_id>" in r.text
    assert "<countries><![CDATA[DEU, FRA, ITA]]></countries>" in r.text
    assert "<applyUrl><![CDATA[https://www.joinrs.com/jobs/3218063]]></applyUrl>" in r.text
    assert "utm_" not in r.text.split("<applyUrl>")[1].split("</applyUrl>")[0]

    r2 = client.get("/wrapping/jooble")
    assert r2.status_code == 200
    assert "<countries>" not in r2.text

    r3 = client.get("/wrapping/")
    assert r3.status_code == 200
    assert "<countries>" not in r3.text


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


def test_wrapping_whatjobs_empty(client: TestClient):
    r = client.get("/wrapping/whatjobs")
    assert r.status_code == 200
    assert "application/xml" in r.headers.get("content-type", "")
    assert "<jobs>" in r.text
    assert "</jobs>" in r.text
    assert "<source>" not in r.text


def test_wrapping_whatjobs_one_job_cdata_and_tags(client: TestClient):
    get_sess = list(app.dependency_overrides.values())[0]
    with next(get_sess()) as s:  # type: ignore
        row = models.WhatjobsJobFeed(
            id=3218063,
            link="https://www.joinrs.com/jobs/3218063",
            name="Software Engineer",
            region="Milan - Italy",
            remote="Hybrid",
            salary="25000-29000 EUR",
            description="<p>Role with ]]> edge case</p>",
            company="Acme Corp",
            company_logo="https://example.com/logo.png",
            pubdate="01.06.2026",
            updated="08.06.2026",
            expire="31.07.2026",
            jobtype="full-time",
            employers_id=589893,
            priority=2,
            experience_level="Mid Level",
        )
        s.add(row)
        s.commit()

    r = client.get("/wrapping/whatjobs")
    assert r.status_code == 200
    assert '<job id="3218063">' in r.text
    assert "<link><![CDATA[https://www.joinrs.com/jobs/3218063]]></link>" in r.text
    assert "<name><![CDATA[Software Engineer]]></name>" in r.text
    assert "<region><![CDATA[Milan - Italy]]></region>" in r.text
    assert "<remote><![CDATA[Hybrid]]></remote>" in r.text
    assert "<salary><![CDATA[25000-29000 EUR]]></salary>" in r.text
    assert "<company><![CDATA[Acme Corp]]></company>" in r.text
    assert "<jobtype><![CDATA[full-time]]></jobtype>" in r.text
    assert "]]]]><![CDATA[>" in r.text
    assert "<employers_id>" not in r.text
    assert "<priority>" not in r.text
    assert "<experience_level>" not in r.text


def test_wrapping_whatjobs_omits_empty_optional_tags(client: TestClient):
    get_sess = list(app.dependency_overrides.values())[0]
    with next(get_sess()) as s:  # type: ignore
        row = models.WhatjobsJobFeed(
            id=1,
            link="https://www.joinrs.com/jobs/1",
            name="Intern",
            region="Rome - Italy",
            remote="",
            salary=None,
            description="<p>Desc</p>",
            company="Acme",
            company_logo="",
            pubdate="01.06.2026",
            updated="08.06.2026",
            expire="31.07.2026",
            jobtype="full-time",
        )
        s.add(row)
        s.commit()

    r = client.get("/wrapping/whatjobs")
    assert r.status_code == 200
    assert "<remote>" not in r.text
    assert "<salary>" not in r.text
    assert "<company_logo>" not in r.text


def test_wrapping_whatjobs_reads_from_table_not_job_postings(client: TestClient):
    _now = datetime.now(timezone.utc)
    get_sess = list(app.dependency_overrides.values())[0]
    with next(get_sess()) as s:  # type: ignore
        s.add(
            models.JobPostings(
                id=99,
                position="Only LinkedIn",
                created_at=_now,
                updated_at=_now,
            )
        )
        s.add(
            models.WhatjobsJobFeed(
                id=1,
                link="https://www.joinrs.com/jobs/1",
                name="Only WhatJobs",
                region="Turin - Italy",
                description="<p>Test</p>",
                company="Employer",
                pubdate="01.06.2026",
                updated="08.06.2026",
                expire="31.07.2026",
                jobtype="full-time",
            )
        )
        s.commit()

    r = client.get("/wrapping/whatjobs")
    assert r.status_code == 200
    assert "<![CDATA[Only WhatJobs]]>" in r.text
    assert "Only LinkedIn" not in r.text

    r2 = client.get("/wrapping/")
    assert r2.status_code == 200
    assert "<![CDATA[Only LinkedIn]]>" in r2.text
    assert "Only WhatJobs" not in r2.text


