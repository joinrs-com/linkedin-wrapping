"""create jobrapido_job_feed table and pipeline_run stats

Revision ID: 0016_create_jobrapido_job_feed
Revises: 0015_add_salary_and_adzuna_pipeline_stats
Create Date: 2026-09-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_create_jobrapido_job_feed"
down_revision: Union[str, None] = "0015_add_salary_and_adzuna_pipeline_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobrapido_job_feed",
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
    op.add_column(
        "job_feed_pipeline_run",
        sa.Column("jobrapido_inserted", sa.Integer(), nullable=False, server_default="0"),
        schema="lw",
    )
    op.add_column(
        "job_feed_pipeline_run",
        sa.Column("jobrapido_deleted", sa.Integer(), nullable=False, server_default="0"),
        schema="lw",
    )
    op.add_column(
        "job_feed_pipeline_run",
        sa.Column("jobrapido_total", sa.Integer(), nullable=False, server_default="0"),
        schema="lw",
    )


def downgrade() -> None:
    op.drop_column("job_feed_pipeline_run", "jobrapido_total", schema="lw")
    op.drop_column("job_feed_pipeline_run", "jobrapido_deleted", schema="lw")
    op.drop_column("job_feed_pipeline_run", "jobrapido_inserted", schema="lw")
    op.drop_table("jobrapido_job_feed", schema="lw")
