-- Crea le tabelle per la pipeline di enrichment.
-- Esegui nel database usato da DB_NAME (es. lw). Es: mysql -u ... -p ... < create_enrichment_tables.sql
-- Esegui solo se le tabelle non esistono già.

-- Sorgente annunci (solo lettura dalla pipeline)
CREATE TABLE IF NOT EXISTS blue_collar_copy (
    id INT AUTO_INCREMENT PRIMARY KEY,
    position VARCHAR(512),
    description TEXT,
    employment_type VARCHAR(128),
    type VARCHAR(128),
    created_at DATETIME,
    updated_at DATETIME,
    normalized_title VARCHAR(1024),
    normalized_text TEXT,
    language VARCHAR(16),
    collar_type VARCHAR(32)
);

-- Output pipeline
CREATE TABLE IF NOT EXISTS job_enrichment (
    job_id INT PRIMARY KEY,
    normalized_title VARCHAR(1024),
    normalized_text TEXT,
    detected_language VARCHAR(16),
    processing_version VARCHAR(32),
    collar_type VARCHAR(32),
    collar_confidence FLOAT,
    sector_macro_id INT,
    sector_micro_id INT,
    sector_confidence FLOAT,
    sector_method VARCHAR(32),
    gpt_group_id INT,
    gpt_question_id INT,
    gpt_confidence FLOAT,
    gpt_method VARCHAR(32),
    seniority_id INT,
    seniority_confidence FLOAT,
    seniority_method VARCHAR(32),
    education_level_id INT,
    education_confidence FLOAT,
    education_method VARCHAR(32),
    explanation_json JSON,
    model_version VARCHAR(64),
    created_at DATETIME,
    updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS job_education_types (
    job_id INT,
    education_type_id INT,
    confidence FLOAT,
    evidence VARCHAR(512),
    created_at DATETIME,
    PRIMARY KEY (job_id, education_type_id),
    FOREIGN KEY (job_id) REFERENCES job_enrichment(job_id) ON DELETE CASCADE
);
