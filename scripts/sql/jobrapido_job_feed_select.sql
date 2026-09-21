-- Italy jobs for Job Rapido feed (GET /wrapping/jobrapido).
-- Output columns match lw.jobrapido_job_feed (one row per job, first Italian city — like Adzuna).
-- Enriched descriptions are merged in Python at INSERT time.
-- CPC from priority: 1→0.08, 2→0.07, 3→0.03, 4→0.03, 5→0.

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

location_agg AS (
    SELECT
        lr.job_posting_id,
        COUNT(lr.city_label) AS city_count,
        MAX(CASE WHEN lr.city_ord = 1 THEN lr.city_label END) AS first_city_label,
        GROUP_CONCAT(
            DISTINCT TRIM(
                CASE
                    WHEN lr.city_label REGEXP ' - [A-Z]{2,3}$'
                        THEN REGEXP_REPLACE(lr.city_label, ' - [A-Z]{2,3}$', '')
                    ELSE lr.city_label
                END
            )
            ORDER BY lr.city_ord
            SEPARATOR ', '
        ) AS city_list
    FROM location_rows lr
    GROUP BY lr.job_posting_id
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
        MAX(CASE WHEN cr.country_code = 'ITA' THEN 1 ELSE 0 END) AS has_ita
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
                            WHEN LOWER(TRIM(wr.wm_name)) IN ('on site', 'on-site', 'onsite') THEN 'On-site'
                            WHEN LOWER(TRIM(wr.wm_name)) IN ('hybrid', 'hybrid working') THEN 'Hybrid'
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

salary_extracted AS (
    SELECT
        jp.id AS job_posting_id,
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
        jp.created_at,
        jp.is_easy_apply,
        jp.employers_id,
        e.name AS employer_name,
        e.product,
        e.priority,
        ec.total_jobs,
        COALESCE(la.city_count, 0) AS city_count,
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
    LEFT JOIN workmode_agg wa
        ON wa.job_posting_id = jp.id
    LEFT JOIN salary_formatted sf
        ON sf.job_posting_id = jp.id
    INNER JOIN country_agg ca
        ON ca.job_posting_id = jp.id
        AND ca.has_ita = 1
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
            WHEN LOWER(x.raw_seniority) = 'internship' THEN 'Internship'
            WHEN LOWER(x.raw_seniority) = 'mid' THEN 'Mid Level'
            WHEN LOWER(x.raw_seniority) IN ('mid-senior', 'mid senior', 'mid senior level') THEN 'Mid-Senior level'
            WHEN LOWER(x.raw_seniority) = 'senior' THEN 'Senior'
            ELSE TRIM(BOTH '"' FROM REPLACE(REPLACE(REPLACE(x.raw_seniority,'[',''),']',''),'''',''))
        END AS normalized_seniority
    FROM extracted x
)

SELECT
    CAST(n.id AS CHAR) AS reference_id,
    n.id AS job_posting_id,
    n.position AS title,

    CONCAT(
        '<p><strong>Questa posizione è in ', n.employer_name, '</strong></p>',
        '<br><br>',
        '<p><em>Il processo di selezione sarà interamente gestito ', n.employer_name, '.</em></p>',
        '<br><br>',
        CASE
            WHEN n.city_count > 1 THEN CONCAT(
                '<p><em>Questa opportunità è disponibile in ',
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
            CASE WHEN n.all_workmodes LIKE '%Remote%' THEN '[#LI-REMOTE] ' ELSE '' END,
            CASE WHEN n.city_count > 1 THEN '[#J-MCITY] ' ELSE '' END,
            CASE WHEN n.product = 'pro' THEN '[#J-ENTERPRISE] ' ELSE '' END,
            CASE WHEN n.product = 'one' THEN '[#J-ONE] ' ELSE '' END,
            CASE WHEN COALESCE(n.total_jobs, 0) < 15 THEN '[#J-MIN] ' ELSE '' END
        )),
        '</strong></p>',
        CASE
            WHEN n.is_easy_apply = 1 THEN '<p><strong>[#J-INTERNAL]</strong></p>'
            ELSE ''
        END
    ) AS description,

    CONCAT(
        'https://www.joinrs.com/jobs/',
        n.id,
        '?utm_source=jobrapido'
    ) AS url,

    CASE
        WHEN NULLIF(TRIM(n.first_city_label), '') IS NULL THEN 'Italy'
        ELSE TRIM(SUBSTRING_INDEX(n.first_city_label, ' - ', 1))
    END AS location,

    CASE
        WHEN NULLIF(TRIM(n.first_city_label), '') IS NULL THEN 'Italia'
        WHEN n.first_city_label REGEXP ' - [A-Z]{2,3}$'
            THEN TRIM(SUBSTRING_INDEX(n.first_city_label, ' - ', -1))
        ELSE 'Italia'
    END AS state,

    'IT' AS country,
    NULL AS postalcode,
    n.employer_name AS company,
    'www.joinrs.com' AS website,
    DATE(n.created_at) AS publishdate,
    DATE(DATE_ADD(DATE(n.created_at), INTERVAL 60 DAY)) AS expirydate,
    n.salary AS salary,
    NULL AS education,
    'fulltime' AS jobtype,
    NULLIF(TRIM(COALESCE(n.all_workmodes, '')), '') AS category,
    NULLIF(TRIM(COALESCE(n.normalized_seniority, '')), '') AS experience,

    CASE n.priority
        WHEN 1 THEN 0.08
        WHEN 2 THEN 0.07
        WHEN 3 THEN 0.03
        WHEN 4 THEN 0.03
        WHEN 5 THEN 0
        ELSE 0
    END AS cpc,

    n.priority AS priority

FROM normalized n

WHERE
    (
        n.product IN ('pro', 'one', 'pro_unlimited')
        OR n.product IS NULL
    )
    AND n.priority IN (1, 2, 3, 4, 5)
    AND n.employers_id <> 1179402

ORDER BY
    n.priority ASC,
    n.created_at DESC;
