from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import delete, func, select

from .. import audit
from ..analysis.modules_config import MODULES
from ..deps import CurrentUser, SessionDep, load_patient_scoped
from ..errors import ApiError, not_found
from ..models import (Analysis, Case, FootRiskAssessment, Image,
                      InvestigationResult, LabPanel, LabResult, Lesion,
                      Patient)
from ..schemas import PatientCreate, PatientOut, PatientUpdate
from ..storage import get_storage

router = APIRouter(prefix="/patients", tags=["patients"])


async def _by_ref(session, external_ref: str, user) -> Patient | None:
    return await load_patient_scoped(session, external_ref, user)


@router.post("", response_model=PatientOut, status_code=201)
async def create_patient(
    body: PatientCreate, session: SessionDep, user: CurrentUser
) -> PatientOut:
    if await _by_ref(session, body.external_ref, user):
        raise ApiError(
            409, "patient_exists",
            f"A patient record with reference '{body.external_ref}' already exists.",
            hint="Use the existing record, or choose a different site-local code.",
        )
    patient = Patient(
        organisation_id=user.organisation_id,
        external_ref=body.external_ref,
        dob_year=body.dob_year,
        sex=body.sex,
        skin_tone_monk=body.skin_tone_monk,
        consent_flag=body.consent_flag,
        created_by=user.id,
    )
    session.add(patient)
    await session.flush()
    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="patient.create", entity="patient",
        entity_id=patient.id,
        meta={"consent_flag": body.consent_flag,
              "skin_tone_recorded": body.skin_tone_monk is not None},
    )
    await session.commit()
    return PatientOut.model_validate(patient)


@router.get("", response_model=list[PatientOut])
async def list_patients(
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[PatientOut]:
    result = await session.execute(
        select(Patient)
        .where(Patient.organisation_id == user.organisation_id)
        .order_by(Patient.created_at.desc()).limit(limit).offset(offset)
    )
    return [PatientOut.model_validate(p) for p in result.scalars().all()]


@router.get("/{external_ref}", response_model=PatientOut)
async def get_patient(
    external_ref: str, session: SessionDep, user: CurrentUser
) -> PatientOut:
    patient = await _by_ref(session, external_ref, user)
    if not patient:
        raise not_found("patient", external_ref)
    return PatientOut.model_validate(patient)


@router.patch("/{external_ref}", response_model=PatientOut)
async def update_patient(
    external_ref: str, body: PatientUpdate, session: SessionDep, user: CurrentUser
) -> PatientOut:
    patient = await _by_ref(session, external_ref, user)
    if not patient:
        raise not_found("patient", external_ref)
    changed = []
    for field in ("dob_year", "sex", "skin_tone_monk", "consent_flag"):
        value = getattr(body, field)
        if value is not None:
            setattr(patient, field, value)
            changed.append(field)
    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="patient.update", entity="patient",
        entity_id=patient.id, meta={"fields": changed},
    )
    await session.commit()
    return PatientOut.model_validate(patient)


@router.get("/{external_ref}/export")
async def export_patient(
    external_ref: str, session: SessionDep, user: CurrentUser
) -> dict:
    """Portability: everything held about this pseudonymous record."""
    patient = await _by_ref(session, external_ref, user)
    if not patient:
        raise not_found("patient", external_ref)

    cases = (await session.execute(
        select(Case).where(Case.patient_id == patient.id).order_by(Case.created_at)
    )).scalars().all()

    payload_cases = []
    for case in cases:
        analyses = (await session.execute(
            select(Analysis).where(Analysis.case_id == case.id)
            .order_by(Analysis.created_at)
        )).scalars().all()
        images = (await session.execute(
            select(Image).where(Image.case_id == case.id)
        )).scalars().all()
        panels = (await session.execute(
            select(LabPanel).where(LabPanel.case_id == case.id)
            .order_by(LabPanel.created_at)
        )).scalars().all()
        lab_payload = []
        for panel in panels:
            rows = (await session.execute(
                select(LabResult).where(LabResult.panel_id == panel.id)
            )).scalars().all()
            lab_payload.append({
                "id": str(panel.id),
                "panel_name": panel.panel_name,
                "collected_at": (panel.collected_at.isoformat()
                                 if panel.collected_at else None),
                "created_at": panel.created_at.isoformat(),
                "triage_grade": panel.triage_grade,
                "triage_label": panel.triage_label,
                "next_investigation": panel.next_investigation,
                "interpretation": panel.interpretation_json,
                "results": [
                    {"code": r.code, "name": r.name, "value": r.value,
                     "unit": r.unit, "flag": r.flag, "critical": r.critical,
                     "submitted_value": r.submitted_value,
                     "submitted_unit": r.submitted_unit,
                     "reference": {"low": r.ref_low, "high": r.ref_high}}
                    for r in rows
                ],
            })
        investigations = (await session.execute(
            select(InvestigationResult)
            .where(InvestigationResult.case_id == case.id)
            .order_by(InvestigationResult.created_at)
        )).scalars().all()
        foot_risks = (await session.execute(
            select(FootRiskAssessment)
            .where(FootRiskAssessment.case_id == case.id)
            .order_by(FootRiskAssessment.created_at)
        )).scalars().all()
        payload_cases.append({
            "id": str(case.id),
            "module": case.module,
            "module_label": MODULES[case.module]["label_en"],
            "status": case.status,
            "body_site": case.body_site,
            "created_at": case.created_at.isoformat(),
            "images": [
                {"id": str(i.id), "storage_key": i.storage_key,
                 "width": i.width, "height": i.height,
                 "captured_at": i.captured_at.isoformat(),
                 "quality": i.quality_json}
                for i in images
            ],
            "analyses": [
                {"id": str(a.id), "module": a.module,
                 "model_version": a.model_version, "backend": a.backend,
                 "triage_grade": a.triage_grade, "triage_label": a.triage_label,
                 "confidence": a.confidence,
                 "next_investigation": a.next_investigation,
                 "detail": a.rationale_json,
                 "created_at": a.created_at.isoformat()}
                for a in analyses
            ],
            "lab_panels": lab_payload,
            "foot_risk_assessments": [
                {"id": str(f.id), "foot": f.foot, "category": f.category,
                 "complete": f.complete,
                 "screening_interval": f.screening_interval,
                 "grade": f.grade, "detail": f.detail_json,
                 "created_at": f.created_at.isoformat()}
                for f in foot_risks
            ],
            "investigation_results": [
                {"id": str(i.id), "category": i.category, "modality": i.modality,
                 "body_site": i.body_site,
                 "performed_at": i.performed_at.isoformat() if i.performed_at else None,
                 "reporting_service": i.reporting_service,
                 "report_text": i.report_text, "storage_key": i.storage_key,
                 "content_type": i.content_type, "size_bytes": i.size_bytes,
                 "created_at": i.created_at.isoformat(),
                 "automated_interpretation": False}
                for i in investigations
            ],
        })

    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="patient.export", entity="patient",
        entity_id=patient.id, meta={"case_count": len(cases)},
    )
    await session.commit()
    return {
        "patient": PatientOut.model_validate(patient).model_dump(mode="json"),
        "cases": payload_cases,
        "note": "Images are held in object storage under the listed keys and "
                "are downloadable by an authorised clinician.",
    }


