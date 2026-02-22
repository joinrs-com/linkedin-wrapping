from fastapi import APIRouter

from api.wrapping import wrapping


router = APIRouter(
    prefix="/wrapping",
    tags=["Wrapping"]
)

router.get("/")(wrapping.get_wrapping)
router.get("/jooble")(wrapping.get_wrapping_jooble)

