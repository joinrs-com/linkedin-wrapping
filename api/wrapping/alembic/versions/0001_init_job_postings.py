"""init lw tables

Revision ID: 0001_init_job_postings
Revises: 
Create Date: 2025-01-27 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_init_job_postings"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # job_postings
    op.create_table(
        "job_postings",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("position", sa.String(255), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), server_onupdate=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        schema="lw",
    )


def downgrade() -> None:
    op.drop_table("job_postings", schema="lw")


