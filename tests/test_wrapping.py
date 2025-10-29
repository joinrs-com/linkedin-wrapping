from __future__ import annotations

import os
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
    assert r.json() == {"Ok!"}


def test_root_endpoint(client: TestClient):
    """Test root endpoint."""
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["message"] == "LinkedIn Wrapping Service API"
    assert data["version"] == "1.0.0"


def test_wrapping_endpoint_empty(client: TestClient):
    """Test wrapping endpoint with no job postings."""
    r = client.get("/wrapping")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/xml"
    content = r.text
    assert "<postings>" in content
    assert "</postings>" in content


def test_wrapping_endpoint_with_jobs(client: TestClient):
    """Test wrapping endpoint with job postings."""
    # Create test job postings
    get_sess = list(app.dependency_overrides.values())[0]
    with next(get_sess()) as s:  # type: ignore
        job1 = models.JobPostings(id=1, position="Software Engineer")
        job2 = models.JobPostings(id=2, position="Data Scientist")
        s.add(job1)
        s.add(job2)
        s.commit()
    
    r = client.get("/wrapping")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/xml"
    content = r.text
    
    # Check XML structure
    assert "<postings>" in content
    assert "</postings>" in content
    assert 'id="1"' in content
    assert 'position="Software Engineer"' in content
    assert 'id="2"' in content
    assert 'position="Data Scientist"' in content
    assert "<job" in content
    assert "/>" in content or "</job>" in content

