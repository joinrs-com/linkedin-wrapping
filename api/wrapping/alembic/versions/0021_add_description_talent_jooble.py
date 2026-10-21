"""add description_talent to jooble_job_feed for Talent pre-sanitize

Revision ID: 0021_add_description_talent_jooble
Revises: 0020_string_pk_jooble_abroad_explode
Create Date: 2026-10-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0021_add_description_talent_jooble"
down_revision: Union[str, None] = "0020_string_pk_jooble_abroad_explode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jooble_job_feed",
        sa.Column("description_talent", sa.Text(), nullable=True),
        schema="lw",
    )


def downgrade() -> None:
    op.drop_column("jooble_job_feed", "description_talent", schema="lw")
