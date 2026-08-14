"""Permanent case deletion.

The properties that matter:

  * it is HARD, not soft -- the image bytes leave storage, because those are
    the only genuinely identifying material the platform holds;
  * it takes everything derived from the case with it, so nothing is left
    orphaned pointing at a case that no longer exists;
  * it does NOT delete the patient, which is a different request;
  * the audit trail survives, because a system that can erase the evidence of
    its own erasures is not auditable;
  * it cannot be reached across an organisation boundary, and it cannot happen
    by accident.
"""

from __future__ import annotations

import uuid as uuidlib

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import (Analysis, AuditLog, Case, CaseFollowUp,
                        FootRiskAssessment, Image, InvestigationResult,
                        LabPanel, LabResult, Lesion, Patient)
from app.sample_data import png_bytes
from app.storage import get_storage
from tests.conftest import API, make_case, make_patient

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


async def _full_case(client, auth, ref_factory) -> tuple[str, str]:
    """A case carrying one of everything that hangs off a case."""
    ref = ref_factory("del")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")

    resp = await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("s.png", png_bytes("foot_urgent"), "image/png")},
    )
    assert resp.status_code == 200, resp.text

    await client.post(
        f"{API}/cases/{case_id}/labs", headers=auth,
        json={"results": [{"code": "crp", "value": 90, "unit": "mg/L"}]},
    )
    await client.post(
        f"{API}/cases/{case_id}/foot-risk", headers=auth,
        json={"lops": "absent", "pad": "absent"},
    )
    await client.post(
        f"{API}/cases/{case_id}/investigations", headers=auth,
        data={"category": "radiology", "identifiers_removed": "true",
              "report_text": "No acute abnormality."},
        files={"file": ("r.pdf", PDF, "application/pdf")},
    )
    await client.post(
        f"{API}/cases/{case_id}/follow-up", headers=auth,
        json={"answers": {"probe_to_bone": "yes"}, "note": "Probed to bone."},
    )
    return ref, case_id


async def _counts(case_id: str) -> dict[str, int]:
    async with SessionLocal() as session:
        cid = uuidlib.UUID(case_id)
        analysis_ids = (await session.execute(
            select(Analysis.id).where(Analysis.case_id == cid)
        )).scalars().all()
        panel_ids = (await session.execute(
            select(LabPanel.id).where(LabPanel.case_id == cid)
        )).scalars().all()

        async def count(model, clause) -> int:
            return int((await session.execute(
                select(func.count()).select_from(model).where(clause)
            )).scalar_one())

        return {
            "cases": await count(Case, Case.id == cid),
            "analyses": len(analysis_ids),
            "images": await count(Image, Image.case_id == cid),
            "lesions": (await count(Lesion, Lesion.analysis_id.in_(analysis_ids))
                        if analysis_ids else 0),
            "lab_panels": len(panel_ids),
            "lab_results": (await count(LabResult,
                                        LabResult.panel_id.in_(panel_ids))
                            if panel_ids else 0),
            "foot_risk": await count(FootRiskAssessment,
                                     FootRiskAssessment.case_id == cid),
            "investigations": await count(InvestigationResult,
                                          InvestigationResult.case_id == cid),
            "follow_ups": await count(CaseFollowUp, CaseFollowUp.case_id == cid),
        }


async def _storage_keys(case_id: str) -> list[str]:
    async with SessionLocal() as session:
        cid = uuidlib.UUID(case_id)
        keys = list((await session.execute(
            select(Image.storage_key).where(Image.case_id == cid)
        )).scalars().all())
        keys += [k for k in (await session.execute(
            select(Analysis.overlay_key).where(Analysis.case_id == cid)
        )).scalars().all() if k]
        keys += [k for k in (await session.execute(
            select(InvestigationResult.storage_key)
            .where(InvestigationResult.case_id == cid)
        )).scalars().all() if k]
    return keys


# --- the guard ---------------------------------------------------------------

async def test_delete_without_confirmation_is_refused(client, auth, ref_factory):
    _ref, case_id = await _full_case(client, auth, ref_factory)
    resp = await client.delete(f"{API}/cases/{case_id}", headers=auth)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "confirmation_required"
    # And nothing was touched on the way to refusing.
    assert (await _counts(case_id))["cases"] == 1


async def test_another_organisation_cannot_delete_a_case(
    client, auth, other_auth, ref_factory
):
    _ref, case_id = await _full_case(client, auth, ref_factory)
    resp = await client.delete(
        f"{API}/cases/{case_id}?confirm=true", headers=other_auth)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "case_not_found"
    assert (await _counts(case_id))["cases"] == 1


