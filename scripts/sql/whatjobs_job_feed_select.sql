-- Italy jobs for WhatJobs sponsorship feed (GET /wrapping/whatjobs).
-- Output columns match lw.whatjobs_job_feed for CSV export / INSERT.
--
-- Workflow:
--   1. scripts/sql/whatjobs_job_feed_truncate.sql
--   2. Run this SELECT, export results, load into lw.whatjobs_job_feed
--   3. GET /wrapping/whatjobs

WITH employer_counts AS (
    SELECT
        jp.employers_id,
        COUNT(*) AS total_jobs
    FROM job_postings.job_postings_1 jp
    GROUP BY jp.employers_id
),

location_rows AS (
    SELECT
        jp.id AS job_posting_id,
        jt.ord AS city_ord,
        jt.city_label,
        jt.country_code
    FROM job_postings.job_postings_1 jp
    LEFT JOIN JSON_TABLE(
        CASE
            WHEN JSON_VALID(jp.locations) THEN jp.locations
            ELSE '{"cities":[]}'
        END,
        '$.cities[*]'
        COLUMNS (
            ord FOR ORDINALITY,
            city_label VARCHAR(255) PATH '$.label',
            country_code VARCHAR(10) PATH '$.country_code'
        )
    ) jt ON TRUE
),

-- Filtriamo solo le città con country_code = 'ITA' e ricalcoliamo l'ordinalità
-- così region/description conterranno SOLO le città italiane dell'annuncio
italy_location_rows AS (
    SELECT
        lr.job_posting_id,
        ROW_NUMBER() OVER (PARTITION BY lr.job_posting_id ORDER BY lr.city_ord) AS city_ord,
        lr.city_label
    FROM location_rows lr
    WHERE lr.country_code = 'ITA'
),

location_agg AS (
    SELECT
        ilr.job_posting_id,
        COUNT(ilr.city_label) AS city_count,
        MAX(CASE 
            WHEN ilr.city_ord = 1 
            THEN TRIM(SUBSTRING_INDEX(ilr.city_label, ' - ', 1)) 
        END) AS first_city_label,
        -- Estraiamo solo il nome della città, ripulito da eventuale " - Paese" già presente
        -- e limitato alle sole città italiane
        GROUP_CONCAT(
            DISTINCT TRIM(SUBSTRING_INDEX(ilr.city_label, ' - ', 1))
            ORDER BY ilr.city_ord
            SEPARATOR ', '
        ) AS city_list
    FROM italy_location_rows ilr
    GROUP BY ilr.job_posting_id
),

country_rows AS (
    SELECT
        jp.id AS job_posting_id,
        jt.country_code
    FROM job_postings.job_postings_1 jp
    LEFT JOIN JSON_TABLE(
        CASE
            WHEN JSON_VALID(jp.locations) THEN jp.locations
            ELSE '{"cities":[]}'
        END,
        '$.cities[*]'
        COLUMNS (
            country_code VARCHAR(10) PATH '$.country_code'
        )
    ) jt ON TRUE

    UNION ALL

    SELECT
        jp.id AS job_posting_id,
        jt.country_code
    FROM job_postings.job_postings_1 jp
    LEFT JOIN JSON_TABLE(
        CASE
            WHEN JSON_VALID(jp.locations) THEN jp.locations
            ELSE '{"countries":[]}'
        END,
        '$.countries[*]'
        COLUMNS (
            country_code VARCHAR(10) PATH '$.country_code'
        )
    ) jt ON TRUE
),

country_agg AS (
    SELECT
        cr.job_posting_id,
        MAX(CASE WHEN cr.country_code = 'ITA' THEN 1 ELSE 0 END) AS has_ita,
        MAX(CASE WHEN cr.country_code = 'ESP' THEN 1 ELSE 0 END) AS has_esp,
        MAX(CASE WHEN cr.country_code = 'POR' THEN 1 ELSE 0 END) AS has_por,
        MAX(CASE WHEN cr.country_code = 'FRA' THEN 1 ELSE 0 END) AS has_fra,
        MAX(CASE WHEN cr.country_code = 'DEU' THEN 1 ELSE 0 END) AS has_deu,
        MAX(CASE WHEN cr.country_code = 'GBR' THEN 1 ELSE 0 END) AS has_gbr,
        MAX(CASE WHEN cr.country_code = 'BEL' THEN 1 ELSE 0 END) AS has_bel,
        COUNT(DISTINCT NULLIF(cr.country_code, '')) AS country_count
    FROM country_rows cr
    GROUP BY cr.job_posting_id
),

