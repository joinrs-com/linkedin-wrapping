-- Audit apply_url utm_medium in job_postings (MySQL, database/schema già selezionati).
-- Esegui dopo refresh job_posting_pre o prima di sync_apply_url_from_pre_to_postings.sql

SELECT
    SUM(CASE WHEN apply_url LIKE '%utm_medium=job-offer-ats%' THEN 1 ELSE 0 END) AS rows_job_offer_ats,
    SUM(
        CASE
            WHEN apply_url REGEXP 'utm_medium=[0-9]+-[0-9]+'
                AND apply_url NOT LIKE '%utm_medium=job-offer-ats%'
            THEN 1
            ELSE 0
        END
    ) AS rows_employer_priority_medium,
    SUM(CASE WHEN apply_url IS NULL OR apply_url = '' THEN 1 ELSE 0 END) AS rows_empty_apply_url,
    COUNT(*) AS total_rows
FROM job_postings;

-- Stesso breakdown su staging (dovrebbe riflettere la query di refresh aggiornata)
SELECT
    SUM(CASE WHEN apply_url LIKE '%utm_medium=job-offer-ats%' THEN 1 ELSE 0 END) AS pre_job_offer_ats,
    SUM(
        CASE
            WHEN apply_url REGEXP 'utm_medium=[0-9]+-[0-9]+'
                AND apply_url NOT LIKE '%utm_medium=job-offer-ats%'
            THEN 1
            ELSE 0
        END
    ) AS pre_employer_priority_medium,
    COUNT(*) AS pre_total
FROM job_posting_pre;
