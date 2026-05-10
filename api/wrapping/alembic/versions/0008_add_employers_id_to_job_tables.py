"""add employers_id to job_postings and job_posting_pre

Revision ID: 0008_add_employers_id
Revises: 0007_drop_job_jooble_mapping
Create Date: 2026-05-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_add_employers_id"
down_revision: Union[str, None] = "0007_drop_job_jooble_mapping"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_postings",
        sa.Column("employers_id", sa.BigInteger(), nullable=True),
        schema="lw",
    )
    op.add_column(
        "job_posting_pre",
        sa.Column("employers_id", sa.BigInteger(), nullable=True),
        schema="lw",
    )


def downgrade() -> None:
    op.drop_column("job_posting_pre", "employers_id", schema="lw")
    op.drop_column("job_postings", "employers_id", schema="lw")
