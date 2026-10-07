-- Enterprise jobs abroad for Jooble sponsorship feed.
-- Output columns match lw.jooble_abroad_job_feed (one row per city; id = job_id-ord).
-- Joinrs employers: body-only description (no intro). Others: English intro, no [#J-…] tags.
-- Synced incrementally by scripts/run_job_feed_pipeline.py (no OpenAI overlay).
-- Priority 1–4: any non-Italy-only location. Priority 5: Spain (ESP) only.

WITH country_rows AS (
    SELECT
        jp.id AS job_posting_id,
        jt.country_code
    FROM job_postings.job_postings_1 jp
    JOIN JSON_TABLE(
        CASE
            WHEN JSON_VALID(jp.locations) THEN jp.locations
            ELSE '{"cities":[]}'
        END,
        '$.cities[*]'
        COLUMNS (
            country_code VARCHAR(10) PATH '$.country_code'
        )
    ) jt

    UNION ALL

    SELECT
        jp.id AS job_posting_id,
        jt.country_code
    FROM job_postings.job_postings_1 jp
    JOIN JSON_TABLE(
        CASE
            WHEN JSON_VALID(jp.locations) THEN jp.locations
            ELSE '{"countries":[]}'
        END,
        '$.countries[*]'
        COLUMNS (
            country_code VARCHAR(10) PATH '$.country_code'
        )
    ) jt
),

country_agg AS (
    SELECT
        cr.job_posting_id,
        MAX(CASE WHEN cr.country_code = 'ITA' THEN 1 ELSE 0 END) AS has_ita,
        MAX(CASE WHEN cr.country_code = 'ESP' THEN 1 ELSE 0 END) AS has_esp,
        COUNT(DISTINCT cr.country_code) AS country_count,
        GROUP_CONCAT(
            DISTINCT cr.country_code
            ORDER BY cr.country_code
            SEPARATOR ', '
        ) AS countries
    FROM country_rows cr
    GROUP BY cr.job_posting_id
),

all_cities AS (
    SELECT
        jp.id AS job_posting_id,
        jt.ord AS city_ord,
        TRIM(SUBSTRING_INDEX(jt.city_label, ' - ', 1)) AS city_name,
        jt.country_code
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
    WHERE NULLIF(TRIM(jt.city_label), '') IS NOT NULL
),

city_list_agg AS (
    SELECT
        ac.job_posting_id,
        COUNT(*) AS city_count
    FROM all_cities ac
    GROUP BY ac.job_posting_id
),

location_rows AS (
    SELECT
        ac.job_posting_id,
        ac.city_ord,
        ac.city_name AS location,
        ac.country_code AS countries
    FROM all_cities ac

    UNION ALL

    -- Jobs with country codes but no city labels: one fallback row
    SELECT
        ca.job_posting_id,
        1 AS city_ord,
        'Multi-country' AS location,
        ca.countries AS countries
    FROM country_agg ca
    LEFT JOIN city_list_agg cla
        ON cla.job_posting_id = ca.job_posting_id
    WHERE COALESCE(cla.city_count, 0) = 0
      AND NULLIF(TRIM(ca.countries), '') IS NOT NULL
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
        COALESCE(ca.has_ita, 0) AS has_ita,
        COALESCE(ca.has_esp, 0) AS has_esp,
        COALESCE(ca.country_count, 0) AS country_count,
        ca.countries,
        sf.salary,
        CASE
            WHEN JSON_VALID(jp.workmode) THEN jp.workmode
            ELSE JSON_QUOTE(TRIM(COALESCE(jp.workmode, '')))
        END AS safe_workmode_json,
        CASE
            WHEN JSON_VALID(jp.seniority) THEN jp.seniority
            ELSE JSON_QUOTE(TRIM(COALESCE(jp.seniority, '')))
        END AS safe_seniority_json
    FROM job_postings.job_postings_1 jp
    JOIN employers.employers e
        ON e.id = jp.employers_id
    LEFT JOIN country_agg ca
        ON ca.job_posting_id = jp.id
    LEFT JOIN salary_formatted sf
        ON sf.job_posting_id = jp.id
),

extracted AS (
    SELECT
        p.*,
        TRIM(
            COALESCE(
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_workmode_json, '$.name')),
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_workmode_json, '$.label')),
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_workmode_json, '$.value')),
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_workmode_json, '$[0].name')),
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_workmode_json, '$[0].label')),
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_workmode_json, '$[0].value')),
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_workmode_json, '$[0]')),
                JSON_UNQUOTE(JSON_EXTRACT(p.safe_workmode_json, '$'))
            )
        ) AS raw_workmode,
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
            WHEN LOWER(x.raw_workmode) IN ('on site', 'on-site', 'onsite') THEN 'On-site'
            WHEN LOWER(x.raw_workmode) IN ('hybrid', 'hybrid working') THEN 'Hybrid'
            WHEN LOWER(x.raw_workmode) IN ('full remote', 'remote', 'fully remote') THEN 'Remote'
            ELSE COALESCE(NULLIF(x.raw_workmode, ''), '')
        END AS normalized_workplace_type,
        CASE
            WHEN LOWER(x.raw_seniority) IN ('junior', 'entry-level', 'entry level') THEN 'Entry Level'
            WHEN LOWER(x.raw_seniority) = 'internship' THEN 'Internship'
            WHEN LOWER(x.raw_seniority) = 'mid' THEN 'Mid Level'
            WHEN LOWER(x.raw_seniority) IN ('mid-senior', 'mid senior', 'mid senior level') THEN 'Mid-Senior level'
            WHEN LOWER(x.raw_seniority) = 'senior' THEN 'Senior'
            ELSE TRIM(BOTH '"' FROM REPLACE(REPLACE(REPLACE(x.raw_seniority,'[',''),']',''),'''',''))
        END AS normalized_seniority
    FROM extracted x
),

eligible_combinations AS (
    SELECT DISTINCT
        employers_id,
        product,
        priority
    FROM normalized
    WHERE has_ita = 1
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
            '<p><strong>This position is at ', n.employer_name, '</strong></p>',
            '<br><br>',
            '<p><em>The selection process will be entirely managed by ', n.employer_name, '.</em></p>',
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

    COALESCE(NULLIF(TRIM(lr.countries), ''), n.countries) AS countries,
    n.normalized_workplace_type AS workplace_types,
    n.normalized_seniority AS experience_level,

    'Full Time' AS jobtype,
    CONCAT(n.id, '-', lr.city_ord) AS partner_job_id,
    n.created_at AS last_build_date,
    n.salary AS salary

FROM normalized n
INNER JOIN location_rows lr
    ON lr.job_posting_id = n.id

JOIN eligible_combinations ec
    ON ec.employers_id = n.employers_id
   AND ec.product = n.product
   AND ec.priority = n.priority

WHERE
    n.product IN ('pro', 'one', 'pro_unlimited')
    AND (
        n.priority IN (1, 2, 3, 4)
        OR (n.priority = 5 AND n.has_esp = 1)
    )
    AND NOT (
        n.has_ita = 1
        AND n.country_count = 1
    )
    AND n.employers_id <> 1179402

ORDER BY
    n.priority ASC,
    n.created_at DESC,
    lr.city_ord ASC;
