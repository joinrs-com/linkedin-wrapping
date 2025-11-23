"""create job_posting_pre table

Revision ID: 0005_create_job_posting_pre
Revises: 0004_add_partner_job_id_and_last_build_date
Create Date: 2025-01-27 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_create_job_posting_pre"
down_revision: Union[str, None] = "0004_add_partner_job_id_and_last_build_date"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Crea tabella job_posting_pre identica a job_postings ma con job_description invece di description
    op.create_table(
        "job_posting_pre",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("position", sa.String(255), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=True),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("apply_url", sa.Text(), nullable=True),
        sa.Column("company_id", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("workplace_types", sa.String(length=50), nullable=True),
        sa.Column("experience_level", sa.String(length=50), nullable=True),
        sa.Column("jobtype", sa.String(length=50), nullable=True),
        sa.Column("partner_job_id", sa.String(length=255), nullable=True),
        sa.Column("last_build_date", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), server_onupdate=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        schema="lw",
    )


def downgrade() -> None:
    op.drop_table("job_posting_pre", schema="lw")

