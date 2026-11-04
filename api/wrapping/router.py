from fastapi import APIRouter

from api.wrapping import wrapping


router = APIRouter(
    prefix="/wrapping",
    tags=["Wrapping"]
)

# Jooble — 15 feeds (/it = Italy P1–4, /it5 = Italy P5)
router.get("/jooble/it")(wrapping.get_wrapping_jooble_it)
router.get("/jooble/it5")(wrapping.get_wrapping_jooble_it5)
router.get("/jooble/es")(wrapping.get_wrapping_jooble_es)
router.get("/jooble/us/{shard}")(wrapping.get_wrapping_jooble_us_shard)
router.get("/jooble/uk")(wrapping.get_wrapping_jooble_uk)
router.get("/jooble/fr")(wrapping.get_wrapping_jooble_fr)
router.get("/jooble/de")(wrapping.get_wrapping_jooble_de)
router.get("/jooble/eu")(wrapping.get_wrapping_jooble_eu)
router.get("/jooble/americas")(wrapping.get_wrapping_jooble_americas)
router.get("/jooble/asia")(wrapping.get_wrapping_jooble_asia)
router.get("/jooble/row")(wrapping.get_wrapping_jooble_row)
router.get("/jooble/abroad", deprecated=True, responses={410: {"description": "Feed retired; use geographic feeds"}})(wrapping.get_wrapping_jooble_abroad)

router.get("/hirematic")(wrapping.get_wrapping_hirematic)
router.get("/whatjobs")(wrapping.get_wrapping_whatjobs)

# Talent — same geography as Jooble
router.get("/talent/it")(wrapping.get_wrapping_talent_it)
router.get("/talent/it5")(wrapping.get_wrapping_talent_it5)
router.get("/talent/es")(wrapping.get_wrapping_talent_es)
router.get("/talent/us/{shard}")(wrapping.get_wrapping_talent_us_shard)
router.get("/talent/uk")(wrapping.get_wrapping_talent_uk)
router.get("/talent/fr")(wrapping.get_wrapping_talent_fr)
router.get("/talent/de")(wrapping.get_wrapping_talent_de)
router.get("/talent/eu")(wrapping.get_wrapping_talent_eu)
router.get("/talent/americas")(wrapping.get_wrapping_talent_americas)
router.get("/talent/asia")(wrapping.get_wrapping_talent_asia)
router.get("/talent/row")(wrapping.get_wrapping_talent_row)

# Adzuna — same geography (+ CPC)
router.get("/adzuna/it")(wrapping.get_wrapping_adzuna_it)
router.get("/adzuna/it5")(wrapping.get_wrapping_adzuna_it5)
router.get("/adzuna/es")(wrapping.get_wrapping_adzuna_es)
router.get("/adzuna/us/{shard}")(wrapping.get_wrapping_adzuna_us_shard)
router.get("/adzuna/uk")(wrapping.get_wrapping_adzuna_uk)
router.get("/adzuna/fr")(wrapping.get_wrapping_adzuna_fr)
router.get("/adzuna/de")(wrapping.get_wrapping_adzuna_de)
router.get("/adzuna/eu")(wrapping.get_wrapping_adzuna_eu)
router.get("/adzuna/americas")(wrapping.get_wrapping_adzuna_americas)
router.get("/adzuna/asia")(wrapping.get_wrapping_adzuna_asia)
router.get("/adzuna/row")(wrapping.get_wrapping_adzuna_row)

router.get("/jobrapido")(wrapping.get_wrapping_jobrapido)
