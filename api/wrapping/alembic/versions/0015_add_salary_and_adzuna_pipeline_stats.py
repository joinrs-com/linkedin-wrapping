"""add salary to feed tables and adzuna stats on pipeline_run

Revision ID: 0015_add_salary_and_adzuna_pipeline_stats
Revises: 0014_create_adzuna_job_feed
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_add_salary_and_adzuna_pipeline_stats"
down_revision: Union[str, None] = "0014_create_adzuna_job_feed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jooble_job_feed",
        sa.Column("salary", sa.String(100), nullable=True),
        schema="lw",
    )
    op.add_column(
        "jooble_abroad_job_feed",
        sa.Column("salary", sa.String(100), nullable=True),
        schema="lw",
    )
    op.add_column(
        "hirematic_job_feed",
        sa.Column("salary", sa.String(100), nullable=True),
        schema="lw",
    )
    op.add_column(
        "job_feed_pipeline_run",
        sa.Column("adzuna_inserted", sa.Integer(), nullable=False, server_default="0"),
        schema="lw",
    )
    op.add_column(
        "job_feed_pipeline_run",
        sa.Column("adzuna_deleted", sa.Integer(), nullable=False, server_default="0"),
        schema="lw",
    )
    op.add_column(
        "job_feed_pipeline_run",
        sa.Column("adzuna_total", sa.Integer(), nullable=False, server_default="0"),
        schema="lw",
    )


def downgrade() -> None:
    op.drop_column("job_feed_pipeline_run", "adzuna_total", schema="lw")
    op.drop_column("job_feed_pipeline_run", "adzuna_deleted", schema="lw")
    op.drop_column("job_feed_pipeline_run", "adzuna_inserted", schema="lw")
    op.drop_column("hirematic_job_feed", "salary", schema="lw")
    op.drop_column("jooble_abroad_job_feed", "salary", schema="lw")
    op.drop_column("jooble_job_feed", "salary", schema="lw")
