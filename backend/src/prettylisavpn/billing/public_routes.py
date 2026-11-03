"""Provider-independent payment return pages; browser navigation is not payment evidence."""

from pathlib import Path

from fastapi import APIRouter
from starlette.responses import FileResponse, HTMLResponse

from prettylisavpn.public_web import PUBLIC_PAGE_HEADERS as HEADERS

router = APIRouter(tags=["payment-return"])
ASSETS = Path(__file__).with_name("public")


@router.api_route(
    "/payment/success",
    methods=["GET", "HEAD", "POST"],
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def payment_success() -> HTMLResponse:
    return HTMLResponse((ASSETS / "success.html").read_text(encoding="utf-8"), headers=HEADERS)


@router.api_route(
    "/payment/failure",
    methods=["GET", "HEAD", "POST"],
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def payment_failure() -> HTMLResponse:
    return HTMLResponse((ASSETS / "failure.html").read_text(encoding="utf-8"), headers=HEADERS)


@router.get("/payment/assets/style.css", include_in_schema=False)
async def payment_styles() -> FileResponse:
    return FileResponse(ASSETS / "style.css", media_type="text/css", headers=HEADERS)


@router.get("/payment/assets/logo.svg", include_in_schema=False)
async def payment_logo() -> FileResponse:
    return FileResponse(ASSETS / "logo.svg", media_type="image/svg+xml", headers=HEADERS)
