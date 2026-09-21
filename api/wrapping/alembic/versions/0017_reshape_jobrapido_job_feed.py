"""reshape jobrapido_job_feed to Job Rapido XML schema (explode locations)

Revision ID: 0017_reshape_jobrapido_job_feed
Revises: 0016_create_jobrapido_job_feed
Create Date: 2026-09-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_reshape_jobrapido_job_feed"
down_revision: Union[str, None] = "0016_create_jobrapido_job_feed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("jobrapido_job_feed", schema="lw")
    op.create_table(
        "jobrapido_job_feed",
        sa.Column("reference_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("job_posting_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("country", sa.String(10), nullable=False),
        sa.Column("postalcode", sa.String(20), nullable=True),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("website", sa.String(255), nullable=False),
        sa.Column("publishdate", sa.Date(), nullable=False),
        sa.Column("expirydate", sa.Date(), nullable=False),
        sa.Column("salary", sa.String(100), nullable=True),
        sa.Column("education", sa.String(255), nullable=True),
        sa.Column("jobtype", sa.String(100), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("experience", sa.String(255), nullable=True),
        sa.Column("cpc", sa.Numeric(10, 3), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        schema="lw",
    )
    op.create_index(
        "ix_jobrapido_job_feed_job_posting_id",
        "jobrapido_job_feed",
        ["job_posting_id"],
        schema="lw",
    )


def downgrade() -> None:
    op.drop_table("jobrapido_job_feed", schema="lw")
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
