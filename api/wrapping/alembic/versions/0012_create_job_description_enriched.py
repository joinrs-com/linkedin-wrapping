"""create job_description_enriched table for shared OpenAI descriptions

Revision ID: 0012_create_job_description_enriched
Revises: 0011_create_whatjobs_job_feed
Create Date: 2026-07-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_create_job_description_enriched"
down_revision: Union[str, None] = "0011_create_whatjobs_job_feed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_description_enriched",
        sa.Column("job_id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("has_ita", sa.SmallInteger(), nullable=True),
        sa.Column("employers_id", sa.BigInteger(), nullable=True),
        sa.Column("enriched_at", sa.DateTime(), nullable=False),
        schema="lw",
    )


def downgrade() -> None:
    op.drop_table("job_description_enriched", schema="lw")
