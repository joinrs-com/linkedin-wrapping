from fastapi import APIRouter

from api.wrapping import wrapping


router = APIRouter(
    prefix="/wrapping",
    tags=["Wrapping"]
)

router.get("/jooble")(wrapping.get_wrapping_jooble)
router.get("/jooble/us")(wrapping.get_wrapping_jooble_us)
router.get("/jooble/eu3")(wrapping.get_wrapping_jooble_eu3)
router.get("/jooble/row")(wrapping.get_wrapping_jooble_row)
router.get("/jooble/abroad")(wrapping.get_wrapping_jooble_abroad)  # deprecated
router.get("/hirematic")(wrapping.get_wrapping_hirematic)
router.get("/whatjobs")(wrapping.get_wrapping_whatjobs)
router.get("/talent")(wrapping.get_wrapping_talent)
router.get("/talent/us")(wrapping.get_wrapping_talent_us)
router.get("/talent/eu3")(wrapping.get_wrapping_talent_eu3)
router.get("/talent/row")(wrapping.get_wrapping_talent_row)
router.get("/adzuna")(wrapping.get_wrapping_adzuna)
router.get("/adzuna/us")(wrapping.get_wrapping_adzuna_us)
router.get("/adzuna/eu3")(wrapping.get_wrapping_adzuna_eu3)
router.get("/adzuna/row")(wrapping.get_wrapping_adzuna_row)
router.get("/jobrapido")(wrapping.get_wrapping_jobrapido)
