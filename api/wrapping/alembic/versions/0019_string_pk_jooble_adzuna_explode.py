"""string PK for jooble/adzuna feeds (per-city explode ids)

Revision ID: 0019_string_pk_jooble_adzuna_explode
Revises: 0018_add_jooble_abroad_pipeline_stats
Create Date: 2026-10-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0019_string_pk_jooble_adzuna_explode"
down_revision: Union[str, None] = "0018_add_jooble_abroad_pipeline_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("jooble_job_feed", schema="lw")
    op.create_table(
        "jooble_job_feed",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("job_posting_id", sa.BigInteger(), nullable=False),
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
        sa.Column("salary", sa.String(100), nullable=True),
        schema="lw",
    )
    op.create_index(
        "ix_jooble_job_feed_job_posting_id",
        "jooble_job_feed",
        ["job_posting_id"],
        schema="lw",
    )

    op.drop_table("adzuna_job_feed", schema="lw")
    op.create_table(
        "adzuna_job_feed",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("job_posting_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("country", sa.String(10), nullable=False),
        sa.Column("remote", sa.String(50), nullable=True),
        sa.Column("salary", sa.String(100), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("cpc", sa.Numeric(10, 3), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        schema="lw",
    )
    op.create_index(
        "ix_adzuna_job_feed_job_posting_id",
        "adzuna_job_feed",
        ["job_posting_id"],
        schema="lw",
    )


def downgrade() -> None:
    op.drop_table("adzuna_job_feed", schema="lw")
    op.create_table(
        "adzuna_job_feed",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("country", sa.String(10), nullable=False),
        sa.Column("remote", sa.String(50), nullable=True),
        sa.Column("salary", sa.String(100), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("cpc", sa.Numeric(10, 3), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        schema="lw",
    )

    op.drop_table("jooble_job_feed", schema="lw")
    op.create_table(
        "jooble_job_feed",
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
        sa.Column("salary", sa.String(100), nullable=True),
        schema="lw",
    )
