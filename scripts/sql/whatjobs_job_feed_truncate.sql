-- Refresh manuale giornaliero di lw.whatjobs_job_feed
-- 1. TRUNCATE TABLE lw.whatjobs_job_feed;
-- 2. Esegui la SELECT in whatjobs_job_feed_select.sql ed importa i risultati nella tabella
-- 3. Verifica GET /wrapping/whatjobs

TRUNCATE TABLE lw.whatjobs_job_feed;
