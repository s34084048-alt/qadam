from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .config import settings
from .db import create_schema
from .errors import ApiError, api_error_handler, http_error_handler
from .logging_conf import configure_logging
from .routers import (admin, auth, cases, follow_up, foot, investigations,
                      labs, meta, patients)
from .safety import DEVICE_NOTICE, DISCLAIMER, INTENDED_USE
from .version import __version__

DESCRIPTION = f"""
**{DEVICE_NOTICE}**

{DISCLAIMER}

QADAM performs **surface screening and triage routing only**. It grades what is
visible in a photograph and recommends which real investigation or specialty to
route the patient to. It does not diagnose, and it cannot confirm or exclude any
internal or sub-surface condition — including fracture, dislocation, tendon
rupture, muscle tear or internal bleeding.

A qualified clinician must confirm every clinically significant output.

{INTENDED_USE}
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    if settings.auto_create_schema:
        await create_schema()
    yield


app = FastAPI(
    title="QADAM — visual triage platform",
    description=DESCRIPTION,
    version=__version__,
    lifespan=lifespan,
    openapi_tags=[
        {"name": "meta", "description": "Catalogue, health and the safety boundary."},
        {"name": "auth", "description": "OAuth2 password flow, JWT bearer tokens."},
        {"name": "patients", "description": "Pseudonymous records, consent, erasure."},
        {"name": "cases", "description": "Capture, analyse, review, export."},
        {"name": "labs", "description": "Numeric laboratory results — typed, never OCR'd."},
        {"name": "investigations", "description": "Results filed against a case. Stored, never interpreted."},
        {"name": "diabetic foot", "description": "IWGDF risk stratification from clinical findings."},
        {"name": "admin", "description": "Model registry, fairness, audit."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(HTTPException, http_error_handler)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Validation failures in the same structured shape as every other error.

    The submitted values are deliberately NOT echoed back: a rejected request
    body can contain a patient reference or an image payload.
    """
    problems = []
    missing = []
    for err in exc.errors():
        parts = [str(p) for p in err.get("loc", ())
                 if p not in ("body", "query", "path", "header")]
        field = ".".join(parts) or "(request body)"
        problems.append({"field": field, "problem": err.get("msg", "invalid value")})
        if err.get("type") == "missing":
            missing.append(field)

    if missing:
        hint = "Provide a value for: " + ", ".join(missing) + "."
    else:
        hint = "Correct the listed fields and send the request again."

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "The request could not be accepted: "
                           + "; ".join(f"{p['field']} — {p['problem']}"
                                       for p in problems),
                "hint": hint,
                "details": {"fields": problems},
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    # Never echo the exception body: it may contain fragments of a payload.
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "The request could not be completed.",
                "hint": "Retry. If it persists, quote the time of the request "
                        "to your administrator.",
                "details": {},
            }
        },
    )


@app.middleware("http")
async def safety_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-QADAM-Clinical-Use"] = "false"
    # HTTP header values are latin-1; keep this line ASCII-only.
    response.headers["X-QADAM-Disclaimer"] = (
        "Research/decision-support tool - not a diagnosis. "
        "Not a substitute for clinical assessment."
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


prefix = settings.api_v1_prefix
app.include_router(meta.router, prefix=prefix)
app.include_router(auth.router, prefix=prefix)
app.include_router(patients.router, prefix=prefix)
app.include_router(cases.router, prefix=prefix)
app.include_router(labs.router, prefix=prefix)
app.include_router(labs.case_router, prefix=prefix)
app.include_router(investigations.router, prefix=prefix)
app.include_router(foot.router, prefix=prefix)
app.include_router(foot.info_router, prefix=prefix)
app.include_router(follow_up.router, prefix=prefix)
app.include_router(follow_up.info_router, prefix=prefix)
app.include_router(admin.router, prefix=prefix)


def resolve_web_asset(web_root: Path, full_path: str) -> Path:
    """Which file answers a request under a single-origin web mount.

    A real file inside the bundle, or index.html. The fallback is what a
    client-side router needs: `/cases/<uuid>` is a route in the browser, not a
    file on disk, and refreshing that URL must not 404. StaticFiles alone will
    not do it — its `html=True` only covers directory paths.

    The containment check is the security-relevant half. `..` segments survive
    URL decoding, so without resolving the candidate and confirming it is still
    inside the bundle, a crafted path walks out and reads arbitrary files from
    the container — application source and anything else the process can open.
    """
    index = web_root / "index.html"
    if not full_path:
        return index
    try:
        candidate = (web_root / full_path).resolve()
    except (OSError, ValueError):        # malformed or over-long path
        return index
    if candidate.is_file() and candidate.is_relative_to(web_root):
        return candidate
    return index


async def root() -> dict:
    return {
        "name": "QADAM",
        "version": __version__,
        "clinical_use": False,
        "device_notice": DEVICE_NOTICE,
        "disclaimer": DISCLAIMER,
        "docs": "/docs",
        "api": prefix,
    }


# Registered LAST so nothing here can shadow the API or /docs.
#
# When SERVE_WEB_DIR is set the web app owns "/", and the JSON landing payload
# above is not registered at all -- two different things cannot both answer the
# same path, and on a single-origin host the browser asking for "/" wants the
# app, not a description of the API.
_web_dir = Path(settings.serve_web_dir) if settings.serve_web_dir else None

if _web_dir is not None and not _web_dir.is_dir():
    logging.getLogger(__name__).warning(
        "SERVE_WEB_DIR=%s does not exist; serving the API only.", _web_dir
    )
    _web_dir = None

if _web_dir is None:
    app.get("/", include_in_schema=False)(root)
else:
    _web_root = _web_dir.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        return FileResponse(resolve_web_asset(_web_root, full_path))
