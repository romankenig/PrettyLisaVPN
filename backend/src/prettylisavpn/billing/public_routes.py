"""Public payment return pages and a fail-closed 1Plat callback address.

Browser navigation is never payment evidence. Until the live provider adapter is
configured, do not acknowledge callbacks or consume/store their sensitive bodies.
"""

from pathlib import Path

from fastapi import APIRouter
from starlette.responses import FileResponse, HTMLResponse, Response

from prettylisavpn.main_errors import error_response

router = APIRouter(tags=["payment-return"])
ASSETS = Path(__file__).with_name("public")
HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'self'; img-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
}


@router.get("/payment/success", response_class=HTMLResponse, include_in_schema=False)
async def payment_success() -> HTMLResponse:
    return HTMLResponse((ASSETS / "success.html").read_text(encoding="utf-8"), headers=HEADERS)


@router.get("/payment/failure", response_class=HTMLResponse, include_in_schema=False)
async def payment_failure() -> HTMLResponse:
    return HTMLResponse((ASSETS / "failure.html").read_text(encoding="utf-8"), headers=HEADERS)


@router.get("/payment/assets/style.css", include_in_schema=False)
async def payment_styles() -> FileResponse:
    return FileResponse(ASSETS / "style.css", media_type="text/css", headers=HEADERS)


@router.get("/payment/assets/logo.svg", include_in_schema=False)
async def payment_logo() -> FileResponse:
    return FileResponse(ASSETS / "logo.svg", media_type="image/svg+xml", headers=HEADERS)


@router.post("/api/payments/1plat/callback", status_code=503)
async def oneplat_callback() -> Response:
    response = error_response("BILLING_NOT_CONFIGURED", 503)
    response.headers.update({"Cache-Control": "no-store", "Retry-After": "60"})
    return response