workmode_rows AS (
    SELECT
        jp.id AS job_posting_id,
        jt.wm_name
    FROM job_postings.job_postings_1 jp
    LEFT JOIN JSON_TABLE(
        CASE
            WHEN JSON_VALID(jp.workmode) THEN
                CASE
                    WHEN JSON_TYPE(jp.workmode) = 'ARRAY' THEN jp.workmode
                    ELSE JSON_ARRAY(jp.workmode)
                END
            ELSE JSON_ARRAY(TRIM(COALESCE(jp.workmode, '')))
        END,
        '$[*]'
        COLUMNS (
            wm_name VARCHAR(255) PATH '$'
        )
    ) jt ON TRUE
),

workmode_agg AS (
    SELECT
        wr.job_posting_id,
        GROUP_CONCAT(
            DISTINCT TRIM(
                CASE
                    WHEN JSON_VALID(wr.wm_name) THEN
                        CASE
                            WHEN LOWER(COALESCE(
                                JSON_UNQUOTE(JSON_EXTRACT(wr.wm_name, '$.name')),
                                JSON_UNQUOTE(JSON_EXTRACT(wr.wm_name, '$.label')),
                                JSON_UNQUOTE(JSON_EXTRACT(wr.wm_name, '$.value')),
                                wr.wm_name
                            )) IN ('on site', 'on-site', 'onsite') THEN 'On-site'
                            WHEN LOWER(COALESCE(
                                JSON_UNQUOTE(JSON_EXTRACT(wr.wm_name, '$.name')),
                                JSON_UNQUOTE(JSON_EXTRACT(wr.wm_name, '$.label')),
                                JSON_UNQUOTE(JSON_EXTRACT(wr.wm_name, '$.value')),
                                wr.wm_name
                            )) IN ('hybrid', 'hybrid working') THEN 'Hybrid'
                            WHEN LOWER(COALESCE(
                                JSON_UNQUOTE(JSON_EXTRACT(wr.wm_name, '$.name')),
                                JSON_UNQUOTE(JSON_EXTRACT(wr.wm_name, '$.label')),
                                JSON_UNQUOTE(JSON_EXTRACT(wr.wm_name, '$.value')),
                                wr.wm_name
                            )) IN ('full remote', 'remote', 'fully remote') THEN 'Remote'
                            ELSE COALESCE(
                                JSON_UNQUOTE(JSON_EXTRACT(wr.wm_name, '$.name')),
                                JSON_UNQUOTE(JSON_EXTRACT(wr.wm_name, '$.label')),
                                JSON_UNQUOTE(JSON_EXTRACT(wr.wm_name, '$.value')),
                                wr.wm_name
                            )
                        END
                    ELSE
                        CASE
                            WHEN LOWER(TRIM(wr.wm_name)) IN ('on site', 'on-site', 'onsite')       THEN 'On-site'
                            WHEN LOWER(TRIM(wr.wm_name)) IN ('hybrid', 'hybrid working')            THEN 'Hybrid'
                            WHEN LOWER(TRIM(wr.wm_name)) IN ('full remote', 'remote', 'fully remote') THEN 'Remote'
                            ELSE TRIM(wr.wm_name)
                        END
                END
            )
            SEPARATOR ', '
        ) AS all_workmodes
    FROM workmode_rows wr
    WHERE wr.wm_name IS NOT NULL AND TRIM(wr.wm_name) <> ''
    GROUP BY wr.job_posting_id
),

