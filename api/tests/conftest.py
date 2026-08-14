from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest

# Environment must be set before the application (and its settings singleton)
# is imported. Tests run entirely on SQLite + local-filesystem storage, so
# `pytest` needs no services.
_TMP = Path(tempfile.mkdtemp(prefix="qadam-test-"))
os.environ.update(
    DATABASE_URL=f"sqlite+aiosqlite:///{(_TMP / 'test.db').as_posix()}",
    STORAGE_BACKEND="local",
    LOCAL_STORAGE_DIR=str(_TMP / "storage"),
    JWT_SECRET="test-secret",
    AUTO_CREATE_SCHEMA="true",
    ENVIRONMENT="local",
    REQUIRE_CONSENT="true",
)

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal, create_schema  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ModelRegistry, Organisation, User  # noqa: E402
from app.security import hash_password  # noqa: E402

API = settings.api_v1_prefix

CLINICIAN = ("clinician@test.local", "clinician-pw")
ADMIN = ("admin@test.local", "admin-pw")
# A second, entirely separate organisation. Its only job is to prove that
# nothing of theirs is reachable from the first one.
OTHER_CLINICIAN = ("clinician@other.local", "other-pw")
OTHER_ADMIN = ("admin@other.local", "other-admin-pw")


@pytest.fixture(scope="session", autouse=True)
async def _schema():
    await create_schema()
    async with SessionLocal() as session:
        first = Organisation(name="Test Clinic", slug="test-clinic")
        second = Organisation(name="Other Clinic", slug="other-clinic")
        session.add_all([first, second])
        await session.flush()
        session.add_all([
            User(organisation_id=first.id, email=CLINICIAN[0],
                 password_hash=hash_password(CLINICIAN[1]), role="clinician"),
            User(organisation_id=first.id, email=ADMIN[0],
                 password_hash=hash_password(ADMIN[1]), role="admin"),
            User(organisation_id=second.id, email=OTHER_CLINICIAN[0],
                 password_hash=hash_password(OTHER_CLINICIAN[1]),
                 role="clinician"),
            User(organisation_id=second.id, email=OTHER_ADMIN[0],
                 password_hash=hash_password(OTHER_ADMIN[1]), role="admin"),
        ])
        for module in ("foot",):
            session.add(ModelRegistry(
                module=module, name="classical-cv", version="0.1.0",
                backend="classical_cv", active=True, metrics_json={"validated": False},
            ))
        await session.commit()
    yield


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _login(client: httpx.AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post(
        f"{API}/auth/login", data={"username": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
async def auth(client):
    return await _login(client, *CLINICIAN)


@pytest.fixture
async def admin_auth(client):
    return await _login(client, *ADMIN)


@pytest.fixture
async def other_auth(client):
    """A clinician at a different organisation."""
    return await _login(client, *OTHER_CLINICIAN)


@pytest.fixture
async def other_admin_auth(client):
    return await _login(client, *OTHER_ADMIN)


@pytest.fixture
def ref_factory():
    """Unique pseudonymous patient references per test."""
    def _make(prefix: str = "T") -> str:
        return f"{prefix}-{uuid.uuid4().hex[:10]}"
    return _make


async def make_patient(client, auth, ref: str, *, consent: bool = True,
                       skin_tone: int | None = 5) -> str:
    resp = await client.post(
        f"{API}/patients",
        headers=auth,
        json={"external_ref": ref, "dob_year": 1980, "sex": "unknown",
              "skin_tone_monk": skin_tone, "consent_flag": consent},
    )
    assert resp.status_code == 201, resp.text
    return ref


async def make_case(client, auth, ref: str, module: str) -> str:
    resp = await client.post(
        f"{API}/cases", headers=auth,
        json={"module": module, "patient_ref": ref, "body_site": "test site"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]
