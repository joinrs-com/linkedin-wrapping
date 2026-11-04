"""Campaign feed keys for Jooble / Talent / Adzuna (country + priority + USA shard).

15 feeds per platform (≤~30k explode rows), full descriptions in MySQL artifacts:
  it, it5, es, usa_1..usa_5, uk, fr, de, eu, americas, asia, row
"""

from __future__ import annotations

import zlib

# --- feed keys ---
FEED_IT = "it"
FEED_IT5 = "it5"
FEED_ES = "es"
FEED_UK = "uk"
FEED_FR = "fr"
FEED_DE = "de"
FEED_EU = "eu"
FEED_AMERICAS = "americas"
FEED_ASIA = "asia"
FEED_ROW = "row"
USA_SHARD_COUNT = 5
FEED_USA = tuple(f"usa_{i}" for i in range(1, USA_SHARD_COUNT + 1))

FEEDS: tuple[str, ...] = (
    FEED_IT,
    FEED_IT5,
    FEED_ES,
    *FEED_USA,
    FEED_UK,
    FEED_FR,
    FEED_DE,
    FEED_EU,
    FEED_AMERICAS,
    FEED_ASIA,
    FEED_ROW,
)

# Back-compat aliases used by older imports / scripts
BUCKETS = FEEDS
BUCKET_ITA_ESP = FEED_IT
BUCKET_USA = "usa_1"
BUCKET_EU3 = FEED_EU
BUCKET_ROW = FEED_ROW

# Root /wrapping/{platform} → Italy P1–4
ARTIFACT_ROOT_ALIASES: dict[str, str] = {
    "jooble": f"jooble_{FEED_IT}",
    "talent": f"talent_{FEED_IT}",
    "adzuna": f"adzuna_{FEED_IT}",
}

# ISO-3166-1 alpha-3 → alpha-2 (Adzuna <country>)
_ISO3_TO_ISO2: dict[str, str] = {
    "ITA": "IT",
    "ESP": "ES",
    "USA": "US",
    "FRA": "FR",
    "GBR": "GB",
    "DEU": "DE",
    "NLD": "NL",
    "BEL": "BE",
    "CHE": "CH",
    "AUT": "AT",
    "PRT": "PT",
    "POL": "PL",
    "IRL": "IE",
    "CAN": "CA",
    "AUS": "AU",
    "BRA": "BR",
    "MEX": "MX",
    "ARG": "AR",
    "ROU": "RO",
    "CZE": "CZ",
    "SWE": "SE",
    "DNK": "DK",
    "NOR": "NO",
    "FIN": "FI",
    "GRC": "GR",
    "HUN": "HU",
    "BGR": "BG",
    "HRV": "HR",
    "SVK": "SK",
    "SVN": "SI",
    "LUX": "LU",
    "EST": "EE",
    "LVA": "LV",
    "LTU": "LT",
    "IND": "IN",
    "CHN": "CN",
    "JPN": "JP",
    "KOR": "KR",
    "SGP": "SG",
    "ARE": "AE",
    "ZAF": "ZA",
    "TUR": "TR",
    "RUS": "RU",
    "UKR": "UA",
    "COL": "CO",
    "PER": "PE",
    "CHL": "CL",
    "PHL": "PH",
    "MYS": "MY",
    "TWN": "TW",
    "IDN": "ID",
    "THA": "TH",
    "VNM": "VN",
    "HKG": "HK",
    "PAK": "PK",
    "BGD": "BD",
}

# /eu — Europe incl. PRT+BEL; excl. ITA, ESP, DEU, FRA, GBR (own feeds)
_EU_COUNTRIES: frozenset[str] = frozenset(
    {
        "PRT",
        "BEL",
        "NLD",
        "CHE",
        "AUT",
        "POL",
        "IRL",
        "ROU",
        "SWE",
        "HUN",
        "CZE",
        "DNK",
        "BGR",
        "LUX",
        "NOR",
        "GRC",
        "SVK",
        "FIN",
        "UKR",
        "SRB",
        "HRV",
        "LTU",
        "EST",
        "CYP",
        "LVA",
        "SVN",
        "ALB",
        "MDA",
        "LIE",
        "BIH",
        "MCO",
        "ISL",
        "MLT",
        "MKD",
        "MNE",
        "SMR",
        "AND",
        "XK",
        "VAT",
        "RUS",
        "JEY",
        "GGY",
        "GIB",
        "IMN",
        "ALA",
        "SUI",
        "FRO",
        "GRL",
    }
)

