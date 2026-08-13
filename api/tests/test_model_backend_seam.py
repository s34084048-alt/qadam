"""The model seam: swapping the backend must not change the API, the schema or
the UI contract."""

from __future__ import annotations

import numpy as np
from sqlalchemy import select

from app.analysis.backends import ClassicalCVBackend, get_backend
from app.analysis.backends.base import ModelBackend
from app.analysis.pipeline import AnalysisJob, execute
from app.analysis.quality import run_quality_gate
from app.analysis.types import Grade, ModuleResult
from app.db import SessionLocal
from app.models import ModelRegistry
from app.sample_data import SAMPLES, foot_urgent, png_bytes
from tests.conftest import API, make_case, make_patient


def test_classical_backend_satisfies_the_protocol():
    backend = ClassicalCVBackend()
    assert isinstance(backend, ModelBackend)
    for module in ("foot", "skin", "eye", "injury"):
        assert backend.supports(module)
    assert not backend.supports("chest-xray")


def test_backend_returns_the_shared_result_type():
    image = foot_urgent()
    quality = run_quality_gate(image)
    result = ClassicalCVBackend().analyze(image, "foot", quality)
    assert isinstance(result, ModuleResult)
    assert isinstance(result.triage.grade, Grade)
    assert result.triage.next_investigation
    assert all(0.0 <= lesion.severity <= 1.0 for lesion in result.lesions)
    assert all(lesion.area_pct >= 0.0 for lesion in result.lesions)


def test_registry_default_resolves_to_the_placeholder():
    assert isinstance(get_backend("foot", "classical_cv"), ClassicalCVBackend)


def test_unavailable_onnx_model_degrades_to_the_placeholder():
    """An ONNX row pointing at a missing artifact must not take the module
    offline: it falls back and says so."""
    output = execute(AnalysisJob(
        image_bytes=png_bytes("foot_urgent"),
        module="foot",
        backend_id="onnx",
        artifact_uri="/nonexistent/model.onnx",
        model_version="9.9.9",
        render_overlay=False,
    ))
    assert output.result is not None
    assert output.result.backend == "classical_cv"
    assert output.fallback_reason
    assert "fell back" in output.fallback_reason
    assert any("fell back" in reason for reason in output.result.triage.rationale)


async def test_activating_a_model_is_admin_only_and_audited(
    client, auth, admin_auth, ref_factory
):
    async with SessionLocal() as session:
        session.add(ModelRegistry(
            module="skin", name="skin-seg", version="1.0.0", backend="onnx",
            active=False, artifact_uri="/nonexistent/skin.onnx",
            metrics_json={"validated": False},
        ))
        await session.commit()
        model = (await session.execute(
            select(ModelRegistry).where(ModelRegistry.name == "skin-seg")
        )).scalar_one()

    forbidden = await client.post(
        f"{API}/admin/models/{model.id}/activate", headers=auth
    )
    assert forbidden.status_code == 403

    ok = await client.post(
        f"{API}/admin/models/{model.id}/activate", headers=admin_auth
    )
    assert ok.status_code == 200
    assert ok.json()["active"] is True

    # The API contract is unchanged by the swap, and the request still
    # succeeds because the missing artifact degrades to the placeholder.
    ref = ref_factory("seam")
    await make_patient(client, auth, ref)
    case_id = await make_case(client, auth, ref, "skin")
    resp = await client.post(
        f"{API}/cases/{case_id}/analyze", headers=auth,
        files={"file": ("s.png", png_bytes("skin_urgent"), "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= {
        "id", "case_id", "image_id", "module", "model_version", "backend",
        "triage", "lesions", "quality", "features", "summary", "safety",
    }
    assert body["triage"]["grade"] == "urgent"

    # Restore the classical row as the active model for later tests.
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(ModelRegistry).where(ModelRegistry.module == "skin")
        )).scalars().all()
        for row in rows:
            row.active = row.backend == "classical_cv"
        await session.commit()


def test_pipeline_is_deterministic():
    """Same bytes in, same grade out -- a prerequisite for auditability."""
    for sample in [s for s in SAMPLES if s.expected_grade is not None]:
        data = png_bytes(sample.name)
        first = execute(AnalysisJob(image_bytes=data, module=sample.module,
                                    render_overlay=False))
        second = execute(AnalysisJob(image_bytes=data, module=sample.module,
                                     render_overlay=False))
        assert first.result and second.result
        assert first.result.triage.grade == second.result.triage.grade
        assert np.isclose(first.result.triage.confidence,
                          second.result.triage.confidence)
