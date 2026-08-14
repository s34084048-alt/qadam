"""Results of investigations QADAM routed the patient to.

STORED, NEVER INTERPRETED. Nothing in this module imports the analysis
package, no model reads these files, and no grade is produced from them. QADAM
tells a health worker to obtain an X-ray; this is where the X-ray report comes
back, so the referral stops trailing off into nothing.

Reading a radiology study needs the whole study, the clinical context, prior
imaging and a trained reporter. A triage application has none of those, and a
false negative on imaging is catastrophic — so the honest feature here is a
filing cabinet, not an interpreter.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, File, Form, Response, UploadFile
from sqlalchemy import select

from .. import audit
from ..config import settings
from ..deps import CurrentUser, SessionDep, load_case_scoped
from ..errors import ApiError, not_found
from ..models import Case, InvestigationResult
from ..storage import build_key, get_storage

router = APIRouter(prefix="/cases", tags=["investigations"])

CATEGORIES = {"radiology", "endoscopy", "histopathology", "physiology",
              "laboratory", "other"}
MODALITIES = {"x-ray", "ultrasound", "ct", "mri", "nuclear", "other"}

# PDF and flat images only. DICOM is refused on purpose -- see below.
ACCEPTED_TYPES = {
    "application/pdf", "image/jpeg", "image/jpg", "image/png", "image/webp",
    "text/plain",
}
DICOM_TYPES = {"application/dicom", "application/dicom+json", "image/dicom"}
EXTENSIONS = {
    "application/pdf": "pdf", "image/jpeg": "jpg", "image/jpg": "jpg",
    "image/png": "png", "image/webp": "webp", "text/plain": "txt",
}

NOT_INTERPRETED = (
    "STORED, NOT INTERPRETED. QADAM has not read this document and has "
    "produced no finding, grade or opinion from it. It is filed against the "
    "case so the clinician who ordered the investigation can see the result "
    "alongside the referral that prompted it."
)

IDENTIFIER_WARNING = (
    "Radiology reports, PDFs and screenshots routinely carry the patient's "
    "name, date of birth and accession number. This platform stores "
    "pseudonymous records only. Remove or cover identifiers before uploading."
)


def _serialise(row: InvestigationResult) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "case_id": str(row.case_id),
        "category": row.category,
        "modality": row.modality,
        "body_site": row.body_site,
        "performed_at": row.performed_at.isoformat() if row.performed_at else None,
        "reporting_service": row.reporting_service,
        "report_text": row.report_text,
        "has_file": row.storage_key is not None,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "identifiers_removed_ack": row.identifiers_removed_ack,
        "created_at": row.created_at.isoformat(),
        # Repeated on every single record, not just at the collection level:
        # this field is the one a downstream integrator is most likely to read.
        "automated_interpretation": False,
        "interpretation_note": NOT_INTERPRETED,
    }


@router.post("/{case_id}/investigations", status_code=201)
async def add_investigation_result(
    case_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    category: str = Form(...),
    identifiers_removed: bool = Form(
        ...,
        description="Must be true. Confirms identifiers were removed from the "
                    "document before it entered a pseudonymous record.",
    ),
    modality: str | None = Form(None),
    body_site: str | None = Form(None),
    performed_at: str | None = Form(None),
    reporting_service: str | None = Form(None),
    report_text: str | None = Form(None),
    file: UploadFile | None = File(None),
) -> dict[str, Any]:
    """Attach a report and/or a document to a case. No interpretation is run."""
    case = await load_case_scoped(session, case_id, user)

    if category not in CATEGORIES:
        raise ApiError(
            400, "unknown_category", f"'{category}' is not a known category.",
            hint="Use one of: " + ", ".join(sorted(CATEGORIES)),
        )
    if modality and modality not in MODALITIES:
        raise ApiError(
            400, "unknown_modality", f"'{modality}' is not a known modality.",
            hint="Use one of: " + ", ".join(sorted(MODALITIES)),
        )
    if not identifiers_removed:
        raise ApiError(
            422, "identifiers_not_confirmed",
            "The upload was refused because removal of identifiers has not "
            "been confirmed.",
            hint=IDENTIFIER_WARNING,
        )
    if not report_text and file is None:
        raise ApiError(
            400, "nothing_to_store",
            "Provide the report text, a file, or both.",
            hint="A record with neither says nothing about what came back.",
        )

    storage_key = content_type = None
    size = None
    if file is not None:
        content_type = (file.content_type or "").lower()
        if content_type in DICOM_TYPES or (file.filename or "").lower().endswith(
            (".dcm", ".dicom")
        ):
            raise ApiError(
                415, "dicom_not_accepted",
                "DICOM files are not accepted.",
                hint="DICOM headers carry the patient's name, date of birth "
                     "and accession number, so storing one would silently "
                     "break the pseudonymity this platform guarantees. Export "
                     "a de-identified PDF or image from the PACS instead.",
            )
        if content_type not in ACCEPTED_TYPES:
            raise ApiError(
                415, "unsupported_media_type",
                f"Content type '{file.content_type}' is not accepted.",
                hint="Upload a PDF, JPEG, PNG, WebP or plain-text report.",
                details={"accepted": sorted(ACCEPTED_TYPES)},
            )
        data = await file.read()
        if not data:
            raise ApiError(400, "empty_upload", "The uploaded file is empty.",
                           hint="Re-export the document and try again.")
        if len(data) > settings.max_upload_bytes:
            raise ApiError(
                413, "file_too_large",
                f"File is {len(data) // 1024} KB; the limit is "
                f"{settings.max_upload_bytes // 1024} KB.",
                hint="Compress the PDF or export at a lower resolution.",
            )
        # The original filename is discarded rather than stored: it routinely
        # contains the patient's name or hospital number.
        storage_key = build_key(str(case.id), "investigation", data,
                                EXTENSIONS.get(content_type, "bin"))
        get_storage().put(storage_key, data, content_type)
        size = len(data)

    performed = None
    if performed_at:
        try:
            performed = dt.datetime.fromisoformat(performed_at)
        except ValueError:
            raise ApiError(
                422, "invalid_performed_at",
                f"'{performed_at}' is not a valid ISO-8601 timestamp.",
                hint="Use a format like 2026-08-12T09:30:00Z.",
            )

    row = InvestigationResult(
        case_id=case.id, category=category, modality=modality,
        body_site=body_site, performed_at=performed,
        reporting_service=reporting_service, report_text=report_text,
        storage_key=storage_key, content_type=content_type, size_bytes=size,
        identifiers_removed_ack=True, created_by=user.id,
    )
    session.add(row)
    await session.flush()

    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="investigation.attach",
        entity="investigation_result", entity_id=row.id,
        meta={
            "case_id": str(case.id), "category": category, "modality": modality,
            "has_file": storage_key is not None, "size_bytes": size,
            "interpreted": False,
        },
    )
    await session.commit()
    await session.refresh(row)
    return _serialise(row)


@router.get("/{case_id}/investigations")
async def list_investigation_results(
    case_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> dict[str, Any]:
    case = await load_case_scoped(session, case_id, user)
    rows = (await session.execute(
        select(InvestigationResult)
        .where(InvestigationResult.case_id == case_id)
        .order_by(InvestigationResult.created_at.desc())
    )).scalars().all()
    return {
        "case_id": str(case_id),
        "results": [_serialise(r) for r in rows],
        "total": len(rows),
        "automated_interpretation": False,
        "interpretation_note": NOT_INTERPRETED,
    }


@router.get("/{case_id}/investigations/{result_id}/file")
async def get_investigation_file(
    case_id: uuid.UUID,
    result_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> Response:
    """Return the stored document for a clinician to read. Nothing is run on it."""
    row = await session.get(InvestigationResult, result_id)
    if row is None or row.case_id != case_id:
        raise not_found("investigation result", str(result_id))
    if not row.storage_key:
        raise ApiError(
            404, "no_file",
            "This record holds report text only; no file was attached.",
            hint="Read the report text from the record itself.",
        )
    try:
        data = get_storage().get(row.storage_key)
    except Exception:
        raise ApiError(
            404, "file_missing",
            "The stored document is no longer in object storage.",
            hint="It may have been removed by a patient erasure request.",
        )

    await audit.record(
        session, actor_user_id=user.id,
        organisation_id=user.organisation_id, action="investigation.view_file",
        entity="investigation_result", entity_id=row.id,
        meta={"case_id": str(case_id), "content_type": row.content_type},
    )
    await session.commit()
    return Response(
        content=data,
        media_type=row.content_type or "application/octet-stream",
        headers={"X-QADAM-Interpreted": "false"},
    )
