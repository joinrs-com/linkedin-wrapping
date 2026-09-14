"""create adzuna_job_feed table for Adzuna XML export

Revision ID: 0014_create_adzuna_job_feed
Revises: 0013_create_job_feed_pipeline_run
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_create_adzuna_job_feed"
down_revision: Union[str, None] = "0013_create_job_feed_pipeline_run"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_table("adzuna_job_feed", schema="lw")
