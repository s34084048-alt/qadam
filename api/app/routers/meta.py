from __future__ import annotations

from fastapi import APIRouter

from ..analysis.modules_config import GRADE_STYLE, catalogue
from ..config import settings
from ..reference import emergency_reference
from ..safety import safety_block
from ..schemas import HealthOut
from ..version import __version__

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    return HealthOut(
        status="ok",
        clinical_use=False,
        version=__version__,
        environment=settings.environment,
        demo_mode=settings.demo_mode,
        disclaimer=safety_block()["disclaimer"],
        device_notice=safety_block()["device_notice"],
    )


@router.get("/safety")
async def safety() -> dict:
    """The boundary, machine-readable. Clients render this verbatim."""
    return {
        **safety_block(),
        "data_residency": settings.data_residency,
        "consent_required": settings.require_consent,
    }


@router.get("/reference/emergency")
async def emergency_reference_endpoint() -> dict:
    """Fixed responder reference. Takes no input and reads no case.

    Deliberately outside the analysis pipeline: it must be impossible for an
    image, a grade or a model to influence what this returns.
    """
    return emergency_reference()


@router.get("/modules")
async def modules() -> dict:
    return {
        "modules": catalogue(),
        "grades": GRADE_STYLE,
        "safety": safety_block(),
    }
