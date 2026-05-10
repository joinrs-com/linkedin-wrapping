-- Allinea job_postings.apply_url da job_posting_pre (stesso partner_job_id).
-- Serve quando job_posting_pre ha già utm_medium=<employers_id>-<priority> e job_postings
-- contiene ancora utm_medium=job-offer-ats (dati inseriti prima del refresh SQL).
--
-- MySQL: eseguire sul database che contiene lw.job_postings / job_posting_pre
-- (se usi schema lw, prefissa i nomi tabella con lw.)

UPDATE job_postings j
INNER JOIN job_posting_pre p
    ON j.partner_job_id = p.partner_job_id
    AND j.partner_job_id IS NOT NULL
    AND TRIM(j.partner_job_id) <> ''
    AND p.partner_job_id IS NOT NULL
    AND TRIM(p.partner_job_id) <> ''
SET
    j.apply_url = p.apply_url
WHERE
    p.apply_url IS NOT NULL
    AND TRIM(p.apply_url) <> '';

-- Dopo `alembic upgrade head` (0008_add_employers_id), allinea anche employers_id:
-- UPDATE job_postings j
-- INNER JOIN job_posting_pre p
--     ON j.partner_job_id = p.partner_job_id
--     AND j.partner_job_id IS NOT NULL
--     AND TRIM(j.partner_job_id) <> ''
--     AND p.partner_job_id IS NOT NULL
--     AND TRIM(p.partner_job_id) <> ''
-- SET j.employers_id = p.employers_id
-- WHERE p.employers_id IS NOT NULL;

-- Variante più conservativa (solo righe con medium legacy in job_postings):
-- Aggiungi alla WHERE finale:
--   AND (j.apply_url LIKE '%utm_medium=job-offer-ats%' OR j.apply_url IS NULL);
