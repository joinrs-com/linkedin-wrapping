-- Tabella di mapping per Jooble: partner_job_id -> jo_ais_id
-- Usata dall'endpoint GET /wrapping/jooble per costruire l'apply URL:
-- https://www.joinrs.ai/it/jobs/{jo_ais_id}/?utm_source=jooble&utm_medium=job-offer-ats&utm_campaign={jo_ais_id}-scraped
--
-- Su MySQL eseguire questo script (nessuno schema).
-- Su PostgreSQL usare la migrazione Alembic 0006 che crea la tabella nello schema "lw".

CREATE TABLE IF NOT EXISTS job_jooble_mapping (
    id BIGINT NOT NULL AUTO_INCREMENT,
    partner_job_id VARCHAR(255) NOT NULL,
    jo_ais_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY ix_job_jooble_mapping_partner_job_id (partner_job_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
