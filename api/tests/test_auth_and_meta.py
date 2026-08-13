from __future__ import annotations

import pytest

from app.analysis.modules_config import MODULES
from app.config import InsecureDeployment, Settings, assert_deployable
from tests.conftest import API, CLINICIAN


async def test_health_declares_non_clinical_use(client):
    resp = await client.get(f"{API}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["clinical_use"] is False
    assert "not a diagnosis" in body["disclaimer"].lower()
    assert "NOT A MEDICAL DEVICE" in body["device_notice"]
    assert resp.headers["x-qadam-clinical-use"] == "false"


async def test_safety_endpoint_states_the_boundary(client):
    body = (await client.get(f"{API}/safety")).json()
    assert body["clinical_use"] is False
    assert "clinician" in body["human_in_the_loop"].lower()
    assert any("fracture" in claim for claim in body["never_claims"])
    assert body["consent_required"] is True


async def test_module_catalogue_carries_limitations(client):
    body = (await client.get(f"{API}/modules")).json()
    ids = {m["id"] for m in body["modules"]}
    assert ids == set(MODULES)

    by_id = {m["id"]: m for m in body["modules"]}

    injury = by_id["injury"]
    assert injury["routing_only"] is True
    joined = " ".join(injury["limitations"]).lower()
    assert "cannot confirm or exclude" in joined
    assert "fracture" in joined
    assert "does not exclude internal injury" in injury["no_flag_caveat"].lower()

    eye = by_id["eye"]
    eye_text = " ".join(eye["limitations"]).lower()
    assert "fundus camera" in eye_text
    assert "retinal" in eye_text

    # Every grade in every module routes somewhere real.
    for module in body["modules"]:
        for grade, spec in module["routing"].items():
            assert spec["next_investigation"].strip()
            assert spec["routing_target"].strip()


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", f"{API}/cases"),
        ("post", f"{API}/cases"),
        ("get", f"{API}/patients"),
        ("get", f"{API}/admin/fairness"),
        ("get", f"{API}/admin/audit"),
    ],
)
async def test_protected_endpoints_reject_anonymous(client, method, path):
    resp = await getattr(client, method)(path)
    assert resp.status_code == 401


async def test_login_rejects_bad_password(client):
    resp = await client.post(
        f"{API}/auth/login",
        data={"username": CLINICIAN[0], "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


async def test_validation_errors_are_structured_and_echo_nothing_back(client):
    """A missing field must say which field and what to do -- and must not
    reflect the submitted values, which can carry a patient reference."""
    resp = await client.post(f"{API}/auth/login", data={"grant_type": "password"})
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "validation_error"
    assert "username" in error["hint"] and "password" in error["hint"]
    fields = {f["field"] for f in error["details"]["fields"]}
    assert {"username", "password"} <= fields

    secret = "PATIENT-REF-SHOULD-NOT-ECHO"
    resp = await client.post(
        f"{API}/patients",
        headers={"Authorization": "Bearer x"},
        json={"external_ref": secret, "dob_year": "not-a-year"},
    )
    assert secret not in resp.text


async def test_login_tolerates_pasted_whitespace_and_capitals(client):
    resp = await client.post(
        f"{API}/auth/login",
        data={"username": f"  {CLINICIAN[0].upper()}  ", "password": CLINICIAN[1]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == CLINICIAN[0]


async def test_login_and_me(client, auth):
    resp = await client.get(f"{API}/auth/me", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["email"] == CLINICIAN[0]


async def test_invalid_token_rejected(client):
    resp = await client.get(
        f"{API}/auth/me", headers={"Authorization": "Bearer not-a-token"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_token"


async def test_clinician_cannot_reach_admin(client, auth):
    resp = await client.get(f"{API}/admin/fairness", headers=auth)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "admin_required"


# --- refusing to deploy on published credentials -----------------------------

@pytest.mark.parametrize(
    "field,value",
    [
        ("jwt_secret", "change-me-in-production"),
        ("seed_admin_password", "qadam-admin"),
        ("seed_clinician_password", "qadam-clinician"),
    ],
)
def test_public_deployment_refuses_shipped_defaults(field, value):
    """These defaults are printed in the repository, the compose file and the
    README. Any one of them surviving to a public host is a published
    credential, so the process must refuse to start rather than warn."""
    kwargs = {
        "environment": "prod",
        "jwt_secret": "generated-secret",
        "seed_admin_password": "generated-admin",
        "seed_clinician_password": "generated-clinician",
        "storage_backend": "local",
    }
    kwargs[field] = value
    with pytest.raises(InsecureDeployment) as exc:
        assert_deployable(Settings(**kwargs))
    assert field.upper() in str(exc.value)


def test_a_configured_public_deployment_starts():
    assert_deployable(Settings(
        environment="prod",
        jwt_secret="generated-secret",
        seed_admin_password="generated-admin",
        seed_clinician_password="generated-clinician",
        storage_backend="local",
    ))


def test_local_runs_need_no_configuration():
    """The defaults exist so `pytest` and a laptop run work with nothing set.
    The guard must not break that."""
    assert_deployable(Settings(environment="local"))
