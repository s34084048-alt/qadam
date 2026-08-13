"""Organisational isolation.

One clinic must not see another's patients, cases, images, results or audit
trail. This is tested by ENUMERATING every case-scoped route rather than
spot-checking a few, because the failure mode is a single forgotten filter on
one endpoint and a spot check would not find it.

Cross-organisation access answers 404, never 403: a 403 confirms the id exists,
which lets one clinic enumerate another's case identifiers.
"""

from __future__ import annotations

import uuid as uuidlib

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import Case, Patient
from app.sample_data import png_bytes
from tests.conftest import API, make_case, make_patient

PDF = b"%PDF-1.4\ntrailer\n<<>>\n%%EOF\n"


async def _foreign_case(client, other_auth, ref_factory) -> tuple[str, str]:
    """A fully populated case belonging to the OTHER organisation."""
    ref = ref_factory("other")
    await make_patient(client, other_auth, ref)
    case_id = await make_case(client, other_auth, ref, "foot")
    await client.post(
        f"{API}/cases/{case_id}/analyze", headers=other_auth,
        files={"file": ("f.png", png_bytes("foot_urgent"), "image/png")},
    )
    await client.post(f"{API}/cases/{case_id}/foot-risk", headers=other_auth,
                      json={"lops": "present", "pad": "absent"})
    await client.post(f"{API}/cases/{case_id}/labs", headers=other_auth,
                      json={"results": [{"code": "crp", "value": 90,
                                         "unit": "mg/L"}]})
    await client.post(
        f"{API}/cases/{case_id}/investigations", headers=other_auth,
        data={"category": "radiology", "identifiers_removed": "true",
              "report_text": "Foreign report."},
    )
    return ref, case_id


def _case_scoped_routes() -> list[tuple[str, str]]:
    """Every route carrying a {case_id}, discovered from the app itself so a
    new endpoint cannot quietly skip this test."""
    found = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if "{case_id}" not in path:
            continue
        for method in sorted(getattr(route, "methods", set())):
            if method in {"HEAD", "OPTIONS"}:
                continue
            found.append((method, path))
    return sorted(set(found))


def test_every_case_route_is_covered_by_this_file():
    """A guard on the guard: if someone adds a case route, this list must grow."""
    routes = _case_scoped_routes()
    paths = {path for _method, path in routes}
    assert paths >= {
        f"{API}/cases/{{case_id}}",
        f"{API}/cases/{{case_id}}/analyze",
        f"{API}/cases/{{case_id}}/labs",
        f"{API}/cases/{{case_id}}/foot-risk",
        f"{API}/cases/{{case_id}}/investigations",
        f"{API}/cases/{{case_id}}/summary.pdf",
        f"{API}/cases/{{case_id}}/follow-up",
    }
    # Deletion is the one case route that destroys data. It must be discovered
    # by the leak test above like every other route.
    assert ("DELETE", f"{API}/cases/{{case_id}}") in routes
    assert len(routes) >= 12


async def test_no_case_scoped_route_leaks_across_organisations(
    client, auth, other_auth, ref_factory
):
    _ref, foreign_case = await _foreign_case(client, other_auth, ref_factory)

    # Bodies good enough to get past validation, so a 404 proves the
    # organisation check fired rather than a schema error masking it.
    bodies = {
        f"{API}/cases/{{case_id}}/labs":
            {"results": [{"code": "crp", "value": 5, "unit": "mg/L"}]},
        f"{API}/cases/{{case_id}}/foot-risk": {"lops": "absent", "pad": "absent"},
        f"{API}/cases/{{case_id}}/follow-up":
            {"answers": {"pedal_pulses": "both_absent"}, "note": "x"},
    }
    # DELETE demands ?confirm=true. The organisation check must fire BEFORE
    # that: answering "confirmation_required" for a case belonging to another
    # clinic would confirm the case exists.
    params = {f"{API}/cases/{{case_id}}": {"confirm": "true"}}
    forms = {
        f"{API}/cases/{{case_id}}/investigations":
            {"category": "radiology", "identifiers_removed": "true",
             "report_text": "x"},
    }
    files = {
        f"{API}/cases/{{case_id}}/analyze":
            {"file": ("f.png", png_bytes("foot_clean"), "image/png")},
    }

    checked = 0
    for method, template in _case_scoped_routes():
        path = template.replace("{case_id}", foreign_case)
        # Sub-resource ids we do not know; a random one is enough to prove the
        # case check fires first.
        path = path.replace("{analysis_id}", str(uuidlib.uuid4()))
        path = path.replace("{result_id}", str(uuidlib.uuid4()))

        kwargs: dict = {"headers": auth}
        if template in params:
            kwargs["params"] = params[template]
        if template in bodies:
            kwargs["json"] = bodies[template]
        if template in forms:
            kwargs["data"] = forms[template]
        if template in files:
            kwargs["files"] = files[template]

        resp = await client.request(method, path, **kwargs)
        assert resp.status_code == 404, (
            f"{method} {template} returned {resp.status_code} for another "
            f"organisation's case — expected 404"
        )
        assert resp.json()["error"]["code"] in {"case_not_found",
                                                "analysis_not_found",
                                                "investigation result_not_found"}
        checked += 1

    assert checked >= 9