-- -------------------------------------------------------
-- CTE per estrarre e formattare il salario dal JSON
-- -------------------------------------------------------
salary_extracted AS (
    SELECT
        jp.id AS job_posting_id,

        -- Leggiamo i campi dal JSON salary
        CASE
            WHEN JSON_VALID(jp.salary)
             AND JSON_UNQUOTE(JSON_EXTRACT(jp.salary, '$.isAvailable')) = 'true'
            THEN JSON_EXTRACT(jp.salary, '$.min')
            ELSE NULL
        END AS salary_min,

        CASE
            WHEN JSON_VALID(jp.salary)
             AND JSON_UNQUOTE(JSON_EXTRACT(jp.salary, '$.isAvailable')) = 'true'
            THEN JSON_EXTRACT(jp.salary, '$.max')
            ELSE NULL
        END AS salary_max,

        CASE
            WHEN JSON_VALID(jp.salary)
             AND JSON_UNQUOTE(JSON_EXTRACT(jp.salary, '$.isAvailable')) = 'true'
            THEN UPPER(TRIM(JSON_UNQUOTE(JSON_EXTRACT(jp.salary, '$.currency'))))
            ELSE NULL
        END AS salary_currency

    FROM job_postings.job_postings_1 jp
),

-- Formattiamo il campo salary nel formato atteso dall'XML:
-- es. "25000 EUR" oppure "25000-29000 EUR"
salary_formatted AS (
    SELECT
        se.job_posting_id,
        CASE
            WHEN se.salary_min IS NULL THEN NULL
            WHEN se.salary_min = se.salary_max
                THEN CONCAT(FORMAT(se.salary_min, 0), ' ', se.salary_currency)
            ELSE
                CONCAT(
                    FORMAT(se.salary_min, 0),
                    '-',
                    FORMAT(se.salary_max, 0),
                    ' ',
                    se.salary_currency
                )
        END AS salary
    FROM salary_extracted se
),

prepared AS (
    SELECT
        jp.id,
        jp.position,
        jp.description,
        jp.url,
        jp.created_at,
        jp.updated_at,
        jp.is_easy_apply,
        jp.employers_id,
        e.name           AS employer_name,
        e.logo       AS employer_logo,   -- adatta se il campo si chiama diversamente
        e.product,
        e.priority,
        ec.total_jobs,

        COALESCE(la.city_count, 0)  AS city_count,
        COALESCE(ca.has_ita, 0)     AS has_ita,
        COALESCE(ca.has_esp, 0)     AS has_esp,
        COALESCE(ca.has_por, 0)     AS has_por,
        COALESCE(ca.has_fra, 0)     AS has_fra,
        COALESCE(ca.has_deu, 0)     AS has_deu,
        COALESCE(ca.has_gbr, 0)     AS has_gbr,
        COALESCE(ca.has_bel, 0)     AS has_bel,
        COALESCE(ca.country_count, 0) AS country_count,

        la.first_city_label,
        la.city_list,
        wa.all_workmodes,
        sf.salary,

        CASE
            WHEN JSON_VALID(jp.seniority) THEN jp.seniority
            ELSE JSON_QUOTE(TRIM(COALESCE(jp.seniority, '')))
        END AS safe_seniority_json

    FROM job_postings.job_postings_1 jp
    JOIN employers.employers e
        ON e.id = jp.employers_id

    LEFT JOIN employer_counts ec
        ON ec.employers_id = jp.employers_id

    LEFT JOIN location_agg la
        ON la.job_posting_id = jp.id

    LEFT JOIN country_agg ca
        ON ca.job_posting_id = jp.id

    LEFT JOIN workmode_agg wa
        ON wa.job_posting_id = jp.id

    LEFT JOIN salary_formatted sf
        ON sf.job_posting_id = jp.id
),

extracted AS (
    SELECT
        p.*,
        TRIM(
            COALESCE(
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_seniority_json, '$.name')),
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_seniority_json, '$.label')),
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_seniority_json, '$.value')),
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_seniority_json, '$[0].name')),
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_seniority_json, '$[0].label')),
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_seniority_json, '$[0].value')),
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_seniority_json, '$[0]')),
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_seniority_json, '$'))
            )
        ) AS raw_seniority
    FROM prepared p
),

