"""Jooble wrapping: apply URLs use jo_ais_id from job_jooble_mapping when present."""
UTM_SOURCE = "jooble"

# URL template when jo_ais_id is in mapping: https://www.joinrs.ai/it/jobs/{jo_ais_id}/?...
APPLY_URL_TEMPLATE = "https://www.joinrs.ai/it/jobs/{jo_ais_id}/?utm_source=jooble&utm_medium=job-offer-ats&utm_campaign={jo_ais_id}-scraped"


def build_apply_url_for_jooble(jo_ais_id: str) -> str:
    return APPLY_URL_TEMPLATE.format(jo_ais_id=jo_ais_id)

