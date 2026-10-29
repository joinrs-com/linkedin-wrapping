-- Full-catalog Adzuna explode (GET /wrapping/adzuna + /us|/eu3|/row).
-- One row per city label or country-only fallback; bucket = ita_esp|usa|eu3|row.
-- Description: body only (no employer intro). HTML normalized in pipeline.
-- CPC from priority: 1→0.08, 2→0.07, 3→0.03, 4→0.03, 5→0. country = ISO2.
-- All priorities/products (blacklist employer 1179402).

WITH feed_cities AS (
    SELECT
        jp.id AS job_posting_id,
        jt.ord AS city_ord,
        TRIM(SUBSTRING_INDEX(jt.city_label, ' - ', 1)) AS city_name,
        UPPER(TRIM(jt.country_code)) AS country_code
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
      AND NULLIF(TRIM(jt.country_code), '') IS NOT NULL
),

country_only AS (
    SELECT DISTINCT
        jp.id AS job_posting_id,
        UPPER(TRIM(jt.country_code)) AS country_code
    FROM job_postings.job_postings_1 jp
    INNER JOIN JSON_TABLE(
        CASE
            WHEN JSON_VALID(jp.locations) THEN jp.locations
            ELSE '{"countries":[]}'
        END,
        '$.countries[*]'
        COLUMNS (
            country_code VARCHAR(10) PATH '$.country_code'
        )
    ) jt ON TRUE
    WHERE NULLIF(TRIM(jt.country_code), '') IS NOT NULL
),

cities_by_country AS (
    SELECT
        fc.job_posting_id,
        fc.country_code,
        COUNT(*) AS city_count
    FROM feed_cities fc
    GROUP BY fc.job_posting_id, fc.country_code
),

location_rows AS (
    SELECT
        fc.job_posting_id,
        fc.city_ord,
        fc.city_name AS location,
        fc.country_code
    FROM feed_cities fc

    UNION ALL

    SELECT
        co.job_posting_id,
        CAST(100000 + (CRC32(co.country_code) % 89999) AS UNSIGNED) AS city_ord,
        co.country_code AS location,
        co.country_code
    FROM country_only co
    LEFT JOIN cities_by_country cbc
        ON cbc.job_posting_id = co.job_posting_id
       AND cbc.country_code = co.country_code
    WHERE COALESCE(cbc.city_count, 0) = 0
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
    n.position AS title,

    CONCAT('<p>', n.description, '</p>') AS description,

    CONCAT(
        'https://www.joinrs.com/jobs/',
        n.id,
        '?utm_source=adzuna'
    ) AS url,

    lr.location AS location,

    CASE lr.country_code
        WHEN 'ITA' THEN 'IT'
        WHEN 'ESP' THEN 'ES'
        WHEN 'USA' THEN 'US'
        WHEN 'FRA' THEN 'FR'
        WHEN 'GBR' THEN 'GB'
        WHEN 'DEU' THEN 'DE'
        WHEN 'NLD' THEN 'NL'
        WHEN 'BEL' THEN 'BE'
        WHEN 'CHE' THEN 'CH'
        WHEN 'AUT' THEN 'AT'
        WHEN 'PRT' THEN 'PT'
        WHEN 'POL' THEN 'PL'
        WHEN 'IRL' THEN 'IE'
        WHEN 'CAN' THEN 'CA'
        WHEN 'AUS' THEN 'AU'
        WHEN 'BRA' THEN 'BR'
        ELSE LEFT(lr.country_code, 2)
    END AS country,

    CASE
        WHEN n.all_workmodes LIKE '%Remote%' THEN 'Remote'
        ELSE 'Non-Remote'
    END AS remote,

    n.salary AS salary,
    n.employer_name AS company,

    CONCAT_WS(
        ', ',
        NULLIF(TRIM(COALESCE(n.all_workmodes, '')), ''),
        NULLIF(TRIM(COALESCE(n.normalized_seniority, '')), '')
    ) AS category,

    DATE(n.created_at) AS `date`,

    CASE n.priority
        WHEN 1 THEN 0.08
        WHEN 2 THEN 0.07
        WHEN 3 THEN 0.03
        WHEN 4 THEN 0.03
        WHEN 5 THEN 0
        ELSE 0
    END AS cpc,

    n.priority AS priority,

    lr.country_code AS country_code,

    CASE
        WHEN lr.country_code IN ('ITA', 'ESP') THEN 'ita_esp'
        WHEN lr.country_code = 'USA' THEN 'usa'
        WHEN lr.country_code IN ('FRA', 'GBR', 'DEU') THEN 'eu3'
        ELSE 'row'
    END AS bucket

FROM normalized n
INNER JOIN location_rows lr
    ON lr.job_posting_id = n.id

WHERE n.employers_id <> 1179402

ORDER BY
    n.priority ASC,
    n.created_at DESC,
    lr.city_ord ASC;
