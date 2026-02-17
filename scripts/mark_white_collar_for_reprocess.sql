-- Reprocess ONLY rows where job_enrichment.collar_type = 'white'.
-- (Previously these may have been filled with sector_macro_id/sector_micro_id; after reprocessing
--  white collar will get sector = NULL and only gpt_group_id / gpt_question_id.)
--
-- 1) Optional: see how many will be reprocessed
--    SELECT COUNT(*) AS white_collar_count FROM job_enrichment WHERE collar_type = 'white';
--
-- 2) Mark only white collar rows (sets sector_method = '' so needs_repair is true)
UPDATE job_enrichment
SET sector_method = ''
WHERE collar_type = 'white';

-- 3) Then run the pipeline (from project root, with venv active):
--    python -m enrichment --batch-size 200 --mode incremental
