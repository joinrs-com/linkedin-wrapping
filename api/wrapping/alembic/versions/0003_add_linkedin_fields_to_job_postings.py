"""add linkedin fields to job_postings

Revision ID: 0003_add_linkedin_fields_to_job_postings
Revises: 0002_add_description_to_job_postings
Create Date: 2025-01-27 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_add_linkedin_fields_to_job_postings"
down_revision: Union[str, None] = "0002_add_description_to_job_postings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("job_postings", sa.Column("company", sa.String(length=255), nullable=True), schema="lw")
    op.add_column("job_postings", sa.Column("apply_url", sa.Text(), nullable=True), schema="lw")
    op.add_column("job_postings", sa.Column("company_id", sa.String(length=255), nullable=True), schema="lw")
    op.add_column("job_postings", sa.Column("location", sa.String(length=255), nullable=True), schema="lw")
    op.add_column("job_postings", sa.Column("workplace_types", sa.String(length=50), nullable=True), schema="lw")
    op.add_column("job_postings", sa.Column("experience_level", sa.String(length=50), nullable=True), schema="lw")
    op.add_column("job_postings", sa.Column("jobtype", sa.String(length=50), nullable=True), schema="lw")


def downgrade() -> None:
    op.drop_column("job_postings", "jobtype", schema="lw")
    op.drop_column("job_postings", "experience_level", schema="lw")
    op.drop_column("job_postings", "workplace_types", schema="lw")
    op.drop_column("job_postings", "location", schema="lw")
    op.drop_column("job_postings", "company_id", schema="lw")
    op.drop_column("job_postings", "apply_url", schema="lw")
    op.drop_column("job_postings", "company", schema="lw")



