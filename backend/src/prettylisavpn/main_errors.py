"""Stable HTTP error response helpers shared by routers."""

from starlette.responses import JSONResponse


def error_response(code: str, status_code: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code}}, status_code=status_code)
