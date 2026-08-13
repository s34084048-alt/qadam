from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from .. import audit
from ..analysis.modules_config import MODULES
from ..deps import AdminUser, SessionDep
from ..errors import ApiError, not_found
from ..models import Analysis, AuditLog, Case, Image, ModelRegistry, Patient
from ..schemas import ModelRegistryOut

router = APIRouter(prefix="/admin", tags=["admin"])

# Monk Skin Tone bands used for stratified reporting. Never pooled into one
# headline number -- a single aggregate hides exactly the disparity that
# matters.
MST_GROUPS = [
    ("1-2", 1, 2), ("3-4", 3, 4), ("5-6", 5, 6), ("7-8", 7, 8), ("9-10", 9, 10),
]


def _group_for(tone: int | None) -> str:
    if tone is None:
        return "not recorded"
    for label, lo, hi in MST_GROUPS:
        if lo <= tone <= hi:
            return label
    return "not recorded"


@router.get("/fairness")
async def fairness_dashboard(
    session: SessionDep,
    admin: AdminUser,
    module: str | None = Query(None),
) -> dict:
    """Stratified usage and outcome distribution by Monk Skin Tone group.

    PLACEHOLDER. These are counts of what the platform produced, not measured
    accuracy: there are no ground-truth labels in this system. Sensitivity,
    specificity and calibration must come from a prospective validation study
    with clinician-confirmed outcomes, and must be reported per group -- never
    as a single pooled figure.
    """
    if module and module not in MODULES:
        raise ApiError(400, "unknown_module", f"'{module}' is not a QADAM module.",
                       hint="Call GET /api/v1/modules.")

    stmt = (
        select(
            Patient.skin_tone_monk,
            Analysis.module,
            Analysis.triage_grade,
            Analysis.confidence,
            Image.quality_json,
        )
        .join(Case, Case.id == Analysis.case_id)
        .join(Patient, Patient.id == Case.patient_id)
        .join(Image, Image.id == Analysis.image_id)
        # An administrator administers THEIR organisation. There is no
        # cross-organisation view, deliberately.
        .where(Case.organisation_id == admin.organisation_id)
    )
    if module:
        stmt = stmt.where(Analysis.module == module)
    rows = (await session.execute(stmt)).all()

    buckets: dict[str, dict] = {}
    for tone, mod, grade, confidence, quality in rows:
        key = _group_for(tone)
        b = buckets.setdefault(
            key,
            {"group": key, "analyses": 0, "by_module": {}, "by_grade": {},
             "confidence_sum": 0.0, "quality_passed": 0},
        )
        b["analyses"] += 1
        b["by_module"][mod] = b["by_module"].get(mod, 0) + 1
        b["by_grade"][grade] = b["by_grade"].get(grade, 0) + 1
        b["confidence_sum"] += float(confidence or 0.0)
        if (quality or {}).get("passed"):
            b["quality_passed"] += 1

    strata = []
    for label, _lo, _hi in [*MST_GROUPS, ("not recorded", 0, 0)]:
        b = buckets.get(label)
        if not b:
            strata.append({
                "group": label, "analyses": 0, "by_module": {}, "by_grade": {},
                "mean_confidence": None, "quality_pass_rate": None,
            })
            continue
        n = b["analyses"]
        strata.append({
            "group": label,
            "analyses": n,
            "by_module": b["by_module"],
            "by_grade": b["by_grade"],
            "mean_confidence": round(b["confidence_sum"] / n, 3) if n else None,
            "quality_pass_rate": round(b["quality_passed"] / n, 3) if n else None,
        })

    recorded = sum(s["analyses"] for s in strata if s["group"] != "not recorded")
    total = sum(s["analyses"] for s in strata)

    return {
        "status": "placeholder",
        "strata": strata,
        "coverage": {
            "analyses_total": total,
            "skin_tone_recorded": recorded,
            "recorded_fraction": round(recorded / total, 3) if total else None,
        },
        "notes": [
            "These are counts of platform output, not measured accuracy. "
            "There is no ground truth in this system.",
            "Sensitivity, specificity, PPV and calibration require a "
            "prospective validation study with clinician-confirmed outcomes.",
            "Performance must always be reported per skin-tone group. A single "
            "pooled number is not an acceptable summary.",
            "Low recorded_fraction means this dashboard cannot yet support any "
            "fairness claim.",
            "Monk Skin Tone is patient-declared, optional, and is never used as "
            "a model input.",
        ],
    }


@router.get("/models", response_model=list[ModelRegistryOut])
async def list_models(
    session: SessionDep, admin: AdminUser, module: str | None = Query(None)
) -> list[ModelRegistryOut]:
    stmt = select(ModelRegistry).order_by(
        ModelRegistry.module, ModelRegistry.created_at.desc()
    )
    if module:
        stmt = stmt.where(ModelRegistry.module == module)
    rows = (await session.execute(stmt)).scalars().all()
    return [ModelRegistryOut.model_validate(r) for r in rows]


@router.post("/models/{model_id}/activate", response_model=ModelRegistryOut)
async def activate_model(
    model_id: uuid.UUID, session: SessionDep, admin: AdminUser
) -> ModelRegistryOut:
    model = await session.get(ModelRegistry, model_id)
    if model is None:
        raise not_found("model", str(model_id))

    others = (await session.execute(
        select(ModelRegistry).where(
            ModelRegistry.module == model.module, ModelRegistry.active.is_(True)
        )
    )).scalars().all()
    for other in others:
        other.active = False
    model.active = True

    await audit.record(
        session, actor_user_id=admin.id,
        organisation_id=admin.organisation_id, action="model.activate",
        entity="model_registry", entity_id=model.id,
        meta={"module": model.module, "backend": model.backend,
              "version": model.version,
              "deactivated": [str(o.id) for o in others]},
    )
    await session.commit()
    await session.refresh(model)
    return ModelRegistryOut.model_validate(model)


@router.get("/audit")
async def audit_log(
    session: SessionDep,
    admin: AdminUser,
    action: str | None = Query(None),
    entity: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    stmt = (select(AuditLog)
            .where(AuditLog.organisation_id == admin.organisation_id)
            .order_by(AuditLog.ts.desc()))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    total = (await session.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()
    rows = (await session.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "actor_user_id": str(r.actor_user_id) if r.actor_user_id else None,
                "action": r.action,
                "entity": r.entity,
                "entity_id": r.entity_id,
                "ts": r.ts.isoformat(),
                "meta": r.meta_json,
            }
            for r in rows
        ],
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "note": "Append-only. The application never updates or deletes these rows.",
    }
