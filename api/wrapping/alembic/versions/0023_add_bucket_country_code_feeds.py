"""add bucket + country_code to jooble_job_feed and adzuna_job_feed

Revision ID: 0023_add_bucket_country_code_feeds
Revises: 0022_create_feed_xml_artifact
Create Date: 2026-10-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0023_add_bucket_country_code_feeds"
down_revision: Union[str, None] = "0022_create_feed_xml_artifact"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jooble_job_feed",
        sa.Column("country_code", sa.String(10), nullable=True),
        schema="lw",
    )
    op.add_column(
        "jooble_job_feed",
        sa.Column("bucket", sa.String(16), nullable=True),
        schema="lw",
    )
    op.create_index(
        "ix_jooble_job_feed_bucket",
        "jooble_job_feed",
        ["bucket"],
        schema="lw",
    )
    op.create_index(
        "ix_jooble_job_feed_bucket_country",
        "jooble_job_feed",
        ["bucket", "country_code"],
        schema="lw",
    )

    op.add_column(
        "adzuna_job_feed",
        sa.Column("country_code", sa.String(10), nullable=True),
        schema="lw",
    )
    op.add_column(
        "adzuna_job_feed",
        sa.Column("bucket", sa.String(16), nullable=True),
        schema="lw",
    )
    op.create_index(
        "ix_adzuna_job_feed_bucket",
        "adzuna_job_feed",
        ["bucket"],
        schema="lw",
    )
    op.create_index(
        "ix_adzuna_job_feed_bucket_country",
        "adzuna_job_feed",
        ["bucket", "country_code"],
        schema="lw",
    )


def downgrade() -> None:
    op.drop_index("ix_adzuna_job_feed_bucket_country", table_name="adzuna_job_feed", schema="lw")
    op.drop_index("ix_adzuna_job_feed_bucket", table_name="adzuna_job_feed", schema="lw")
    op.drop_column("adzuna_job_feed", "bucket", schema="lw")
    op.drop_column("adzuna_job_feed", "country_code", schema="lw")

    op.drop_index("ix_jooble_job_feed_bucket_country", table_name="jooble_job_feed", schema="lw")
    op.drop_index("ix_jooble_job_feed_bucket", table_name="jooble_job_feed", schema="lw")
    op.drop_column("jooble_job_feed", "bucket", schema="lw")
    op.drop_column("jooble_job_feed", "country_code", schema="lw")
