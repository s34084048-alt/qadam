from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from fastapi import APIRouter
from sqlalchemy import select

from pydantic import BaseModel, Field

from .. import audit
from ..analysis.modules_config import GRADE_STYLE
from ..deps import CurrentUser, SessionDep, load_case_scoped
from ..errors import ApiError, not_found
from ..labs.catalog import GROUPS, REFERENCE_RANGE_CAVEAT, UnitError, catalogue
from ..labs.interpret import LabInterpretation, interpret
from ..models import Case, LabPanel, LabResult, Patient
from ..safety import safety_block

router = APIRouter(prefix="/labs", tags=["labs"])
case_router = APIRouter(prefix="/cases", tags=["labs"])


class LabValue(BaseModel):
    code: str = Field(min_length=1, max_length=32,
                      description="Analyte code from GET /labs/catalogue.")
    value: float
    unit: str = Field(min_length=1, max_length=24,
                      description="Required. Never inferred — a value in the "
                                  "wrong unit is a different patient.")


class LabPanelIn(BaseModel):
    results: list[LabValue] = Field(min_length=1, max_length=60)
    panel_name: str | None = Field(default=None, max_length=128)
    age: int | None = Field(default=None, ge=0, le=120,
                            description="Needed for eGFR and FIB-4.")
    sex: Literal["female", "male", "other", "unknown"] | None = None
    patient_ref: str | None = Field(default=None, max_length=64)
    collected_at: str | None = None


@router.get("/catalogue")
async def lab_catalogue(user: CurrentUser) -> dict[str, Any]:
    """Analyte definitions, for building the entry form and validating units."""
    return {
        "analytes": catalogue(),
        "groups": GROUPS,
        "reference_range_caveat": REFERENCE_RANGE_CAVEAT,
        "safety": safety_block("lab"),
    }


@router.post("/interpret")
async def interpret_panel(
    body: LabPanelIn, session: SessionDep, user: CurrentUser
) -> dict[str, Any]:
    """Flag a panel against reference ranges and route on critical values.

    Takes TYPED VALUES, never an image. Optical character recognition of a
    report is not accepted here: a misread decimal point in a potassium is a
    different patient, so any extraction must be confirmed by a human into this
    form before it is interpreted.
    """
    try:
        result = interpret(
            [r.model_dump() for r in body.results],
            age=body.age,
            sex=body.sex,
        )
    except UnitError as exc:
        raise ApiError(
            422, "unit_not_accepted", str(exc),
            hint="Check GET /api/v1/labs/catalogue for the accepted units of "
                 "each analyte. The unit is never guessed.",
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(
            422, "invalid_lab_value",
            f"A result could not be read: {exc}",
            hint="Each result needs a catalogue code, a numeric value and a "
                 "unit.",
        )

    payload = result.to_json()
    payload["module"] = "lab"
    payload["triage"]["color"] = GRADE_STYLE[payload["triage"]["grade"]]["color"]
    payload["safety"] = safety_block("lab", payload["triage"]["grade"])
    payload["input_kind"] = "typed_numeric_values"
    payload["interpreted_from_image"] = False

    # The audit trail records THAT a panel was interpreted and how it was
    # graded. It never records the values -- those are clinical data and the
    # trail is not where they belong.
    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="lab.interpret", entity="lab",
        entity_id=body.patient_ref,
        meta={
            "analyte_count": len(result.results),
            "flagged": sum(1 for r in result.results if r.flag != "normal"),
            "critical": sum(1 for r in result.results if r.critical),
            "grade": payload["triage"]["grade"],
            "derived": [d["code"] for d in result.derived],
            "unrecognised": [u["code"] for u in result.unrecognised],
        },
    )
    await session.commit()
    return payload


# --- persisted, attached to a case ------------------------------------------

def _payload(result: LabInterpretation) -> dict[str, Any]:
    payload = result.to_json()
    payload["module"] = "lab"
    payload["triage"]["color"] = GRADE_STYLE[payload["triage"]["grade"]]["color"]
    payload["safety"] = safety_block("lab", payload["triage"]["grade"])
    payload["input_kind"] = "typed_numeric_values"
    payload["interpreted_from_image"] = False
    return payload


