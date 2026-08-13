"""Open demo access: one click, no password.

The reason this is safe enough to offer at all is the property asserted in
`test_two_demo_visitors_cannot_see_each_other`. An open link on a tool like
this will eventually have a real patient photographed into it — the people most
likely to try it are exactly the people with patients in front of them. If every
visitor shared one account, that photograph would be browsable by everyone who
has the link. Each visitor getting their own organisation is what prevents it.

Off by default. A deployment that does not ask for this does not get it.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.sample_data import png_bytes
from tests.conftest import API


@pytest.fixture
def demo_on():
    original = settings.demo_mode
    settings.demo_mode = True
    yield
    settings.demo_mode = original


@pytest.fixture
def demo_off():
    original = settings.demo_mode
    settings.demo_mode = False
    yield
    settings.demo_mode = original


async def _demo(client) -> dict[str, str]:
    resp = await client.post(f"{API}/auth/demo")
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# --- off by default ----------------------------------------------------------

async def test_disabled_by_default(client, demo_off):
    resp = await client.post(f"{API}/auth/demo")
    # 404 rather than 403: in a normal deployment this endpoint does not exist,
    # and "forbidden" would advertise that it could.
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_health_reports_whether_it_is_on(client, demo_on):
    assert (await client.get(f"{API}/health")).json()["demo_mode"] is True


async def test_health_reports_when_off(client, demo_off):
    assert (await client.get(f"{API}/health")).json()["demo_mode"] is False


def test_the_default_is_closed():
    """The SHIPPED default, not whatever this machine's .env happens to say.

    `_env_file=None` matters: without it this reads a local .env and passes or
    fails on the developer's configuration rather than on the code. It failed
    exactly that way once, which is how the hole was found.
    """
    from app.config import Settings

    assert Settings(_env_file=None).demo_mode is False


# --- the isolation property --------------------------------------------------

async def test_two_demo_visitors_cannot_see_each_other(client, demo_on):
    """The property the whole feature rests on.

    Two strangers open the same link. Neither may see the other's patient, the
    other's case, or the other's photograph.
    """
    first, second = await _demo(client), await _demo(client)

    await client.post(f"{API}/patients", headers=first,
                      json={"external_ref": "VISITOR-ONE", "consent_flag": True})
    created = await client.post(f"{API}/cases", headers=first,
                                json={"module": "foot",
                                      "patient_ref": "VISITOR-ONE"})
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]

    analysed = await client.post(
        f"{API}/cases/{case_id}/analyze", headers=first,
        files={"file": ("s.png", png_bytes("foot_urgent"), "image/png")},
    )
    assert analysed.status_code == 200, analysed.text

    # The second visitor sees an empty platform.
    listing = await client.get(f"{API}/cases", headers=second)
    assert listing.status_code == 200
    assert case_id not in [item["id"] for item in listing.json()["items"]]

    # And cannot reach the first visitor's case or patient by id.
    assert (await client.get(f"{API}/cases/{case_id}",
                             headers=second)).status_code == 404
    assert (await client.get(f"{API}/patients/VISITOR-ONE",
                             headers=second)).status_code == 404
    assert (await client.delete(f"{API}/cases/{case_id}?confirm=true",
                                headers=second)).status_code == 404

    # The owner still can.
    assert (await client.get(f"{API}/cases/{case_id}",
                             headers=first)).status_code == 200


async def test_a_demo_visitor_cannot_see_the_seeded_organisation(
    client, auth, demo_on, ref_factory
):
    ref = ref_factory("seeded")
    await client.post(f"{API}/patients", headers=auth,
                      json={"external_ref": ref, "consent_flag": True})
    created = await client.post(f"{API}/cases", headers=auth,
                                json={"module": "foot", "patient_ref": ref})
    case_id = created.json()["id"]

    visitor = await _demo(client)
    assert (await client.get(f"{API}/cases/{case_id}",
                             headers=visitor)).status_code == 404
    assert case_id not in [
        item["id"]
        for item in (await client.get(f"{API}/cases",
                                      headers=visitor)).json()["items"]
    ]


async def test_the_same_patient_code_is_free_in_every_demo_session(client,
                                                                   demo_on):
    """Two visitors both typing 'P-1' must not collide, and must not meet."""
    first, second = await _demo(client), await _demo(client)
    for headers in (first, second):
        resp = await client.post(f"{API}/patients", headers=headers,
                                 json={"external_ref": "P-1",
                                       "consent_flag": True})
        assert resp.status_code == 201, resp.text

    one = (await client.get(f"{API}/patients/P-1", headers=first)).json()
    two = (await client.get(f"{API}/patients/P-1", headers=second)).json()
    assert one["id"] != two["id"]


# --- the account itself ------------------------------------------------------

async def test_the_demo_account_has_no_usable_password(client, demo_on):
    """It holds a random hash nobody has, so /auth/login is not a way in."""
    headers = await _demo(client)
    email = (await client.get(f"{API}/auth/me", headers=headers)).json()["email"]

    for guess in ("", "demo", "password", email, "qadam-clinician"):
        resp = await client.post(f"{API}/auth/login",
                                 data={"username": email, "password": guess})
        assert resp.status_code == 401, f"{guess!r} signed in"


async def test_a_demo_visitor_is_not_an_admin(client, demo_on):
    headers = await _demo(client)
    assert (await client.get(f"{API}/auth/me",
                             headers=headers)).json()["role"] == "clinician"
    assert (await client.get(f"{API}/admin/fairness",
                             headers=headers)).status_code == 403
    assert (await client.get(f"{API}/admin/audit",
                             headers=headers)).status_code == 403


async def test_consent_is_still_required(client, demo_on):
    """Open access does not open the consent gate."""
    headers = await _demo(client)
    await client.post(f"{API}/patients", headers=headers,
                      json={"external_ref": "NO-CONSENT", "consent_flag": False})
    created = await client.post(f"{API}/cases", headers=headers,
                                json={"module": "foot",
                                      "patient_ref": "NO-CONSENT"})
    resp = await client.post(
        f"{API}/cases/{created.json()['id']}/analyze", headers=headers,
        files={"file": ("s.png", png_bytes("foot_clean"), "image/png")},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "consent_required"


async def test_the_safety_boundary_is_unchanged_for_a_demo_visitor(client,
                                                                   demo_on):
    headers = await _demo(client)
    safety = (await client.get(f"{API}/safety", headers=headers)).json()
    assert safety["clinical_use"] is False
    assert "NOT A MEDICAL DEVICE" in safety["device_notice"]


async def test_capacity_is_bounded(client, demo_on):
    """The endpoint creates rows and faces the open internet."""
    original = settings.demo_max_sessions
    settings.demo_max_sessions = 0
    try:
        resp = await client.post(f"{API}/auth/demo")
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "demo_capacity_reached"
    finally:
        settings.demo_max_sessions = original
