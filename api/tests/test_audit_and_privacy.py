from __future__ import annotations

import json
import uuid

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Analysis, AuditLog, Case, Image, Lesion, Patient
from app.sample_data import png_bytes
from app.storage import get_storage
from tests.conftest import API, make_case, make_patient


async def _audit_rows(entity_id: str) -> list[AuditLog]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.entity_id == entity_id)
        )
        return list(result.scalars().all())


async def test_every_mutating_action_is_audited(client, auth, ref_factory):
    ref = ref_factory("audit")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "skin")
    await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("s.png", png_bytes("skin_urgent"), "image/png")},
    )
    await client.get(f"{API}/cases/{case_id}", headers=auth)
    await client.get(f"{API}/cases/{case_id}/summary.pdf", headers=auth)

    actions = {row.action for row in await _audit_rows(case_id)}
    assert {"case.create", "case.view", "case.export_pdf"} <= actions

    async with SessionLocal() as session:
        analysis = (await session.execute(
            select(Analysis).where(Analysis.case_id == uuid.UUID(case_id))
        )).scalar_one()
    analysis_actions = {row.action for row in await _audit_rows(str(analysis.id))}
    assert "analysis.create" in analysis_actions


async def test_audit_records_login_success_and_failure(client):
    await client.post(f"{API}/auth/login",
                      data={"username": "clinician@test.local", "password": "no"})
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(AuditLog).where(AuditLog.action == "auth.login_failed")
        )).scalars().all()
    assert rows


async def test_audit_meta_never_carries_phi_or_image_bytes(client, auth, ref_factory):
    ref = ref_factory("phi")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")
    await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("f.png", png_bytes("foot_urgent"), "image/png")},
    )

    async with SessionLocal() as session:
        rows = (await session.execute(select(AuditLog))).scalars().all()

    for row in rows:
        blob = json.dumps(row.meta_json).lower()
        for banned in ("base64", "image_bytes", "\\x89png", "patient_name", "@"):
            assert banned not in blob, f"audit meta leaked {banned!r}"
        # The pseudonymous reference is fine; a raw identifier is not.
        assert "password" not in blob


async def test_admin_audit_endpoint_lists_rows(client, admin_auth):
    body = (await client.get(f"{API}/admin/audit", headers=admin_auth,
                             params={"action": "analysis.create"})).json()
    assert body["total"] >= 1
    assert body["items"][0]["action"] == "analysis.create"
    assert "append-only" in body["note"].lower()


async def test_patient_export_returns_everything_held(client, auth, ref_factory):
    ref = ref_factory("export")
    await make_patient(client, auth, ref, skin_tone=7)
    case_id = await make_case(client, auth, ref, "eye")
    await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("e.png", png_bytes("eye_urgent"), "image/png")},
    )

    body = (await client.get(f"{API}/patients/{ref}/export", headers=auth)).json()
    assert body["patient"]["external_ref"] == ref
    assert body["patient"]["skin_tone_monk"] == 7
    assert len(body["cases"]) == 1
    assert body["cases"][0]["analyses"][0]["triage_grade"] == "urgent"
    assert body["cases"][0]["images"][0]["storage_key"]


async def test_right_to_erasure_removes_images_and_rows_but_keeps_audit(
    client, auth, ref_factory
):
    ref = ref_factory("erase")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "foot")
    await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("f.png", png_bytes("foot_urgent"), "image/png")},
    )

    cid = uuid.UUID(case_id)
    async with SessionLocal() as session:
        image = (await session.execute(
            select(Image).where(Image.case_id == cid)
        )).scalar_one()
        analysis = (await session.execute(
            select(Analysis).where(Analysis.case_id == cid)
        )).scalar_one()
        image_key, overlay_key = image.storage_key, analysis.overlay_key
        analysis_id = analysis.id

    storage = get_storage()
    assert storage.exists(image_key)

    resp = await client.delete(f"{API}/patients/{ref}", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["erased"] is True
    assert body["objects_deleted"] >= 1
    assert body["audit_retained"] is True

    assert not storage.exists(image_key)
    if overlay_key:
        assert not storage.exists(overlay_key)

    async with SessionLocal() as session:
        assert (await session.execute(
            select(Patient).where(Patient.external_ref == ref)
        )).scalar_one_or_none() is None
        assert (await session.execute(
            select(Case).where(Case.id == cid)
        )).scalar_one_or_none() is None
        assert (await session.execute(
            select(Image).where(Image.case_id == cid)
        )).scalars().all() == []
        assert (await session.execute(
            select(Lesion).where(Lesion.analysis_id == analysis_id)
        )).scalars().all() == []
        # The audit trail survives erasure: it holds no identifiers.
        assert (await session.execute(
            select(AuditLog).where(AuditLog.entity_id == case_id)
        )).scalars().all()

    assert (await client.get(f"{API}/cases/{case_id}", headers=auth)).status_code == 404


async def test_patient_ref_rejects_obvious_identifiers(client, auth):
    resp = await client.post(
        f"{API}/patients", headers=auth,
        json={"external_ref": "patient@example.com", "consent_flag": True},
    )
    assert resp.status_code == 422


async def test_fairness_dashboard_is_stratified_and_labelled(client, admin_auth):
    body = (await client.get(f"{API}/admin/fairness", headers=admin_auth)).json()
    assert body["status"] == "placeholder"
    groups = {s["group"] for s in body["strata"]}
    assert {"1-2", "3-4", "5-6", "7-8", "9-10", "not recorded"} == groups
    assert any(s["analyses"] > 0 for s in body["strata"])
    notes = " ".join(body["notes"]).lower()
    assert "not measured accuracy" in notes
    assert "per skin-tone group" in notes
    # There is deliberately no single pooled accuracy figure.
    assert "accuracy" not in {k.lower() for k in body}
