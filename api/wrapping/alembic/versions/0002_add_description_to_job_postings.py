"""add description to job_postings

Revision ID: 0002_add_description_to_job_postings
Revises: 0001_init_job_postings
Create Date: 2025-01-27 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_add_description_to_job_postings"
down_revision: Union[str, None] = "0001_init_job_postings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_postings",
        sa.Column("description", sa.Text(), nullable=True),
        schema="lw",
    )


def downgrade() -> None:
    op.drop_column("job_postings", "description", schema="lw")

