from fastapi import APIRouter

from api.wrapping import wrapping


router = APIRouter(
    prefix="/wrapping",
    tags=["Wrapping"]
)

router.get("/")(wrapping.get_wrapping)
router.get("/jooble")(wrapping.get_wrapping_jooble)
router.get("/jooble/abroad")(wrapping.get_wrapping_jooble_abroad)
router.get("/hirematic")(wrapping.get_wrapping_hirematic)
router.get("/whatjobs")(wrapping.get_wrapping_whatjobs)
router.get("/talent")(wrapping.get_wrapping_talent)

