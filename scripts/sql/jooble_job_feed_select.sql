-- Italy jobs for Jooble/Talent feed (GET /wrapping/jooble, /wrapping/talent).
-- Output columns match lw.jooble_job_feed (one row per Italian city; id = job_id-ord).
-- Joinrs employers: body-only description (no intro). No [#J-…] / [#LI-…] tags.

WITH country_rows AS (
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

ita_cities AS (
    SELECT
        jp.id AS job_posting_id,
        jt.ord AS city_ord,
        TRIM(SUBSTRING_INDEX(jt.city_label, ' - ', 1)) AS city_name
    FROM job_postings.job_postings_1 jp
    INNER JOIN JSON_TABLE(
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
    WHERE jt.country_code = 'ITA'
      AND NULLIF(TRIM(jt.city_label), '') IS NOT NULL
),

city_list_agg AS (
    SELECT
        ic.job_posting_id,
        COUNT(*) AS city_count
    FROM ita_cities ic
    GROUP BY ic.job_posting_id
),

location_rows AS (
    SELECT
        ic.job_posting_id,
        ic.city_ord,
        ic.city_name AS location
    FROM ita_cities ic

    UNION ALL

    SELECT
        ca.job_posting_id,
        1 AS city_ord,
        'Italy' AS location
    FROM country_agg ca
    LEFT JOIN city_list_agg cla
        ON cla.job_posting_id = ca.job_posting_id
    WHERE ca.has_ita = 1
      AND COALESCE(cla.city_count, 0) = 0
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
        jp.employers_id,
        e.name AS employer_name,
        e.product,
        e.priority,
        wa.all_workmodes,
        sf.salary,
        CASE
            WHEN JSON_VALID(jp.seniority) THEN jp.seniority
            ELSE JSON_QUOTE(TRIM(COALESCE(jp.seniority, '')))
        END AS safe_seniority_json
    FROM job_postings.job_postings_1 jp
    JOIN employers.employers e
        ON e.id = jp.employers_id
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
    CONCAT(n.id, '-', lr.city_ord) AS id,
    n.id AS job_posting_id,
    n.position AS position,
    n.employer_name AS employers_name,
    n.employers_id AS employers_id,
    n.priority AS priority,

    CASE
        WHEN n.employers_id IN (
            327107, 829928, 829944, 829946, 829948, 829951, 848251, 2006564, 4004682
        ) THEN CONCAT('<p>', n.description, '</p>')
        ELSE CONCAT(
            '<p><strong>Questa posizione è in ', n.employer_name, '</strong></p>',
            '<br><br>',
            '<p><em>Il processo di selezione sarà interamente gestito ', n.employer_name, '.</em></p>',
            '<br><br>',
            '<p>--</p>',
            '<p>', n.description, '</p>',
            '<p>--</p>'
        )
    END AS description,

    'Joinrs' AS company,

    CONCAT(
        'https://www.joinrs.com/jobs/',
        n.id
    ) AS apply_url,

    '829928' AS company_id,

    lr.location AS location,

    'ITA' AS countries,

    COALESCE(n.all_workmodes, '') AS workplace_types,
    n.normalized_seniority AS experience_level,

    'Full Time' AS jobtype,
    CONCAT(n.id, '-', lr.city_ord) AS partner_job_id,
    n.created_at AS last_build_date,
    n.salary AS salary

FROM normalized n
INNER JOIN location_rows lr
    ON lr.job_posting_id = n.id

WHERE
    (
        n.product IN ('pro', 'one', 'pro_unlimited')
        OR n.product IS NULL
    )
    AND n.priority IN (1, 2, 3, 4, 5)
    AND n.employers_id <> 1179402

ORDER BY
    n.priority ASC,
    n.created_at DESC,
    lr.city_ord ASC;
