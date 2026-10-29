"""Jooble/Talent omit CPC; Adzuna requires CPC; countryCode present."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from api.wrapping.wrapping import generate_adzuna_xml, generate_wrapping_xml  # noqa: E402


def test_jooble_xml_has_country_code_no_cpc():
    job = SimpleNamespace(
        id="1-1",
        partner_job_id="1-1",
        position="Dev",
        description="<p>hi</p>",
        apply_url="https://www.joinrs.com/jobs/1",
        company="Joinrs",
        employers_name="Acme",
        employers_id=1,
        company_id="829928",
        location="Rome",
        countries="ITA",
        country_code="ITA",
        workplace_types="On-site",
        experience_level="Junior",
        jobtype="Full Time",
        priority=1,
        salary=None,
        last_build_date=datetime(2026, 1, 1),
        description_talent=None,
    )
    xml = generate_wrapping_xml(
        [job],
        apply_url_mode="jooble",
        prefer_employers_name_as_company=True,
        include_priority=True,
        include_employers_id=True,
        include_country_code=True,
    )
    assert "<countryCode>" in xml
    assert "ITA" in xml
    assert "<cpc>" not in xml
    assert "<priority>" in xml


def test_adzuna_xml_has_cpc_and_country_code():
    job = SimpleNamespace(
        id="1-1",
        title="Dev",
        description="<p>hi</p>",
        url="https://www.joinrs.com/jobs/1?utm_source=adzuna",
        location="Madrid",
        country="ES",
        country_code="ESP",
        remote="Non-Remote",
        salary=None,
        company="Acme",
        category=None,
        posted_date=None,
        cpc=0.08,
        priority=1,
    )
    xml = generate_adzuna_xml([job])
    assert "<cpc>" in xml
    assert "0.08" in xml
    assert "<country>" in xml
    assert "<country_code>" in xml
    assert "ESP" in xml
