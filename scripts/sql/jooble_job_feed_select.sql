-- Non-Italy EU jobs for Jooble main feed (GET /wrapping/jooble).
-- Output columns match lw.jooble_job_feed for CSV export / INSERT.
--
-- Workflow:
--   1. scripts/sql/jooble_job_feed_truncate.sql
--   2. Run this SELECT, export results, load into lw.jooble_job_feed
--   3. GET /wrapping/jooble

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
        MAX(CASE WHEN cr.country_code = 'ITA' THEN 1 ELSE 0 END) AS has_ita,
        MAX(CASE WHEN cr.country_code = 'ESP' THEN 1 ELSE 0 END) AS has_esp,
        MAX(CASE WHEN cr.country_code = 'POR' THEN 1 ELSE 0 END) AS has_por,
        MAX(CASE WHEN cr.country_code = 'FRA' THEN 1 ELSE 0 END) AS has_fra,
        MAX(CASE WHEN cr.country_code = 'DEU' THEN 1 ELSE 0 END) AS has_deu,
        MAX(CASE WHEN cr.country_code = 'GBR' THEN 1 ELSE 0 END) AS has_gbr,
        MAX(CASE WHEN cr.country_code = 'BEL' THEN 1 ELSE 0 END) AS has_bel,
        COUNT(DISTINCT NULLIF(cr.country_code, '')) AS country_count,
        GROUP_CONCAT(
            DISTINCT CASE
                WHEN cr.country_code <> 'ITA'
                THEN cr.country_code
            END
            ORDER BY cr.country_code
            SEPARATOR ', '
        ) AS countries
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

prepared AS (
    SELECT
        jp.id,
        jp.position,
        jp.description,
        jp.url,
        jp.created_at,
        jp.is_easy_apply,
        jp.employers_id,
        e.name AS employer_name,
        e.product,
        e.priority,
        ec.total_jobs,

        COALESCE(la.city_count, 0) AS city_count,
        COALESCE(ca.has_ita, 0) AS has_ita,
        COALESCE(ca.has_esp, 0) AS has_esp,
        COALESCE(ca.has_por, 0) AS has_por,
        COALESCE(ca.has_fra, 0) AS has_fra,
        COALESCE(ca.has_deu, 0) AS has_deu,
        COALESCE(ca.has_gbr, 0) AS has_gbr,
        COALESCE(ca.has_bel, 0) AS has_bel,
        COALESCE(ca.country_count, 0) AS country_count,

        la.first_city_label,
        la.city_list,
        ca.countries,
        wa.all_workmodes,

        '' AS ai_summary,

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
    n.id AS id,
    n.position AS position,
    n.employer_name AS employers_name,
    n.employers_id AS employers_id,
    n.priority AS priority,

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

    'Joinrs' AS company,

    CONCAT(
        'https://www.joinrs.com/jobs/',
        n.id
    ) AS apply_url,

    '829928' AS company_id,

    COALESCE(
        NULLIF(n.city_list, ''),
        n.first_city_label
    ) AS location,

    CASE
        WHEN n.has_gbr = 1 THEN 'GBR'
        WHEN n.has_deu = 1 THEN 'DEU'
        WHEN n.has_fra = 1 THEN 'FRA'
        WHEN n.has_esp = 1 THEN 'ESP'
        WHEN n.has_por = 1 THEN 'POR'
        WHEN n.has_bel = 1 THEN 'BEL'
        ELSE SUBSTRING_INDEX(COALESCE(n.countries, ''), ', ', 1)
    END AS countries,

    COALESCE(n.all_workmodes, '') AS workplace_types,
    n.normalized_seniority AS experience_level,

    'Full Time' AS jobtype,
    n.id AS partner_job_id,
    n.created_at AS last_build_date

FROM normalized n

WHERE
    (
        n.product IN ('pro', 'one', 'pro_unlimited')
        OR n.product IS NULL
    )
    AND n.priority IN (1, 2, 3, 4, 5)
    AND n.has_ita = 0
    AND n.employers_id <> 1179402
    AND (
           n.has_esp = 1
        OR n.has_por = 1
        OR n.has_fra = 1
        OR n.has_deu = 1
        OR n.has_gbr = 1
        OR n.has_bel = 1
    )

ORDER BY
    n.priority ASC,
    n.created_at DESC;
