"""Investigation results filed against a case.

The safety property here is a NEGATIVE one: these documents must never be
interpreted. That is asserted structurally, not just in wording.
"""

from __future__ import annotations

import uuid as uuidlib

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import InvestigationResult
from app.storage import get_storage
from tests.conftest import API, make_case, make_patient

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


async def _case(client, auth, ref_factory, module: str = "injury") -> str:
    ref = ref_factory("inv")
    await make_patient(client, auth, ref)
    return await make_case(client, auth, ref, module)


async def test_report_text_only_is_stored(client, auth, ref_factory):
    case_id = await _case(client, auth, ref_factory)
    resp = await client.post(
        f"{API}/cases/{case_id}/investigations", headers=auth,
        data={
            "category": "radiology", "modality": "x-ray",
            "body_site": "left ankle", "identifiers_removed": "true",
            "reporting_service": "City Hospital Radiology",
            "report_text": "No acute bony injury identified. Soft tissue "
                           "swelling lateral malleolus.",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["automated_interpretation"] is False
    assert "STORED, NOT INTERPRETED" in body["interpretation_note"]
    assert body["has_file"] is False
    assert body["modality"] == "x-ray"

    listed = (await client.get(f"{API}/cases/{case_id}/investigations",
                               headers=auth)).json()
    assert listed["total"] == 1
    assert listed["automated_interpretation"] is False


async def test_file_is_stored_and_served_back_unchanged(
    client, auth, ref_factory
):
    case_id = await _case(client, auth, ref_factory)
    created = await client.post(
        f"{API}/cases/{case_id}/investigations", headers=auth,
        data={"category": "radiology", "modality": "mri",
              "identifiers_removed": "true"},
        files={"file": ("report.pdf", PDF, "application/pdf")},
    )
    assert created.status_code == 201, created.text
    result_id = created.json()["id"]
    assert created.json()["size_bytes"] == len(PDF)

    fetched = await client.get(
        f"{API}/cases/{case_id}/investigations/{result_id}/file", headers=auth)
    assert fetched.status_code == 200
    assert fetched.content == PDF
    assert fetched.headers["x-qadam-interpreted"] == "false"


async def test_original_filename_is_discarded(client, auth, ref_factory):
    """Filenames routinely carry the patient's name."""
    case_id = await _case(client, auth, ref_factory)
    created = await client.post(
        f"{API}/cases/{case_id}/investigations", headers=auth,
        data={"category": "radiology", "identifiers_removed": "true"},
        files={"file": ("Ahmed_Al-Farsi_MRN123456_MRI.pdf", PDF,
                        "application/pdf")},
    )
    assert created.status_code == 201
    body = created.json()
    assert "filename" not in body
    assert "Ahmed" not in str(body)

    async with SessionLocal() as session:
        row = (await session.execute(
            select(InvestigationResult)
            .where(InvestigationResult.id == uuidlib.UUID(body["id"]))
        )).scalar_one()
    assert "Ahmed" not in (row.storage_key or "")
    assert "MRN123456" not in (row.storage_key or "")


async def test_dicom_is_refused_because_headers_carry_identifiers(
    client, auth, ref_factory
):
    case_id = await _case(client, auth, ref_factory)
    resp = await client.post(
        f"{API}/cases/{case_id}/investigations", headers=auth,
        data={"category": "radiology", "identifiers_removed": "true"},
        files={"file": ("study.dcm", b"DICM\x00\x00", "application/dicom")},
    )
    assert resp.status_code == 415
    error = resp.json()["error"]
    assert error["code"] == "dicom_not_accepted"
    assert "name" in error["hint"] and "pseudonymity" in error["hint"]

    # Also caught by extension when the browser guesses the content type.
    by_extension = await client.post(
        f"{API}/cases/{case_id}/investigations", headers=auth,
        data={"category": "radiology", "identifiers_removed": "true"},
        files={"file": ("study.dcm", b"DICM\x00\x00", "application/octet-stream")},
    )
    assert by_extension.status_code == 415
    assert by_extension.json()["error"]["code"] == "dicom_not_accepted"


async def test_identifier_removal_must_be_confirmed(client, auth, ref_factory):
    case_id = await _case(client, auth, ref_factory)
    resp = await client.post(
        f"{API}/cases/{case_id}/investigations", headers=auth,
        data={"category": "radiology", "identifiers_removed": "false",
              "report_text": "Normal study."},
    )
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "identifiers_not_confirmed"
    assert "pseudonymous" in error["hint"]

    listed = (await client.get(f"{API}/cases/{case_id}/investigations",
                               headers=auth)).json()
    assert listed["total"] == 0


async def test_empty_record_is_refused(client, auth, ref_factory):
    case_id = await _case(client, auth, ref_factory)
    resp = await client.post(
        f"{API}/cases/{case_id}/investigations", headers=auth,
        data={"category": "radiology", "identifiers_removed": "true"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "nothing_to_store"


@pytest.mark.parametrize("field,value,code", [
    ("category", "astrology", "unknown_category"),
    ("modality", "telepathy", "unknown_modality"),
])
async def test_unknown_vocabulary_is_rejected_with_the_list(
    client, auth, ref_factory, field, value, code
):
    case_id = await _case(client, auth, ref_factory)
    data = {"category": "radiology", "identifiers_removed": "true",
            "report_text": "x"}
    data[field] = value
    resp = await client.post(f"{API}/cases/{case_id}/investigations",
                             headers=auth, data=data)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == code
    assert "Use one of:" in resp.json()["error"]["hint"]


def test_module_never_imports_the_analysis_package():
    """The structural guarantee. Wording can drift; an import cannot hide."""
    import inspect

    from app.routers import investigations

    source = inspect.getsource(investigations)
    for forbidden in ("analysis", "pipeline", "cv2", "AnalysisJob",
                      "ModelBackend", "interpret"):
        assert f"import {forbidden}" not in source, (
            f"investigations.py imports {forbidden!r} — filed documents must "
            f"never be interpreted"
        )
    assert "STORED, NEVER INTERPRETED" in investigations.__doc__


async def test_attaching_a_result_does_not_create_an_analysis(
    client, auth, ref_factory
):
    """The case must not gain a grade because a report was filed."""
    case_id = await _case(client, auth, ref_factory)
    before = (await client.get(f"{API}/cases/{case_id}", headers=auth)).json()
    assert before["latest_analysis"] is None

    await client.post(
        f"{API}/cases/{case_id}/investigations", headers=auth,
        data={"category": "radiology", "identifiers_removed": "true",
              "report_text": "Undisplaced fracture of the distal fibula."},
        files={"file": ("r.pdf", PDF, "application/pdf")},
    )
    after = (await client.get(f"{API}/cases/{case_id}", headers=auth)).json()
    assert after["latest_analysis"] is None
    assert after["history"] == []
    # Even a report naming a fracture produces no QADAM grade — QADAM did not
    # read it, and the radiologist's words are not QADAM's finding.
    assert after["status"] == "created"


async def test_erasure_removes_filed_documents(client, auth, ref_factory):
    ref = ref_factory("inv-erase")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "injury")
    created = await client.post(
        f"{API}/cases/{case_id}/investigations", headers=auth,
        data={"category": "radiology", "identifiers_removed": "true"},
        files={"file": ("r.pdf", PDF, "application/pdf")},
    )
    result_id = uuidlib.UUID(created.json()["id"])

    async with SessionLocal() as session:
        row = (await session.execute(
            select(InvestigationResult)
            .where(InvestigationResult.id == result_id)
        )).scalar_one()
        key = row.storage_key
    assert get_storage().exists(key)

    export = (await client.get(f"{API}/patients/{ref}/export",
                               headers=auth)).json()
    assert export["cases"][0]["investigation_results"][0]["category"] == "radiology"

    assert (await client.delete(f"{API}/patients/{ref}",
                                headers=auth)).status_code == 200

    assert not get_storage().exists(key)
    async with SessionLocal() as session:
        assert (await session.execute(
            select(InvestigationResult)
            .where(InvestigationResult.id == result_id)
        )).scalar_one_or_none() is None


async def test_investigations_require_authentication(client, auth, ref_factory):
    case_id = await _case(client, auth, ref_factory)
    assert (await client.get(
        f"{API}/cases/{case_id}/investigations")).status_code == 401
    assert (await client.post(
        f"{API}/cases/{case_id}/investigations",
        data={"category": "radiology", "identifiers_removed": "true",
              "report_text": "x"})).status_code == 401
