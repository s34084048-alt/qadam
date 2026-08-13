from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from .. import audit
from ..deps import CurrentUser, SessionDep, load_case_scoped
from ..errors import not_found
from ..foot_risk import CATEGORIES, SOURCE, stratify
from ..models import Case, FootRiskAssessment, Patient
from ..safety import safety_block

router = APIRouter(prefix="/cases", tags=["diabetic foot"])
info_router = APIRouter(prefix="/foot", tags=["diabetic foot"])

Finding = Literal["present", "absent", "not_tested"]


class FootRiskIn(BaseModel):
    foot: Literal["left", "right", "both"] = "both"
    lops: Finding = Field(
        ...,
        description="Loss of protective sensation, by 10 g monofilament. "
                    "'not_tested' is honest and will block stratification; "
                    "recording 'absent' for a test you did not do is not.",
    )
    pad: Finding = Field(
        ...,
        description="Peripheral artery disease, by pulses and ankle/toe "
                    "pressures.",
    )
    deformity: Finding = "not_tested"
    previous_ulcer: Finding = "not_tested"
    previous_amputation: Finding = "not_tested"
    end_stage_renal_disease: Finding = "not_tested"


@info_router.get("/risk-model")
async def risk_model(user: CurrentUser) -> dict[str, Any]:
    """The stratification rule, published rather than hidden in the code."""
    return {
        "source": SOURCE,
        "categories": CATEGORIES,
        "required_tests": {
            "lops": "10 g monofilament at the standard sites. A 128 Hz tuning "
                    "fork or the Ipswich touch test are alternatives where no "
                    "monofilament is available.",
            "pad": "Dorsalis pedis and posterior tibial pulses; ankle-brachial "
                   "or toe pressures where pulses are absent. In diabetes the "
                   "ankle index can be falsely high from medial arterial "
                   "calcification — toe pressures are more reliable.",
        },
        "refuses_to_stratify_when": "Either required test was not performed. "
                                    "An absent test is not a negative test.",
        "derived_from_image": False,
        "safety": safety_block("foot"),
    }


@router.post("/{case_id}/foot-risk", status_code=201)
async def create_foot_risk(
    case_id: uuid.UUID, body: FootRiskIn, session: SessionDep, user: CurrentUser
) -> dict[str, Any]:
    """Record a structured foot examination and stratify it."""
    case = await load_case_scoped(session, case_id, user)
    patient = await session.get(Patient, case.patient_id)
    if patient is None:
        raise not_found("patient", str(case.patient_id))

    result = stratify(
        lops=body.lops, pad=body.pad, deformity=body.deformity,
        previous_ulcer=body.previous_ulcer,
        previous_amputation=body.previous_amputation,
        end_stage_renal_disease=body.end_stage_renal_disease,
    )
    payload = result.to_json()

    row = FootRiskAssessment(
        case_id=case.id, foot=body.foot, lops=body.lops, pad=body.pad,
        deformity=body.deformity, previous_ulcer=body.previous_ulcer,
        previous_amputation=body.previous_amputation,
        end_stage_renal_disease=body.end_stage_renal_disease,
        category=result.category, complete=result.complete,
        screening_interval=result.screening_interval,
        grade=str(result.grade), detail_json=payload, created_by=user.id,
    )
    session.add(row)
    await session.flush()

    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="foot_risk.create",
        entity="foot_risk_assessment", entity_id=row.id,
        meta={
            "case_id": str(case.id), "foot": body.foot,
            "category": result.category, "complete": result.complete,
            "missing_tests": len(result.missing_tests),
            "grade": str(result.grade),
        },
    )
    await session.commit()
    await session.refresh(row)

    payload["id"] = str(row.id)
    payload["case_id"] = str(case.id)
    payload["foot"] = row.foot
    payload["created_at"] = row.created_at.isoformat()
    payload["findings"] = {
        "lops": row.lops, "pad": row.pad, "deformity": row.deformity,
        "previous_ulcer": row.previous_ulcer,
        "previous_amputation": row.previous_amputation,
        "end_stage_renal_disease": row.end_stage_renal_disease,
    }
    payload["safety"] = safety_block("foot", str(result.grade))
    return payload


@router.get("/{case_id}/foot-risk")
async def list_foot_risk(
    case_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> dict[str, Any]:
    case = await load_case_scoped(session, case_id, user)
    rows = (await session.execute(
        select(FootRiskAssessment)
        .where(FootRiskAssessment.case_id == case_id)
        .order_by(FootRiskAssessment.created_at.desc())
    )).scalars().all()
    return {
        "case_id": str(case_id),
        "assessments": [
            {
                **(r.detail_json or {}),
                "id": str(r.id),
                "foot": r.foot,
                "created_at": r.created_at.isoformat(),
                "findings": {
                    "lops": r.lops, "pad": r.pad, "deformity": r.deformity,
                    "previous_ulcer": r.previous_ulcer,
                    "previous_amputation": r.previous_amputation,
                    "end_stage_renal_disease": r.end_stage_renal_disease,
                },
            }
            for r in rows
        ],
        "total": len(rows),
        "source": SOURCE,
    }
