-- Backfill opzionale employers_id da apply_url quando utm_medium è <cifre>-<cifre>.
-- Richiede colonna employers_id (migrazione Alembic 0008).
-- Eseguire dopo sync_apply_url_from_pre_to_postings.sql se si vuole valorizzare anche
-- righe con URL già corretto senza aver fatto refresh della colonna dalla query.

UPDATE job_postings
SET employers_id = CAST(
    SUBSTRING_INDEX(
        SUBSTRING_INDEX(SUBSTRING_INDEX(apply_url, 'utm_medium=', -1), '&', 1),
        '-',
        1
    ) AS UNSIGNED
WHERE
    apply_url REGEXP 'utm_medium=[0-9]+-[0-9]+'
    AND (employers_id IS NULL OR employers_id = 0);

UPDATE job_posting_pre
SET employers_id = CAST(
    SUBSTRING_INDEX(
        SUBSTRING_INDEX(SUBSTRING_INDEX(apply_url, 'utm_medium=', -1), '&', 1),
        '-',
        1
    ) AS UNSIGNED
WHERE
    apply_url REGEXP 'utm_medium=[0-9]+-[0-9]+'
    AND (employers_id IS NULL OR employers_id = 0);