@router.delete("/{external_ref}", status_code=200)
async def erase_patient(
    external_ref: str, session: SessionDep, user: CurrentUser
) -> dict:
    """Right to erasure. Removes images from object storage and all clinical
    rows. The audit trail is retained -- it holds no identifiers."""
    patient = await _by_ref(session, external_ref, user)
    if not patient:
        raise not_found("patient", external_ref)

    storage = get_storage()
    case_ids = (await session.execute(
        select(Case.id).where(Case.patient_id == patient.id)
    )).scalars().all()

    deleted_objects = 0
    if case_ids:
        image_keys = (await session.execute(
            select(Image.storage_key).where(Image.case_id.in_(case_ids))
        )).scalars().all()
        overlay_keys = (await session.execute(
            select(Analysis.overlay_key).where(Analysis.case_id.in_(case_ids))
        )).scalars().all()
        # Attached reports and scans are held about this patient too, and an
        # erasure that leaves the radiology PDF in the bucket is not an erasure.
        investigation_keys = (await session.execute(
            select(InvestigationResult.storage_key)
            .where(InvestigationResult.case_id.in_(case_ids))
        )).scalars().all()
        for key in [*image_keys, *[k for k in overlay_keys if k],
                    *[k for k in investigation_keys if k]]:
            try:
                storage.delete(key)
                deleted_objects += 1
            except Exception:  # object already gone; erasure still proceeds
                pass

        analysis_ids = (await session.execute(
            select(Analysis.id).where(Analysis.case_id.in_(case_ids))
        )).scalars().all()
        if analysis_ids:
            await session.execute(
                delete(Lesion).where(Lesion.analysis_id.in_(analysis_ids))
            )

        # Laboratory results are clinical data about this patient and must go
        # with everything else. Missing them here would leave identifiable
        # clinical history behind after an erasure request was answered "done".
        panel_ids = (await session.execute(
            select(LabPanel.id).where(LabPanel.case_id.in_(case_ids))
        )).scalars().all()
        if panel_ids:
            await session.execute(
                delete(LabResult).where(LabResult.panel_id.in_(panel_ids))
            )
            await session.execute(
                delete(LabPanel).where(LabPanel.id.in_(panel_ids))
            )
        await session.execute(
            delete(InvestigationResult)
            .where(InvestigationResult.case_id.in_(case_ids))
        )
        await session.execute(
            delete(FootRiskAssessment)
            .where(FootRiskAssessment.case_id.in_(case_ids))
        )
        await session.execute(delete(Analysis).where(Analysis.case_id.in_(case_ids)))
        await session.execute(delete(Image).where(Image.case_id.in_(case_ids)))
        await session.execute(delete(Case).where(Case.id.in_(case_ids)))

    patient_id = patient.id
    await session.delete(patient)
    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="patient.erase", entity="patient",
        entity_id=patient_id,
        meta={"cases_deleted": len(case_ids), "objects_deleted": deleted_objects},
    )
    await session.commit()
    return {
        "erased": True,
        "cases_deleted": len(case_ids),
        "objects_deleted": deleted_objects,
        "audit_retained": True,
    }
