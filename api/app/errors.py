from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    """Structured, actionable error: HTTP status + code + message + hint."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        hint: str | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details or {}

    def payload(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "hint": self.hint,
                "details": self.details,
            }
        }


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.payload())


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"http_{exc.status_code}",
                "message": str(exc.detail),
                "hint": None,
                "details": {},
            }
        },
        headers=getattr(exc, "headers", None),
    )


def not_found(entity: str, ident: str) -> ApiError:
    return ApiError(
        404,
        f"{entity}_not_found",
        f"No {entity} with id {ident}.",
        hint=f"Check the {entity} id, or list {entity}s you have access to.",
    )
