"""create job_jooble_mapping table for Jooble apply URL (jo_ais_id)

Revision ID: 0006_job_jooble_mapping
Revises: 0005_create_job_posting_pre
Create Date: 2025-02-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_job_jooble_mapping"
down_revision: Union[str, None] = "0005_create_job_posting_pre"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_jooble_mapping",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("partner_job_id", sa.String(255), nullable=False),
        sa.Column("jo_ais_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        schema="lw",
    )
    op.create_index(
        "ix_job_jooble_mapping_partner_job_id",
        "job_jooble_mapping",
        ["partner_job_id"],
        unique=True,
        schema="lw",
    )


def downgrade() -> None:
    op.drop_index("ix_job_jooble_mapping_partner_job_id", "job_jooble_mapping", schema="lw")
    op.drop_table("job_jooble_mapping", schema="lw")
