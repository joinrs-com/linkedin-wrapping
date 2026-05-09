"""LinkedIn wrapping: apply URLs use utm_source=linkedin in DB; XML feed uses utm_medium=job-offer-ats."""

UTM_SOURCE = "linkedin"
# Stored apply_url uses employers_id-priority in utm_medium; LinkedIn XML rewrites to this value.
LINKEDIN_FEED_UTM_MEDIUM = "job-offer-ats"
