"""Retire jooble_abroad_job_feed; geographic Jooble feeds replace it.

Revision ID: 0025_drop_jooble_abroad
Revises: 0024_feed_xml_artifact_s3

Take a verified data backup before upgrading. Downgrade restores the empty
schema only; recover historical rows from that backup if required.
"""
from alembic import op
import sqlalchemy as sa

revision = "0025_drop_jooble_abroad"
down_revision = "0024_feed_xml_artifact_s3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("jooble_abroad_job_feed", schema="lw")


def downgrade() -> None:
    op.create_table(
        "jooble_abroad_job_feed",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("job_posting_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.String(255), nullable=False),
        sa.Column("employers_name", sa.String(255), nullable=True),
        sa.Column("employers_id", sa.BigInteger(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("apply_url", sa.Text(), nullable=True),
        sa.Column("company_id", sa.String(255), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("countries", sa.Text(), nullable=True),
        sa.Column("workplace_types", sa.String(50), nullable=True),
        sa.Column("experience_level", sa.String(50), nullable=True),
        sa.Column("jobtype", sa.String(50), nullable=True),
        sa.Column("partner_job_id", sa.String(255), nullable=True),
        sa.Column("last_build_date", sa.DateTime(), nullable=True),
        sa.Column("salary", sa.String(100), nullable=True),
        schema="lw",
    )
    op.create_index(
        "ix_jooble_abroad_job_feed_job_posting_id",
        "jooble_abroad_job_feed",
        ["job_posting_id"],
        schema="lw",
    )
