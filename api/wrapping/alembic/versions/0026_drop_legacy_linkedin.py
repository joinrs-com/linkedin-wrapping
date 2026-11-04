"""Remove retired lw LinkedIn staging, catalog and OpenAI description tables.

Take verified data backups before upgrading. Downgrade recreates empty schemas;
recover rows and exact original DDL from the backups if necessary.
Production source job_postings.job_postings_1 is outside this migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "0026_drop_legacy_linkedin"
down_revision = "0025_drop_jooble_abroad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("job_description_enriched", "job_posting_pre", "job_postings"):
        op.drop_table(table, schema="lw")


def _create_legacy_catalog(table: str, description: str) -> None:
    op.create_table(
        table,
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("position", sa.String(255), nullable=False),
        sa.Column(description, sa.Text(), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("apply_url", sa.Text(), nullable=True),
        sa.Column("company_id", sa.String(255), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("workplace_types", sa.String(50), nullable=True),
        sa.Column("experience_level", sa.String(50), nullable=True),
        sa.Column("jobtype", sa.String(50), nullable=True),
        sa.Column("partner_job_id", sa.String(255), nullable=True),
        sa.Column("last_build_date", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("employers_name", sa.String(255), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("employers_id", sa.BigInteger(), nullable=True),
        schema="lw",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci" if table == "job_posting_pre" else "utf8mb4_0900_ai_ci",
    )


def downgrade() -> None:
    _create_legacy_catalog("job_postings", "description")
    _create_legacy_catalog("job_posting_pre", "job_description")
    if op.get_bind().dialect.name == "mysql":
        op.execute(sa.text(
            "ALTER TABLE lw.job_posting_pre MODIFY updated_at TIMESTAMP NULL "
            "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        ))
    op.create_table(
        "job_description_enriched",
        sa.Column("job_id", sa.BigInteger(), primary_key=True, nullable=False, autoincrement=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("has_ita", sa.SmallInteger(), nullable=True),
        sa.Column("employers_id", sa.BigInteger(), nullable=True),
        sa.Column("enriched_at", sa.DateTime(), nullable=False),
        schema="lw",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