@case_router.post("/{case_id}/labs", status_code=201)
async def add_panel_to_case(
    case_id: uuid.UUID, body: LabPanelIn, session: SessionDep, user: CurrentUser
) -> dict[str, Any]:
    """Attach a panel to a case and store it.

    A panel can be attached to ANY case, not only a `lab` one. That is what
    closes the loop: an injury case routed to imaging and bloods should be able
    to hold the results that came back, instead of the referral trailing off
    into nothing.
    """
    case = await load_case_scoped(session, case_id, user)
    patient = await session.get(Patient, case.patient_id)
    if patient is None:
        raise not_found("patient", str(case.patient_id))

    # Fall back to what the patient record already knows, so the caller does
    # not have to restate it and cannot silently contradict it.
    age = body.age
    if age is None and patient.dob_year:
        age = dt.datetime.now(dt.timezone.utc).year - patient.dob_year
    sex = body.sex or patient.sex

    try:
        result = interpret([r.model_dump() for r in body.results],
                           age=age, sex=sex)
    except UnitError as exc:
        raise ApiError(
            422, "unit_not_accepted", str(exc),
            hint="Check GET /api/v1/labs/catalogue for the accepted units. "
                 "Nothing is stored until every unit is recognised.",
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(422, "invalid_lab_value",
                       f"A result could not be read: {exc}",
                       hint="Each result needs a catalogue code, a numeric "
                            "value and a unit.")

    collected = None
    if body.collected_at:
        try:
            collected = dt.datetime.fromisoformat(body.collected_at)
        except ValueError:
            raise ApiError(
                422, "invalid_collected_at",
                f"'{body.collected_at}' is not a valid ISO-8601 timestamp.",
                hint="Use a format like 2026-08-12T09:30:00Z.",
            )

    payload = _payload(result)
    panel = LabPanel(
        case_id=case.id,
        panel_name=body.panel_name,
        collected_at=collected,
        age_at_collection=age,
        sex_used=sex,
        triage_grade=payload["triage"]["grade"],
        triage_label=payload["triage"]["label"],
        next_investigation=payload["triage"]["next_investigation"],
        interpretation_json={
            "derived": payload["derived"],
            "clinical": payload["clinical"],
            "rationale": payload["triage"]["rationale"],
            "urgency": payload["triage"]["urgency"],
            "routing_target": payload["triage"]["routing_target"],
            "unrecognised": payload["unrecognised"],
        },
        created_by=user.id,
    )
    session.add(panel)
    await session.flush()
    session.add_all([
        LabResult(
            panel_id=panel.id, code=r.code, name=r.name, value=r.value,
            unit=r.unit, submitted_value=r.submitted_value,
            submitted_unit=r.submitted_unit, flag=r.flag, critical=r.critical,
            ref_low=r.reference.get("low"), ref_high=r.reference.get("high"),
        )
        for r in result.results
    ])

    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="lab.panel_create",
        entity="lab_panel", entity_id=panel.id,
        meta={
            "case_id": str(case.id),
            "case_module": case.module,
            "analyte_count": len(result.results),
            "flagged": sum(1 for r in result.results if r.flag != "normal"),
            "critical": sum(1 for r in result.results if r.critical),
            "grade": panel.triage_grade,
        },
    )
    await session.commit()
    await session.refresh(panel)

    payload["id"] = str(panel.id)
    payload["case_id"] = str(case.id)
    payload["created_at"] = panel.created_at.isoformat()
    return payload


@case_router.get("/{case_id}/labs")
async def list_case_panels(
    case_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> dict[str, Any]:
    case = await load_case_scoped(session, case_id, user)

    panels = (await session.execute(
        select(LabPanel).where(LabPanel.case_id == case_id)
        .order_by(LabPanel.created_at.desc())
    )).scalars().all()

    out = []
    for panel in panels:
        rows = (await session.execute(
            select(LabResult).where(LabResult.panel_id == panel.id)
            .order_by(LabResult.critical.desc(), LabResult.code)
        )).scalars().all()
        detail = panel.interpretation_json or {}
        out.append({
            "id": str(panel.id),
            "case_id": str(panel.case_id),
            "panel_name": panel.panel_name,
            "collected_at": (panel.collected_at.isoformat()
                             if panel.collected_at else None),
            "created_at": panel.created_at.isoformat(),
            "age_at_collection": panel.age_at_collection,
            "sex_used": panel.sex_used,
            "triage": {
                "grade": panel.triage_grade,
                "label": panel.triage_label,
                "next_investigation": panel.next_investigation,
                "urgency": detail.get("urgency", ""),
                "routing_target": detail.get("routing_target", ""),
                "rationale": detail.get("rationale", []),
                "color": GRADE_STYLE[panel.triage_grade]["color"],
            },
            "results": [
                {
                    "code": r.code, "name": r.name, "value": r.value,
                    "unit": r.unit, "flag": r.flag, "critical": r.critical,
                    "submitted": {"value": r.submitted_value,
                                  "unit": r.submitted_unit},
                    "converted": r.submitted_unit != r.unit,
                    "reference": {"low": r.ref_low, "high": r.ref_high},
                }
                for r in rows
            ],
            "derived": detail.get("derived", []),
            "clinical": detail.get("clinical"),
            "unrecognised": detail.get("unrecognised", []),
            "safety": safety_block("lab", panel.triage_grade),
        })

    return {
        "case_id": str(case_id),
        "panels": out,
        "total": len(out),
        "reference_range_caveat": REFERENCE_RANGE_CAVEAT,
    }