async def test_deleting_an_unknown_case_is_404(client, auth):
    resp = await client.delete(
        f"{API}/cases/{uuidlib.uuid4()}?confirm=true", headers=auth)
    assert resp.status_code == 404


# --- the deletion ------------------------------------------------------------

async def test_delete_removes_the_case_and_everything_derived(
    client, auth, ref_factory
):
    _ref, case_id = await _full_case(client, auth, ref_factory)

    before = await _counts(case_id)
    assert all(before[k] >= 1 for k in before), before

    resp = await client.delete(f"{API}/cases/{case_id}?confirm=true",
                               headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted"]["analyses"] == before["analyses"]
    assert body["deleted"]["follow_ups"] == before["follow_ups"]
    assert body["deleted"]["lesions"] == before["lesions"]

    after = await _counts(case_id)
    assert all(value == 0 for value in after.values()), after


async def test_delete_removes_the_image_bytes_from_storage(
    client, auth, ref_factory
):
    """A soft delete leaves the photographs behind a flag. That is the opposite
    of what deleting a case is for."""
    _ref, case_id = await _full_case(client, auth, ref_factory)
    keys = await _storage_keys(case_id)
    assert keys, "fixture stored nothing"
    storage = get_storage()
    assert all(storage.exists(key) for key in keys)

    resp = await client.delete(f"{API}/cases/{case_id}?confirm=true",
                               headers=auth)
    assert resp.status_code == 200
    assert resp.json()["images_removed"] >= len(keys)
    for key in keys:
        assert not storage.exists(key), f"{key} survived deletion"


async def test_deleted_case_is_gone_from_every_read_path(
    client, auth, ref_factory
):
    _ref, case_id = await _full_case(client, auth, ref_factory)
    await client.delete(f"{API}/cases/{case_id}?confirm=true", headers=auth)

    for path in (
        f"{API}/cases/{case_id}",
        f"{API}/cases/{case_id}/summary.pdf",
        f"{API}/cases/{case_id}/labs",
        f"{API}/cases/{case_id}/follow-up",
        f"{API}/cases/{case_id}/investigations",
    ):
        resp = await client.get(path, headers=auth)
        assert resp.status_code == 404, f"{path} still answers {resp.status_code}"

    listing = await client.get(f"{API}/cases", headers=auth,
                               params={"limit": 100})
    assert case_id not in [item["id"] for item in listing.json()["items"]]


async def test_delete_is_idempotent_in_effect(client, auth, ref_factory):
    _ref, case_id = await _full_case(client, auth, ref_factory)
    first = await client.delete(f"{API}/cases/{case_id}?confirm=true",
                                headers=auth)
    assert first.status_code == 200
    second = await client.delete(f"{API}/cases/{case_id}?confirm=true",
                                 headers=auth)
    assert second.status_code == 404


# --- what must survive -------------------------------------------------------

async def test_the_patient_record_is_not_deleted(client, auth, ref_factory):
    """Deleting a case is not the same request as erasing a patient, and other
    cases may still reference them."""
    ref, case_id = await _full_case(client, auth, ref_factory)
    other_case = await make_case(client, auth, ref, "lab")

    await client.delete(f"{API}/cases/{case_id}?confirm=true", headers=auth)

    resp = await client.get(f"{API}/patients/{ref}", headers=auth)
    assert resp.status_code == 200
    assert (await client.get(f"{API}/cases/{other_case}",
                             headers=auth)).status_code == 200

    async with SessionLocal() as session:
        assert (await session.execute(
            select(func.count()).select_from(Patient)
            .where(Patient.external_ref == ref)
        )).scalar_one() == 1


async def test_the_audit_trail_survives_the_deletion(client, auth, ref_factory):
    """A system that can erase the record of its own erasures is not auditable.

    The audit log holds no patient identifier and no clinical content, so
    keeping it removes nothing about the patient.
    """
    _ref, case_id = await _full_case(client, auth, ref_factory)
    resp = await client.delete(f"{API}/cases/{case_id}?confirm=true",
                               headers=auth)
    assert resp.status_code == 200
    assert resp.json()["audit_retained"] is True

    async with SessionLocal() as session:
        rows = (await session.execute(
            select(AuditLog).where(AuditLog.entity_id == case_id)
        )).scalars().all()

    actions = {row.action for row in rows}
    assert "case.create" in actions, "history of the case was lost"
    assert "case.delete" in actions, "the deletion itself was not recorded"

    deletion = next(row for row in rows if row.action == "case.delete")
    assert deletion.meta_json["deleted"]["analyses"] >= 1
    # The audit entry records the shape of what went, never its content.
    blob = str(deletion.meta_json).lower()
    assert "probed to bone" not in blob
    assert "no acute abnormality" not in blob