async def test_case_listing_shows_only_your_own(client, auth, other_auth,
                                                ref_factory):
    ref, _case = await _foreign_case(client, other_auth, ref_factory)

    mine = (await client.get(f"{API}/cases", headers=auth,
                             params={"patient_ref": ref})).json()
    assert mine["total"] == 0, "another organisation's case appeared in the list"

    theirs = (await client.get(f"{API}/cases", headers=other_auth,
                               params={"patient_ref": ref})).json()
    assert theirs["total"] == 1


async def test_patient_routes_do_not_cross(client, auth, other_auth, ref_factory):
    ref, _case = await _foreign_case(client, other_auth, ref_factory)

    assert (await client.get(f"{API}/patients/{ref}",
                             headers=auth)).status_code == 404
    assert (await client.get(f"{API}/patients/{ref}/export",
                             headers=auth)).status_code == 404
    assert (await client.patch(f"{API}/patients/{ref}", headers=auth,
                               json={"consent_flag": False})).status_code == 404

    # And erasure must not reach across either — the worst possible leak.
    assert (await client.delete(f"{API}/patients/{ref}",
                                headers=auth)).status_code == 404
    async with SessionLocal() as session:
        assert (await session.execute(
            select(Patient).where(Patient.external_ref == ref)
        )).scalar_one_or_none() is not None, "erasure crossed organisations"

    listed = (await client.get(f"{API}/patients", headers=auth)).json()
    assert all(p["external_ref"] != ref for p in listed)


async def test_the_same_patient_code_can_exist_in_both_organisations(
    client, auth, other_auth
):
    """external_ref is unique WITHIN an organisation. A global unique index
    would let one clinic discover another's codes by collision."""
    shared = "SHARED-CODE-1"
    first = await client.post(f"{API}/patients", headers=auth, json={
        "external_ref": shared, "consent_flag": True})
    second = await client.post(f"{API}/patients", headers=other_auth, json={
        "external_ref": shared, "consent_flag": True})
    assert first.status_code == 201
    assert second.status_code == 201, (
        "a second organisation could not reuse a code the first had taken — "
        "that collision leaks the existence of the first clinic's record"
    )
    assert first.json()["id"] != second.json()["id"]


async def test_admin_views_are_organisation_scoped(
    client, auth, admin_auth, other_auth, other_admin_auth, ref_factory
):
    ref, _case = await _foreign_case(client, other_auth, ref_factory)

    # The other organisation's analysis must not appear in our fairness counts.
    before = (await client.get(f"{API}/admin/fairness",
                               headers=admin_auth)).json()
    theirs = (await client.get(f"{API}/admin/fairness",
                               headers=other_admin_auth)).json()
    assert theirs["coverage"]["analyses_total"] >= 1

    mine_ref = ref_factory("mine")
    await make_patient(client, auth, mine_ref)
    case_id = await make_case(client, auth, mine_ref, "foot")
    await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("f.png", png_bytes("foot_urgent"), "image/png")},
    )
    after = (await client.get(f"{API}/admin/fairness", headers=admin_auth)).json()
    assert after["coverage"]["analyses_total"] == \
        before["coverage"]["analyses_total"] + 1, (
            "fairness counts moved by more than our own analysis"
        )

    # Audit likewise.
    audit = (await client.get(f"{API}/admin/audit", headers=admin_auth,
                              params={"limit": 500})).json()
    async with SessionLocal() as session:
        foreign_ids = {
            str(c.id) for c in (await session.execute(
                select(Case).join(Patient, Patient.id == Case.patient_id)
                .where(Patient.external_ref == ref)
            )).scalars().all()
        }
    assert foreign_ids
    seen = {item["entity_id"] for item in audit["items"]}
    assert not (seen & foreign_ids), "audit trail leaked another organisation"


async def test_overlay_of_a_foreign_case_is_not_served(
    client, auth, other_auth, ref_factory
):
    _ref, foreign_case = await _foreign_case(client, other_auth, ref_factory)
    detail = (await client.get(f"{API}/cases/{foreign_case}",
                               headers=other_auth)).json()
    analysis_id = detail["latest_analysis"]["id"]

    resp = await client.get(
        f"{API}/cases/{foreign_case}/analyses/{analysis_id}/overlay.png",
        headers=auth,
    )
    assert resp.status_code == 404
    # The owner can still read it.
    assert (await client.get(
        f"{API}/cases/{foreign_case}/analyses/{analysis_id}/overlay.png",
        headers=other_auth,
    )).status_code == 200
