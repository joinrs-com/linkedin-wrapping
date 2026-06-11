"""create jooble_abroad_job_feed table for Jooble enterprise abroad XML export

Revision ID: 0009_create_jooble_abroad_job_feed
Revises: 0008_add_employers_id
Create Date: 2026-06-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_create_jooble_abroad_job_feed"
down_revision: Union[str, None] = "0008_add_employers_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jooble_abroad_job_feed",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("position", sa.String(255), nullable=False),
        sa.Column("employers_name", sa.String(255), nullable=True),
        sa.Column("employers_id", sa.BigInteger(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("apply_url", sa.Text(), nullable=True),
        sa.Column("company_id", sa.String(255), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("countries", sa.Text(), nullable=True),
        sa.Column("workplace_types", sa.String(50), nullable=True),
        sa.Column("experience_level", sa.String(50), nullable=True),
        sa.Column("jobtype", sa.String(50), nullable=True),
        sa.Column("partner_job_id", sa.String(255), nullable=True),
        sa.Column("last_build_date", sa.DateTime(), nullable=True),
        schema="lw",
    )


def downgrade() -> None:
    op.drop_table("jooble_abroad_job_feed", schema="lw")
