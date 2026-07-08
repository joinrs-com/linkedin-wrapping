"""create whatjobs_job_feed table for WhatJobs XML export

Revision ID: 0011_create_whatjobs_job_feed
Revises: 0010_create_jooble_job_feed
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_create_whatjobs_job_feed"
down_revision: Union[str, None] = "0010_create_jooble_job_feed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "whatjobs_job_feed",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("link", sa.Text(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("region", sa.Text(), nullable=False),
        sa.Column("remote", sa.String(255), nullable=True),
        sa.Column("salary", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("company_logo", sa.Text(), nullable=True),
        sa.Column("pubdate", sa.String(10), nullable=False),
        sa.Column("updated", sa.String(10), nullable=False),
        sa.Column("expire", sa.String(10), nullable=False),
        sa.Column("jobtype", sa.String(50), nullable=False),
        sa.Column("employers_id", sa.BigInteger(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("experience_level", sa.String(50), nullable=True),
        schema="lw",
    )


def downgrade() -> None:
    op.drop_table("whatjobs_job_feed", schema="lw")
