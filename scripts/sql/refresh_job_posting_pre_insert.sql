-- Opzionale (.env): JOB_FEED_DB_JOB_POSTINGS e JOB_FEED_DB_EMPLOYERS (catalog sulla SORGENTE).
-- Due RDS diversi: imposta JOB_FEED_SOURCE_DATABASE_URL (production) e DATABASE_URL (lw su intelligence).
-- Una sola connessione: lascia JOB_FEED_SOURCE_DATABASE_URL vuota e usa solo DATABASE_URL.
INSERT INTO job_posting_pre (
    position,
    job_description,
    company,
    employers_name,
    priority,
    apply_url,
    company_id,
    location,
    workplace_types,
    experience_level,
    jobtype,
    partner_job_id,
    last_build_date
)
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
        MAX(CASE WHEN lr.country_code = 'ITA' THEN 1 ELSE 0 END) AS has_ita,
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

prepared AS (
    SELECT
        jp.id,
        jp.position,
        jp.description,
        jp.url,
        jp.created_at,
        jp.is_easy_apply,
        e.name AS employer_name,
        e.product,
        e.priority,
        ec.total_jobs,
        COALESCE(la.city_count, 0) AS city_count,
        COALESCE(la.has_ita, 0) AS has_ita,
        la.first_city_label,
        la.city_list,
        '' AS ai_summary,

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
    LEFT JOIN employer_counts ec
        ON ec.employers_id = jp.employers_id
    LEFT JOIN location_agg la
        ON la.job_posting_id = jp.id
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
            WHEN x.city_count > 1 THEN 'Remote'
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
            ELSE TRIM(
                BOTH '"' FROM
                REPLACE(
                    REPLACE(
                        REPLACE(COALESCE(x.raw_seniority, ''), '[', ''),
                    ']', ''),
                '''', '')
            )
        END AS normalized_seniority

    FROM extracted x
)

SELECT
    n.position,
    CONCAT(
        '<p><strong>Questa posizione è in ', n.employer_name, '</strong></p>',
        '<br><br>',
        '<p><strong>Riassunto dell''opportunità da parte della <i>Joinrs AI</i>:</strong> ', n.ai_summary, '</p>',
        '<br><br>',
        '<p><em>Il processo di selezione sarà interamente gestito da ', n.employer_name, '.</em></p>',
        '<br><br>',
        CASE
            WHEN n.city_count > 1 THEN CONCAT(
                '<p><em>Questa opportunità è disponibile su ',
                n.city_list,
                '.</em></p>',
                '<br><br>'
            )
            ELSE ''
        END,
        '<p>--</p>',
        '<p>', n.description, '</p>',
        '<p>--</p>',
        '<p><strong>',
        TRIM(CONCAT(
            CASE
                WHEN n.normalized_workplace_type = 'Remote' THEN '[#LI-REMOTE] '
                ELSE ''
            END,
            CASE
                WHEN n.city_count > 1 THEN '[#J-MCITY] '
                ELSE ''
            END,
            CASE
                WHEN n.product = 'pro' THEN '[#J-ENTERPRISE] '
                ELSE ''
            END,
            CASE
                WHEN n.product = 'one' THEN '[#J-ONE] '
                ELSE ''
            END,
            CASE
                WHEN COALESCE(n.total_jobs, 0) < 15 THEN '[#J-MIN] '
                ELSE ''
            END
        )),
        '</strong></p>',
        CASE
            WHEN n.is_easy_apply = 1 THEN '<p><strong>[#J-INTERNAL]</strong></p>'
            ELSE ''
        END
    ) AS job_description,
    'Joinrs' AS company,
    n.employer_name AS employers_name,
    n.priority AS priority,
    CONCAT(
        'https://www.joinrs.com/jobs/',
        n.id,
        '/?utm_source=linkedin&utm_medium=job-offer-ats&utm_campaign=',
        n.id,
        '-', n.product, '-', n.priority
    ) AS apply_url,
    '3807356' AS company_id,
    CASE
        WHEN n.city_count > 1 THEN 'Italy'
        WHEN n.first_city_label IS NOT NULL AND n.first_city_label <> '' THEN
            CASE
                WHEN n.first_city_label REGEXP ' - [A-Z]{2,3}$'
                    THEN REGEXP_REPLACE(n.first_city_label, ' - [A-Z]{2,3}$', '')
                ELSE n.first_city_label
            END
        ELSE ''
    END AS location,
    CASE
        WHEN n.city_count > 1 THEN 'Remote'
        ELSE n.normalized_workplace_type
    END AS workplace_types,
    n.normalized_seniority AS experience_level,
    'Full Time' AS jobtype,
    CAST(n.id AS CHAR) AS partner_job_id,
    n.created_at AS last_build_date

FROM normalized n
WHERE
    n.has_ita = 1
    AND n.product IN ('pro', 'one')
    AND n.priority IN (1, 2, 3)

ORDER BY
    n.priority ASC,
    n.created_at DESC;
