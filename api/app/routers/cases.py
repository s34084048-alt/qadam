from __future__ import annotations

import base64
import datetime as dt
import uuid

from fastapi import APIRouter, File, Query, Response, UploadFile
from sqlalchemy import delete, func, select

from .. import audit
from ..analysis.modules_config import GRADE_STYLE, MODULES
from ..analysis.pipeline import AnalysisJob, UnreadableImage
from ..analysis.runner import get_runner
from ..config import settings
from ..deps import CurrentUser, SessionDep, load_case_scoped
from ..errors import ApiError, not_found
from ..models import (Analysis, Case, CaseFollowUp, FootRiskAssessment, Image,
                      InvestigationResult, LabPanel, LabResult, Lesion,
                      ModelRegistry, Patient)
from ..pdf import build_case_pdf
from ..safety import safety_block
from ..schemas import (
    AnalysisOut,
    CaseCreate,
    CaseDeleteOut,
    CaseListItem,
    CaseListOut,
    CaseOut,
    LesionOut,
    QualityOut,
    TriageOut,
)
from ..storage import build_key, get_storage
from ..summary import build_summary

router = APIRouter(prefix="/cases", tags=["cases"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}


# --- helpers -----------------------------------------------------------------

async def _load_case(session, case_id: uuid.UUID, user) -> Case:
    return await load_case_scoped(session, case_id, user)


async def _patient_of(session, case: Case) -> Patient:
    patient = await session.get(Patient, case.patient_id)
    if patient is None:  # referential integrity guarantees this, defensively handled
        raise not_found("patient", str(case.patient_id))
    return patient


async def _lesions_of(session, analysis_id: uuid.UUID) -> list[Lesion]:
    result = await session.execute(
        select(Lesion).where(Lesion.analysis_id == analysis_id)
        .order_by(Lesion.area_pct.desc())
    )
    return list(result.scalars().all())


async def _active_registry(session, module: str) -> ModelRegistry | None:
    result = await session.execute(
        select(ModelRegistry)
        .where(ModelRegistry.module == module, ModelRegistry.active.is_(True))
        .order_by(ModelRegistry.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _build_analysis_out(
    analysis: Analysis,
    lesions: list[Lesion],
    image: Image,
    overlay_b64: str | None = None,
) -> AnalysisOut:
    detail = analysis.rationale_json or {}
    quality = image.quality_json or {}
    return AnalysisOut(
        id=analysis.id,
        case_id=analysis.case_id,
        image_id=analysis.image_id,
        module=analysis.module,
        model_version=analysis.model_version,
        backend=analysis.backend,
        created_at=analysis.created_at,
        triage=TriageOut(
            grade=analysis.triage_grade,
            label=analysis.triage_label,
            confidence=analysis.confidence,
            rationale=detail.get("rationale", []),
            next_investigation=analysis.next_investigation,
            urgency=detail.get("urgency", ""),
            routing_target=detail.get("routing_target", ""),
            color=GRADE_STYLE[analysis.triage_grade]["color"],
        ),
        lesions=[
            LesionOut(
                id=les.id, kind=les.kind, area_pct=les.area_pct,
                severity=les.severity, bbox=les.bbox_json,
                centroid=les.centroid_json,
                description=detail.get("descriptions", {}).get(les.kind, ""),
            )
            for les in lesions
        ],
        quality=QualityOut(
            passed=quality.get("passed", False),
            width=quality.get("width", image.width),
            height=quality.get("height", image.height),
            subject_fraction=quality.get("subject_fraction", 0.0),
            focus_var=quality.get("focus_var", 0.0),
            exposure_mean=quality.get("exposure_mean", 0.0),
            confidence_factor=quality.get("confidence_factor", 1.0),
            checks=quality.get("checks", []),
            hints=quality.get("hints", []),
        ),
        features=detail.get("features", {}),
        clinical=detail.get("clinical"),
        overlay_png_base64=overlay_b64,
        summary=detail.get("summary", ""),
        safety=safety_block(analysis.module, analysis.triage_grade),
    )


# --- endpoints ---------------------------------------------------------------

@router.post("", response_model=CaseOut, status_code=201)
async def create_case(
    body: CaseCreate, session: SessionDep, user: CurrentUser
) -> CaseOut:
    result = await session.execute(
        select(Patient).where(
            Patient.external_ref == body.patient_ref,
            Patient.organisation_id == user.organisation_id,
        )
    )
    patient = result.scalar_one_or_none()
    if patient is None:
        raise ApiError(
            404, "patient_not_found",
            f"No patient record with reference '{body.patient_ref}'.",
            hint="Create the pseudonymous patient record first with "
                 "POST /api/v1/patients.",
        )
    case = Case(
        organisation_id=user.organisation_id,
        patient_id=patient.id,
        module=body.module,
        created_by=user.id,
        body_site=body.body_site,
        note=body.note,
        status="created",
    )
    session.add(case)
    await session.flush()
    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="case.create", entity="case",
        entity_id=case.id,
        meta={"module": body.module, "patient_id": str(patient.id)},
    )
    await session.commit()
    return CaseOut(
        id=case.id, module=case.module, patient_ref=patient.external_ref,
        status=case.status, body_site=case.body_site, note=case.note,
        created_at=case.created_at, created_by=case.created_by,
        latest_analysis=None, history=[],
    )


@router.post("/{case_id}/analyze", response_model=AnalysisOut)
async def analyze_case(
    case_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    file: UploadFile = File(..., description="JPEG/PNG/WebP image of the body region"),
) -> AnalysisOut:
    case = await _load_case(session, case_id, user)
    patient = await _patient_of(session, case)

    if settings.require_consent and not patient.consent_flag:
        raise ApiError(
            403, "consent_required",
            "This patient record has no stored consent, so no image may be "
            "stored or analysed.",
            hint="Record the patient's consent (PATCH /api/v1/patients/"
                 f"{patient.external_ref}, consent_flag=true) before capturing.",
        )

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ApiError(
            415, "unsupported_media_type",
            f"Content type '{file.content_type}' is not accepted.",
            hint="Upload a JPEG, PNG or WebP image.",
            details={"accepted": sorted(ALLOWED_CONTENT_TYPES)},
        )

    data = await file.read()
    if not data:
        raise ApiError(400, "empty_upload", "The uploaded file is empty.",
                       hint="Re-capture the image and try again.")
    if len(data) > settings.max_upload_bytes:
        raise ApiError(
            413, "file_too_large",
            f"Image is {len(data) // 1024} KB; the limit is "
            f"{settings.max_upload_bytes // 1024} KB.",
            hint="Capture at a lower resolution or compress the image.",
        )

    registry = await _active_registry(session, case.module)
    job = AnalysisJob(
        image_bytes=data,
        module=case.module,
        backend_id=registry.backend if registry else "classical_cv",
        artifact_uri=registry.artifact_uri if registry else None,
        model_version=registry.version if registry else "0.0.0",
    )

    try:
        output = await get_runner().run(job)
    except UnreadableImage as exc:
        raise ApiError(
            400, "unreadable_image", str(exc),
            hint="Upload an image file the device camera produced; a corrupted "
                 "or non-image file cannot be analysed.",
        )

    # -- wrong subject: refuse rather than measure something meaningless ------
    if output.subject_error is not None:
        case.status = "quality_failed"
        await audit.record(
            session, actor_user_id=user.id,
            organisation_id=user.organisation_id,
            action="analysis.subject_rejected", entity="case",
            entity_id=case.id, meta={"module": case.module},
        )
        await session.commit()
        raise ApiError(
            422, "subject_not_recognised", output.subject_error.reason,
            hint=output.subject_error.hint,
            details={"module": case.module,
                     "quality": output.quality.to_json()},
        )

    # -- quality gate failure: reject, do not store the image -----------------
    if output.quality_rejected:
        case.status = "quality_failed"
        await audit.record(
            session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="analysis.quality_rejected",
            entity="case", entity_id=case.id,
            meta={"module": case.module,
                  "failed_checks": [c.name for c in output.quality.failures]},
        )
        await session.commit()
        raise ApiError(
            422, "image_quality_rejected",
            "The image did not pass the quality gate, so it was not analysed "
            "and was not stored.",
            hint="; ".join(c.hint for c in output.quality.failures)
                 or "Re-capture the image.",
            details={"quality": output.quality.to_json()},
        )

    assert output.result is not None
    result = output.result
    storage = get_storage()

    ext = {"image/png": "png", "image/webp": "webp"}.get(file.content_type, "jpg")
    image_key = build_key(str(case.id), "source", data, ext)
    storage.put(image_key, data, file.content_type)

    overlay_key = None
    overlay_b64 = None
    if output.overlay_png:
        overlay_key = build_key(str(case.id), "overlay", output.overlay_png, "png")
        storage.put(overlay_key, output.overlay_png, "image/png")
        overlay_b64 = base64.b64encode(output.overlay_png).decode("ascii")

    captured_at = dt.datetime.now(dt.timezone.utc)
    image = Image(
        case_id=case.id,
        storage_key=image_key,
        content_type=file.content_type,
        width=output.width,
        height=output.height,
        captured_at=captured_at,
        quality_json=output.quality.to_json(),
    )
    session.add(image)
    await session.flush()

    summary_text = build_summary(
        module=case.module,
        patient_ref=patient.external_ref,
        body_site=case.body_site,
        result=result,
        quality=output.quality,
        captured_at=captured_at.isoformat(timespec="seconds"),
    )

    analysis = Analysis(
        case_id=case.id,
        image_id=image.id,
        module=case.module,
        model_version=result.model_version,
        backend=result.backend,
        triage_grade=str(result.triage.grade),
        triage_label=result.triage.label,
        confidence=result.triage.confidence,
        next_investigation=result.triage.next_investigation,
        overlay_key=overlay_key,
        rationale_json={
            "rationale": result.triage.rationale,
            "features": result.features,
            "clinical": result.clinical,
            "urgency": result.triage.urgency,
            "routing_target": result.triage.routing_target,
            "summary": summary_text,
            "notes": output.notes,
            "descriptions": {les.kind: les.description for les in result.lesions},
        },
    )
    session.add(analysis)
    await session.flush()

    lesion_rows = [
        Lesion(
            analysis_id=analysis.id,
            kind=les.kind,
            area_pct=les.area_pct,
            severity=les.severity,
            bbox_json={"x": les.bbox[0], "y": les.bbox[1],
                       "w": les.bbox[2], "h": les.bbox[3]},
            centroid_json={"x": les.centroid[0], "y": les.centroid[1]},
        )
        for les in result.lesions
    ]
    session.add_all(lesion_rows)

    case.status = "analyzed"
    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="analysis.create", entity="analysis",
        entity_id=analysis.id,
        meta={
            "case_id": str(case.id),
            "module": case.module,
            "grade": analysis.triage_grade,
            "confidence": round(analysis.confidence, 3),
            "model_version": analysis.model_version,
            "backend": analysis.backend,
            "quality_passed": output.quality.passed,
        },
    )
    await session.commit()
    await session.refresh(analysis)
    await session.refresh(image)

    return _build_analysis_out(analysis, lesion_rows, image, overlay_b64)


@router.get("/{case_id}", response_model=CaseOut)
async def get_case(
    case_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> CaseOut:
    case = await _load_case(session, case_id, user)
    patient = await _patient_of(session, case)

    analyses = (await session.execute(
        select(Analysis).where(Analysis.case_id == case.id)
        .order_by(Analysis.created_at.desc())
    )).scalars().all()

    images = {
        img.id: img
        for img in (await session.execute(
            select(Image).where(Image.case_id == case.id)
        )).scalars().all()
    }

    outs: list[AnalysisOut] = []
    for a in analyses:
        img = images.get(a.image_id)
        if img is None:
            continue
        outs.append(_build_analysis_out(a, await _lesions_of(session, a.id), img))

    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="case.view", entity="case",
        entity_id=case.id, meta={"module": case.module},
    )
    await session.commit()

    return CaseOut(
        id=case.id, module=case.module, patient_ref=patient.external_ref,
        status=case.status, body_site=case.body_site, note=case.note,
        created_at=case.created_at, created_by=case.created_by,
        latest_analysis=outs[0] if outs else None,
        history=outs[1:],
    )


@router.get("", response_model=CaseListOut)
async def list_cases(
    session: SessionDep,
    user: CurrentUser,
    module: str | None = Query(None),
    patient_ref: str | None = Query(None),
    grade: str | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> CaseListOut:
    if module and module not in MODULES:
        raise ApiError(
            400, "unknown_module", f"'{module}' is not a QADAM module.",
            hint="Call GET /api/v1/modules for the catalogue.",
            details={"modules": list(MODULES)},
        )
    if grade and grade not in GRADE_STYLE:
        raise ApiError(
            400, "unknown_grade", f"'{grade}' is not a triage grade.",
            hint="Use one of: " + ", ".join(GRADE_STYLE),
        )

    latest = (
        select(
            Analysis.case_id.label("case_id"),
            func.max(Analysis.created_at).label("latest_at"),
            func.count(Analysis.id).label("analysis_count"),
        )
        .group_by(Analysis.case_id)
        .subquery()
    )
    stmt = (
        select(Case, Patient.external_ref, Analysis, latest.c.analysis_count)
        .join(Patient, Patient.id == Case.patient_id)
        .where(Case.organisation_id == user.organisation_id)
        .join(latest, latest.c.case_id == Case.id, isouter=True)
        .join(
            Analysis,
            (Analysis.case_id == Case.id)
            & (Analysis.created_at == latest.c.latest_at),
            isouter=True,
        )
    )
    if module:
        stmt = stmt.where(Case.module == module)
    if patient_ref:
        stmt = stmt.where(Patient.external_ref == patient_ref)
    if grade:
        stmt = stmt.where(Analysis.triage_grade == grade)

    total = (await session.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar_one()

    rows = (await session.execute(
        stmt.order_by(Case.created_at.desc()).limit(limit).offset(offset)
    )).all()

    items = [
        CaseListItem(
            id=case.id,
            module=case.module,
            patient_ref=ref,
            status=case.status,
            created_at=case.created_at,
            triage_grade=analysis.triage_grade if analysis else None,
            triage_label=analysis.triage_label if analysis else None,
            confidence=analysis.confidence if analysis else None,
            analysis_count=count or 0,
        )
        for case, ref, analysis, count in rows
    ]
    return CaseListOut(items=items, total=int(total), limit=limit, offset=offset)


@router.delete("/{case_id}", response_model=CaseDeleteOut)
async def delete_case(
    case_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    confirm: bool = Query(
        False,
        description="Must be true. Deletion is permanent and there is no "
                    "recycle bin.",
    ),
) -> CaseDeleteOut:
    """Permanently remove a case and everything attached to it.

    A HARD delete, not a soft one. A soft delete would leave the images -- the
    only genuinely identifying material this platform ever holds -- sitting in
    storage behind a flag, which is the opposite of what someone asking to
    remove a case wants. Image bytes go, and so do the analyses, lesions,
    laboratory panels, foot assessments, filed investigation reports and
    follow-up answers derived from them.

    THE AUDIT LOG SURVIVES. It records that a case existed, was analysed and
    was deleted, by whom and when. It holds no patient identifier and no
    clinical content, so keeping it removes nothing about the patient while
    preserving the one thing an accountable system cannot lose: the fact that
    a record was destroyed.

    The patient record itself is untouched. Deleting a case is not the same
    request as erasing a patient, and other cases may still reference them.
    """
    case = await _load_case(session, case_id, user)

    if not confirm:
        raise ApiError(
            400, "confirmation_required",
            "Deleting a case permanently destroys its images and every "
            "assessment derived from them. This cannot be undone.",
            hint="Repeat the request with ?confirm=true once you are sure.",
            details={"case_id": str(case.id), "module": case.module},
        )

    analyses = (await session.execute(
        select(Analysis).where(Analysis.case_id == case.id)
    )).scalars().all()
    images = (await session.execute(
        select(Image).where(Image.case_id == case.id)
    )).scalars().all()
    filed = (await session.execute(
        select(InvestigationResult)
        .where(InvestigationResult.case_id == case.id)
    )).scalars().all()

    # Storage first, and never fatally. An object already gone -- expired
    # lifecycle rule, manual cleanup, a failed earlier attempt -- must not
    # leave the clinician with a case they cannot delete.
    storage = get_storage()
    removed = 0
    for key in (
        [img.storage_key for img in images]
        + [a.overlay_key for a in analyses if a.overlay_key]
        + [f.storage_key for f in filed if f.storage_key]
    ):
        try:
            storage.delete(key)
            removed += 1
        except Exception:  # noqa: BLE001 - absence is the desired end state
            pass

    analysis_ids = [a.id for a in analyses]
    panel_ids = (await session.execute(
        select(LabPanel.id).where(LabPanel.case_id == case.id)
    )).scalars().all()

    counts = {
        "analyses": len(analyses),
        "images": len(images),
        "investigation_results": len(filed),
        "lab_panels": len(panel_ids),
    }
    counts["lesions"] = int((await session.execute(
        select(func.count()).select_from(Lesion)
        .where(Lesion.analysis_id.in_(analysis_ids))
    )).scalar_one()) if analysis_ids else 0
    counts["lab_results"] = int((await session.execute(
        select(func.count()).select_from(LabResult)
        .where(LabResult.panel_id.in_(panel_ids))
    )).scalar_one()) if panel_ids else 0
    counts["foot_risk_assessments"] = int((await session.execute(
        select(func.count()).select_from(FootRiskAssessment)
        .where(FootRiskAssessment.case_id == case.id)
    )).scalar_one())
    counts["follow_ups"] = int((await session.execute(
        select(func.count()).select_from(CaseFollowUp)
        .where(CaseFollowUp.case_id == case.id)
    )).scalar_one())

    # Children before parents. Lesions and lab results hang off rows that are
    # themselves about to go, and SQLite enforces no cascade for us.
    if analysis_ids:
        await session.execute(
            delete(Lesion).where(Lesion.analysis_id.in_(analysis_ids)))
    if panel_ids:
        await session.execute(
            delete(LabResult).where(LabResult.panel_id.in_(panel_ids)))
    await session.execute(
        delete(CaseFollowUp).where(CaseFollowUp.case_id == case.id))
    await session.execute(
        delete(LabPanel).where(LabPanel.case_id == case.id))
    await session.execute(
        delete(FootRiskAssessment).where(FootRiskAssessment.case_id == case.id))
    await session.execute(
        delete(InvestigationResult).where(InvestigationResult.case_id == case.id))
    await session.execute(delete(Analysis).where(Analysis.case_id == case.id))
    await session.execute(delete(Image).where(Image.case_id == case.id))
    await session.execute(delete(Case).where(Case.id == case.id))

    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="case.delete",
        entity="case", entity_id=case.id,
        meta={"module": case.module, "deleted": counts,
              "objects_removed": removed},
    )
    await session.commit()

    return CaseDeleteOut(
        case_id=case.id,
        deleted=counts,
        images_removed=removed,
        note=(
            "The case, its images and everything derived from them are gone "
            "permanently. The pseudonymous patient record was not deleted, and "
            "the audit trail of this deletion is retained — it holds no "
            "patient identifier and no clinical content."
        ),
    )


@router.get("/{case_id}/analyses/{analysis_id}/overlay.png")
async def get_overlay(
    case_id: uuid.UUID,
    analysis_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> Response:
    await _load_case(session, case_id, user)      # organisation check
    analysis = await session.get(Analysis, analysis_id)
    if analysis is None or analysis.case_id != case_id:
        raise not_found("analysis", str(analysis_id))
    if not analysis.overlay_key:
        raise not_found("overlay", str(analysis_id))
    try:
        data = get_storage().get(analysis.overlay_key)
    except Exception:
        raise ApiError(
            404, "overlay_missing",
            "The annotated overlay for this analysis is no longer in storage.",
            hint="Re-run the analysis to regenerate it.",
        )
    return Response(content=data, media_type="image/png")


@router.get("/{case_id}/summary.pdf")
async def case_summary_pdf(
    case_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> Response:
    case = await _load_case(session, case_id, user)
    patient = await _patient_of(session, case)

    analyses = (await session.execute(
        select(Analysis).where(Analysis.case_id == case.id)
        .order_by(Analysis.created_at.desc())
    )).scalars().all()

    foot_row = (await session.execute(
        select(FootRiskAssessment).where(FootRiskAssessment.case_id == case.id)
        .order_by(FootRiskAssessment.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    panels = (await session.execute(
        select(LabPanel).where(LabPanel.case_id == case.id)
        .order_by(LabPanel.created_at.desc())
    )).scalars().all()
    filed = (await session.execute(
        select(InvestigationResult)
        .where(InvestigationResult.case_id == case.id)
        .order_by(InvestigationResult.created_at.desc())
    )).scalars().all()
    follow_ups = (await session.execute(
        select(CaseFollowUp).where(CaseFollowUp.case_id == case.id)
        .order_by(CaseFollowUp.created_at.desc())
    )).scalars().all()

    # A foot visit where the monofilament test was done but the photograph
    # failed the quality gate is a real visit, and the examination is the part
    # that sets the screening interval. Export it. The same holds for a visit
    # where the only record is what the clinician examined and wrote down.
    if not analyses and not foot_row and not panels and not filed and not follow_ups:
        raise ApiError(
            409, "nothing_to_summarise",
            "This case holds no analysis, foot assessment, laboratory panel or "
            "filed result yet.",
            hint=f"Analyse an image, record a foot examination, or file a "
                 f"result against /api/v1/cases/{case_id} first.",
        )

    latest = analyses[0] if analyses else None
    image = await session.get(Image, latest.image_id) if latest else None
    lesions = await _lesions_of(session, latest.id) if latest else []
    detail = (latest.rationale_json or {}) if latest else {}

    overlay = None
    if latest and latest.overlay_key:
        try:
            overlay = get_storage().get(latest.overlay_key)
        except Exception:
            overlay = None

    lab_payload = []
    for panel in panels:
        rows = (await session.execute(
            select(LabResult).where(LabResult.panel_id == panel.id)
            .order_by(LabResult.critical.desc(), LabResult.code)
        )).scalars().all()
        lab_payload.append({
            "panel_name": panel.panel_name,
            "triage_grade": panel.triage_grade,
            "derived": (panel.interpretation_json or {}).get("derived", []),
            "results": [
                {"name": r.name, "value": r.value, "unit": r.unit,
                 "flag": r.flag, "critical": r.critical,
                 "reference": {"low": r.ref_low, "high": r.ref_high}}
                for r in rows
            ],
        })

    foot_payload = None
    if foot_row:
        foot_payload = {
            **(foot_row.detail_json or {}),
            "findings": {
                "lops": foot_row.lops, "pad": foot_row.pad,
                "deformity": foot_row.deformity,
                "previous_ulcer": foot_row.previous_ulcer,
                "previous_amputation": foot_row.previous_amputation,
                "end_stage_renal_disease": foot_row.end_stage_renal_disease,
            },
        }

    pdf_bytes = build_case_pdf(
        module=latest.module if latest else case.module,
        patient_ref=patient.external_ref,
        case_id=str(case.id),
        body_site=case.body_site,
        created_at=(latest.created_at if latest else case.created_at)
            .isoformat(timespec="seconds"),
        triage=({
            "grade": latest.triage_grade,
            "label": latest.triage_label,
            "confidence": latest.confidence,
            "rationale": detail.get("rationale", []),
            "next_investigation": latest.next_investigation,
            "urgency": detail.get("urgency", ""),
            "routing_target": detail.get("routing_target", ""),
        } if latest else None),
        lesions=[
            {
                "kind": les.kind,
                "area_pct": les.area_pct,
                "severity": les.severity,
                "description": detail.get("descriptions", {}).get(les.kind, ""),
            }
            for les in lesions
        ],
        quality=(image.quality_json if image else {}) or {},
        features=detail.get("features", {}),
        model_version=latest.model_version if latest else None,
        backend=latest.backend if latest else None,
        overlay_png=overlay,
        foot_risk=foot_payload,
        lab_panels=lab_payload,
        investigations=[
            {"category": i.category, "modality": i.modality,
             "body_site": i.body_site, "reporting_service": i.reporting_service,
             "report_text": i.report_text, "has_file": i.storage_key is not None}
            for i in filed
        ],
        follow_ups=[
            {
                "created_at": f.created_at.isoformat(timespec="minutes"),
                "image_grade": f.image_grade,
                "answer_grade": f.answer_grade,
                "combined_grade": f.combined_grade,
                "escalated": f.escalated,
                "answers": f.answers_json or {},
                "triggers": (f.outcome_json or {}).get("triggers", []),
                "note": f.note,
            }
            for f in follow_ups
        ],
        history=[
            {
                "created_at": a.created_at.isoformat(timespec="minutes"),
                "grade": a.triage_grade,
                "confidence": a.confidence,
                "model_version": a.model_version,
            }
            for a in (analyses[1:] if analyses else [])
        ],
    )

    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="case.export_pdf", entity="case",
        entity_id=case.id,
        meta={"analysis_id": str(latest.id) if latest else None,
              "grade": latest.triage_grade if latest else None,
              "foot_risk": foot_payload is not None,
              "lab_panels": len(lab_payload),
              "investigations": len(filed)},
    )
    await session.commit()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'attachment; filename="qadam-{case.module}-{case.id}.pdf"'
        },
    )
