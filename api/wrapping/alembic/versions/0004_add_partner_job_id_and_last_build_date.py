"""add partner_job_id and last_build_date to job_postings

Revision ID: 0004_add_partner_job_id_and_last_build_date
Revises: 0003_add_linkedin_fields_to_job_postings
Create Date: 2025-01-27 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_add_partner_job_id_and_last_build_date"
down_revision: Union[str, None] = "0003_add_linkedin_fields_to_job_postings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("job_postings", sa.Column("partner_job_id", sa.String(length=255), nullable=True), schema="lw")
    op.add_column("job_postings", sa.Column("last_build_date", sa.DateTime(), nullable=True), schema="lw")


def downgrade() -> None:
    op.drop_column("job_postings", "last_build_date", schema="lw")
    op.drop_column("job_postings", "partner_job_id", schema="lw")

