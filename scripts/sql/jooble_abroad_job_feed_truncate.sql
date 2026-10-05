-- Recovery only: svuota lw.jooble_abroad_job_feed.
-- Il flusso quotidiano è incrementale via scripts/run_job_feed_pipeline.py (niente TRUNCATE).
-- 1. TRUNCATE TABLE lw.jooble_abroad_job_feed;
-- 2. Relancia la pipeline (o solo il sync jooble_abroad)
-- 3. Verifica GET /wrapping/jooble/abroad

TRUNCATE TABLE lw.jooble_abroad_job_feed;
