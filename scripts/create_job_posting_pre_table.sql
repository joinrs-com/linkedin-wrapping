-- Script SQL per creare manualmente la tabella job_posting_pre
-- Identica a job_postings ma con job_description invece di description

CREATE TABLE IF NOT EXISTS job_posting_pre (
    id BIGINT NOT NULL AUTO_INCREMENT,
    position VARCHAR(255) NOT NULL,
    job_description TEXT NULL,
    company VARCHAR(255) NULL,
    apply_url TEXT NULL,
    company_id VARCHAR(255) NULL,
    location VARCHAR(255) NULL,
    workplace_types VARCHAR(50) NULL,
    experience_level VARCHAR(50) NULL,
    jobtype VARCHAR(50) NULL,
    partner_job_id VARCHAR(255) NULL,
    last_build_date DATETIME NULL,
    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

