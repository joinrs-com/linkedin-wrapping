"""add jooble abroad stats on pipeline_run

Revision ID: 0018_add_jooble_abroad_pipeline_stats
Revises: 0017_reshape_jobrapido_job_feed
Create Date: 2026-10-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0018_add_jooble_abroad_pipeline_stats"
down_revision: Union[str, None] = "0017_reshape_jobrapido_job_feed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_feed_pipeline_run",
        sa.Column("jooble_abroad_inserted", sa.Integer(), nullable=False, server_default="0"),
        schema="lw",
    )
    op.add_column(
        "job_feed_pipeline_run",
        sa.Column("jooble_abroad_deleted", sa.Integer(), nullable=False, server_default="0"),
        schema="lw",
    )
    op.add_column(
        "job_feed_pipeline_run",
        sa.Column("jooble_abroad_total", sa.Integer(), nullable=False, server_default="0"),
        schema="lw",
    )


def downgrade() -> None:
    op.drop_column("job_feed_pipeline_run", "jooble_abroad_total", schema="lw")
    op.drop_column("job_feed_pipeline_run", "jooble_abroad_deleted", schema="lw")
    op.drop_column("job_feed_pipeline_run", "jooble_abroad_inserted", schema="lw")
