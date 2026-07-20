-- Hirematic/Appcast feed (GET /wrapping/hirematic).
-- Output columns match lw.hirematic_job_feed.
-- Enriched descriptions are merged in Python at INSERT time.

WITH filtered_jobs AS (
  SELECT
    j.id,
    j.description,
    j.position,
    j.locations,
    j.workmode,
    j.seniority,
    j.created_at,
    j.employers_id,
    e.name AS company,
    e.priority
  FROM job_postings.job_postings_1 j
  INNER JOIN employers.employers e
    ON e.id = j.employers_id
  WHERE (
      (
        e.product IN ('one', 'pro')
        AND e.priority IN (1, 2, 3)
      )
      OR e.id in (2434743, 829928) -- Renfe
    )
    AND j.position IS NOT NULL
    AND TRIM(j.position) <> ''
),

job_locations_exploded AS (
  SELECT
    fj.id AS job_id,
    jt.country_code,
    TRIM(SUBSTRING_INDEX(jt.label, ' - ', 1)) AS city,
    jt.city_id
  FROM filtered_jobs fj
  LEFT JOIN JSON_TABLE(
    CASE
      WHEN fj.locations IS NULL
        OR TRIM(fj.locations) = ''
        OR JSON_VALID(fj.locations) = 0
      THEN '{"cities":[]}'
      ELSE fj.locations
    END,
    '$.cities[*]'
    COLUMNS (
      country_code VARCHAR(10) PATH '$.country_code',
      label        VARCHAR(255) PATH '$.label',
      city_id      BIGINT PATH '$.id'
    )
  ) jt ON TRUE
),

job_primary_location AS (
  SELECT
    x.job_id,
    x.city,
    x.country_code
  FROM (
    SELECT
      jle.*,
      ROW_NUMBER() OVER (
        PARTITION BY jle.job_id
        ORDER BY
          CASE
            WHEN jle.city IS NULL OR TRIM(jle.city) = '' THEN 1
            ELSE 0
          END,
          jle.city_id
      ) AS rn
    FROM job_locations_exploded jle
    WHERE jle.country_code IN ('ITA', 'ESP')
  ) x
  WHERE x.rn = 1
),

job_locations_agg AS (
  SELECT
    job_id,
    country_code,
    GROUP_CONCAT(
      DISTINCT NULLIF(TRIM(city), '')
      ORDER BY city
      SEPARATOR ', '
    ) AS cities_list,
    COUNT(DISTINCT NULLIF(TRIM(city), '')) AS cities_count
  FROM job_locations_exploded
  WHERE country_code IN ('ITA', 'ESP')
  GROUP BY job_id, country_code
),

job_workmode AS (
  SELECT
    fj.id AS job_id,
    GROUP_CONCAT(
      DISTINCT LOWER(TRIM(jt.value))
      ORDER BY FIELD(
        LOWER(TRIM(jt.value)),
        'on-site', 'hybrid', 'remote'
      )
      SEPARATOR ', '
    ) AS workmode
  FROM filtered_jobs fj
  LEFT JOIN JSON_TABLE(
    CASE
      WHEN fj.workmode IS NULL
        OR TRIM(fj.workmode) = ''
        OR JSON_VALID(fj.workmode) = 0
      THEN '[]'
      ELSE fj.workmode
    END,
    '$[*]'
    COLUMNS (
      value VARCHAR(100) PATH '$'
    )
  ) jt ON TRUE
  GROUP BY fj.id
),

job_seniority AS (
  SELECT
    fj.id AS job_id,
    GROUP_CONCAT(
      DISTINCT LOWER(TRIM(jt.value))
      ORDER BY FIELD(
        LOWER(TRIM(jt.value)),
        'internship', 'entry-level', 'junior', 'mid', 'senior', 'expert'
      )
      SEPARATOR ', '
    ) AS seniority
  FROM filtered_jobs fj
  LEFT JOIN JSON_TABLE(
    CASE
      WHEN fj.seniority IS NULL
        OR TRIM(fj.seniority) = ''
        OR JSON_VALID(fj.seniority) = 0
      THEN '[]'
      ELSE fj.seniority
    END,
    '$[*]'
    COLUMNS (
      value VARCHAR(100) PATH '$'
    )
  ) jt ON TRUE
  GROUP BY fj.id
)

SELECT
  fj.id AS id,
  fj.position AS title,

  pl.city AS city,

  CASE
    WHEN pl.country_code = 'ITA' THEN 'IT'
    WHEN pl.country_code = 'ESP' THEN 'ES'
  END AS state,

  NULL AS zip,

  CASE
    WHEN pl.country_code = 'ITA' THEN 'IT'
    WHEN pl.country_code = 'ESP' THEN 'ES'
  END AS country,

  DATE(fj.created_at) AS post_date,
  fj.company AS company,
  fj.priority AS priority,

  CONCAT_WS(
    ', ',
    jw.workmode,
    js.seniority
  ) AS category,

  CONCAT(
    'https://www.joinrs.com/jobs/',
    fj.id,
    '?utm_source=hirematic',
    '&utm_medium=',
    fj.employers_id,
    '-',
    fj.priority,
    '&utm_campaign=',
    fj.id
  ) AS url,

  CONCAT(
    'La posizione è aperta all’interno del team di ',
    fj.company,
    '.',
    '\n\n',
    COALESCE(fj.description, ''),
    CASE
      WHEN la.cities_count > 1 THEN CONCAT(
        '\n\nQuesta opportunità è disponibile nelle seguenti città: ',
        la.cities_list,
        '.'
      )
      ELSE ''
    END
  ) AS description,

  NULL AS cpc

FROM filtered_jobs fj
INNER JOIN job_primary_location pl
  ON pl.job_id = fj.id
LEFT JOIN job_locations_agg la
  ON la.job_id = fj.id
  AND la.country_code = pl.country_code
LEFT JOIN job_workmode jw
  ON jw.job_id = fj.id
LEFT JOIN job_seniority js
  ON js.job_id = fj.id

ORDER BY fj.created_at DESC;