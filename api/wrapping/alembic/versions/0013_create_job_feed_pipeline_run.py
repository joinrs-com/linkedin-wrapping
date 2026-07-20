"""create job_feed_pipeline_run table for pipeline run reports

Revision ID: 0013_create_job_feed_pipeline_run
Revises: 0012_create_job_description_enriched
Create Date: 2026-07-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_create_job_feed_pipeline_run"
down_revision: Union[str, None] = "0012_create_job_description_enriched"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_feed_pipeline_run",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("openai_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enriched_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enriched_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("linkedin_active", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("linkedin_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("linkedin_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("linkedin_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jooble_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jooble_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jooble_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("whatjobs_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("whatjobs_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("whatjobs_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hirematic_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hirematic_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hirematic_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        schema="lw",
    )


def downgrade() -> None:
    op.drop_table("job_feed_pipeline_run", schema="lw")