# /americas — CAN + BRA + LATAM (no USA)
_AMERICAS_COUNTRIES: frozenset[str] = frozenset(
    {
        "CAN",
        "BRA",
        "MEX",
        "ARG",
        "COL",
        "PER",
        "CHL",
        "VEN",
        "ECU",
        "BOL",
        "PRY",
        "URY",
        "GUY",
        "SUR",
        "GUF",
        "CRI",
        "PAN",
        "GTM",
        "HND",
        "SLV",
        "NIC",
        "BLZ",
        "CUB",
        "DOM",
        "HTI",
        "JAM",
        "TTO",
        "BRB",
        "BHS",
        "PRI",
        "ABW",
        "CUW",
        "CYM",
        "MTQ",
        "GLP",
        "LCA",
        "VCT",
        "GRD",
        "ATG",
        "DMA",
        "KNA",
        "SXM",
        "BES",
        "AIA",
        "VGB",
        "TCA",
        "MSR",
    }
)

# /asia — principal Asia (excl. Middle East / Oceania → row)
_ASIA_COUNTRIES: frozenset[str] = frozenset(
    {
        "IND",
        "CHN",
        "SGP",
        "PHL",
        "JPN",
        "MYS",
        "TWN",
        "KOR",
        "HKG",
        "THA",
        "VNM",
        "IDN",
        "PAK",
        "BGD",
        "LKA",
        "NPL",
        "MMR",
        "KHM",
        "LAO",
        "MNG",
        "MAC",
        "BRN",
        "BTN",
        "MDV",
        "TLS",
    }
)


def normalize_country_code(code: str | None) -> str:
    return (code or "").strip().upper()


def usa_shard_for_job(job_posting_id: int | str | None) -> str:
    """Stable USA shard usa_1..usa_5 (matches MySQL CRC32(CAST(id AS CHAR)) MOD 5 + 1)."""
    raw = str(int(job_posting_id) if job_posting_id is not None else 0)
    n = (zlib.crc32(raw.encode("utf-8")) & 0xFFFFFFFF) % USA_SHARD_COUNT
    return f"usa_{n + 1}"


def feed_for_row(
    country_code: str | None,
    *,
    priority: int | None = None,
    job_posting_id: int | str | None = None,
) -> str:
    """Map explode row → feed key stored in ``bucket`` column."""
    c = normalize_country_code(country_code)
    if c == "ITA":
        p = int(priority) if priority is not None else 5
        return FEED_IT if p in (1, 2, 3, 4) else FEED_IT5
    if c == "ESP":
        return FEED_ES
    if c == "USA":
        return usa_shard_for_job(job_posting_id)
    if c == "GBR":
        return FEED_UK
    if c == "FRA":
        return FEED_FR
    if c == "DEU":
        return FEED_DE
    if c in _AMERICAS_COUNTRIES:
        return FEED_AMERICAS
    if c in _ASIA_COUNTRIES:
        return FEED_ASIA
    if c in _EU_COUNTRIES:
        return FEED_EU
    return FEED_ROW


def bucket_for_country(country_code: str | None) -> str:
    """Legacy helper: country-only map (ITA→it, USA→usa_1 without real shard)."""
    return feed_for_row(country_code, priority=1, job_posting_id=0)


def country_code_to_iso2(country_code: str | None) -> str:
    """Adzuna-style ISO2; fall back to first two letters of alpha-3."""
    c = normalize_country_code(country_code)
    if not c:
        return "XX"
    if len(c) == 2:
        return c
    if c in _ISO3_TO_ISO2:
        return _ISO3_TO_ISO2[c]
    return c[:2]


def artifact_name(platform: str, feed: str) -> str:
    """Canonical artifact key, e.g. jooble_usa_1."""
    return f"{platform}_{feed}"


def sql_bucket_case(*, country_expr: str, priority_expr: str, job_id_expr: str) -> str:
    """MySQL CASE expression assigning feed keys (keep in sync with feed_for_row)."""
    eu_list = ", ".join(f"'{c}'" for c in sorted(_EU_COUNTRIES))
    am_list = ", ".join(f"'{c}'" for c in sorted(_AMERICAS_COUNTRIES))
    as_list = ", ".join(f"'{c}'" for c in sorted(_ASIA_COUNTRIES))
    return f"""
    CASE
        WHEN {country_expr} = 'ITA' AND COALESCE({priority_expr}, 5) IN (1, 2, 3, 4) THEN 'it'
        WHEN {country_expr} = 'ITA' THEN 'it5'
        WHEN {country_expr} = 'ESP' THEN 'es'
        WHEN {country_expr} = 'USA' THEN CONCAT(
            'usa_',
            (CRC32(CAST({job_id_expr} AS CHAR)) MOD {USA_SHARD_COUNT}) + 1
        )
        WHEN {country_expr} = 'GBR' THEN 'uk'
        WHEN {country_expr} = 'FRA' THEN 'fr'
        WHEN {country_expr} = 'DEU' THEN 'de'
        WHEN {country_expr} IN ({am_list}) THEN 'americas'
        WHEN {country_expr} IN ({as_list}) THEN 'asia'
        WHEN {country_expr} IN ({eu_list}) THEN 'eu'
        ELSE 'row'
    END
    """.strip()
