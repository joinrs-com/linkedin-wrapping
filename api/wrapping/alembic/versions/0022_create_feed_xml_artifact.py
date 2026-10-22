"""create feed_xml_artifact for pre-generated gzip XML feeds

Revision ID: 0022_create_feed_xml_artifact
Revises: 0021_add_description_talent_jooble
Create Date: 2026-10-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "0022_create_feed_xml_artifact"
down_revision: Union[str, None] = "0021_add_description_talent_jooble"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feed_xml_artifact",
        sa.Column("feed_name", sa.String(64), primary_key=True, nullable=False),
        sa.Column("payload", mysql.LONGBLOB(), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False, server_default="application/xml"),
        sa.Column("job_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_uncompressed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        schema="lw",
    )


def downgrade() -> None:
    op.drop_table("feed_xml_artifact", schema="lw")
