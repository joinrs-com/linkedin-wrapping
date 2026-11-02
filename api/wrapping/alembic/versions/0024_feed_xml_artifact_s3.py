"""feed_xml_artifact: S3/file storage_uri + nullable payload

Revision ID: 0024_feed_xml_artifact_s3
Revises: 0023_add_bucket_country_code_feeds
Create Date: 2026-11-02

Full-text campaign XML gzip exceeds MySQL max_allowed_packet; store blobs
outside MySQL and keep only metadata (+ optional small payload) in the table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "0024_feed_xml_artifact_s3"
down_revision: Union[str, None] = "0023_add_bucket_country_code_feeds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "feed_xml_artifact",
        sa.Column("storage_uri", sa.String(512), nullable=True),
        schema="lw",
    )
    op.add_column(
        "feed_xml_artifact",
        sa.Column("bytes_gzip", sa.BigInteger(), nullable=False, server_default="0"),
        schema="lw",
    )
    op.alter_column(
        "feed_xml_artifact",
        "payload",
        existing_type=mysql.LONGBLOB(),
        nullable=True,
        schema="lw",
    )


def downgrade() -> None:
    # Rows with NULL payload cannot be downgraded safely; require payload present.
    op.alter_column(
        "feed_xml_artifact",
        "payload",
        existing_type=mysql.LONGBLOB(),
        nullable=False,
        schema="lw",
    )
    op.drop_column("feed_xml_artifact", "bytes_gzip", schema="lw")
    op.drop_column("feed_xml_artifact", "storage_uri", schema="lw")
