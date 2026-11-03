"""Public support contact page; composing and sending mail belongs to the user."""

from pathlib import Path

from fastapi import APIRouter
from starlette.responses import HTMLResponse

from prettylisavpn.public_web import PUBLIC_PAGE_HEADERS

router = APIRouter(tags=["support"])
PAGE = Path(__file__).with_name("public") / "support.html"


@router.get("/support", response_class=HTMLResponse, include_in_schema=False)
@router.get("/support/", response_class=HTMLResponse, include_in_schema=False)
async def support_page() -> HTMLResponse:
    return HTMLResponse(PAGE.read_text(encoding="utf-8"), headers=PUBLIC_PAGE_HEADERS)
