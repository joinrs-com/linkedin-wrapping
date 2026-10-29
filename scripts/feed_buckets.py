"""Campaign feed buckets for Jooble / Talent / Adzuna (country → bucket)."""

from __future__ import annotations

BUCKET_ITA_ESP = "ita_esp"
BUCKET_USA = "usa"
BUCKET_EU3 = "eu3"
BUCKET_ROW = "row"

BUCKETS: tuple[str, ...] = (BUCKET_ITA_ESP, BUCKET_USA, BUCKET_EU3, BUCKET_ROW)

# Artifact / route naming: platform_bucket (jooble root = jooble_ita_esp keyed as "jooble" for compat)
ARTIFACT_ROOT_ALIASES: dict[str, str] = {
    "jooble": f"jooble_{BUCKET_ITA_ESP}",
    "talent": f"talent_{BUCKET_ITA_ESP}",
    "adzuna": f"adzuna_{BUCKET_ITA_ESP}",
}

# ISO-3166-1 alpha-3 → alpha-2 (Adzuna <country> + campaigns)
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
}


def normalize_country_code(code: str | None) -> str:
    return (code or "").strip().upper()


def bucket_for_country(country_code: str | None) -> str:
    """Map a location country_code to one of the four fixed campaign buckets."""
    c = normalize_country_code(country_code)
    if c in ("ITA", "ESP"):
        return BUCKET_ITA_ESP
    if c == "USA":
        return BUCKET_USA
    if c in ("FRA", "GBR", "DEU"):
        return BUCKET_EU3
    return BUCKET_ROW


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


def artifact_name(platform: str, bucket: str) -> str:
    """Canonical artifact key, e.g. jooble_usa."""
    return f"{platform}_{bucket}"


def legacy_root_artifact_name(platform: str) -> str:
    """Compat keys still used by GET /wrapping/jooble|talent|adzuna."""
    return platform