normalized AS (
    SELECT
        x.*,
        CASE
            WHEN LOWER(x.raw_seniority) IN ('junior', 'entry-level', 'entry level') THEN 'Entry Level'
            WHEN LOWER(x.raw_seniority) = 'internship'                               THEN 'Internship'
            WHEN LOWER(x.raw_seniority) = 'mid'                                      THEN 'Mid Level'
            WHEN LOWER(x.raw_seniority) IN ('mid-senior', 'mid senior', 'mid senior level') THEN 'Mid-Senior level'
            WHEN LOWER(x.raw_seniority) = 'senior'                                   THEN 'Senior'
            ELSE TRIM(BOTH '"' FROM REPLACE(REPLACE(REPLACE(x.raw_seniority,'[',''),']',''),'''',''))
        END AS normalized_seniority
    FROM extracted x
)

-- ===========================================================
-- SELECT finale — colonne rinominate per i tag XML
-- ===========================================================
SELECT
    -- [OBBLIGATORIO] URL del job con UTM tracking
    CONCAT(
        'https://www.joinrs.com/jobs/',
        n.id
    ) AS link,

    -- [OBBLIGATORIO] Titolo della posizione
    n.position AS name,

    -- [OBBLIGATORIO] Regione/location nel formato "città1, città2 - Italy"
    -- Contiene SOLO le città italiane dell'annuncio
    CONCAT(
        COALESCE(
            NULLIF(n.city_list, ''),
            n.first_city_label
        ),
        ' - Italy'
    ) AS region,

    -- Modalità di lavoro (Remote / Hybrid / On-site)
    COALESCE(n.all_workmodes, '') AS remote,

    -- Salario estratto e formattato dal JSON
    -- NULL se isAvailable = false o campo assente
    n.salary AS salary,

    -- [OBBLIGATORIO] Descrizione arricchita con tag tracking
    CONCAT(
        '<p><strong>This position is at ', n.employer_name, '</strong></p>',
        '<br><br>',
        '<p><em>The selection process will be fully managed by ', n.employer_name, '.</em></p>',
        '<br><br>',
        CASE
            WHEN n.city_count > 1 THEN CONCAT(
                '<p><em>This opportunity is available in ',
                n.city_list,
                '.</em></p><br><br>'
            )
            ELSE ''
        END,
        '<p>--</p>',
        '<p>', n.description, '</p>',
        '<p>--</p>',
        '<p><strong>',
        TRIM(CONCAT(
            CASE WHEN n.all_workmodes LIKE '%Remote%'        THEN '[#LI-REMOTE] '   ELSE '' END,
            CASE WHEN n.city_count > 1                       THEN '[#J-MCITY] '     ELSE '' END,
            CASE WHEN n.product = 'pro'                      THEN '[#J-ENTERPRISE] ' ELSE '' END,
            CASE WHEN n.product = 'one'                      THEN '[#J-ONE] '       ELSE '' END,
            CASE WHEN COALESCE(n.total_jobs, 0) < 15         THEN '[#J-MIN] '       ELSE '' END
        )),
        '</strong></p>',
        CASE
            WHEN n.is_easy_apply = 1 THEN '<p><strong>[#J-INTERNAL]</strong></p>'
            ELSE ''
        END
    ) AS description,

    -- [OBBLIGATORIO] Nome azienda (employer, non "Joinrs")
    n.employer_name AS company,

    -- Logo azienda — URL dalla tabella employers
    COALESCE(n.employer_logo, '') AS company_logo,

    -- Data di pubblicazione nel formato DD.MM.YYYY
    DATE_FORMAT(n.created_at, '%d.%m.%Y') AS pubdate,

    -- Data di ultimo aggiornamento (usa updated_at se disponibile, altrimenti created_at)
    DATE_FORMAT(
        COALESCE(n.updated_at, n.created_at),
        '%d.%m.%Y'
    ) AS updated,

    -- Data di scadenza = pubblicazione + 60 giorni
    DATE_FORMAT(
        DATE_ADD(n.created_at, INTERVAL 60 DAY),
        '%d.%m.%Y'
    ) AS expire,

    -- Tipologia contratto (fisso a full-time per questo feed)
    'full-time' AS jobtype,

    -- ---- Campi extra utili per debug / monitoring (non vanno nell'XML) ----
    n.id              AS id,
    n.employers_id    AS employers_id,
    n.priority        AS priority,
    n.normalized_seniority AS experience_level

FROM normalized n

WHERE
    (
        n.product IN ('pro', 'one', 'pro_unlimited')
        OR n.product IS NULL
    )
    AND n.has_ita = 1
    AND n.employers_id <> 1179402
    AND n.priority IN (1, 2, 3, 4, 5)

ORDER BY
    n.priority ASC,
    n.created_at DESC;